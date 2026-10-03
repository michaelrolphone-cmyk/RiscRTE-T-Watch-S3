#include "RiscRuntimeV1.h"
#include "render.h"
#include "effects/effects.h"
#include "twatch_power.h"
#include "twatch_caps.h"

static const risc_runtime_api_v1 *rt;
static const risc_display_output_api_v1 *display;
static const twatch_rtc_api_v1 *rtc;
static const twatch_pmu_api_v1 *pmu;
static const twatch_panel_power_v1 *panel;
static risc_display_frame_v1 held;
static bool alive(uint32_t *ms) {
    risc_runtime_health_v1 h={.struct_size=sizeof(h)};
    if (!rt->health(&h)) return false;
    *ms=h.uptime_ms; return true;
}
static bool present(void) {
    risc_display_present_token_v1 token=0;
    const risc_display_present_options_v1 opts={0,0,0};
    if (!display->submit(display->context,held,NULL,0,&opts,&token)) return false;
    held=0; uint32_t start,now;
    if (!alive(&start)) return false;
    for(unsigned n=0;n<=10000;n++) {
        risc_display_present_status_v1 s={0};
        if (!display->present_status(display->context,token,&s)) return false;
        if (s.state==RISC_DISPLAY_PRESENT_COMPLETE) return true;
        if (s.state==RISC_DISPLAY_PRESENT_FAILED || s.state==RISC_DISPLAY_PRESENT_SUPERSEDED ||
            !alive(&now) || (uint32_t)(now-start)>=10000) return false;
        rt->yield_ms(1);
    }
    return false;
}
static bool frame(risc_display_surface_v1 *surface) {
    if (!display->acquire(display->context,RISC_DISPLAY_FORMAT_RGB565,surface)) return false;
    held=surface->frame;return held!=0;
}
static bool draw_clock(uint32_t now,risc_display_surface_v1 *surface) {
    twatch_rtc_time_v1 date={0};
    bool valid=rtc && rtc->read(rtc->context,&date) && tw_valid_time(&date);
    return watch_clock_render(surface,&date,valid,now/1000);
}
static bool ripple(bool outgoing) {
    uint32_t start,now;
    if (!alive(&start)) return false;
    /* A slow presentation must skip obsolete scans, not stretch all sixteen
     * scans into sixteen slow full-panel transfers. Always submit scan 15. */
    for(unsigned count=0;count<16;count++) {
        risc_display_surface_v1 s={0};
        if (!alive(&now) || !frame(&s)) return false;
        uint32_t age=now-start;
        unsigned scan=age/20u;
        if (scan>15) scan=15;
        if (outgoing && !draw_clock(now,&s)) return false;
        if (!outgoing) {
            if (!watch_boot_render(&s,0)) return false;
        }
        if (!watch_ripple_render(&s,scan) || !present()) return false;
        if (scan==15) return true;
        rt->yield_ms(20);
    }
    return false;
}
static bool startup(void) {
    if (!ripple(false)) return false;
    uint32_t start,now;
    if (!alive(&start)) return false;
    for(unsigned count=0;count<100;count++) {
        risc_display_surface_v1 s={0};
        if (!alive(&now) || !frame(&s)) return false;
        uint32_t age=now-start;
        if (!watch_boot_render(&s,age>1800?1800:age) || !present()) return false;
        if (age>=1800) return true;
        rt->yield_ms(20);
    }
    return false;
}
static bool sleep_cycle(void) {
    if (!ripple(true)) return false;
    /* Every preparation attempt is paired with resume, including partial
     * preparation and platform refusal. No framebuffer lease survives here. */
    bool panel_ok=panel->prepare_sleep(display->context);
    bool pmu_ok=panel_ok && pmu->prepare_sleep(pmu->base.context);
    int32_t rc=RISC_LIGHT_SLEEP_INVALID;
    risc_light_sleep_result_v1 result={.struct_size=sizeof(result)};
    if (pmu_ok) rc=pmu->light_sleep(pmu->base.context,&result);
    bool restored_pmu=pmu->resume(pmu->base.context);
    bool restored_panel=panel->resume(display->context);
    if (!restored_pmu || !restored_panel) {
        rt->diagnostic("WATCH_CLOCK error=sleep-restore");return false;
    }
    if (rc==RISC_LIGHT_SLEEP_RETAINED) {rt->diagnostic("WATCH_CLOCK error=sleep-retained");return false;}
    uint32_t discard;
    if (!pmu->key_events(pmu->base.context,&discard)) return false;
    if (rc==RISC_LIGHT_SLEEP_OK) {
        rt->diagnostic("WATCH_CLOCK woke");
        if (!startup()) return false;
    } else rt->diagnostic("WATCH_CLOCK sleep=refused");
    return pmu->key_events(pmu->base.context,&discard);
}
__attribute__((visibility("default"))) void app_main(void) {
    rt=risc_runtime_get_api(1); held=0;rtc=NULL;display=NULL;pmu=NULL;panel=NULL;
    if (!rt || rt->api_version!=1 || rt->struct_size<RISC_RUNTIME_CAPABILITIES_V1_SIZE ||
        !rt->health || !rt->yield_ms || !rt->diagnostic || !rt->acquire || !rt->release) return;
    risc_runtime_capability_v1 dg={.struct_size=sizeof(dg)},rg={.struct_size=sizeof(rg)},pg={.struct_size=sizeof(pg)};
    bool have_d=rt->acquire("display.output",1,0,&dg),have_r=false,have_p=false;
    if (!have_d) goto done;
    display=dg.api;
    if (!display || display->api_version!=1 || display->struct_size<sizeof(*panel) ||
        !display->get_info || !display->acquire || !display->release || !display->submit ||
        !display->present_status || !display->set_brightness) goto done;
    panel=dg.api;
    if (!panel->prepare_sleep || !panel->resume) goto done;
    have_p=rt->acquire("board.battery",1,0,&pg);
    if (!have_p) goto done;
    pmu=pg.api;
    if (!pmu || pmu->base.api_version!=1 || pmu->base.struct_size<sizeof(*pmu) ||
        !pmu->key_events || !pmu->prepare_sleep || !pmu->resume || !pmu->light_sleep) goto done;
    have_r=rt->acquire("rtc.clock",2,0,&rg);
    if (have_r) {
        rtc=rg.api;
        if (!rtc || rtc->api_version!=2 || rtc->struct_size<sizeof(*rtc) || !rtc->read) rtc=NULL;
    }
    uint32_t discarded,now,last=0,armed_at=0;
    bool first=true;
    if (!display->set_brightness(display->context,40,100) ||
        !pmu->key_events(pmu->base.context,&discarded) || !startup() ||
        !pmu->key_events(pmu->base.context,&discarded) || !alive(&armed_at)) goto done;
    rt->diagnostic("WATCH_CLOCK ready crown=enabled");
    while(alive(&now)) {
        uint32_t events=0;
        if (!pmu->key_events(pmu->base.context,&events)) break;
        /* A short press is reported on release; ignore startup/wake tails. */
        if ((events&2u) && (uint32_t)(now-armed_at)>=250) {
            if (!sleep_cycle() || !alive(&armed_at)) break;
            first=true;continue;
        }
        if (first || (uint32_t)(now-last)>=1000) {
            risc_display_surface_v1 s={0};
            if (!frame(&s) || !draw_clock(now,&s) || !present()) break;
            first=false;last=now;
        }
        rt->yield_ms(20);
    }
done:
    if (held && display && display->release) display->release(display->context,held);
    if (have_r) rt->release(&rg);
    if (have_p) rt->release(&pg);
    if (have_d) rt->release(&dg);
}

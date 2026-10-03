#include "RiscRuntimeV1.h"
#include "nova/nova.h"
#include "display_time.h"
#include "effects/effects.h"
#include "twatch_power.h"
#include "twatch_caps.h"

static const risc_runtime_api_v1 *rt;
static const risc_display_output_api_v1 *display;
static const twatch_rtc_api_v1 *rtc;
static const twatch_pmu_api_v1 *pmu;
static const twatch_panel_power_v1 *panel;
static risc_display_frame_v1 held;
static nova_watch_state face;
static uint32_t rtc_sampled_at, rtc_second_at, battery_sampled_at;
static bool sampled_rtc, sampled_battery;
static void reset_telemetry(void) {
    face=(nova_watch_state){0}; sampled_rtc=false; sampled_battery=false;
}
static bool same_second(const twatch_rtc_time_v1 *a,const twatch_rtc_time_v1 *b) {
    return a->year==b->year && a->month==b->month && a->day==b->day &&
        a->hour==b->hour && a->minute==b->minute && a->second==b->second;
}
static bool alive(uint32_t *ms) {
    risc_runtime_health_v1 h={.struct_size=sizeof(h)};
    if (!rt->health(&h)) return false;
    *ms=h.uptime_ms; return true;
}
static bool present(void) {
    risc_display_present_token_v1 token=0;
    uint32_t start,now;
    if (!alive(&start)) return false;
    bool healthy=true;
    const risc_display_present_options_v1 opts={0,0,0};
    if (!display->submit(display->context,held,NULL,0,&opts,&token)) return false;
    held=0;
    for(unsigned n=0;n<=10000;n++) {
        risc_display_present_status_v1 s={0};
        if (!display->present_status(display->context,token,&s)) return false;
        if (s.state==RISC_DISPLAY_PRESENT_COMPLETE) return healthy;
        if (s.state==RISC_DISPLAY_PRESENT_FAILED || s.state==RISC_DISPLAY_PRESENT_SUPERSEDED) return false;
        if (alive(&now)) {
            if ((uint32_t)(now-start)>=10000) return false;
        } else healthy=false;
        /* A lost health sample must not abandon an already accepted transfer.
         * Drain it within the same bounded poll count, then exit the app. */
        rt->yield_ms(1);
    }
    return false;
}
static bool frame(risc_display_surface_v1 *surface) {
    if (!display->acquire(display->context,RISC_DISPLAY_FORMAT_RGB565,surface)) return false;
    held=surface->frame;return held!=0;
}
static bool draw_clock(uint32_t now,risc_display_surface_v1 *surface) {
    /* RTC sampling and fractional phase are independent of the frame cadence.
     * Only a successful RTC sample may advance civil time. The first observed
     * edge anchors the fractional hand within one 100ms sampling interval. */
    if (!sampled_rtc || (uint32_t)(now-rtc_sampled_at)>=100u) {
        twatch_rtc_time_v1 date={0};
        bool valid=rtc && rtc->read(rtc->context,&date) && watch_display_time(&date,&date);
        if (valid && (!face.time_valid || !same_second(&date,&face.time))) rtc_second_at=now;
        face.time=date; face.time_valid=valid;
        rtc_sampled_at=now; sampled_rtc=true;
    }
    if (!sampled_battery || (uint32_t)(now-battery_sampled_at)>=5000u) {
        risc_battery_sample_v1 sample={0};
        face.battery_valid=pmu->base.read && pmu->base.read(pmu->base.context,&sample) &&
            sample.percent<=100 && !(sample.flags&RISC_BATTERY_PROFILE_MISSING);
        face.battery_percent=sample.percent;
        battery_sampled_at=now; sampled_battery=true;
    }
    uint32_t phase=now-rtc_second_at;
    face.subsecond_ms=face.time_valid ? (phase>999u?999u:(uint16_t)phase) : 0;
    face.animation_ms=now;
    return nova_watch_render(surface,&face);
}
static bool pace_frame(uint32_t began) {
    uint32_t now;
    if (!alive(&now)) return false;
    uint32_t spent = now - began;
    /* Presentation time already counts toward the 20ms animation interval. */
    if (spent < 20u) rt->yield_ms(20u - spent);
    return true;
}
static bool hold_boot_frame(void) {
    uint32_t start,now;
    if (!alive(&start)) return false;
    /* Begin after the final presentation completed, not when it was submitted.
     * A finite iteration guard also bounds a broken/non-advancing clock. */
    for(unsigned n=0;n<=250;n++) {
        if (!alive(&now)) return false;
        uint32_t spent=now-start;
        if (spent>=250u) return true;
        uint32_t left=250u-spent;
        rt->yield_ms(left<20u?left:20u);
    }
    return false;
}
static bool startup(void) {
    uint32_t start,now;
    if (!alive(&start)) return false;
    for(unsigned count=0;count<100;count++) {
        risc_display_surface_v1 s={0};
        if (!alive(&now) || !frame(&s)) return false;
        uint32_t age=now-start;
        if (!watch_boot_render(&s,age>1800?1800:age) || !present()) return false;
        if (age>=1800) return hold_boot_frame();
        if (!pace_frame(now)) return false;
    }
    return false;
}
static bool sleep_cycle(void) {
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
    reset_telemetry();
    if (rc==RISC_LIGHT_SLEEP_OK) {
        rt->diagnostic("WATCH_CLOCK woke");
        if (!startup()) return false;
    } else rt->diagnostic("WATCH_CLOCK sleep=refused");
    return pmu->key_events(pmu->base.context,&discard);
}
__attribute__((visibility("default"))) void app_main(void) {
    rt=risc_runtime_get_api(1); held=0;rtc=NULL;display=NULL;pmu=NULL;panel=NULL;
    reset_telemetry();
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
    uint32_t discarded,now,armed_at=0,last_activity=0;
    if (!display->set_brightness(display->context,40,100) ||
        !pmu->key_events(pmu->base.context,&discarded) || !startup() ||
        !pmu->key_events(pmu->base.context,&discarded) || !alive(&armed_at)) goto done;
    last_activity=armed_at;
    rt->diagnostic("WATCH_CLOCK ready crown=enabled");
    while(alive(&now)) {
        uint32_t events=0;
        if (!pmu->key_events(pmu->base.context,&events)) break;
        /* The clock closure currently exposes only PMU short/long key events.
         * Do not invent touch activity. Short press is reported on release. */
        if (events&3u) last_activity=now;
        bool manual=(events&2u) && (uint32_t)(now-armed_at)>=250u;
        bool idle=(uint32_t)(now-last_activity)>=60000u;
        if (manual || idle) {
            if (!sleep_cycle() || !alive(&armed_at)) break;
            /* A refused/held-key attempt also starts a new bounded interval;
             * it must not turn an expired timeout into a busy retry loop. */
            last_activity=armed_at;
            continue;
        }
        risc_display_surface_v1 s={0};
        if (!frame(&s) || !draw_clock(now,&s) || !present() || !pace_frame(now)) break;
    }
done:
    if (held && display && display->release) display->release(display->context,held);
    if (have_r) rt->release(&rg);
    if (have_p) rt->release(&pg);
    if (have_d) rt->release(&dg);
}

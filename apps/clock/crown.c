#include "RiscRuntimeV1.h"
#include "nova/nova.h"
#include "display_time.h"
#include "effects/effects.h"
#include "twatch_power.h"
#include "twatch_caps.h"
#include "watch_sleep.h"
#include "transitions/PortableTransition.h"
#include <stdlib.h>
#include <string.h>

static const risc_runtime_api_v1 *rt;
#ifdef WATCH_CLOCK_LAUNCHER
#include "launcher_touch.h"
#include "PortableSleepPolicy.h"
static unsigned sleep_mode;
static watch_launcher_touch touch;
static bool launcher_swipe_pending, launcher_activity_pending;
static uint32_t launcher_sampled_at;
/* Sampling must not wait for a whole 240-row presentation. Latch the first
 * qualified swipe, but let the accepted frame finish before handing it off. */
static void sample_launcher_touch(uint32_t now, bool force) {
    if (!touch.subscription || launcher_swipe_pending ||
        (!force && (uint32_t)(now-launcher_sampled_at)<8u)) return;
    bool activity=false;
    launcher_sampled_at=now;
    if (launcher_touch_swipe(&touch,&activity)) launcher_swipe_pending=true;
    if (activity) launcher_activity_pending=true;
}
#endif
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
#ifdef WATCH_CLOCK_LAUNCHER
            sample_launcher_touch(now,false);
#endif
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
#ifdef WATCH_CLOCK_LAUNCHER
    if (launcher_swipe_pending) return true;
#endif
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
/* Transient app-owned images only: the provider's lease is never retained
 * across submit, sleep, or an application switch. Allocation failure preserves
 * the normal sharp clock path instead of making Clock unavailable. */
static bool logo_to_clock(void) {
    const size_t bytes=240u*240u*sizeof(uint16_t);
    uint16_t *old=malloc(bytes),*scratch=old?malloc(bytes):NULL;
    bool ok=false;
    if (!old || !scratch) {
        risc_display_surface_v1 s={0};uint32_t now;
        free(scratch);free(old);
        return alive(&now) && frame(&s) && draw_clock(now,&s) && present() && pace_frame(now);
    }
    risc_display_surface_v1 logo={0,old,240,240,480,bytes,RISC_DISPLAY_FORMAT_RGB565};
    uint32_t start,now;
    if (!watch_boot_render(&logo,1800) || !alive(&start)) goto done;
    for(unsigned count=0;count<100;count++) {
        risc_display_surface_v1 s={0};
        if (!alive(&now) || !frame(&s) || !draw_clock(now,&s)) goto done;
        if (!count) start=now;
        unsigned alpha=portable_transition_alpha(now-start);
        if (!portable_transition_rgb565(s.pixels,s.stride_bytes,old,480,
                scratch,bytes,240,240,alpha) || !present() || !pace_frame(now)) goto done;
        if (alpha==256u) {ok=true;break;}
    }
done:
    free(scratch);free(old);return ok;
}
#ifdef WATCH_CLOCK_RETURN
/* Explicit normal-navigation entry, selected by the clock.elf build. This
 * deployment uses the same retained, single-buffer provider as Springboard.
 * Capture it before drawing, preserve its light level, and never play the boot
 * intro. Actual successful wake below still uses startup() in both variants. */
static bool return_to_clock(void) {
    const size_t bytes=240u*240u*sizeof(uint16_t);
    uint16_t *old=malloc(bytes),*scratch=old?malloc(bytes):NULL;
    bool ok=false;
    uint32_t start,now;
    risc_display_surface_v1 retained={0};
    if (!old || !scratch) {
        free(scratch);free(old);
        return alive(&now) && frame(&retained) && draw_clock(now,&retained) && present();
    }
    if (!frame(&retained)) goto done;
    size_t span;
    if (!retained.pixels || retained.pixel_format!=RISC_DISPLAY_FORMAT_RGB565 ||
        retained.width!=240u || retained.height!=240u || retained.stride_bytes<480u ||
        retained.stride_bytes%sizeof(uint16_t) ||
        !pt_image_span(retained.stride_bytes,480u,240u,&span) || span>retained.size_bytes) goto done;
    for(unsigned y=0;y<240u;y++)
        memcpy(old+y*240u,(const uint8_t *)retained.pixels+(size_t)y*retained.stride_bytes,480u);
    display->release(display->context,held);held=0;
    if (!alive(&start)) goto done;
    /* Alpha zero is already on the panel. Do not render or transfer a duplicate
     * full frame before the first changing image. Bound a stalled clock too. */
    for(unsigned count=0;count<100;count++) {
        risc_display_surface_v1 s={0};
        if (!alive(&now)) goto done;
        uint32_t age=now-start;
        if (!age) {rt->yield_ms(1);continue;}
        uint32_t painted;
        if (!frame(&s) || !draw_clock(now,&s) || !alive(&painted)) goto done;
        age=painted-start; /* Rendering time belongs to the same 60ms budget. */
        unsigned alpha=age>=60u?256u:age*256u/60u;
        if (!portable_transition_rgb565(s.pixels,s.stride_bytes,old,480,
                scratch,bytes,240,240,alpha) || !present()) goto done;
        if (alpha==256u) {ok=true;break;}
        if (!pace_frame(now)) goto done;
    }
done:
    free(scratch);free(old);return ok;
}
#endif
static bool startup(void) {
    uint32_t start,now;
    if (!alive(&start)) return false;
    for(unsigned count=0;count<100;count++) {
        risc_display_surface_v1 s={0};
        if (!alive(&now) || !frame(&s)) return false;
        uint32_t age=now-start;
        if (!watch_boot_render(&s,age>1800?1800:age) || !present()) return false;
        /* The retained provider may already contain a previous app's frame.
         * Entry blanks it before acquiring other capabilities. Restore light
         * only after the first complete new intro frame, never before submit. */
        if (!count && !display->set_brightness(display->context,40,100)) return false;
        if (age>=1800) return hold_boot_frame() && logo_to_clock();
        if (!pace_frame(now)) return false;
    }
    return false;
}
static bool sleep_cycle(void) {
    /* Clear retained panel RAM before sleep, not merely its PWM. If the
     * platform briefly restores the backlight before the panel resume hook,
     * the exposed completed image is black rather than the old Clock. */
    risc_display_surface_v1 blank={0};
    size_t span;
    if (!display->set_brightness(display->context,0,100) || !frame(&blank) ||
        !blank.pixels || blank.pixel_format!=RISC_DISPLAY_FORMAT_RGB565 ||
        blank.width!=240u || blank.height!=240u || blank.stride_bytes<480u ||
        blank.stride_bytes%sizeof(uint16_t) ||
        !pt_image_span(blank.stride_bytes,480u,240u,&span) || span>blank.size_bytes) return false;
    for(unsigned y=0;y<240u;y++) memset((uint8_t *)blank.pixels+(size_t)y*blank.stride_bytes,0,480u);
    if (!present()) return false;
    /* Every preparation attempt is paired with resume, including partial
     * preparation and platform refusal. No framebuffer lease survives here. */
    unsigned mode=PORTABLE_SLEEP_LIGHT;
#ifdef WATCH_CLOCK_LAUNCHER
    mode=sleep_mode;
#endif
    int rc=watch_sleep_prepared(panel,pmu,mode,rt->diagnostic);
    if(rc<0)return false;
    uint32_t discard;
    reset_telemetry();
    if (rc==WATCH_SLEEP_WOKE) {
        rt->diagnostic("WATCH_CLOCK woke");
        if (!display->set_brightness(display->context,0,100) || !startup()) return false;
    } else {
        rt->diagnostic("WATCH_CLOCK sleep=refused");
        risc_display_surface_v1 fresh={0};uint32_t now;
        /* The pre-sleep clear also runs before a refused attempt. Replace it
         * with a complete fresh Clock before restoring the previous level. */
        if (!display->set_brightness(display->context,0,100) || !alive(&now) ||
            !frame(&fresh) || !draw_clock(now,&fresh) || !present() ||
            !display->set_brightness(display->context,40,100)) return false;
    }
    return pmu->key_events(pmu->base.context,&discard);
}
__attribute__((visibility("default"))) void app_main(void) {
    rt=risc_runtime_get_api(1);
#ifdef WATCH_CLOCK_LAUNCHER
    touch=(watch_launcher_touch){0};
    launcher_swipe_pending=launcher_activity_pending=false;
    launcher_sampled_at=0;
#endif
    held=0;rtc=NULL;display=NULL;pmu=NULL;panel=NULL;
    reset_telemetry();
    if (!rt || rt->api_version!=1 || rt->struct_size<RISC_RUNTIME_CAPABILITIES_V1_SIZE ||
        !rt->health || !rt->yield_ms || !rt->diagnostic || !rt->acquire || !rt->release) return;
    risc_runtime_capability_v1 dg={.struct_size=sizeof(dg)},rg={.struct_size=sizeof(rg)},pg={.struct_size=sizeof(pg)};
    bool have_d=rt->acquire("display.output",1,0,&dg),have_r=false,have_p=false;
    if (!have_d) goto done;
    display=dg.api;
    if (!display || display->api_version!=1 || display->struct_size<TWATCH_PANEL_LIGHT_SLEEP_SIZE ||
        !display->get_info || !display->acquire || !display->release || !display->submit ||
        !display->present_status || !display->set_brightness) goto done;
    panel=dg.api;
    if (!panel->prepare_sleep || !panel->resume) goto done;
#ifndef WATCH_CLOCK_RETURN
    if (!display->set_brightness(display->context,0,100)) goto done;
#endif
    have_p=rt->acquire("board.battery",1,0,&pg);
    if (!have_p) goto done;
    pmu=pg.api;
    if (!pmu || pmu->base.api_version!=1 || pmu->base.struct_size<TWATCH_PMU_LIGHT_SLEEP_SIZE ||
        !pmu->key_events || !pmu->prepare_sleep || !pmu->resume || !pmu->light_sleep) goto done;
    have_r=rt->acquire("rtc.clock",2,0,&rg);
    if (have_r) {
        rtc=rg.api;
        if (!rtc || rtc->api_version!=2 || rtc->struct_size<sizeof(*rtc) || !rtc->read) rtc=NULL;
    }
    uint32_t discarded,now,armed_at=0,last_activity=0;
    if (!pmu->key_events(pmu->base.context,&discarded) ||
#ifdef WATCH_CLOCK_RETURN
        !return_to_clock() ||
#else
        !startup() ||
#endif
        !pmu->key_events(pmu->base.context,&discarded) || !alive(&armed_at)) goto done;
#ifdef WATCH_CLOCK_LAUNCHER
    if(!rt->request_launch || !launcher_touch_open(&touch)) goto done;
#endif
    last_activity=armed_at;
#ifdef WATCH_CLOCK_LAUNCHER
    /* Read once per fresh Clock invocation, release the grant before sleep.
     * Settings returns through a fresh Clock, and deep wake boots default. */
    sleep_mode=PORTABLE_SLEEP_HYBRID;
    risc_runtime_capability_v1 sg={.struct_size=sizeof(sg)};
    if(rt->acquire(RISC_KEY_VALUE_CAPABILITY,RISC_KEY_VALUE_API_V1,PORTABLE_SLEEP_STORE_INSTANCE,&sg)) {
        int loaded=portable_sleep_load(sg.api,&sleep_mode);
        if(!rt->release(&sg))goto done;
        if(loaded==PORTABLE_SLEEP_INVALID || loaded==PORTABLE_SLEEP_UNAVAILABLE)
            rt->diagnostic("WATCH_CLOCK settings=unreadable default=hybrid");
    } else rt->diagnostic("WATCH_CLOCK settings=unavailable default=hybrid");
    rt->diagnostic(sleep_mode==PORTABLE_SLEEP_DEEP?"WATCH_CLOCK mode=deep":sleep_mode==PORTABLE_SLEEP_LIGHT?"WATCH_CLOCK mode=light":"WATCH_CLOCK mode=hybrid");
#endif
    rt->diagnostic("WATCH_CLOCK ready crown=enabled");
    while(alive(&now)) {
        uint32_t events=0;
        if (!pmu->key_events(pmu->base.context,&events)) break;
        /* The clock closure currently exposes only PMU short/long key events.
         * Do not invent touch activity. Short press is reported on release. */
        if (events&3u) last_activity=now;
#ifdef WATCH_CLOCK_LAUNCHER
        sample_launcher_touch(now,true);
        if(launcher_activity_pending) last_activity=now;
        launcher_activity_pending=false;
        if(launcher_swipe_pending) {
            launcher_swipe_pending=false;
            /* The completed sharp Clock remains in provider-owned storage.
             * Incoming Springboard owns the single blur/crossfade and adopts
             * the still-held contact as drag-only; never fade through black. */
            if(!launcher_touch_close(&touch)) break;
            if(rt->request_launch("springboard.elf")) break;
            rt->diagnostic("WATCH_CLOCK error=launcher-request");
            if(!launcher_touch_open(&touch) || !alive(&now)) break;
            last_activity=now;
        }
#endif
        bool manual=(events&2u) && (uint32_t)(now-armed_at)>=250u;
        bool idle=(uint32_t)(now-last_activity)>=60000u;
        if (manual || idle) {
#ifdef WATCH_CLOCK_LAUNCHER
            /* Retained input subscriptions must not veto platform sleep. */
            if(!launcher_touch_close(&touch)) break;
#endif
            if (!sleep_cycle() || !alive(&armed_at)) break;
            /* A refused/held-key attempt also starts a new bounded interval;
             * it must not turn an expired timeout into a busy retry loop. */
            last_activity=armed_at;
#ifdef WATCH_CLOCK_LAUNCHER
            if(!launcher_touch_open(&touch)) break;
#endif
            continue;
        }
        risc_display_surface_v1 s={0};
        if (!frame(&s) || !draw_clock(now,&s) || !present() || !pace_frame(now)) break;
    }
done:
#ifdef WATCH_CLOCK_LAUNCHER
    if(!launcher_touch_close(&touch)) rt->diagnostic("WATCH_CLOCK error=touch-release");
#endif
    if (held && display && display->release) display->release(display->context,held);
    if (have_r) rt->release(&rg);
    if (have_p) rt->release(&pg);
    if (have_d) rt->release(&dg);
}

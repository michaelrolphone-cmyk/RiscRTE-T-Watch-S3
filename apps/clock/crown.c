#if defined(WATCH_PAIRED_BOOT_CONFIRM) && !defined(WATCH_CLOCK_RETURN)
#include "runtime_boot_confirm.h"
#endif
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
static char sleep_status[32];

static const risc_runtime_api_v1 *rt;
#ifdef WATCH_RUNTIME_FEATURES
#include "../runtime_features/clock_runtime.h"
static watch_clock_runtime native_clock;
#endif
#ifdef WATCH_CONTEXTS_CLIENT
#include "PortableContextsClient.h"
static portable_contexts_client clock_contexts;
static bool clock_contexts_uncertain,clock_contexts_handoff;
static char clock_context_message[33];
static bool clock_contexts_capture_checkpoint(void *context) {
    (void)context;
    if(clock_contexts_uncertain)return false;
#ifdef WATCH_RUNTIME_FEATURES
    if(native_clock.halted)return false;
#endif
    if(portable_contexts_capture(&clock_contexts))return true;
    clock_contexts_uncertain=true;
    if(!portable_contexts_retain(&clock_contexts))for(;;)rt->yield_ms(50);
    return false;
}
static bool clock_contexts_pause(void) {
    if(clock_contexts_uncertain)return false;
    if(portable_contexts_pause(&clock_contexts))return true;
    clock_contexts_uncertain=true;
#ifdef WATCH_RUNTIME_FEATURES
    watch_runtime_retain(rt);
#endif
    return false;
}
#endif
#ifdef WATCH_BLE_BROADCAST
#include "PortableBroadcastClient.h"
static portable_broadcast_client clock_broadcast;
static bool clock_broadcast_uncertain,clock_handoff;
static bool clock_broadcast_step(void) {
    if(clock_broadcast_uncertain)return false;
    if(!clock_broadcast.api)return true;
    if(!portable_broadcast_step(&clock_broadcast,true)) {
        clock_broadcast_uncertain=true;
#ifdef WATCH_RUNTIME_FEATURES
        watch_runtime_retain(rt);
#endif
        return false;
    }
    return true;
}
static bool clock_broadcast_pause(void) {
    if(clock_broadcast_uncertain)return false;
    if(!portable_broadcast_pause(&clock_broadcast)) {
        clock_broadcast_uncertain=true;
#ifdef WATCH_RUNTIME_FEATURES
        watch_runtime_retain(rt);
#endif
        return false;
    }
    return true;
}
#endif
#if defined(WATCH_CONTEXTS_CLIENT) || defined(WATCH_BLE_BROADCAST)
static bool clock_background_pause(void) {
#ifdef WATCH_CONTEXTS_CLIENT
    if(!clock_contexts_pause())return false;
#endif
#ifdef WATCH_BLE_BROADCAST
    if(!clock_broadcast_pause())return false;
#endif
    return true;
}
#endif
#ifdef WATCH_CLOCK_ALARMS
#ifndef WATCH_CLOCK_LAUNCHER
#error Alarm Clock requires its normal touch launcher deployment
#endif
static bool clock_alarm_modal,clock_display_settled;
static bool clock_alarm_foreground(void);
static bool clock_alarm_failure(void);
#endif
#ifdef WATCH_CLOCK_LAUNCHER
#include "faces/picker.h"
#ifdef WATCH_QUICK_ACTIONS
#include "PortableQuickSession.h"
#include "PortableQuickRender.h"
static pqa_session clock_quick;
#ifdef WATCH_QUICK_RADIOS
#include "PortableQuickRadios.h"
static pqa_radios clock_radios;
#ifdef PORTABLE_LOW_BATTERY
#include "PortableLowBattery.h"
static portable_low_battery clock_low_battery;
static uint32_t clock_low_battery_at;
static bool clock_low_battery_sampled;
#endif
#endif
#endif
#include "launcher_touch.h"
#include "PortableSleepPolicy.h"
#include "PortableTimeFormat.h"
static unsigned sleep_mode;
static watch_face_picker picker;
static nova_watch_picker_cache *picker_scratch;
static bool picker_open_pending,picker_select_pending,picker_save_failed;
static unsigned picker_selection_pending;
static watch_launcher_touch touch;
static bool launcher_swipe_pending, launcher_activity_pending;
static uint32_t launcher_sampled_at;
/* Sampling must not wait for a whole 240-row presentation. Latch the first
 * qualified swipe, but let the accepted frame finish before handing it off. */
static void sample_launcher_touch(uint32_t now, bool force) {
#ifdef WATCH_CONTEXTS_CLIENT
    if(!clock_contexts_capture_checkpoint(NULL))return;
#endif
#ifdef WATCH_CLOCK_ALARMS
    if(clock_alarm_modal)return;
#endif
    if (!touch.subscription || launcher_swipe_pending ||
        (!force && (uint32_t)(now-launcher_sampled_at)<8u)) return;
    bool activity=false;
    launcher_sampled_at=now;
    unsigned action=launcher_touch_sample(&touch,&picker,now,&activity);
    if(action==WATCH_FACE_LAUNCHER)launcher_swipe_pending=true;
    if(action==WATCH_FACE_OPEN)picker_open_pending=true;
    if(action==WATCH_FACE_SELECT){picker_selection_pending=watch_face_page_for(picker.category)->ids[picker.target];picker_select_pending=true;}
    if (activity) launcher_activity_pending=true;
}
#endif
static const risc_display_output_api_v1 *display;
static const twatch_rtc_api_v1 *rtc;
static const twatch_pmu_api_v1 *pmu;
static const twatch_panel_power_v1 *panel;
static risc_display_frame_v1 held;
static nova_watch_state face;
#ifdef WATCH_CLOCK_POINTS
#include "points_projection.h"
static points_config clock_points_config;
static points_meta clock_points_meta;
static nova_points_state clock_points_view;
static bool clock_points_available;
static uint32_t clock_points_second;
static bool clock_points_sampled;
static bool clock_points_load(void) {
    risc_runtime_capability_v1 grant={.struct_size=sizeof(grant)};
    clock_points_config=(points_config){0};clock_points_meta=(points_meta){0};clock_points_sampled=false;
    clock_points_view=(nova_points_state){.status=NOVA_POINTS_UNAVAILABLE};clock_points_available=false;
    if(!rt->acquire(RISC_KEY_VALUE_CAPABILITY,1,5,&grant))return true;
    const risc_key_value_v1 *kv=grant.api;
    if(kv&&kv->api_version==1&&kv->struct_size>=sizeof(*kv)&&kv->get) {
        uint8_t bytes[POINTS_RECORD_SIZE];uint32_t n=0;
        int32_t result=kv->get(kv->context,POINTS_CONFIG_KEY,bytes,sizeof(bytes),&n);
        clock_points_available=result==RISC_KEY_VALUE_NOT_FOUND||
            (result==RISC_KEY_VALUE_OK&&points_config_decode(&clock_points_config,bytes,n));
#ifdef POINTS_DEFAULTS_AVAILABLE
        /* A missing catalog exposes the shared virtual defaults. Never replace
         * a present empty, malformed or unavailable saved catalog. */
        bool defaults=result==RISC_KEY_VALUE_NOT_FOUND;
        if(defaults)clock_points_config=points_default_config();
#endif
#if WATCH_POINTS_EXTENDED
        n=0;result=kv->get(kv->context,POINTS_META_KEY,bytes,sizeof(bytes),&n);
#ifdef POINTS_DEFAULTS_AVAILABLE
        if(defaults&&result==RISC_KEY_VALUE_NOT_FOUND)clock_points_meta=points_default_meta();
#endif
        if(result==RISC_KEY_VALUE_OK&&!points_meta_decode(&clock_points_meta,bytes,n)) {
            clock_points_meta=(points_meta){0};
            rt->diagnostic("WATCH_CLOCK points-meta=invalid fallback=generic");
        } else if(result!=RISC_KEY_VALUE_OK&&result!=RISC_KEY_VALUE_NOT_FOUND) {
            clock_points_meta=(points_meta){0};
            rt->diagnostic("WATCH_CLOCK points-meta=unavailable fallback=generic");
        }
#endif
        clock_points_view.status=clock_points_available?NOVA_POINTS_EMPTY:NOVA_POINTS_ERROR;
    }
    return rt->release(&grant);
}
#endif
static uint32_t rtc_sampled_at, rtc_second_at, battery_sampled_at;
static bool sampled_rtc, sampled_battery;
static void reset_telemetry(void) {
    face=(nova_watch_state){0}; sampled_rtc=false; sampled_battery=false;
#ifdef WATCH_CONTEXTS_CLIENT
    face.capture_audio=clock_contexts_capture_checkpoint;
#endif
#ifdef WATCH_CLOCK_POINTS
    clock_points_sampled=false;face.points=&clock_points_view;
#endif
}
#ifdef WATCH_CLOCK_LAUNCHER
static bool reload_time_format(void) {
    unsigned mode=PORTABLE_TIME_FORMAT_12;
    risc_runtime_capability_v1 grant={.struct_size=sizeof(grant)};
    if(rt->acquire(RISC_KEY_VALUE_CAPABILITY,1,PORTABLE_TIME_FORMAT_STORE_INSTANCE,&grant)) {
        (void)portable_time_format_load(grant.api,&mode);
        if(!rt->release(&grant))return false;
    }
    face.hour_24=mode==PORTABLE_TIME_FORMAT_24;
    return true;
}
#endif
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
#ifdef WATCH_CONTEXTS_CLIENT
    if(!clock_contexts_capture_checkpoint(NULL))return false;
#endif
    risc_display_present_token_v1 token=0;
    uint32_t start,now;
    if (!alive(&start)) return false;
    bool healthy=true;
    const risc_display_present_options_v1 opts={0,0,0};
#ifdef WATCH_CLOCK_ALARMS
    clock_display_settled=false;
#endif
    if (!display->submit(display->context,held,NULL,0,&opts,&token)) return false;
    held=0;
    for(unsigned n=0;n<=10000;n++) {
#ifdef WATCH_CONTEXTS_CLIENT
        if(!clock_contexts_capture_checkpoint(NULL))return false;
#endif
        risc_display_present_status_v1 s={0};
        if (!display->present_status(display->context,token,&s)) return false;
        if (s.state==RISC_DISPLAY_PRESENT_COMPLETE) {
#ifdef WATCH_CLOCK_ALARMS
            clock_display_settled=true;
#endif
            return healthy;
        }
        if (s.state==RISC_DISPLAY_PRESENT_FAILED || s.state==RISC_DISPLAY_PRESENT_SUPERSEDED) return false;
        if (alive(&now)) {
            if ((uint32_t)(now-start)>=10000) return false;
#ifdef WATCH_CLOCK_LAUNCHER
            sample_launcher_touch(now,false);
#ifdef WATCH_CONTEXTS_CLIENT
            if(clock_contexts_uncertain)return false;
#endif
#endif
        } else healthy=false;
        /* A lost health sample must not abandon an already accepted transfer.
         * Drain it within the same bounded poll count, then exit the app. */
        rt->yield_ms(1);
    }
    return false;
}
static bool frame(risc_display_surface_v1 *surface) {
#ifdef WATCH_CONTEXTS_CLIENT
    if(!clock_contexts_capture_checkpoint(NULL))return false;
#endif
    if (!display->acquire(display->context,RISC_DISPLAY_FORMAT_RGB565,surface)) return false;
    held=surface->frame;return held!=0;
}
static bool draw_clock(uint32_t now,risc_display_surface_v1 *surface) {
    /* RTC sampling and fractional phase are independent of the frame cadence.
     * Only a successful RTC sample may advance civil time. The first observed
     * edge anchors the fractional hand within one 100ms sampling interval. */
    if (!sampled_rtc || (uint32_t)(now-rtc_sampled_at)>=100u) {
        twatch_rtc_time_v1 date={0};
        #ifdef WATCH_RUNTIME_FEATURES
        uint16_t native_fraction=0;
        bool valid=watch_runtime_read(&native_clock,&date,&native_fraction);
        if(native_clock.halted)return false;
#else
        bool valid=rtc && rtc->read(rtc->context,&date);
#endif
#ifdef WATCH_CLOCK_POINTS
        uint32_t raw_seconds=0;
        bool raw_valid=valid&&alarm_calendar_seconds(date.year,date.month,date.day,date.hour,date.minute,date.second,&raw_seconds);
        if(!raw_valid)clock_points_view.status=NOVA_POINTS_ERROR;
        else if(clock_points_available&&(!clock_points_sampled||clock_points_second!=raw_seconds||clock_points_view.status==NOVA_POINTS_ERROR)) {
            (void)watch_points_projection(&clock_points_config,&clock_points_meta,raw_seconds,&clock_points_view);
            clock_points_second=raw_seconds;clock_points_sampled=true;
        }
        face.points=&clock_points_view;
#endif
        valid=valid&&watch_display_time(&date,&date);
        #ifdef WATCH_RUNTIME_FEATURES
        if(valid && !native_clock.fallback)rtc_second_at=now-native_fraction;
        else if(valid && (!face.time_valid || !same_second(&date,&face.time)))rtc_second_at=now;
#else
        if (valid && (!face.time_valid || !same_second(&date,&face.time))) rtc_second_at=now;
#endif
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
    #ifdef WATCH_CLOCK_LAUNCHER
    if(picker.open&&picker_scratch) {
        watch_face_animate(&picker,now);
        picker.category_positions[picker.category]=picker.position;
        return nova_watch_picker_collections_render(surface,&face,picker.selected,picker.category_position,picker.category_positions,picker_save_failed?"SAVE FAILED":NULL,picker.pulse_face,picker.pulse_active?nova_watch_picker_pulse(now-picker.pulse_started):256u,picker_scratch);
    }
#ifdef WATCH_CONTEXTS_CLIENT
    if(clock_context_message[0])return nova_watch_context_message(surface,clock_context_message);
#endif
    bool rendered=nova_watch_face_render(surface,&face,picker.selected);
#ifdef WATCH_QUICK_ACTIONS
    pqa_animate(&clock_quick.ui,now);
    if(rendered && pqa_visible(&clock_quick.ui)) {
        nova_watch_labels labels;nova_watch_format(&face,&labels);
        rendered=pqa_render(surface,&clock_quick.ui,labels.hour_minute,face.battery_valid,face.battery_percent);
    }
#endif
    if(rendered && sleep_status[0])rendered=nova_watch_sleep_status(surface,sleep_status);
    return rendered;
#else
    return nova_watch_render(surface,&face);
#endif
}
static bool pace_frame(uint32_t began) {
#ifdef WATCH_BLE_BROADCAST
    if(!clock_broadcast_step())return false;
#endif
#ifdef WATCH_CLOCK_LAUNCHER
    if (launcher_swipe_pending) return true;
#endif
    uint32_t now;
    if (!alive(&now)) return false;
    uint32_t spent = now - began;
    /* Presentation time already counts toward the 20ms animation interval. */
    #ifdef WATCH_CONTEXTS_CLIENT
    uint32_t remaining=spent<20u?20u-spent:0;
    while(remaining){uint32_t slice=remaining>8?8:remaining;rt->yield_ms(slice);remaining-=slice;if(!clock_contexts_capture_checkpoint(NULL))return false;}
#else
    if (spent < 20u) rt->yield_ms(20u - spent);
#endif
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
#ifdef WATCH_RUNTIME_FEATURES
    if(native_clock.halted)return false;
#endif
#ifdef WATCH_BLE_BROADCAST
    if(clock_broadcast_uncertain)return false;
#endif
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
#ifdef WATCH_RUNTIME_FEATURES
    if(native_clock.halted)return false;
#endif
#ifdef WATCH_BLE_BROADCAST
    if(clock_broadcast_uncertain)return false;
#endif
    free(scratch);free(old);return ok;
}
#endif
static unsigned clock_brightness(void) {
#ifdef WATCH_QUICK_ACTIONS
    return clock_quick.brightness;
#else
    return 40;
#endif
}
#ifdef PORTABLE_LOW_BATTERY
static bool clock_low_battery_poll(uint32_t now) {
    if(held)return true;
#ifdef WATCH_CLOCK_ALARMS
    if(!clock_display_settled||clock_alarm_modal)return true;
#endif
    if(clock_low_battery_sampled&&(uint32_t)(now-clock_low_battery_at)<5000u)return true;
    clock_low_battery_sampled=true;clock_low_battery_at=now;
    risc_battery_sample_v1 sample={0,255,RISC_BATTERY_PROFILE_MISSING};
    if(!pmu->base.read||!pmu->base.read(pmu->base.context,&sample))return true;
#if defined(WATCH_BLE_BROADCAST) || defined(WATCH_CONTEXTS_CLIENT)
    if(portable_low_battery_sample_valid(&sample) && sample.percent<PORTABLE_LOW_BATTERY_THRESHOLD &&
       (!clock_low_battery.observed || !clock_low_battery.low) && !clock_background_pause())return false;
#endif
    unsigned result=portable_low_battery_update(&clock_low_battery,rt,&sample);
    if(result&PORTABLE_LOW_BATTERY_RETAINED) {
#ifdef WATCH_RUNTIME_FEATURES
        watch_runtime_halt(&native_clock);
#endif
        return false;
    }
    if(result&PORTABLE_LOW_BATTERY_ERROR)rt->diagnostic("LOW_BATTERY settings=unconfirmed");
    if(!(result&PORTABLE_LOW_BATTERY_ENTERED))return true;
    pqa_cancel(&clock_quick.ui);(void)pqa_take_action(&clock_quick.ui);
    if(!pqa_session_load(&clock_quick,rt)||!pqa_radios_load(&clock_radios,&clock_quick.ui,rt)||
       !pqa_session_restore(&clock_quick,display))return false;
    rt->diagnostic(result&PORTABLE_LOW_BATTERY_ERROR?"LOW_BATTERY crossing=partial-once":"LOW_BATTERY crossing=applied-once");return true;
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
        if (!count && !display->set_brightness(display->context,(uint16_t)clock_brightness(),100)) return false;
        if (age>=1800) return hold_boot_frame() && logo_to_clock();
        if (!pace_frame(now)) return false;
    }
    return false;
}
#ifdef WATCH_CLOCK_ALARMS
#include "clock_alarm.inc"
#ifdef WATCH_MOTION_WAKE
#include "watch_motion_client.h"
#endif
#endif
#ifdef WATCH_CONTEXTS_CLIENT
#include "clock_contexts.inc"
#endif
#if defined(WATCH_RUNTIME_FEATURES) && !defined(WATCH_CLOCK_RETURN)
static bool resume_from_deep(void) {
    risc_display_surface_v1 fresh={0};uint32_t now;
    return display->set_brightness(display->context,0,100) && alive(&now) &&
        frame(&fresh) && draw_clock(now,&fresh) && present() &&
        display->set_brightness(display->context,(uint16_t)clock_brightness(),100);
}
#endif
static int sleep_cycle(void) {
    sleep_status[0]=0;
#if defined(WATCH_BLE_BROADCAST) || defined(WATCH_CONTEXTS_CLIENT)
    if(!clock_background_pause())return WATCH_SLEEP_RETAINED;
#endif
#ifdef PORTABLE_LOW_BATTERY
    watch_sleep_light_ms=clock_quick.deep_ms;
#endif
#ifdef WATCH_QUICK_RADIOS
    if(!pqa_radios_suspend(rt)){rt->diagnostic("QUICK Bluetooth cleanup-unconfirmed");return false;}
#endif
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
#ifdef WATCH_CLOCK_ALARMS
    (void)watch_sleep_prepared;
#ifdef WATCH_MOTION_WAKE
    (void)watch_alarm_sleep_prepared;
    int rc=watch_motion_sleep(rt,panel,pmu,mode,clock_alarm.api);
#else
    int rc=watch_alarm_sleep_prepared(panel,pmu,mode,clock_alarm.api,rt->diagnostic);
#endif
#else
    int rc=watch_sleep_prepared(panel,pmu,mode,rt->diagnostic);
#endif
    if(rc==WATCH_SLEEP_RETAINED)return WATCH_SLEEP_RETAINED;
    if(rc<0)return false;
#ifdef WATCH_QUICK_RADIOS
    if(!pqa_radios_resume(&clock_radios,&clock_quick.ui,rt))return false;
#endif
    uint32_t discard;
    reset_telemetry();
#ifdef WATCH_CLOCK_LAUNCHER
    if(!reload_time_format())return false;
#endif
#ifdef WATCH_CLOCK_ALARMS
    /* Due work is handled before wake intro; short/crown and touch are fresh. */
    if(!launcher_touch_open(&touch) || !clock_alarm_foreground() || !launcher_touch_close(&touch))return false;
#endif
    if (rc==WATCH_SLEEP_WOKE) {
        rt->diagnostic("WATCH_CLOCK woke");
        if (!display->set_brightness(display->context,0,100) || !startup()) return false;
    } else {
        rt->diagnostic("WATCH_CLOCK sleep=refused");
        static const char *const stages[]={"UNKNOWN","SENSOR","PANEL","PMU","ALARM","LIGHT","DEEP","ACQUIRE","API"};
        memcpy(sleep_status,"SLEEP ",6);unsigned count=6;
        const char *name=stages[watch_sleep_stage<9?watch_sleep_stage:0];
        while(*name && count<20)sleep_status[count++]=*name++;
        sleep_status[count++]=' ';uint32_t value=(uint32_t)watch_sleep_detail;
        if(watch_sleep_detail<0){sleep_status[count++]='-';value=0u-value;}
        char digits[10];unsigned used=0;do{digits[used++]=(char)('0'+value%10u);value/=10u;}while(value&&used<10);
        while(used&&count+1<sizeof(sleep_status)){sleep_status[count++]=digits[--used];}
        sleep_status[count]=0;
        risc_display_surface_v1 fresh={0};uint32_t now;
        /* The pre-sleep clear also runs before a refused attempt. Replace it
         * with a complete fresh Clock before restoring the previous level. */
        if (!display->set_brightness(display->context,0,100) || !alive(&now) ||
            !frame(&fresh) || !draw_clock(now,&fresh) || !present() ||
            !display->set_brightness(display->context,(uint16_t)clock_brightness(),100)) return false;
    }
    return pmu->key_events(pmu->base.context,&discard);
}
__attribute__((visibility("default"))) void app_main(void) {
    rt=risc_runtime_get_api(1);
#if defined(WATCH_RUNTIME_FEATURES) && defined(WATCH_CLOCK_RETURN)
    (void)watch_runtime_promote;
#endif
#ifdef WATCH_CLOCK_ALARMS
    clock_alarm=(portable_alarm_client){0};clock_display_settled=true;
    clock_alarm_modal=clock_alarm_failed_cleaned=clock_alarm_error_seen=false;
#endif
#ifdef WATCH_CLOCK_LAUNCHER
    touch=(watch_launcher_touch){0};
#ifdef WATCH_QUICK_ACTIONS
    pqa_session_init(&clock_quick);
#ifdef PORTABLE_LOW_BATTERY
    clock_low_battery=(portable_low_battery){0};clock_low_battery_sampled=false;clock_low_battery_at=0;
#endif
#endif
    launcher_swipe_pending=launcher_activity_pending=false;
    launcher_sampled_at=0;
    picker=(watch_face_picker){0};picker_scratch=NULL;
    picker_open_pending=picker_select_pending=picker_save_failed=false;
    picker_selection_pending=0;
#endif
    held=0;rtc=NULL;display=NULL;pmu=NULL;panel=NULL;
#ifdef WATCH_BLE_BROADCAST
    clock_broadcast=(portable_broadcast_client){0};clock_broadcast_uncertain=clock_handoff=false;
#endif
#ifdef WATCH_CONTEXTS_CLIENT
    clock_contexts=(portable_contexts_client){0};clock_contexts_uncertain=clock_contexts_handoff=false;clock_context_message[0]=0;
#endif
    reset_telemetry();
    if (!rt || rt->api_version!=1 || rt->struct_size<RISC_RUNTIME_CAPABILITIES_V1_SIZE ||
        !rt->health || !rt->yield_ms || !rt->diagnostic || !rt->acquire || !rt->release) return;
    risc_runtime_capability_v1 dg={.struct_size=sizeof(dg)},rg={.struct_size=sizeof(rg)},pg={.struct_size=sizeof(pg)};
    bool have_d=false,have_r=false,have_p=false;
#ifdef WATCH_RUNTIME_FEATURES
    if(!watch_runtime_open(&native_clock,rt,
#ifdef WATCH_CLOCK_RETURN
        false
#else
        true
#endif
        ))goto done;
#endif
#ifdef WATCH_BLE_BROADCAST
    if(!portable_broadcast_open(&clock_broadcast,rt))goto done;
#endif
#ifdef WATCH_CONTEXTS_CLIENT
    if(!portable_contexts_open(&clock_contexts,rt)||!clock_contexts_pause())goto done;
#endif
    have_d=rt->acquire("display.output",1,0,&dg);
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
#ifdef WATCH_RUNTIME_FEATURES
    if(!watch_runtime_seed(&native_clock,rtc))goto done;
#endif
    #ifdef WATCH_CLOCK_LAUNCHER
    /* Load before the first sharp Clock frame on fresh boot and normal return.
     * This is the existing shared app-settings namespace, never a driver write. */
    risc_runtime_capability_v1 face_grant={.struct_size=sizeof(face_grant)};
    if(rt->acquire(RISC_KEY_VALUE_CAPABILITY,1,WATCH_FACE_STORE_INSTANCE,&face_grant)) {
        unsigned selected=0;int rc=watch_face_load(face_grant.api,&selected);
        picker.selected=(uint8_t)selected;
        unsigned format=PORTABLE_TIME_FORMAT_12;(void)portable_time_format_load(face_grant.api,&format);
        face.hour_24=format==PORTABLE_TIME_FORMAT_24;
        if(!rt->release(&face_grant))goto done;
        if(rc!=RISC_KEY_VALUE_OK&&rc!=RISC_KEY_VALUE_NOT_FOUND)rt->diagnostic("WATCH_CLOCK face=unreadable default=nova");
    }
#endif
#ifdef WATCH_QUICK_ACTIONS
    if(!pqa_session_load(&clock_quick,rt))goto done;
#ifdef WATCH_QUICK_RADIOS
    if(!pqa_radios_load(&clock_radios,&clock_quick.ui,rt))goto done;
#endif
#endif
#ifdef WATCH_CLOCK_ALARMS
#ifdef WATCH_CLOCK_POINTS
    if(!clock_points_load())goto done;
#endif
    /* Deep reset and normal return both reconcile before any boot intro. */
    if(!portable_alarm_open(&clock_alarm,rt) || !launcher_touch_open(&touch) || !clock_alarm_foreground())goto done;
#endif
    uint32_t discarded,now,armed_at=0,last_activity=0;
    if (!pmu->key_events(pmu->base.context,&discarded) ||
#ifdef WATCH_CLOCK_RETURN
        !return_to_clock() ||
#else
#ifdef WATCH_RUNTIME_FEATURES
        !(native_clock.resume?resume_from_deep():startup()) ||
#else
        !startup() ||
#endif
#endif
        !pmu->key_events(pmu->base.context,&discarded) || !alive(&armed_at)) goto done;
#ifdef WATCH_CLOCK_LAUNCHER
#ifdef WATCH_CLOCK_ALARMS
    if(!rt->request_launch)goto done;
#else
    if(!rt->request_launch || !launcher_touch_open(&touch)) goto done;
#endif
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
#if defined(WATCH_PAIRED_BOOT_CONFIRM) && !defined(WATCH_CLOCK_RETURN)
    /* Startup has presented a complete frame and admitted all startup services.
     * A pending native/store pair must remain unconfirmed on every earlier
     * failure, intentional exit, queued handoff or native-retained path. */
#ifdef WATCH_RUNTIME_FEATURES
    int promoted=watch_runtime_promote(&native_clock);
    if(promoted==RISC_PROVIDER_PROMOTION_RETAINED)return;
    if(promoted!=RISC_PROVIDER_PROMOTION_OK && promoted!=RISC_PROVIDER_PROMOTION_ALREADY_READY) {
        rt->diagnostic("WATCH_CLOCK error=provider-promotion");goto done;
    }
#endif
    if(!watch_confirm_paired_boot(rt)) {
        rt->diagnostic("WATCH_CLOCK error=paired-boot-confirm");goto done;
    }
#endif
    rt->diagnostic("WATCH_CLOCK ready crown=enabled");
#ifdef WATCH_CONTEXTS_CLIENT
    if(!clock_contexts_recover_export())goto done;
#endif
    while(alive(&now)) {
#ifdef WATCH_BLE_BROADCAST
        if(!clock_broadcast_step())return;
#endif
#ifdef WATCH_CLOCK_ALARMS
        if(!clock_alarm_foreground() || !alive(&now))break;
#endif
#ifdef PORTABLE_LOW_BATTERY
        if(!clock_low_battery_poll(now))break;
#endif
#ifdef WATCH_CONTEXTS_CLIENT
        if(!clock_contexts_tick())break;
        if(clock_contexts_handoff)break;
#endif
        uint32_t events=0;
        if (!pmu->key_events(pmu->base.context,&events)) break;
        /* The clock closure currently exposes only PMU short/long key events.
         * Do not invent touch activity. Short press is reported on release. */
        if (events&3u) last_activity=now;
#ifdef WATCH_CLOCK_LAUNCHER
        sample_launcher_touch(now,true);
#ifdef WATCH_CONTEXTS_CLIENT
        if(clock_contexts_uncertain)break;
#endif
#ifdef WATCH_CONTEXTS_CLIENT
        if(clock_context_message[0]&&(launcher_activity_pending||(events&3u))){clock_context_message[0]=0;clock_alarm_cancel_input();events=0;}
#endif
        if(launcher_activity_pending) last_activity=now;
        launcher_activity_pending=false;
#ifdef WATCH_QUICK_ACTIONS
        if(events&3u)pqa_close(&clock_quick.ui);
        uint32_t quick_actions=pqa_take_action(&clock_quick.ui);bool volume_changed=false;
#ifdef WATCH_CONTEXTS_CLIENT
        if(quick_actions&&!clock_contexts_pause())return;
#endif
        if(!pqa_session_apply(&clock_quick,rt,display,quick_actions,&volume_changed))break;
#ifdef WATCH_CONTEXTS_CLIENT
        if(quick_actions&PQA_CONTEXTS)portable_contexts_settings_changed(&clock_contexts,clock_quick.ui.contexts_valid);
#endif
#ifdef WATCH_QUICK_RADIOS
#ifdef WATCH_BLE_BROADCAST
        if((quick_actions&(PQA_WIFI|PQA_BLUETOOTH|PQA_AIRPLANE)) && !clock_broadcast_pause())return;
#endif
        if(!pqa_radios_apply(&clock_radios,&clock_quick.ui,rt,quick_actions))break;
#endif
#ifdef WATCH_CLOCK_ALARMS
        if(volume_changed && clock_alarm.api)(void)clock_alarm.api->refresh(clock_alarm.api->context);
#endif
        if(!clock_quick.ui.radio_controls && (quick_actions&PQA_WIFI)) {
            pqa_cancel(&clock_quick.ui);
            if(!pqa_session_restore(&clock_quick,display) || !launcher_touch_close(&touch))break;
            if(rt->request_launch("wifi_settings.elf")) {
#ifdef WATCH_BLE_BROADCAST
                clock_handoff=true;
#endif
                break;
            }
            clock_quick.ui.error_flags|=PQA_ERROR_WIFI;
            if(!launcher_touch_open(&touch))break;
        }
#endif
        if(picker_open_pending) {
            picker_open_pending=false;
            if(!picker_scratch){picker_scratch=malloc(sizeof(*picker_scratch));if(picker_scratch)picker_scratch->valid_mask=0;}
            if(!picker_scratch){watch_face_close(&picker);rt->diagnostic("WATCH_CLOCK picker=out-of-memory");}
        }
        /* Crown close/sleep supersedes any contact action sampled while an
         * accepted display transfer was draining. */
        if(events&3u)picker_select_pending=false;
        if(picker_select_pending) {
            picker_select_pending=false;
            risc_runtime_capability_v1 setting={.struct_size=sizeof(setting)};bool saved=false;
            if(rt->acquire(RISC_KEY_VALUE_CAPABILITY,1,WATCH_FACE_STORE_INSTANCE,&setting)) {
                saved=watch_face_save(setting.api,picker_selection_pending);
                if(!rt->release(&setting))break;
            }
            if(saved) {
                picker.selected=(uint8_t)picker_selection_pending;
                watch_face_close(&picker);free(picker_scratch);picker_scratch=NULL;
                picker_open_pending=launcher_swipe_pending=false;
            }
            picker_save_failed=!saved;
            rt->diagnostic(saved?"WATCH_CLOCK face=saved":"WATCH_CLOCK face=save-failed");
        }
        /* A short crown press dismisses the picker without changing selection;
         * the existing long-press sleep path remains untouched. */
        if(picker.open&&(events&1u)){watch_face_close(&picker);free(picker_scratch);picker_scratch=NULL;picker_save_failed=false;}
        if(launcher_swipe_pending) {
            launcher_swipe_pending=false;
            /* The completed sharp Clock remains in provider-owned storage.
             * Incoming Springboard owns the single blur/crossfade and adopts
             * the still-held contact as drag-only; never fade through black. */
            if(!launcher_touch_close(&touch)) break;
            if(rt->request_launch("springboard.elf")) {
#ifdef WATCH_BLE_BROADCAST
                clock_handoff=true;
#endif
                break;
            }
            rt->diagnostic("WATCH_CLOCK error=launcher-request");
            if(!launcher_touch_open(&touch) || !alive(&now)) break;
            last_activity=now;
        }
#endif
        bool manual=(events&2u) && (uint32_t)(now-armed_at)>=250u;
        bool idle=(uint32_t)(now-last_activity)>=
#ifdef PORTABLE_LOW_BATTERY
            clock_quick.idle_ms;
#else
            60000u;
#endif
#ifdef PORTABLE_LOW_BATTERY
        idle=idle&&clock_quick.idle_ms!=0;
#endif
        if (manual || idle) {
#ifdef WATCH_CLOCK_LAUNCHER
#ifdef WATCH_QUICK_ACTIONS
            pqa_cancel(&clock_quick.ui);(void)pqa_take_action(&clock_quick.ui);
#endif
            /* Retained input subscriptions must not veto platform sleep. */
            if(!launcher_touch_close(&touch)) break;
            watch_face_close(&picker);free(picker_scratch);picker_scratch=NULL;
            picker_open_pending=picker_select_pending=picker_save_failed=false;
#endif
#ifdef WATCH_RUNTIME_FEATURES
            if(!watch_runtime_stage(&native_clock)) {
                if(native_clock.halted)return;
                break;
            }
#endif
            int sleep_result=sleep_cycle();
            if(sleep_result==WATCH_SLEEP_RETAINED)return; /* Runtime retains before fini. */
#ifdef WATCH_RUNTIME_FEATURES
            if(!watch_runtime_abandon(&native_clock)) {
                if(native_clock.halted)return;
                break;
            }
#endif
            if (!sleep_result || !alive(&armed_at)) break;
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
#ifdef WATCH_RUNTIME_FEATURES
    if(native_clock.halted)return;
#endif
#ifdef WATCH_CONTEXTS_CLIENT
    if(clock_contexts_uncertain||!clock_contexts_pause())return;
    if(!portable_contexts_close(&clock_contexts)) {
#ifdef WATCH_RUNTIME_FEATURES
        watch_runtime_retain(rt);
#endif
        return;
    }
#endif
#ifdef WATCH_BLE_BROADCAST
    if(clock_broadcast_uncertain)return;
    if(!clock_handoff && !clock_broadcast_pause())return;
    if(!portable_broadcast_close(&clock_broadcast,rt)) {
#ifdef WATCH_RUNTIME_FEATURES
        watch_runtime_retain(rt);
#endif
        return;
    }
#endif
#ifdef WATCH_RUNTIME_FEATURES
    if(native_clock.halted)return;
    if(!watch_runtime_close(&native_clock))return;
#endif
#ifdef WATCH_QUICK_ACTIONS
    if(clock_quick.ui.torch && display && !pqa_session_restore(&clock_quick,display))rt->diagnostic("QUICK brightness-restore-failed");
#endif
#ifdef WATCH_CLOCK_ALARMS
    clock_alarm_finish();
#endif
#ifdef WATCH_CLOCK_LAUNCHER
    free(picker_scratch);picker_scratch=NULL;
    if(!launcher_touch_close(&touch)) rt->diagnostic("WATCH_CLOCK error=touch-release");
#endif
    if (held && display && display->release) display->release(display->context,held);
    if (have_r) rt->release(&rg);
    if (have_p) rt->release(&pg);
    if (have_d) rt->release(&dg);
}

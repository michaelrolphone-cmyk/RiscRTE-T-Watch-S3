/* Clock-only caller of the same shared service client. Included after the
 * settled frame helpers; contains no schedule/RTC/output policy. */
#include "PortableAlarmClient.h"
#include "PortableTouch.h"
#include "watch_alarm_sleep.h"
static portable_alarm_client clock_alarm;
static bool clock_alarm_failed_cleaned,clock_alarm_error_seen;
static int32_t clock_alarm_seen_error;
static uint32_t clock_alarm_seen_snapshot;
static void clock_alarm_cancel_input(void) {
    launcher_swipe_pending=launcher_activity_pending=false;
    picker_open_pending=picker_select_pending=false;
    watch_face_reset_contact(&picker);
}
static bool clock_alarm_failure(void) {
    if(clock_alarm_failed_cleaned)return false;
    clock_alarm_failed_cleaned=true;
    if(!portable_alarm_failure_stop(&clock_alarm)) {
        rt->diagnostic("ALARM clock-failed output-stop-unconfirmed; invocation retained");
        for(;;)rt->yield_ms(50);
    }
    return false;
}
static bool clock_alarm_foreground(void) {
    (void)portable_touch_open;(void)portable_touch_close;
    if(!clock_display_settled || held)return clock_alarm_failure();
    if(!portable_alarm_pump(&clock_alarm))return clock_alarm_failure();
    for(unsigned n=0;clock_alarm.status.state==ALARM_STATE_LOADING;n++) {
        if(n>=64)return clock_alarm_failure();
        rt->yield_ms(1);
        if(!portable_alarm_pump(&clock_alarm))return clock_alarm_failure();
    }
    bool error=clock_alarm.status.state==ALARM_STATE_BLOCKED;
    if(!portable_alarm_owned(&clock_alarm) && (!error || (clock_alarm_error_seen &&
       clock_alarm_seen_error==clock_alarm.status.error && clock_alarm_seen_snapshot==clock_alarm.status.snapshot)))return true;
    clock_alarm_cancel_input();clock_alarm_modal=true;
    portable_touch alert_touch={.api=touch.api,.subscription=touch.subscription};
    uint32_t discarded;
    if(!pmu->key_events(pmu->base.context,&discarded))return clock_alarm_failure();
    alarm_token_v1 shown=clock_alarm.status.occurrence;
    bool redraw=true;
    for(;;) {
        if(redraw) {
            risc_display_surface_v1 s={0};
            if(!frame(&s) || !nova_watch_alarm_render(&s,clock_alarm.status.occurrence.kind==ALARM_KIND_COUNTDOWN,
               clock_alarm.status.state==ALARM_STATE_BLOCKED,clock_alarm.status.error==ALARM_RTC,
               clock_alarm.status.state==ALARM_STATE_DISMISSING,clock_alarm.status.output_uncertain,
               clock_alarm.status.occurrence.generation!=0) || !present() ||
               !display->set_brightness(display->context,40,100))return clock_alarm_failure();
            redraw=false;
        }
        uint32_t now,events=0;
        if(!clock_display_settled || held || !alive(&now))return clock_alarm_failure();
        rt->yield_ms(20);
        if(!pmu->key_events(pmu->base.context,&events))return clock_alarm_failure();
        portable_touch_sample sample;portable_touch_read(&alert_touch,&sample);
        bool tap=sample.valid && sample.released && sample.tap_eligible && !sample.cancelled && !sample.moved;
        bool retry=tap && sample.y>=198;
        bool dismiss=(events&3u) || (tap && sample.y>=150 && sample.y<198);
        if(clock_alarm.status.state==ALARM_STATE_BLOCKED && retry) {
            (void)clock_alarm.api->refresh(clock_alarm.api->context);alert_touch.neutral=alert_touch.down=false;redraw=true;
        } else if(dismiss) {
            if(clock_alarm.status.occurrence.generation) {
                alarm_token_v1 token=clock_alarm.status.occurrence;
                (void)clock_alarm.api->acknowledge(clock_alarm.api->context,&token);
                alert_touch.neutral=alert_touch.down=false;redraw=true;
            } else if(clock_alarm.status.state==ALARM_STATE_BLOCKED && !clock_alarm.status.output_uncertain) {
                clock_alarm_error_seen=true;clock_alarm_seen_error=clock_alarm.status.error;
                clock_alarm_seen_snapshot=clock_alarm.status.snapshot;break;
            }
        }
        uint32_t old=clock_alarm.status.state;int32_t old_error=clock_alarm.status.error;
        if(!portable_alarm_pump(&clock_alarm))return clock_alarm_failure();
        if(memcmp(&shown,&clock_alarm.status.occurrence,sizeof(shown))) {
            shown=clock_alarm.status.occurrence;alert_touch.neutral=alert_touch.down=false;redraw=true;
        }
        if(old!=clock_alarm.status.state || old_error!=clock_alarm.status.error)redraw=true;
        if(clock_alarm.status.state==ALARM_STATE_READY && !portable_alarm_owned(&clock_alarm))break;
    }
    clock_alarm_modal=false;clock_alarm_cancel_input();return true;
}
static void clock_alarm_finish(void) {
    if(clock_alarm.api && !clock_alarm_failed_cleaned &&
       (!clock_display_settled || !portable_alarm_status(&clock_alarm) || portable_alarm_owned(&clock_alarm)))
        (void)clock_alarm_failure();
    if(!portable_alarm_close(&clock_alarm,rt))rt->diagnostic("ALARM clock-release-failed");
}

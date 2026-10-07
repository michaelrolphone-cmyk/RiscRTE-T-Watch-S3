/* Exact production service and Watch policy, with independent physical-calendar
 * and platform-monotonic boundaries. No hardware drift measurement is implied. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "AlarmRecords.h"
#include "PointsRecords.h"
#include "AlarmVolume.h"
#include "AlarmDnd.h"
#include "RiscBoundKeyValueV1.h"
#include "RiscPlatformClockV1.h"
#define WATCH_ALARM_SLEEP_RESUME 1
#ifndef WATCH_ALARM_HELPER_HEADER
#define WATCH_ALARM_HELPER_HEADER "apps/clock/watch_alarm_sleep.h"
#endif
#include WATCH_ALARM_HELPER_HEADER
static uint8_t test_blobs[9][64];static uint32_t test_sizes[9];
static uint64_t test_ms;static uint32_t test_wall,test_rtc_advance,test_mono_advance,test_epoch;
static bool test_rtc_ok,test_read_fail,test_fail_after_resume,test_held,test_bad_after_light;
static unsigned test_outputs,test_light_calls,test_deep_calls,test_resumes,test_refreshes,test_panel_resumes;
static uint32_t test_deep_ms;static int32_t test_native_result;
static const risc_driver_v2 *test_provider;
static const alarm_service_v1 *test_client;
static const alarm_service_sleep_v1 *test_sleep_client;
static alarm_service_sleep_v1 test_observed;
static int test_key(const char *key){
    const char *keys[]={ALARM_CONFIG_KEY,ALARM_TIMER_KEY,ALARM_MODE_KEY,ALARM_OCCURRENCE_KEY,ALARM_TIMER_OCCURRENCE_KEY,POINTS_CONFIG_KEY,POINTS_OCCURRENCE_KEY,ALARM_VOLUME_KEY,ALARM_DND_KEY};
    for(unsigned i=0;i<9;i++)if(!strcmp(key,keys[i]))return (int)i;
    assert(0);return -1;
}
static int32_t test_get(void *c,const char *k,void *b,uint32_t cap,uint32_t *n){
    (void)c;assert(!test_held);int i=test_key(k);*n=0;
    if(test_read_fail)return RISC_BOUND_KEY_VALUE_IO;
    if(!test_sizes[i])return RISC_BOUND_KEY_VALUE_NOT_FOUND;
    assert(cap>=test_sizes[i]);memcpy(b,test_blobs[i],test_sizes[i]);*n=test_sizes[i];return 0;
}
static int32_t test_put(void *c,const char *k,const void *b,uint32_t n){
    (void)c;assert(!test_held);int i=test_key(k);assert(n<=64);memcpy(test_blobs[i],b,n);test_sizes[i]=n;return 0;
}
static uint64_t test_mono(void *c){(void)c;return test_ms;}
static bool test_rtc(void *c,twatch_rtc_time_v1 *out){
    (void)c;assert(!test_held);if(!test_rtc_ok)return false;
    int64_t elapsed=(int64_t)test_wall-test_epoch;assert(elapsed>=-1 && elapsed<86400);
    uint32_t seconds=(uint32_t)(elapsed<0?86400+elapsed:elapsed);
    *out=(twatch_rtc_time_v1){2026,10,(uint8_t)(elapsed<0?5:6),(uint8_t)(elapsed<0?1:2),(uint8_t)(seconds/3600),(uint8_t)(seconds/60%60),(uint8_t)(seconds%60)};return true;
}
static bool test_effect(void *c,uint8_t e){(void)c;(void)e;test_outputs++;return true;}
static bool test_yes(void *c){(void)c;return true;}
static bool test_audio_open(void *c,uint32_t r,uint8_t n){(void)c;(void)r;(void)n;test_outputs++;return true;}
static bool test_audio_write(void *c,const int16_t *p,size_t n){(void)c;(void)p;(void)n;test_outputs++;return true;}
static bool test_gain(void *c,uint16_t g,uint16_t m){(void)c;(void)g;(void)m;return true;}
static const risc_bound_key_value_v1 test_store={1,sizeof(test_store),NULL,test_get,test_put};
static const risc_platform_clock_api_v1 test_clock={1,sizeof(test_clock),NULL,test_mono,NULL};
static const twatch_rtc_api_v1 test_calendar={2,sizeof(test_calendar),NULL,test_rtc,NULL,NULL,NULL};
static const twatch_haptic_api_v1 test_haptic={1,sizeof(test_haptic),NULL,test_effect,test_yes};
static const twatch_audio_out_api_v1 test_audio={1,sizeof(test_audio),NULL,test_audio_open,test_audio_write,test_gain,test_yes,test_yes};
static const risc_provider_dependency_v1 test_deps[]={
    {"storage.key-value.bound",1,&test_store},{"platform.clock",1,&test_clock},{"rtc.clock",2,&test_calendar},
    {"haptic.effect",1,&test_haptic},{"audio.output",1,&test_audio}};
static int32_t test_resume(void *c,const alarm_sleep_v1 *ticket){
    assert(!test_held && test_light_calls==1 && !test_deep_calls && !test_refreshes);test_resumes++;
    int32_t rc=test_sleep_client->resume_sleep(c,ticket);
    if(rc==ALARM_OK && test_fail_after_resume)test_read_fail=true;
    return rc;
}
static int32_t test_refresh(void *c){assert(!test_held);test_refreshes++;return test_client->refresh(c);}
static void test_initial(uint32_t deadline_offset){
    if(test_provider)assert(test_provider->quiesce());
    memset(test_blobs,0,sizeof(test_blobs));memset(test_sizes,0,sizeof(test_sizes));
    test_ms=0;assert(alarm_calendar_seconds(2026,10,6,0,0,0,&test_epoch));test_wall=test_epoch;test_rtc_advance=300;test_mono_advance=300000;
    test_rtc_ok=true;test_read_fail=test_fail_after_resume=test_held=test_bad_after_light=false;test_native_result=RISC_LIGHT_SLEEP_OK;
    test_outputs=test_light_calls=test_deep_calls=test_resumes=test_refreshes=test_panel_resumes=test_deep_ms=0;
    points_config empty={.revision=1};points_config_encode(&empty,test_blobs[5]);test_sizes[5]=64;
    if(deadline_offset){alarm_config c={.revision=1,.deadline=test_wall+deadline_offset,.created=test_wall,.kind=1,.enabled=1};alarm_config_encode(&c,test_blobs[0]);test_sizes[0]=32;}
    test_provider=t5_driver_get(2);test_client=test_provider->capability;
    assert(test_client->struct_size>=ALARM_SERVICE_SLEEP_V1_SIZE);
    test_sleep_client=(const alarm_service_sleep_v1 *)test_client;
    assert(test_provider->start(test_deps,5));
    test_observed=*test_sleep_client;test_observed.base.refresh=test_refresh;test_observed.resume_sleep=test_resume;
}
static alarm_status_v1 test_status(void){
    alarm_status_v1 status={.struct_size=sizeof(status)};assert(test_client->status(NULL,&status)==ALARM_OK);return status;
}
static void test_reach(unsigned target){
    for(unsigned i=0;i<100 && test_status().state!=target;i++){(void)test_client->step(NULL);test_ms++;}
    assert(test_status().state==target);
}
static void test_ring(void){
    for(unsigned i=0;i<100 && !test_outputs;i++){(void)test_client->step(NULL);test_ms++;}
    assert(test_outputs && test_status().state==ALARM_STATE_ALERT && !test_status().error);
}
static bool test_panel_prepare(void *c){(void)c;assert(!test_held);return true;}
static int32_t test_panel_deep(void *c){(void)c;assert(!test_held);test_held=true;return 0;}
static bool test_panel_resume(void *c){(void)c;test_held=false;test_panel_resumes++;return true;}
static int32_t test_panel_status(void *c){return test_panel_resume(c)?0:RISC_DEEP_SLEEP_PLATFORM;}
static bool test_keys(void *c,uint32_t *events){(void)c;*events=0;return true;}
static bool test_pending(void *c,bool *pending){(void)c;*pending=false;return true;}
static int32_t test_light(void *c,uint32_t ms,risc_light_sleep_result_v1 *result){
    (void)c;assert(ms && !test_held);test_light_calls++;
    if(test_native_result==RISC_LIGHT_SLEEP_OK){test_ms+=test_mono_advance;test_wall+=test_rtc_advance;if(test_bad_after_light)test_rtc_ok=false;result->wake_cause=RISC_LIGHT_SLEEP_WAKE_TIMER;}
    return test_native_result;
}
static int32_t test_untimed(void *c,risc_light_sleep_result_v1 *r){return test_light(c,1,r);}
static int32_t test_deep(void *c,uint32_t ms){(void)c;assert(test_held);test_deep_calls++;test_deep_ms=ms;return RISC_DEEP_SLEEP_ACTIVE_WAKE;}
static int32_t test_deep_untimed(void *c){return test_deep(c,0);}
static bool test_log(const char *s){(void)s;return true;}
static const twatch_panel_power_v1 test_panel={.base={.api_version=1,.struct_size=sizeof(test_panel)},.prepare_sleep=test_panel_prepare,.resume=test_panel_resume,.prepare_deep_sleep=test_panel_deep,.resume_status=test_panel_status};
static const twatch_pmu_api_v1 test_pmu={.base={.api_version=1,.struct_size=sizeof(test_pmu)},.key_events=test_keys,.prepare_sleep=test_yes,.resume=test_yes,.light_sleep=test_untimed,.deep_sleep=test_deep_untimed,.light_sleep_for=test_light,.sleep_wake_pending=test_pending,.deep_sleep_for=test_deep};
static int test_sleep(unsigned mode){return watch_alarm_sleep_prepared(&test_panel,&test_pmu,mode,&test_observed.base,test_log);}
int main(void){
    (void)watch_sleep_prepared;
    for(unsigned direction=0;direction<2;direction++){
        test_initial(1000);test_reach(ALARM_STATE_READY);
        test_rtc_advance=direction?300:303;test_mono_advance=direction?303000:300000;
        assert(test_sleep(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_REFUSED); /* intentional native Deep refusal */
        assert(test_resumes==1 && test_deep_calls==1 && test_deep_ms==(1000-test_rtc_advance)*1000 && !test_status().error && !test_outputs);
        assert(test_panel_resumes==1 && !test_held);test_reach(ALARM_STATE_READY);
        printf("Hybrid independent clocks %u/%u: Deep attempted, remaining RTC deadline exact, service healthy PASS\n",test_rtc_advance,test_mono_advance/1000);
        test_initial(300);test_reach(ALARM_STATE_READY);
        test_rtc_advance=direction?300:303;test_mono_advance=direction?303000:300000;
        assert(test_sleep(PORTABLE_SLEEP_LIGHT)==WATCH_SLEEP_WOKE);assert(test_resumes==1 && !test_deep_calls);
        test_ring();
        printf("Alarm timed Light independent clocks %u/%u: durable due alarm started without RTC error PASS\n",test_rtc_advance,test_mono_advance/1000);
    }
    test_initial(301);test_reach(ALARM_STATE_READY);test_rtc_advance=303;
    assert(test_sleep(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_WOKE);
    assert(test_resumes==1 && !test_deep_calls);test_ring();
    puts("Hybrid RTC deadline becomes due during Light: alert wins over Deep PASS");
    for(unsigned backward=0;backward<2;backward++){
        test_initial(1000);test_reach(ALARM_STATE_READY);
        if(backward)test_rtc_advance=UINT32_MAX;else test_bad_after_light=true;
        assert(test_sleep(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_REFUSED);
        assert(test_resumes==1 && !test_deep_calls && !test_refreshes && !test_outputs);
        assert(test_status().state==ALARM_STATE_BLOCKED && test_status().error==ALARM_RTC);
        assert(watch_sleep_stage==4 && watch_sleep_detail==ALARM_RTC);
    }
    test_initial(1000);test_reach(ALARM_STATE_READY);test_fail_after_resume=true;
    assert(test_sleep(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_REFUSED);
    assert(test_resumes==1 && !test_deep_calls && !test_refreshes && test_status().state==ALARM_STATE_BLOCKED && test_status().error==ALARM_STORAGE);
    assert(watch_sleep_stage==4 && watch_sleep_detail==ALARM_STORAGE && !test_outputs);
    test_initial(1000);test_reach(ALARM_STATE_READY);test_native_result=RISC_LIGHT_SLEEP_ACTIVE_WAKE;
    assert(test_sleep(PORTABLE_SLEEP_HYBRID)==WATCH_SLEEP_REFUSED);assert(!test_resumes && !test_deep_calls);
    test_ms+=1000;test_wall+=4;test_reach(ALARM_STATE_BLOCKED);assert(test_status().error==ALARM_RTC && !test_outputs);
    assert(test_provider->quiesce());
    puts("Production service + Watch current resume: independent clocks, actual Hybrid Deep decision, due alarm, storage failure, native refusal and awake edit protection PASS");
}

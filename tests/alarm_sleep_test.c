#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "apps/clock/watch_alarm_sleep.h"
static unsigned now=1000,deadline,steps,prepares,refreshes,light_calls,deep_calls,pmu_resumes,panel_resumes,checks;
static uint32_t duration_seen;
static int32_t entry_result=RISC_DEEP_SLEEP_ACTIVE_WAKE;
static bool service_pending,service_due,crown,retained,deep_short,rtc_bad;
static int32_t service_blocked,block_after_light;
static int32_t prepare(void*c,alarm_sleep_v1*s){(void)c;prepares++;if(rtc_bad)return ALARM_RTC;if(service_due)return ALARM_PENDING;
 if(!service_pending){service_pending=true;return ALARM_PENDING;}
 if(steps%3)return ALARM_PENDING;
 *s=(alarm_sleep_v1){sizeof(*s),prepares,now,deadline};service_pending=false;return ALARM_OK;}
static int32_t step(void*c){(void)c;steps++;return ALARM_OK;}
static int32_t status(void*c,alarm_status_v1*s){(void)c;*s=(alarm_status_v1){.api_version=1,.struct_size=sizeof(*s),.state=service_blocked?ALARM_STATE_BLOCKED:service_due?ALARM_STATE_ALERT:ALARM_STATE_LOADING,.error=service_blocked};if(service_due)s->occurrence.generation=1;return ALARM_OK;}
static int32_t refresh(void*c){(void)c;refreshes++;return ALARM_PENDING;}
static bool diagnostic(const char*s){(void)s;return true;}
static bool panel_prepare(void*c){(void)c;return true;}
static int32_t panel_deep(void*c){(void)c;return retained?RISC_DEEP_SLEEP_RETAINED:deep_short?RISC_DEEP_SLEEP_UNSUPPORTED:0;}
static bool fail_resume,retained_resume;
static bool panel_resume(void*c){(void)c;assert(!retained);panel_resumes++;return true;}
static int32_t panel_resume_status(void*c){if(retained_resume)return RISC_DEEP_SLEEP_RETAINED;if(fail_resume)return RISC_LIGHT_SLEEP_PLATFORM;return panel_resume(c)?0:RISC_LIGHT_SLEEP_PLATFORM;}
static bool pmu_prepare(void*c){(void)c;return true;}
static bool pmu_resume(void*c){(void)c;assert(!retained);pmu_resumes++;return true;}
static bool key(void*c,uint32_t*e){(void)c;*e=0;return true;}
static bool pending(void*c,bool*b){(void)c;checks++;*b=crown;return true;}
static int32_t timed_light(void*c,uint32_t ms,risc_light_sleep_result_v1*r){(void)c;assert(!service_pending);light_calls++;duration_seen=ms;
 if(entry_result==RISC_LIGHT_SLEEP_OK){service_blocked=block_after_light;now+=ms/1000;r->wake_cause=crown?RISC_LIGHT_SLEEP_WAKE_GPIO:RISC_LIGHT_SLEEP_WAKE_TIMER;if(deadline&&now>=deadline)service_due=true;}
 return entry_result;}
static int32_t light(void*c,risc_light_sleep_result_v1*r){return timed_light(c,1,r);}
static int32_t deep_timed(void*c,uint32_t ms){(void)c;assert(!service_pending);deep_calls++;duration_seen=ms;return entry_result;}
static int32_t deep(void*c){return deep_timed(c,0);}
static const alarm_service_v1 api={.api_version=1,.struct_size=sizeof(api),.status=status,.step=step,.prepare_sleep=prepare,.refresh=refresh};
static twatch_panel_power_v1 panel={.base={.struct_size=sizeof(panel)},.prepare_sleep=panel_prepare,.resume=panel_resume,.prepare_deep_sleep=panel_deep,.resume_status=panel_resume_status};
static twatch_pmu_api_v1 pmu={.base={.struct_size=sizeof(pmu)},.key_events=key,.prepare_sleep=pmu_prepare,.resume=pmu_resume,.light_sleep=light,.deep_sleep=deep,.light_sleep_for=timed_light,.sleep_wake_pending=pending,.deep_sleep_for=deep_timed};
static void reset(void){now=1000;deadline=1100;steps=prepares=refreshes=light_calls=deep_calls=pmu_resumes=panel_resumes=checks=duration_seen=0;
 service_blocked=block_after_light=0;service_pending=service_due=crown=retained=deep_short=rtc_bad=fail_resume=retained_resume=false;entry_result=RISC_LIGHT_SLEEP_ACTIVE_WAKE;pmu.base.struct_size=sizeof(pmu);}
static bool motion_registered,motion_fail_prepare,motion_fail_resume,motion_event,motion_fail_pending;
static unsigned motion_prepares,motion_resumes,set_calls;
static bool motion_prepare(void*c){(void)c;motion_prepares++;motion_registered=true;return !motion_fail_prepare;}
static bool motion_resume(void*c){(void)c;motion_resumes++;if(motion_fail_resume)return false;motion_registered=false;return true;}
static bool motion_pending(void*c,bool*out){(void)c;assert(motion_registered);*out=motion_event;return !motion_fail_pending;}
static twatch_motion_api_v1 motion={.api_version=1,.struct_size=sizeof(motion),.prepare_wake=motion_prepare,.resume_wake=motion_resume,.wake_pending=motion_pending};
static int32_t light_set(void*c,uint32_t ms,risc_light_sleep_result_v1*r){assert(motion_registered);set_calls++;return timed_light(c,ms,r);}
static int32_t deep_set(void*c,uint32_t ms){assert(motion_registered);set_calls++;return deep_timed(c,ms);}
static void motion_reset(void){reset();motion_registered=motion_fail_prepare=motion_fail_resume=motion_event=motion_fail_pending=false;motion_prepares=motion_resumes=set_calls=0;pmu.light_sleep_set=light_set;pmu.deep_sleep_set=deep_set;motion.struct_size=sizeof(motion);}
static void test_motion(void){
 for(unsigned mode=0;mode<3;mode++)for(int rc=RISC_DEEP_SLEEP_RETAINED;rc<0;rc++){
  motion_reset();entry_result=rc;int got=watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,mode,&api,diagnostic);
  assert(set_calls==1&&motion_prepares==1);
  if(rc==RISC_DEEP_SLEEP_RETAINED)assert(got==WATCH_SLEEP_RETAINED&&motion_registered&&!motion_resumes&&!pmu_resumes&&!panel_resumes);
  else assert(got==WATCH_SLEEP_REFUSED&&!motion_registered&&motion_resumes==1&&pmu_resumes==1&&panel_resumes==1);
 }
 motion_reset();motion_fail_prepare=true;assert(watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,0,&api,diagnostic)==0);assert(!set_calls&&!motion_registered&&motion_resumes==1);
 motion_reset();motion_fail_resume=true;assert(watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,0,&api,diagnostic)==WATCH_SLEEP_RETAINED);assert(motion_registered&&!pmu_resumes&&!panel_resumes&&!refreshes);
 motion_reset();motion.struct_size=TWATCH_MOTION_SAMPLE_SIZE;assert(watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,0,&api,diagnostic)==0);assert(!motion_prepares&&!set_calls);
 motion_reset();entry_result=0;deadline=2000;motion_event=true;assert(watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,PORTABLE_SLEEP_HYBRID,&api,diagnostic)==1);assert(set_calls==1&&!deep_calls&&!motion_registered);
 motion_reset();entry_result=0;deadline=2000;motion_fail_pending=true;assert(watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,PORTABLE_SLEEP_HYBRID,&api,diagnostic)==0);assert(set_calls==1&&!deep_calls&&!motion_registered);
 motion_reset();motion_event=true;assert(watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,PORTABLE_SLEEP_DEEP,&api,diagnostic)==0);assert(!set_calls&&!deep_calls&&!motion_registered);
 motion_reset();entry_result=0;deadline=2000;assert(watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,PORTABLE_SLEEP_HYBRID,&api,diagnostic)==WATCH_SLEEP_RETAINED);assert(set_calls==2&&duration_seen==700000&&motion_registered&&!motion_resumes);
 motion_reset();entry_result=0;assert(watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,PORTABLE_SLEEP_LIGHT,&api,diagnostic)==1);assert(service_due&&!motion_registered&&refreshes==1);
 for(unsigned mode=0;mode<3;mode++){motion_reset();entry_result=-4;assert(watch_sleep_motion_prepared(&panel,&pmu,&motion,mode,diagnostic)==0);assert(set_calls==1&&!motion_registered);}
 puts("Motion sleep adapters: Light/Deep/Hybrid groups, exact alarm deadline, crown/sensor boundary precedence, partial prepare, cleanup retention and short API PASS");
}
int main(void){(void)watch_sleep_prepared;
 for(unsigned mode=0;mode<3;mode++)for(int rc=RISC_DEEP_SLEEP_RETAINED;rc<0;rc++){
  reset();entry_result=rc;int got=watch_alarm_sleep_prepared(&panel,&pmu,mode,&api,diagnostic);
  assert(mode==PORTABLE_SLEEP_DEEP?deep_calls==1:light_calls==1);assert(duration_seen==100000);
  assert(got==(rc==RISC_DEEP_SLEEP_RETAINED?WATCH_SLEEP_RETAINED:WATCH_SLEEP_REFUSED));
  assert(rc==RISC_DEEP_SLEEP_RETAINED?!pmu_resumes&&!panel_resumes:pmu_resumes==1&&panel_resumes==1&&refreshes==1);
 }
 reset();entry_result=0;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_LIGHT,&api,diagnostic)==WATCH_SLEEP_WOKE);assert(service_due&&refreshes==1&&!deep_calls);
 reset();entry_result=0;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_HYBRID,&api,diagnostic)==WATCH_SLEEP_WOKE);assert(service_due&&!deep_calls);
 reset();deadline=2000;entry_result=0;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_HYBRID,&api,diagnostic)==WATCH_SLEEP_RETAINED);assert(light_calls==1&&deep_calls==1&&duration_seen==700000&&prepares>=6&&!refreshes);
 reset();deadline=2000;crown=true;entry_result=0;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_HYBRID,&api,diagnostic)==WATCH_SLEEP_WOKE);assert(!deep_calls&&refreshes==1);
 reset();deadline=200000;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_DEEP,&api,diagnostic)==WATCH_SLEEP_REFUSED);assert(duration_seen==RISC_TIMED_SLEEP_MAX_MS);
 reset();deadline=0;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_DEEP,&api,diagnostic)==WATCH_SLEEP_REFUSED);assert(deep_calls==1&&!duration_seen);
 reset();pmu.base.struct_size=TWATCH_PMU_TIMED_SLEEP_SIZE;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_DEEP,&api,diagnostic)==WATCH_SLEEP_REFUSED);assert(!deep_calls&&refreshes==1);
 reset();rtc_bad=true;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_DEEP,&api,diagnostic)==WATCH_SLEEP_REFUSED);assert(!deep_calls&&!refreshes);
 reset();service_due=true;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_DEEP,&api,diagnostic)==WATCH_SLEEP_REFUSED);assert(!deep_calls&&refreshes==1);
 reset();retained=true;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_DEEP,&api,diagnostic)==WATCH_SLEEP_RETAINED);assert(steps&&!deep_calls&&!pmu_resumes&&!panel_resumes);
 reset();retained_resume=true;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_DEEP,&api,diagnostic)==WATCH_SLEEP_RETAINED);assert(!refreshes);
 reset();fail_resume=true;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_DEEP,&api,diagnostic)==WATCH_SLEEP_FAILED);assert(!refreshes);
 reset();panel.base.struct_size=TWATCH_PANEL_DEEP_SLEEP_SIZE;assert(watch_alarm_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_DEEP,&api,diagnostic)==WATCH_SLEEP_REFUSED);assert(!deep_calls);panel.base.struct_size=sizeof(panel);
 for(int error=ALARM_STORAGE;error>=ALARM_RTC;error--){
  reset();service_blocked=error;alarm_sleep_v1 decision={.struct_size=sizeof(decision)};
  assert(watch_alarm_deadline(&api,&decision)==error);
  motion_reset();entry_result=RISC_LIGHT_SLEEP_OK;deadline=2000;block_after_light=error;
  assert(watch_alarm_sleep_motion_prepared(&panel,&pmu,&motion,PORTABLE_SLEEP_HYBRID,&api,diagnostic)==WATCH_SLEEP_REFUSED);
  assert(light_calls==1 && !deep_calls && pmu_resumes==1 && panel_resumes==1 && !refreshes);
  assert(watch_sleep_stage==4 && watch_sleep_detail==error && !motion_registered);
 }
 test_motion();
 puts("Alarm owned sleep: fresh RTC decisions, Light due, hybrid fresh Deep, crown, invalid/blocked/refusal/retained/short suffix passed");
 return 0;
}

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
#include "apps/clock/watch_sleep.h"
static unsigned scenario,light_calls,timed_calls,deep_calls,panel_prepares,deep_prepares,pmu_prepares,resumes,observations,diagnostics;
static uint32_t elapsed;
static bool terminal;
static bool log_message(const char*s){assert(s);diagnostics++;return true;}
static bool panel_prepare(void*c){(void)c;panel_prepares++;return scenario!=1;}
static bool pmu_prepare(void*c){(void)c;assert(panel_prepares||deep_prepares);pmu_prepares++;return scenario!=2;}
static int32_t panel_deep(void*c){(void)c;deep_prepares++;return scenario==10?RISC_DEEP_SLEEP_RETAINED:scenario==11?RISC_DEEP_SLEEP_PLATFORM:0;}
static bool resume(void*c){(void)c;resumes++;return scenario!=12;}
static bool keys(void*c,uint32_t*out){(void)c;*out=0;return true;}
static bool pending(void*c,bool*out){(void)c;assert(timed_calls);observations++;*out=scenario==5 || (scenario==6&&observations==2);return scenario!=7;}
static int32_t light(void*c,risc_light_sleep_result_v1*r){(void)c;light_calls++;r->wake_cause=RISC_LIGHT_SLEEP_WAKE_GPIO;return 0;}
static int32_t timed(void*c,uint32_t ms,risc_light_sleep_result_v1*r){(void)c;assert(ms==300000);timed_calls++;elapsed=ms;
 r->wake_cause=scenario==3?RISC_LIGHT_SLEEP_WAKE_GPIO:scenario==4?RISC_LIGHT_SLEEP_WAKE_OTHER:RISC_LIGHT_SLEEP_WAKE_TIMER;
 if(scenario==3)elapsed=ms-1;
 return scenario==8?RISC_LIGHT_SLEEP_RETAINED:scenario==9?RISC_LIGHT_SLEEP_PLATFORM:0;
}
static int32_t deep(void*c){(void)c;assert(!resumes);deep_calls++;
 if(terminal){assert(elapsed==300000&&timed_calls==1&&observations==2&&deep_prepares==1);_exit(77);}
 return scenario==13?0:scenario==14?RISC_DEEP_SLEEP_RETAINED:RISC_DEEP_SLEEP_ACTIVE_WAKE;
}
static twatch_panel_power_v1 panel={{.api_version=1,.struct_size=sizeof(panel)},panel_prepare,resume,panel_deep,NULL};
static twatch_pmu_api_v1 pmu={{1,sizeof(pmu),NULL,NULL},keys,pmu_prepare,resume,light,deep,timed,pending,NULL};
static void reset(unsigned n){scenario=n;light_calls=timed_calls=deep_calls=panel_prepares=deep_prepares=pmu_prepares=resumes=observations=diagnostics=elapsed=0;terminal=false;panel.base.struct_size=sizeof(panel);pmu.base.struct_size=sizeof(pmu);}
int main(void){
 for(unsigned n=0;n<15;n++) {
  reset(n);int status=watch_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_HYBRID,log_message);
  if(n==8||n==10||n==13||n==14){assert(status==WATCH_SLEEP_RETAINED&&!resumes);continue;}
  assert(resumes==2);
  if(n==12){assert(status==WATCH_SLEEP_FAILED);continue;}
  if(n==3||n==4||n==5||n==6){assert(status==WATCH_SLEEP_WOKE&&!deep_calls);}
  else assert(status==WATCH_SLEEP_REFUSED);
  if(n==3||n==4)assert(!deep_prepares&&!observations);
  if(n==5)assert(!deep_prepares&&observations==1);
  if(n==6)assert(deep_prepares==1&&observations==2);
  if(n==1||n==2)assert(!timed_calls&&!deep_calls);
 }
 reset(0);pmu.base.struct_size=TWATCH_PMU_DEEP_SLEEP_SIZE;
 assert(watch_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_HYBRID,log_message)==0&&!timed_calls&&!light_calls&&resumes==2);
 reset(0);pmu.base.struct_size=TWATCH_PMU_TIMED_SLEEP_SIZE-1;
 assert(watch_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_HYBRID,log_message)==0&&!timed_calls&&resumes==2);
 reset(0);assert(watch_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_LIGHT,log_message)==1&&light_calls==1&&!timed_calls&&!deep_calls);
 reset(0);assert(watch_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_DEEP,log_message)==0&&deep_calls==1&&!timed_calls&&!panel_prepares);
 for(unsigned boot=0;boot<3;boot++) {
  pid_t p=fork();assert(p>=0);if(!p){reset(0);terminal=true;(void)watch_sleep_prepared(&panel,&pmu,PORTABLE_SLEEP_HYBRID,log_message);_exit(99);}
  int status;assert(waitpid(p,&status,0)==p&&WIFEXITED(status)&&WEXITSTATUS(status)==77);
 }
 puts("Hybrid policy: exact timer, early/user/other wake, both crown boundary samples, preparation/refusal/retention, old ABI, manual modes and terminal fresh boots PASS");
}

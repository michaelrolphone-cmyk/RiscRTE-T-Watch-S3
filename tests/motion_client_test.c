#define main alarm_adapter_fixture_main
#include "alarm_sleep_test.c"
#undef main
#include "apps/clock/watch_motion_client.h"
static unsigned acquired, released;
static bool acquire_ok,release_ok;
static bool acquire_motion(const char* capability,uint32_t version,uint64_t instance,risc_runtime_capability_v1* grant){
 assert(!strcmp(capability,"motion.accel")&&version==1&&instance==7);acquired++;
 if(!acquire_ok)return false;
 grant->api=&motion;return true;
}
static bool release_motion(risc_runtime_capability_v1* grant){assert(grant->api==&motion);released++;return release_ok;}
static const risc_runtime_api_v1 rt={.api_version=1,.struct_size=sizeof(rt),.diagnostic=diagnostic,.acquire=acquire_motion,.release=release_motion};
static void client_reset(void){motion_reset();acquired=released=0;acquire_ok=release_ok=true;}
int main(void){
 for(unsigned mode=0;mode<3;mode++)for(int result=RISC_DEEP_SLEEP_UNSUPPORTED;result<=0;result++){
  client_reset();entry_result=result;
  int got=watch_motion_sleep(&rt,&panel,&pmu,mode,&api);
  assert(acquired==1);
  if(result==RISC_DEEP_SLEEP_RETAINED || (result==0 && mode==PORTABLE_SLEEP_DEEP))assert(got==WATCH_SLEEP_RETAINED&&!released&&motion_registered);
  else assert(released==1&&!motion_registered);
 }
 client_reset();acquire_ok=false;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&!released&&!motion_prepares);
 client_reset();motion.struct_size=TWATCH_MOTION_SAMPLE_SIZE;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&released==1&&!motion_prepares);
 client_reset();pmu.base.struct_size=TWATCH_PMU_TIMED_DEEP_SLEEP_SIZE;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&released==1&&!motion_prepares);
 client_reset();release_ok=false;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_RETAINED&&released==1&&!motion_registered);
 client_reset();motion_fail_resume=true;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_RETAINED&&!released&&motion_registered);
 puts("Motion grant-client acquire/refusal/release/retention and all entry return-code checks PASS");
}

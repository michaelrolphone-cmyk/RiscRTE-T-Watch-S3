#define main alarm_adapter_fixture_main
#include "alarm_sleep_test.c"
#undef main
#include "apps/clock/watch_motion_client.h"
static unsigned acquired,released,storage_acquired,storage_released,configured;
static bool acquire_ok,release_ok,storage_ok,storage_release_ok,info_ok,configure_ok;
static uint16_t profile,configured_value;
static int storage_status;
static uint8_t record[8];
static int32_t read_preference(void*c,const char*key,void*data,uint32_t capacity,uint32_t*length){
 (void)c;assert(!strcmp(key,PORTABLE_TAP_KEY)&&capacity==8);*length=0;
 if(storage_status==RISC_KEY_VALUE_OK){memcpy(data,record,8);*length=8;}return storage_status;
}
static int32_t put_preference(void*c,const char*k,const void*p,uint32_t n){(void)c;(void)k;(void)p;(void)n;assert(!"Sleep never writes settings");return -1;}
static const risc_key_value_v1 store={1,sizeof(store),NULL,read_preference,put_preference};
static bool info(void*c,twatch_tap_info_v1*out){(void)c;*out=(twatch_tap_info_v1){sizeof(*out),profile,0,profile==1?7:15,profile==1?3:12};return info_ok;}
static bool configure(void*c,uint16_t value){(void)c;configured++;configured_value=value;return configure_ok;}
static bool begin_observe(void*c,uint16_t value){(void)c;(void)value;assert(!"Sleep never calibrates");return false;}
static bool observe(void*c,twatch_tap_observation_v1*out){(void)c;(void)out;assert(!"Sleep never acknowledges motion");return false;}
static bool acquire_motion(const char* capability,uint32_t version,uint64_t instance,risc_runtime_capability_v1* grant){
 assert(version==1);
 if(!strcmp(capability,RISC_KEY_VALUE_CAPABILITY)){assert(instance==1);storage_acquired++;if(!storage_ok)return false;grant->api=&store;return true;}
 assert(!strcmp(capability,"motion.accel")&&instance==7);acquired++;
 if(!acquire_ok)return false;
 grant->api=&motion;return true;
}
static bool release_motion(risc_runtime_capability_v1* grant){
 if(grant->api==&store){storage_released++;return storage_release_ok;}
 assert(grant->api==&motion);released++;return release_ok;
}
static const risc_runtime_api_v1 rt={.api_version=1,.struct_size=sizeof(rt),.diagnostic=diagnostic,.acquire=acquire_motion,.release=release_motion};
static void client_reset(void){
 motion_reset();acquired=released=storage_acquired=storage_released=configured=0;
 acquire_ok=release_ok=storage_ok=storage_release_ok=info_ok=configure_ok=true;storage_status=RISC_KEY_VALUE_NOT_FOUND;profile=1;
 motion.tap_info=info;motion.tap_configure=configure;motion.tap_observe_begin=begin_observe;motion.tap_observe=observe;
}
static void stored(bool enabled,unsigned bma423,unsigned bma456h){
 const uint8_t value[]={0x57,1,enabled,(uint8_t)bma423,(uint8_t)bma456h,3,0,0};memcpy(record,value,8);
 uint16_t checksum=portable_tap_checksum(record);record[6]=(uint8_t)checksum;record[7]=(uint8_t)(checksum>>8);storage_status=RISC_KEY_VALUE_OK;
}
int main(void){
 for(unsigned mode=0;mode<3;mode++)for(int result=RISC_DEEP_SLEEP_UNSUPPORTED;result<=0;result++){
  client_reset();entry_result=result;
  int got=watch_motion_sleep(&rt,&panel,&pmu,mode,&api);
  assert(acquired==1 && storage_acquired==1 && storage_released==1 && configured==1 && configured_value==3);
  if(result==RISC_DEEP_SLEEP_RETAINED || (result==0 && mode==PORTABLE_SLEEP_DEEP))assert(got==WATCH_SLEEP_RETAINED&&!released&&motion_registered);
  else assert(released==1&&!motion_registered);
 }
 for(unsigned variant=1;variant<=2;variant++){
  client_reset();profile=variant;stored(true,6,14);assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED);
  assert(configured_value==(variant==1?6:14));
 }
 for(unsigned mode=0;mode<3;mode++){
  client_reset();stored(false,6,14);entry_result=RISC_LIGHT_SLEEP_OK;crown=mode!=PORTABLE_SLEEP_DEEP;
  int got=watch_motion_sleep(&rt,&panel,&pmu,mode,&api);
  assert(got==(mode==PORTABLE_SLEEP_DEEP?WATCH_SLEEP_RETAINED:WATCH_SLEEP_WOKE));
  assert(!acquired&&!released&&!configured&&!motion_prepares&&!set_calls && (mode==PORTABLE_SLEEP_DEEP?deep_calls:light_calls));
 }
 client_reset();storage_ok=false;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&!acquired);
 client_reset();storage_release_ok=false;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_RETAINED&&!acquired);
 client_reset();storage_status=RISC_KEY_VALUE_IO;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&!acquired&&light_calls==1);
 client_reset();stored(true,3,12);record[7]^=1;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&!acquired&&light_calls==1);
 client_reset();acquire_ok=false;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&!released&&!motion_prepares);
 client_reset();motion.struct_size=TWATCH_MOTION_SAMPLE_SIZE;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&released==1&&!motion_prepares);
 client_reset();motion.struct_size=TWATCH_MOTION_DIAGNOSTIC_SIZE;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&released==1&&!motion_prepares);
 client_reset();pmu.base.struct_size=TWATCH_PMU_TIMED_DEEP_SLEEP_SIZE;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&released==1&&!motion_prepares);
 client_reset();info_ok=false;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&released==1&&!motion_prepares);
 client_reset();profile=3;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&released==1&&!motion_prepares);
 client_reset();configure_ok=false;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_REFUSED&&released==1&&!motion_prepares);
 client_reset();release_ok=false;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_RETAINED&&released==1&&!motion_registered);
 client_reset();motion_fail_resume=true;assert(watch_motion_sleep(&rt,&panel,&pmu,0,&api)==WATCH_SLEEP_RETAINED&&!released&&motion_registered);
 puts("Motion persistent Off/On, both profile values, crown/alarm sleep, corruption, cleanup and retained-client checks PASS");
}

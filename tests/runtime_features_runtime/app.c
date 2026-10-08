#include <assert.h>
#include <RiscDeepSleepV1.h>
#include "../../apps/runtime_features/clock_runtime.h"
extern int test_wake_mode(void);
extern unsigned test_wake_cause(void);
extern unsigned test_time_seeds(void);
extern void test_wake_refused(void);
static unsigned rtc_reads;
static bool rtc_read(void*c,twatch_rtc_time_v1*out){
 (void)c;++rtc_reads;*out=(twatch_rtc_time_v1){.year=2026,.month=10,.day=8,.weekday=4,.hour=6,.minute=31,.second=12};return true;
}
__attribute__((visibility("default"))) void app_main(void){
 const risc_runtime_api_v1*rt=risc_runtime_get_api(1);assert(rt);int mode=test_wake_mode();
 watch_clock_runtime c;assert(watch_runtime_open(&c,rt,true));
 assert(c.cause==test_wake_cause() && c.resume==(mode==1||mode==9));
 const twatch_rtc_api_v1 rtc={.read=rtc_read};
 if(mode==7){assert(!watch_runtime_seed(&c,&rtc));assert(watch_runtime_close(&c));return;}
 assert(watch_runtime_seed(&c,&rtc));assert(rtc_reads==(c.cause<RISC_BOOT_DEEP_TIMER||mode==9));
 assert(test_time_seeds()==rtc_reads);
 twatch_rtc_time_v1 date;uint16_t fraction=0;
 assert(watch_runtime_read(&c,&date,&fraction));assert(date.year==2026&&date.month==10&&date.day==8&&date.hour==(c.cause>=RISC_BOOT_DEEP_TIMER&&mode!=9?7:6)&&date.minute==31&&date.second==12);
 int promoted=watch_runtime_promote(&c);
 if(mode==8){assert(promoted==RISC_PROVIDER_PROMOTION_FAILED);assert(watch_runtime_close(&c));return;}
 assert(promoted==RISC_PROVIDER_PROMOTION_OK);
 assert(watch_runtime_promote(&c)==RISC_PROVIDER_PROMOTION_ALREADY_READY);
 assert(watch_runtime_stage(&c));
 if(mode==2||mode==3||mode==4){
  risc_runtime_capability_v1 other={.struct_size=sizeof(other)};
  assert(rt->acquire("test.deep",1,7,&other));
  const struct {uint32_t version,size;int32_t(*enter)(void);}*deep=other.api;
  int result=deep->enter();assert(mode!=2);
  assert(result==(mode==3?RISC_DEEP_SLEEP_ACTIVE_WAKE:RISC_DEEP_SLEEP_RETAINED));
  if(mode==4)return; /* Native terminal return pins the actual invocation. */
  test_wake_refused();assert(rt->release(&other));
 }
 assert(watch_runtime_abandon(&c));assert(watch_runtime_close(&c));
}

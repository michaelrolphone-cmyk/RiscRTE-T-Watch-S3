#include <assert.h>
#include <stdio.h>
#include "../apps/runtime_features/clock_runtime.h"
static risc_realtime_snapshot_v1 sample;
static risc_retained_wake_record_v1 checkpoint;
static unsigned cause,reads,seeds,stages,clears,releases,promotes;
static int read_status,wake_status,promote_status,stage_status;
static bool release_ok=true;
static int32_t read_time(void*c,risc_realtime_snapshot_v1*out){(void)c;reads++;if(read_status)return read_status;*out=sample;return 0;}
static int32_t seed_time(void*c,int64_t epoch,uint32_t ns){(void)c;seeds++;assert(ns==0);sample.epoch_seconds=epoch;sample.validity=1;return 0;}
static int32_t read_wake(void*c,uint32_t type,uint32_t schema,risc_retained_wake_record_v1*out,uint32_t*boot){
 (void)c;assert(type==WATCH_CLOCK_CHECKPOINT_TYPE&&schema==1);*boot=cause;if(!wake_status)*out=checkpoint;return wake_status;}
static int32_t stage_wake(void*c,const risc_retained_wake_record_v1*r){(void)c;stages++;checkpoint=*r;return stage_status;}
static int32_t clear_wake(void*c){(void)c;clears++;return 0;}
static int32_t promote(void*c){(void)c;promotes++;return promote_status;}
static const risc_realtime_control_api_v1 realtime={1,sizeof(realtime),NULL,read_time,seed_time};
static const risc_retained_wake_api_v1 wake={1,sizeof(wake),NULL,read_wake,stage_wake,clear_wake};
static const risc_provider_promotion_api_v1 promotion={1,sizeof(promotion),NULL,promote};
static bool acquire(const char*n,uint32_t api,uint64_t instance,risc_runtime_capability_v1*g){
 assert(api==1&&!instance);g->slot=1;g->generation=1;
 g->api=!strcmp(n,RISC_REALTIME_CONTROL_CAPABILITY)?(const void*)&realtime:
        !strcmp(n,RISC_RETAINED_WAKE_CAPABILITY)?(const void*)&wake:(const void*)&promotion;return true;}
static bool release(risc_runtime_capability_v1*g){releases++;if(!release_ok)return false;*g=(risc_runtime_capability_v1){.struct_size=sizeof(*g)};return true;}
static const risc_runtime_api_v1 rt={.acquire=acquire,.release=release};
static twatch_rtc_time_v1 rtc_date={.year=2026,.month=10,.day=8,.weekday=4,.hour=6,.minute=31,.second=12};
static unsigned rtc_reads;
static bool rtc_read(void*c,twatch_rtc_time_v1*out){(void)c;rtc_reads++;*out=rtc_date;return true;}
static const twatch_rtc_api_v1 rtc={.read=rtc_read};
static void reset(void){sample=(risc_realtime_snapshot_v1){.struct_size=sizeof(sample)};reads=seeds=stages=clears=releases=promotes=rtc_reads=0;cause=0;read_status=promote_status=stage_status=0;wake_status=1;release_ok=true;}
int main(void){
 watch_clock_runtime c;reset();assert(watch_runtime_open(&c,&rt,true));assert(!c.resume);
 assert(watch_runtime_seed(&c,&rtc)&&seeds==1&&rtc_reads==1);assert(sample.epoch_seconds==1791412272);
 twatch_rtc_time_v1 date;uint16_t fraction=0;sample.nanoseconds=234000000;
 assert(watch_runtime_read(&c,&date,&fraction)&&fraction==234);assert(!memcmp(&date,&rtc_date,sizeof(date)));
 assert(watch_runtime_stage(&c)&&stages==1&&checkpoint.size==1&&checkpoint.payload[0]==1);
 assert(watch_runtime_abandon(&c)&&clears==1);assert(watch_runtime_promote(&c)==0&&promotes==1);
 assert(watch_runtime_close(&c)&&releases==3);
 // Every admitted date/hour maps to precisely the old RTC civil basis and
 // Denver presentation; no changed DST policy or timezone preference is added.
 unsigned cases=0;
 for(unsigned y=2000;y<=2038;y++)for(unsigned m=1;m<=12;m++)for(unsigned d=1;d<=watch_month_days(y,m);d++)for(unsigned h=0;h<24;h++){
  twatch_rtc_time_v1 raw={.year=y,.month=m,.day=d,.weekday=watch_weekday(y,m,d),.hour=h,.minute=37,.second=22},recovered,old_ui,new_ui;int64_t epoch;
  if(!watch_runtime_epoch(&raw,&epoch))continue;
  assert(watch_runtime_calendar(epoch,&recovered));assert(!memcmp(&raw,&recovered,sizeof(raw)));
  bool old_valid=watch_display_time(&raw,&old_ui);assert(old_valid==watch_display_time(&recovered,&new_ui));if(old_valid)assert(!memcmp(&old_ui,&new_ui,sizeof(old_ui)));cases++;
 }
 for(unsigned reason=0;reason<=4;reason++){
  reset();cause=reason;wake_status=0;sample.validity=1;sample.epoch_seconds=1791412272;
  assert(watch_runtime_open(&c,&rt,true));assert(c.resume==(reason>=2));
  assert(watch_runtime_seed(&c,&rtc));assert(rtc_reads==(reason<2));assert(seeds==(reason<2));assert(watch_runtime_close(&c));
 }
 reset();cause=RISC_BOOT_DEEP_TIMER;wake_status=0;checkpoint.payload[0]=0;
 assert(watch_runtime_open(&c,&rt,true)&&!c.resume);assert(watch_runtime_seed(&c,&rtc)&&seeds==1);assert(watch_runtime_close(&c));
 reset();cause=RISC_BOOT_DEEP_GPIO;wake_status=RISC_RETAINED_WAKE_MISMATCH;
 assert(watch_runtime_open(&c,&rt,true)&&!c.resume);assert(watch_runtime_close(&c));
 reset();assert(watch_runtime_open(&c,&rt,false)&&!c.wake);assert(watch_runtime_stage(&c)&&!stages);assert(watch_runtime_close(&c));
 reset();assert(watch_runtime_open(&c,&rt,true));promote_status=RISC_PROVIDER_PROMOTION_FAILED;
 assert(watch_runtime_promote(&c)==RISC_PROVIDER_PROMOTION_FAILED&&releases==1);assert(watch_runtime_close(&c));
 reset();assert(watch_runtime_open(&c,&rt,true));promote_status=RISC_PROVIDER_PROMOTION_RETAINED;
 assert(watch_runtime_promote(&c)==RISC_PROVIDER_PROMOTION_RETAINED&&c.halted&&!releases);
 assert(!watch_runtime_close(&c)&&!watch_runtime_stage(&c)&&!watch_runtime_abandon(&c)&&!releases);
 reset();assert(watch_runtime_open(&c,&rt,true));read_status=RISC_REALTIME_IO;memset(&date,0xa5,sizeof(date));twatch_rtc_time_v1 before=date;
 assert(!watch_runtime_read(&c,&date,&fraction)&&!memcmp(&date,&before,sizeof(date)));assert(watch_runtime_close(&c));
 reset();assert(watch_runtime_open(&c,&rt,true));read_status=RISC_REALTIME_CONTEXT;
 assert(!watch_runtime_read(&c,&date,&fraction)&&c.halted);assert(!watch_runtime_close(&c)&&!releases);
 reset();assert(watch_runtime_open(&c,&rt,true));sample.validity=1;sample.epoch_seconds=1791412272;sample.nanoseconds=1000000000;
 assert(!watch_runtime_read(&c,&date,&fraction));assert(watch_runtime_close(&c));
 reset();assert(watch_runtime_open(&c,&rt,true));release_ok=false;assert(!watch_runtime_close(&c)&&c.halted&&releases==1);
 reset();assert(watch_runtime_open(&c,&rt,true));rtc_date.year=2099;rtc_date.weekday=watch_weekday(2099,rtc_date.month,rtc_date.day);
 assert(watch_runtime_seed(&c,&rtc)&&c.fallback==&rtc&&!seeds);
 assert(watch_runtime_read(&c,&date,&fraction)&&date.year==2099&&!fraction);assert(watch_runtime_close(&c));
 printf("Watch Runtime client: %u RTC/Denver parity cases; cold/reset/deep, unset recovery, refusal/error/retained custody passed\n",cases);
}

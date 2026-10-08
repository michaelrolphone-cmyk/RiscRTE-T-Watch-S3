#pragma once
/* Watch-owned policy over public Runtime mechanisms. No hardware identities,
 * pointers, grant tokens, or boot-local counters enter the checkpoint. */
#include "RiscRuntimeV1.h"
#include "sdk/RiscRetainedWakeV1.h"
#include "sdk/RiscRealtimeV1.h"
#include "sdk/RiscProviderPromotionV1.h"
#include "../clock/display_time.h"
#include <string.h>
#define WATCH_CLOCK_CHECKPOINT_TYPE 0x57434c4bu
#define WATCH_CLOCK_CHECKPOINT_SCHEMA 1u

typedef struct {
 const risc_runtime_api_v1 *runtime;
 risc_runtime_capability_v1 time_grant,wake_grant;
 const risc_realtime_control_api_v1 *time;
 const risc_retained_wake_api_v1 *wake;
 const twatch_rtc_api_v1 *fallback;
 bool time_live,wake_live,halted,resume;
 uint32_t cause;
} watch_clock_runtime;

/* Canonical append-only Runtime 0.1.54 invocation fence; frozen Watch SDK
 * retains its public prefix, so read only after proving this suffix exists. */
static inline void watch_runtime_retain(const risc_runtime_api_v1 *rt) {
 bool (*retain)(void)=NULL;
 size_t offset=RISC_RUNTIME_CAPABILITIES_V1_SIZE+sizeof(bool (*)(void));
 if(rt && rt->struct_size>=offset+sizeof(retain)) {
  memcpy(&retain,(const unsigned char*)rt+offset,sizeof(retain));
  if(retain)(void)retain();
 }
}
static inline void watch_runtime_halt(watch_clock_runtime *c) {
 c->halted=true;watch_runtime_retain(c->runtime);
}

static bool watch_runtime_close(watch_clock_runtime *c) {
 if(c->halted)return false;
 if(c->wake_live) {
  if(!c->runtime->release(&c->wake_grant)){watch_runtime_halt(c);return false;}
  c->wake_live=false;c->wake=NULL;
 }
 if(c->time_live) {
  if(!c->runtime->release(&c->time_grant)){watch_runtime_halt(c);return false;}
  c->time_live=false;c->time=NULL;
 }
 return true;
}
static bool watch_runtime_snapshot(watch_clock_runtime *c,risc_realtime_snapshot_v1 *out) {
 if(c->halted || !c->time)return false;
 risc_realtime_snapshot_v1 sample={.struct_size=sizeof(sample)};
 int rc=c->time->read(c->time->context,&sample);
 if(rc==RISC_REALTIME_CONTEXT){watch_runtime_halt(c);return false;}
 if(rc!=RISC_REALTIME_OK || sample.struct_size!=sizeof(sample) || sample.reserved ||
    sample.nanoseconds>=1000000000u || sample.nanoseconds%1000u ||
    sample.monotonic_before_us>sample.monotonic_after_us ||
    sample.validity>RISC_REALTIME_VALID || sample.epoch_seconds<0 || sample.epoch_seconds>INT32_MAX ||
    (!sample.validity && (sample.epoch_seconds || sample.nanoseconds)))return false;
 *out=sample;return true;
}
/* Existing Watch RTC ownership is explicitly fixed UTC+08. The UTC native
 * clock never receives Denver local wall time, compiler time, or an estimate. */
static bool watch_runtime_epoch(const twatch_rtc_time_v1 *date,int64_t *out) {
 if(!tw_valid_time(date))return false;
 int64_t days=10957; /* 2000-01-01 minus Unix epoch. */
 for(unsigned y=2000;y<date->year;y++)days+=365u+(y%4==0);
 for(unsigned m=1;m<date->month;m++)days+=watch_month_days(date->year,m);
 int64_t epoch=(days+date->day-1)*86400+(int64_t)date->hour*3600+
               (int64_t)date->minute*60+date->second-8*3600;
 if(epoch<0 || epoch>INT32_MAX)return false;
 *out=epoch;return true;
}
static bool watch_runtime_calendar(int64_t epoch,twatch_rtc_time_v1 *out) {
 if(epoch<946656000 || epoch>INT32_MAX)return false;
 uint32_t local=(uint32_t)(epoch+8*3600),days=local/86400;
 uint32_t remaining=days-10957,seconds=local%86400;
 unsigned year=2000,month=1;
 while(remaining>=365u+(year%4==0)){remaining-=365u+(year%4==0);++year;}
 while(remaining>=watch_month_days(year,month)){remaining-=watch_month_days(year,month);++month;}
 *out=(twatch_rtc_time_v1){.year=(uint16_t)year,.month=(uint8_t)month,.day=(uint8_t)(remaining+1),
  .weekday=(uint8_t)((days+4)%7),.hour=(uint8_t)(seconds/3600),
  .minute=(uint8_t)(seconds/60%60),.second=(uint8_t)(seconds%60)};
 return tw_valid_time(out);
}
static bool watch_runtime_open(watch_clock_runtime *c,const risc_runtime_api_v1 *rt,bool is_default) {
 *c=(watch_clock_runtime){.runtime=rt,.cause=RISC_BOOT_RESET};
 c->time_grant=(risc_runtime_capability_v1){.struct_size=sizeof(c->time_grant)};
 if(!rt->acquire(RISC_REALTIME_CONTROL_CAPABILITY,1,0,&c->time_grant))return false;
 c->time_live=true;c->time=c->time_grant.api;
 if(!c->time || c->time->api_version!=1 || c->time->struct_size<sizeof(*c->time) ||
    !c->time->read || !c->time->seed)return false;
 if(!is_default)return true;
 c->wake_grant=(risc_runtime_capability_v1){.struct_size=sizeof(c->wake_grant)};
 if(!rt->acquire(RISC_RETAINED_WAKE_CAPABILITY,1,0,&c->wake_grant))return false;
 c->wake_live=true;c->wake=c->wake_grant.api;
 if(!c->wake || c->wake->api_version!=1 || c->wake->struct_size<sizeof(*c->wake) ||
    !c->wake->read || !c->wake->stage || !c->wake->clear)return false;
 risc_retained_wake_record_v1 record={.struct_size=sizeof(record)};
 int rc=c->wake->read(c->wake->context,WATCH_CLOCK_CHECKPOINT_TYPE,WATCH_CLOCK_CHECKPOINT_SCHEMA,&record,&c->cause);
 if(rc==RISC_RETAINED_WAKE_CONTEXT){watch_runtime_halt(c);return false;}
 if(rc!=RISC_RETAINED_WAKE_OK && rc!=RISC_RETAINED_WAKE_ABSENT && rc!=RISC_RETAINED_WAKE_MISMATCH)return false;
 if(c->cause>RISC_BOOT_DEEP_OTHER)return false;
 c->resume=rc==RISC_RETAINED_WAKE_OK && c->cause>=RISC_BOOT_DEEP_TIMER &&
  record.struct_size==sizeof(record) && record.type==WATCH_CLOCK_CHECKPOINT_TYPE &&
  record.schema_version==WATCH_CLOCK_CHECKPOINT_SCHEMA && record.size==1 && record.payload[0]==1;
 return true;
}
static bool watch_runtime_seed(watch_clock_runtime *c,const twatch_rtc_api_v1 *rtc) {
 risc_realtime_snapshot_v1 sample;
 if(!watch_runtime_snapshot(c,&sample))return false;
 /* A classified deep boot preserves native time, even if this app has no
  * checkpoint. A normal invocation reseeds from the same persisted RTC basis,
  * so a completed Settings time edit takes effect on its Clock return. */
 if(c->cause>=RISC_BOOT_DEEP_TIMER && sample.validity==RISC_REALTIME_VALID)return true;
 twatch_rtc_time_v1 date={0};int64_t epoch=0;
 if(!rtc || !rtc->read)return true; /* Explicit TIME UNSET remains visible. */
 if(!rtc->read(rtc->context,&date))return false;
 if(!watch_runtime_epoch(&date,&epoch)) {
  /* Runtime v1 has a signed-32-bit epoch. Preserve the accepted Watch's
   * wider 2000..2099 civil domain through its original RTC outside that range. */
  if(tw_valid_time(&date)){c->fallback=rtc;return true;}
  return sample.validity==RISC_REALTIME_UNSET;
 }
 int rc=c->time->seed(c->time->context,epoch,0);
 if(rc==RISC_REALTIME_CONTEXT)watch_runtime_halt(c);
 return rc==RISC_REALTIME_OK;
}
static bool watch_runtime_read(watch_clock_runtime *c,twatch_rtc_time_v1 *out,uint16_t *fraction_ms) {
 if(c->halted)return false;
 if(c->fallback) {
  twatch_rtc_time_v1 date={0};
  if(!c->fallback->read(c->fallback->context,&date) || !tw_valid_time(&date))return false;
  *out=date;*fraction_ms=0;return true;
 }
 risc_realtime_snapshot_v1 sample;
 if(!watch_runtime_snapshot(c,&sample) || sample.validity!=RISC_REALTIME_VALID ||
    !watch_runtime_calendar(sample.epoch_seconds,out))return false;
 *fraction_ms=(uint16_t)(sample.nanoseconds/1000000u);return true;
}
static bool watch_runtime_stage(watch_clock_runtime *c) {
 if(c->halted)return false;
 if(!c->wake)return true;
 const risc_retained_wake_record_v1 record={.struct_size=sizeof(record),
  .type=WATCH_CLOCK_CHECKPOINT_TYPE,.schema_version=WATCH_CLOCK_CHECKPOINT_SCHEMA,.size=1,.payload={1}};
 int rc=c->wake->stage(c->wake->context,&record);
 if(rc==RISC_RETAINED_WAKE_CONTEXT)watch_runtime_halt(c);
 return rc==RISC_RETAINED_WAKE_OK;
}
static bool watch_runtime_abandon(watch_clock_runtime *c) {
 if(c->halted)return false;
 if(!c->wake)return true;
 int rc=c->wake->clear(c->wake->context);
 if(rc==RISC_RETAINED_WAKE_CONTEXT)watch_runtime_halt(c);
 return rc==RISC_RETAINED_WAKE_OK;
}
static int watch_runtime_promote(watch_clock_runtime *c) {
 if(c->halted)return RISC_PROVIDER_PROMOTION_RETAINED;
 risc_runtime_capability_v1 grant={.struct_size=sizeof(grant)};
 if(!c->runtime->acquire(RISC_PROVIDER_PROMOTION_CAPABILITY,1,0,&grant)){watch_runtime_halt(c);return RISC_PROVIDER_PROMOTION_RETAINED;}
 const risc_provider_promotion_api_v1 *api=grant.api;
 int rc=api && api->api_version==1 && api->struct_size>=sizeof(*api) && api->promote?
  api->promote(api->context):RISC_PROVIDER_PROMOTION_FAILED;
 if(rc==RISC_PROVIDER_PROMOTION_RETAINED){watch_runtime_halt(c);return rc;}
 if(!c->runtime->release(&grant)){watch_runtime_halt(c);return RISC_PROVIDER_PROMOTION_RETAINED;}
 return rc;
}

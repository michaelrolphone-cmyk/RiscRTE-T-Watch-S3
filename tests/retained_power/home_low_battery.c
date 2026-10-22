/* Exact-source composition fixture. Only providers, storage and time are fake. */
#if !defined(PORTABLE_LOW_BATTERY) || !defined(WATCH_ATOMIC_PREFERENCES) || !defined(PORTABLE_QUICK_ATOMIC_PREFERENCES) || !defined(PORTABLE_PREFERENCE_STORE) || !defined(WATCH_CRASH_REPORT_NAMESPACE) || WATCH_CRASH_REPORT_NAMESPACE != 61
#error Exact retained Home full feature definitions and namespace 61 are required
#endif
#include "home_fixture.inc"

enum { EDGE, IDLE, DEEP, BRIGHT, RADIO, MODE, RECORDS };
static const char *const keys[RECORDS] = {"battery_edge", "sleep_idle", "sleep_deep", "brightness", "quick_radio", "sleep_mode"};
static struct { uint8_t bytes[64]; uint32_t size; unsigned writes, attempts, reads; } records[RECORDS];
static uint64_t revision = 1, token;
static unsigned pref_reads, kv_reads, submissions, collections, io_calls, invocations;
static unsigned applied, partial, unconfirmed, healthy_samples, low_samples, invalid_samples;
static unsigned wifi_disconnects, wifi_reads, bluetooth_sets, last_brightness;
static unsigned case_kind, chosen_mode, fail_kind, phase, end_at;
static unsigned prepares, resumes, light_requests, deep_requests, arming_at, idle_at;
static bool seed_write, scheduling, armed, predeadline, request_done, saw_policy;
static bool wifi_connected;
static risc_key_value_v1 namespace_kv[7];
static risc_key_value_atomic_v1 preference_api;
static wifi_api_v1 wifi_api;
static portable_bluetooth_control_v1 bluetooth_api;
static risc_key_value_atomic_receipt_v1 copied_receipt;

static void boundary(void) { check_io(); ++io_calls; }
static int index_of(const char *key) {
 for (unsigned i=0;i<RECORDS;++i) if (!strcmp(key,keys[i])) return (int)i;
 return -1;
}
static int32_t shared_get(void *context,const char *key,void *out,uint32_t cap,uint32_t *size) {
 boundary(); unsigned ns=(unsigned)(uintptr_t)context; assert(ns<7); ++kv_reads; *size=0;
 int ix=index_of(key);
 if (ix<0) return fast_get(NULL,key,out,cap,size);
 if(ns!=1) return RISC_KEY_VALUE_NOT_FOUND;
 ++records[ix].reads; *size=records[ix].size;
 if(!*size) return RISC_KEY_VALUE_NOT_FOUND;
 if(cap<*size) return RISC_KEY_VALUE_BUFFER_SMALL;
 memcpy(out,records[ix].bytes,*size); return RISC_KEY_VALUE_OK;
}
static void store_record(int ix,const void *value,uint32_t size) {
 assert(ix>=0&&ix<RECORDS&&size<=64); memcpy(records[ix].bytes,value,size);
 records[ix].size=size; ++records[ix].writes; ++revision;
}
static int32_t user_seed_put(void *context,const char *key,const void *value,uint32_t size) {
 boundary(); assert(seed_write&&(uintptr_t)context==1); store_record(index_of(key),value,size); return RISC_KEY_VALUE_OK;
}
static risc_key_value_v1 user_store={1,sizeof(user_store),(void*)(uintptr_t)1,shared_get,user_seed_put};
static int32_t preference_state(void *context,risc_key_value_atomic_state_v1 *state) {
 boundary(); assert((uintptr_t)context==1&&!owned&&!pending);
 *state=(risc_key_value_atomic_state_v1){sizeof(*state),RISC_PREFERENCE_STORE_COPIED_INPUT,1,16,64,4096,1024,0,revision};
 return RISC_ATOMIC_OK;
}
static int32_t preference_get(void *context,uint64_t rev,const char *key,void *out,uint32_t cap,uint32_t *size) {
 boundary(); assert((uintptr_t)context==1&&!owned&&!pending); ++pref_reads;
 if(rev!=revision) return RISC_ATOMIC_STALE;
 int rc=shared_get(context,key,out,cap,size);
 return rc==RISC_KEY_VALUE_OK?RISC_ATOMIC_OK:rc==RISC_KEY_VALUE_NOT_FOUND?RISC_ATOMIC_NOT_FOUND:RISC_ATOMIC_IO;
}
static int32_t preference_submit(void *context,uint64_t rev,const risc_key_value_atomic_mutation_v1 *mutations,uint32_t count,const void *intent,uint32_t bytes,uint64_t *out) {
 boundary(); assert((uintptr_t)context==1&&!owned&&!pending&&!token&&count==1&&bytes==176); *out=0;
 const uint8_t *p=intent; int ix=index_of(mutations[0].key);
 assert(ix>=0&&ix<MODE&&mutations[0].kind==RISC_ATOMIC_PUT);
 assert(!memcmp(p,"PFA0001",8)&&p[8]==PORTABLE_PREFERENCE_AUTOMATIC&&p[11]==PORTABLE_AUTOMATIC_LOW_BATTERY);
 assert(!strcmp((const char*)p+12,mutations[0].key)); ++submissions; ++records[ix].attempts;
 if(rev!=revision) return RISC_ATOMIC_STALE;
 if(fail_kind==1&&ix==DEEP) return RISC_ATOMIC_IO;
 store_record(ix,mutations[0].value,mutations[0].size);
 *out=token=1;
 copied_receipt=(risc_key_value_atomic_receipt_v1){sizeof(copied_receipt),RISC_ATOMIC_OK,revision,revision};
 return RISC_ATOMIC_OK;
}
static int32_t preference_collect(void *context,uint64_t accepted,risc_key_value_atomic_receipt_v1 *receipt) {
 boundary(); assert((uintptr_t)context==1&&!owned&&!pending&&accepted==token&&token); ++collections;
 if(fail_kind==2) return RISC_ATOMIC_IO; /* Accepted copied bytes, uncertain outstanding custody. */
 *receipt=copied_receipt; token=0; return RISC_ATOMIC_OK;
}
static int32_t preference_cancel(void *context,uint64_t accepted) {
 boundary(); assert((uintptr_t)context==1&&accepted==token&&token); return RISC_ATOMIC_OK;
}
static bool wifi_disconnect(void *context) { (void)context; boundary(); ++wifi_disconnects; wifi_connected=false; return true; }
static wifi_link_t wifi_observe(void *context) { (void)context; boundary(); ++wifi_reads; return wifi_connected?WIFI_LINK_UP:WIFI_LINK_DOWN; }
static bool bluetooth_set(void *context,bool enabled) { boundary(); ++bluetooth_sets; return fast_ble_enable(context,enabled); }
static bool composition_acquire(const char *name,uint32_t version,uint64_t instance,risc_runtime_capability_v1 *grant) {
 boundary(); bool ok=fast_acquire(name,version,instance,grant);
 if(ok&&!strcmp(name,RISC_KEY_VALUE_CAPABILITY)) {
  assert(instance<7); namespace_kv[instance]=fast_kv; namespace_kv[instance].context=(void*)(uintptr_t)instance;
  namespace_kv[instance].get=shared_get; namespace_kv[instance].put=user_seed_put; grant->api=&namespace_kv[instance];
 } else if(ok&&!strcmp(name,RISC_PREFERENCE_STORE_CAPABILITY)) {
  assert(version==1&&instance==1); grant->api=&preference_api;
 } else if(ok&&!strcmp(name,"net.wifi")) grant->api=&wifi_api;
 else if(ok&&!strcmp(name,"bluetooth.hci")) grant->api=&bluetooth_api;
 return ok;
}
static bool composition_brightness(void *context,uint16_t value,uint16_t max) {
 boundary(); if(value)last_brightness=value; return fast_brightness(context,value,max);
}
static bool composition_battery(void *context,risc_battery_sample_v1 *sample) {
 (void)context; boundary(); unsigned percent=case_kind==2?10:case_kind==0&&clock_ms<5000?10:9,flags=0;
 if(case_kind==3) {
  unsigned step=clock_ms/5000u;
  if(step==1)flags=RISC_BATTERY_CHARGING;
  if(step==2){percent=10;flags=RISC_BATTERY_PROFILE_MISSING;}
  if(step==3)percent=101;
  if(step==4){percent=10;flags=PORTABLE_POWER_STATUS_VALID;}
  if(step==5){++invalid_samples;return false;}
  if(step>=6)flags=PORTABLE_POWER_STATUS_VALID|PORTABLE_POWER_BATTERY_PRESENT|PORTABLE_POWER_CHARGER_ENABLED|PORTABLE_POWER_INPUT_READY;
 }
 *sample=(risc_battery_sample_v1){3900,(uint8_t)percent,(uint8_t)flags};
 /* The inherited static-battery fixture globals are not this scripted provider. */
 if(!portable_low_battery_sample_valid(sample))++invalid_samples;
 else if(percent<10)++low_samples;else ++healthy_samples;
 return true;
}
static bool composition_health(risc_runtime_health_v1 *health_out) {
 boundary();
 if(scheduling&&armed&&clock_deferred_phase==4&&!request_done) {
  if(!phase){clock_ms=5000;phase=1;}
  else if(phase==1&&applied){clock_ms=arming_at+19999;phase=2;}
  else if(phase==2&&predeadline){if(clock_ms<arming_at+20000)clock_ms=arming_at+20000;phase=3;}
 }
 health_out->uptime_ms=clock_ms;return !request_done&&clock_ms<end_at;
}
static bool composition_key(void *context,uint32_t *events) {
 (void)context;boundary();*events=0;
 if(scheduling&&phase==2){assert(!light_requests&&!deep_requests);predeadline=true;}
 if(!idle_at&&clock_deferred_phase==4&&!clock_radios_pending&&applied) {
  assert(clock_quick.brightness==15&&hardware_brightness==15);
  assert(clock_quick.idle_ms==20000&&clock_quick.deep_ms==(fail_kind==1?360000u:60000u));
  assert(clock_radios.valid&&clock_radios.available&&!clock_radios.flags&&!clock_quick.ui.wifi_enabled&&!clock_quick.ui.bluetooth_enabled);
  assert(!ble_state&&!wifi_connected&&wifi_disconnects&&wifi_reads);saw_policy=true;
 }
 return true;
}
static bool composition_diagnostic(const char *message) {
 if(!strcmp(message,"LOW_BATTERY crossing=applied-once"))++applied;
 if(!strcmp(message,"LOW_BATTERY crossing=partial-once")){++partial;++applied;}
 if(!strcmp(message,"LOW_BATTERY settings=unconfirmed"))++unconfirmed;
 if(!strcmp(message,"WATCH_KEY arming=start interval-ms=250")){armed=true;arming_at=clock_ms;}
 if(!strcmp(message,"WATCH_KEY sleep-enter=idle")) {
  assert(scheduling&&predeadline&&saw_policy);idle_at=clock_ms;assert(idle_at>=arming_at+20000&&idle_at<arming_at+20250);
 }
 if(!strncmp(message,"WATCH_CLOCK sleep=refused",25)) {
  char expected[80];snprintf(expected,sizeof(expected),"WATCH_CLOCK sleep=refused stage=DEEP detail=%d",RISC_DEEP_SLEEP_PLATFORM);
  assert(request_done&&deep_requests==1&&!strcmp(message,expected));return true;
 }
 return fast_diagnostic(message);
}
static int32_t composition_begin(uint64_t *accepted) {
 boundary();assert(!owned&&!pending&&!touch.subscription);++prepares;*accepted=77;return RISC_RUNTIME_SLEEP_OK;
}
static int32_t composition_end(uint64_t accepted) {boundary();assert(accepted==77);++resumes;return RISC_RUNTIME_SLEEP_OK;}
static int32_t composition_light(void *context,uint32_t ms,risc_light_sleep_result_v1 *result) {
 (void)context;boundary();assert(idle_at&&watch_sleep_light_ms==60000&&sleep_mode==chosen_mode);
 assert(ms==(chosen_mode==PORTABLE_SLEEP_HYBRID?60000u:0));++light_requests;
 result->wake_cause=RISC_LIGHT_SLEEP_WAKE_TIMER;
 if(chosen_mode==PORTABLE_SLEEP_LIGHT)request_done=true;
 return RISC_LIGHT_SLEEP_OK;
}
static int32_t composition_light_plain(void *context,risc_light_sleep_result_v1 *result) {return composition_light(context,0,result);}
static int32_t composition_deep(void *context,uint32_t ms) {
 (void)context;boundary();assert(!ms&&idle_at&&watch_sleep_light_ms==60000&&sleep_mode==chosen_mode);
 ++deep_requests;request_done=true;return RISC_DEEP_SLEEP_PLATFORM;
}
static int32_t composition_deep_plain(void *context) {return composition_deep(context,0);}
static int32_t composition_panel_deep(void *context) {(void)context;return 0;}
static int32_t composition_panel_resume(void *context) {return da.resume(context)?0:RISC_DEEP_SLEEP_PLATFORM;}
static void initialize_invocation(unsigned kind,unsigned duration) {
 assert(!token);reset_case();++invocations;case_kind=kind;end_at=duration;
 preference_fault=PREF_OK;preference_flags=RISC_PREFERENCE_STORE_COPIED_INPUT;generic_acquires=atomic_acquires=0;
 atomic_count=0;atomic_revision=revision;requested_wakes=0;fake_service_cost=service_start_cost=0;transfer_cost=1;light_wake_drift=0;
 applied=partial=unconfirmed=healthy_samples=low_samples=invalid_samples=0;
 wifi_disconnects=wifi_reads=bluetooth_sets=last_brightness=0;wifi_connected=true;
 phase=prepares=resumes=light_requests=deep_requests=arming_at=idle_at=0;
 armed=predeadline=request_done=saw_policy=false;
 preference_api=(risc_key_value_atomic_v1){1,sizeof(preference_api),(void*)(uintptr_t)1,preference_state,preference_get,preference_submit,preference_collect,preference_cancel};
 wifi_api=qa_wifi;wifi_api.disconnect_checked=wifi_disconnect;wifi_api.status=wifi_observe;
 bluetooth_api=fast_ble;bluetooth_api.set_enabled=bluetooth_set;
 fast_runtime.struct_size=sizeof(fast_runtime);fast_runtime.acquire=composition_acquire;
 fast_runtime.health=composition_health;fast_runtime.diagnostic=composition_diagnostic;
 fast_runtime.sleep_prepare=composition_begin;fast_runtime.sleep_resume=composition_end;
 da.base.set_brightness=composition_brightness;pa.base.read=composition_battery;pa.key_events=composition_key;
 pa.light_sleep=composition_light_plain;pa.light_sleep_for=pa.light_sleep_set=composition_light;
 pa.deep_sleep=composition_deep_plain;pa.deep_sleep_for=pa.deep_sleep_set=composition_deep;
 da.prepare_deep_sleep=composition_panel_deep;da.base.struct_size=sizeof(da);da.resume_status=composition_panel_resume;
}
static void clean_invocation(void) {
 assert(!token&&!retained_fence&&!clock_atomic_retained&&!owned&&!pending&&!held&&!touch.subscription&&!allocations);
 assert(grants==ungrants&&subscribed==unsubscribed&&generic_acquires>0&&pref_reads>0&&atomic_acquires==0);
 assert(sleep_mode==chosen_mode&&prepares==resumes);
}
static void save_profile(uint32_t idle,uint32_t deep,unsigned bright,uint8_t radios) {
 seed_write=true;
 assert(portable_sleep_save(&user_store,chosen_mode));
 assert(portable_sleep_timer_save(&user_store,false,idle)&&portable_sleep_timer_save(&user_store,true,deep));
 assert(pqa_preference_save(&user_store,PQA_BRIGHTNESS_KEY,bright,10)&&portable_radio_save(&user_store,radios));
 seed_write=false;
}
static void profile_is(uint32_t idle,uint32_t deep,unsigned bright,uint8_t radios,bool low) {
 uint32_t value;unsigned level,mode;uint8_t radio;bool stored;
 assert(portable_sleep_timer_load(&user_store,false,&value)==PORTABLE_SLEEP_LOADED&&value==idle);
 assert(portable_sleep_timer_load(&user_store,true,&value)==PORTABLE_SLEEP_LOADED&&value==deep);
 assert(pqa_preference_load(&user_store,PQA_BRIGHTNESS_KEY,40,10,&level)&&level==bright);
 assert(portable_radio_load(&user_store,&radio)&&radio==radios);
 assert(portable_low_battery_load(&user_store,&stored)&&stored==low);
 assert(portable_sleep_load(&user_store,&mode)==PORTABLE_SLEEP_LOADED&&mode==chosen_mode);
}
static void clear_counts(void) {for(unsigned i=0;i<RECORDS;++i)records[i].writes=records[i].attempts=0;}
static void expect_writes(unsigned edge,unsigned idle,unsigned deep,unsigned bright,unsigned radio) {
 const unsigned expected[]={edge,idle,deep,bright,radio,0};
 for(unsigned i=0;i<RECORDS;++i) {
  if(records[i].writes!=expected[i])fprintf(stderr,"key=%s writes=%u expected=%u\n",keys[i],records[i].writes,expected[i]);
  assert(records[i].writes==expected[i]);
 }
}
static void run_crossing(void) {
 initialize_invocation(0,scheduling?24000:17000);app_main();clean_invocation();
 assert(healthy_samples&&low_samples>1&&applied==1&&saw_policy&&last_brightness==15);
 profile_is(20000,fail_kind==1?360000:60000,15,0,true);
 expect_writes(1,1,fail_kind==1?0:1,1,1);
 for(unsigned i=0;i<MODE;++i)assert(records[i].attempts==1);
 assert(partial==(unsigned)(fail_kind==1)&&unconfirmed==partial);
}
int main(int argc,char **argv) {
 assert(argc==3);chosen_mode=(unsigned)strtoul(argv[2],NULL,10);assert(chosen_mode<=2);
 reset_case();save_profile(65000,360000,75,PORTABLE_RADIO_WIFI|PORTABLE_RADIO_BLUETOOTH);clear_counts();
 /* The very same stored bytes feed both facades; a private namespace cannot read them. */
 uint8_t sentinel[64];uint32_t size=99;
 assert(shared_get((void*)(uintptr_t)2,"sleep_idle",sentinel,sizeof(sentinel),&size)==RISC_KEY_VALUE_NOT_FOUND&&!size);
 if(!strcmp(argv[1],"schedule")) {
  scheduling=true;run_crossing();
  assert(request_done&&predeadline&&idle_at&&prepares==1&&resumes==1);
  assert(light_requests==(unsigned)(chosen_mode!=PORTABLE_SLEEP_DEEP));
  assert(deep_requests==(unsigned)(chosen_mode!=PORTABLE_SLEEP_LIGHT));
 } else if(!strcmp(argv[1],"overrides")||!strcmp(argv[1],"invalid-charging")) {
  run_crossing();save_profile(120000,420000,65,PORTABLE_RADIO_WIFI|PORTABLE_RADIO_BLUETOOTH);clear_counts();
  initialize_invocation(!strcmp(argv[1],"invalid-charging")?3:1,!strcmp(argv[1],"invalid-charging")?37000:17000);
  app_main();clean_invocation();expect_writes(0,0,0,0,0);
  assert(!applied&&!partial&&!unconfirmed&&low_samples>1&&last_brightness==65);
  assert(clock_quick.idle_ms==120000&&clock_quick.deep_ms==420000&&clock_quick.brightness==65);
  assert(clock_radios.flags==3&&clock_quick.ui.wifi_enabled&&clock_quick.ui.bluetooth_enabled);
  if(case_kind==3)assert(invalid_samples>3&&!healthy_samples);
  profile_is(120000,420000,65,3,true);
  initialize_invocation(2,7000);app_main();clean_invocation();expect_writes(1,0,0,0,0);
  assert(healthy_samples&&!applied);profile_is(120000,420000,65,3,false);clear_counts();
  initialize_invocation(1,17000);app_main();clean_invocation();expect_writes(1,1,1,1,1);
  assert(applied==1&&saw_policy&&low_samples>1);profile_is(20000,60000,15,0,true);
 } else if(!strcmp(argv[1],"partial")) {
  fail_kind=1;run_crossing();clear_counts();fail_kind=0;
  initialize_invocation(1,17000);app_main();clean_invocation();expect_writes(0,0,0,0,0);
  assert(!applied&&!unconfirmed&&low_samples>1&&clock_quick.deep_ms==360000);
  profile_is(20000,360000,15,0,true);
 } else {
  assert(!strcmp(argv[1],"retained"));fail_kind=2;initialize_invocation(0,17000);app_main();
  assert(retained_fence&&retains==2&&clock_atomic_retained&&native_clock.halted&&token&&home_automatic.operation.token);
  assert(submissions==1&&collections==1&&!applied&&!light_requests&&!deep_requests);expect_writes(1,0,0,0,0);
  unsigned before=io_calls;app_main();assert(io_calls==before&&retains==2&&submissions==1); /* No replay or provider I/O after retain. */
 }
 printf("{\"case\":\"%s\",\"mode\":%u,\"invocations\":%u,\"preference_flags\":4,\"namespace\":1,\"preference_reads\":%u,\"generic_reads\":%u,\"submissions\":%u,\"collections\":%u,\"idle_armed_ms\":%u,\"idle_request_ms\":%u,\"light_requests\":%u,\"deep_requests\":%u,\"retains\":%u,\"passed\":true}\n",argv[1],chosen_mode,invocations,pref_reads,kv_reads,submissions,collections,arming_at,idle_at,light_requests,deep_requests,retains);
 return 0;
}

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
/* Scenario clock/provider/lifecycle cases follow in the next source checkpoint. */
int main(void) { fputs("low-battery composition source checkpoint: qualification pending\n",stderr); return 77; }

/* All-feature historical Settings controller fixture. Production policy,
 * rendering, input dispatch, persistence helpers and both local bridges are
 * compiled from pinned sources, not reproduced here. Only capabilities fake
 * their external devices/services. This is not execution of the retained ELF. */
#if !defined(PORTABLE_LOW_BATTERY) || !defined(PORTABLE_BLE_BROADCAST) || \
 !defined(PORTABLE_TOUCH_ROTATION) || !defined(PORTABLE_RTC_UTC8_DENVER) || \
 !defined(PORTABLE_FORCE_FULL_FRAMES) || !defined(PORTABLE_INPUT_NAVIGATION) || \
 !defined(PORTABLE_INPUT_NAVIGATION_LOCAL) || !defined(PORTABLE_APP_SLEEP_LOCAL) || \
 !defined(PORTABLE_ALARM_CLIENT) || !defined(PORTABLE_QUICK_ACTIONS) || \
 !defined(PORTABLE_QUICK_RADIOS) || !defined(PORTABLE_MOTION_WAKE) || \
 !defined(WATCH_ALARM_SLEEP_RESUME) || !defined(PORTABLE_NOVA_UI) || \
 !defined(PORTABLE_SETTINGS_APP) || !defined(PORTABLE_TAP_SETTINGS) || \
 !defined(PORTABLE_SLEEP_SETTINGS) || !defined(PORTABLE_ALARM_SETTINGS) || \
 !defined(PORTABLE_SETTINGS_VERSION) || !defined(PORTABLE_RETURN_APP) || \
 !defined(PORTABLE_CONTEXTS_CLIENT) || !defined(PORTABLE_ASYNC_RGB565) || \
 !defined(PORTABLE_SETTINGS_CLOCK_CHANGE_CONTROL) || \
 !defined(PORTABLE_WATCH_NATIVE_HEIGHT) || !defined(PORTABLE_NAVIGATION_RETENTION)
#error "Missing a required retained Settings feature flag"
#endif
#if defined(PORTABLE_SETTINGS_ATOMIC_EXPERIMENTAL) || defined(PORTABLE_QUICK_ATOMIC_PREFERENCES)
#error "Retained Settings used synchronous KV, not atomic preference flags"
#endif
#define PORTABLE_SETTINGS_RUNTIME_OVERRIDE
#define PORTABLE_SETTINGS_NAVIGATION_OVERRIDE
/* The unchanged fixture defines this empty rather than as command-line 1.
 * Its adapter only tests definedness. Avoid a redefinition warning, with the
 * original full-feature flag checked above and enabled by that fixture. */
#undef PORTABLE_SETTINGS_APP
#define main retained_original_settings_fixture_main
#include "portable_settings_test.c"
#undef main
#include "RiscPowerKeyV1.h"

typedef struct { const char *key; uint8_t bytes[64]; uint32_t size, gets, puts; } record;
static record records[]={{.key=PORTABLE_SLEEP_KEY}, {.key=PORTABLE_SLEEP_IDLE_KEY}, {.key=PORTABLE_SLEEP_DEEP_KEY}};
static unsigned fault, key_reads, alarm_steps, alarm_statuses, brightness_calls;
static const char *fault_key;
enum { FAULT_NONE, FAULT_WRITE, FAULT_COMMITTED_ERROR, FAULT_READBACK };
static record *lookup(const char *key) {
  for(unsigned i=0;i<3;i++)if(!strcmp(records[i].key,key))return &records[i];
  return NULL;
}
static int32_t profile_get(void *context,const char *key,void *data,uint32_t cap,uint32_t *size) {
  (void)context;*size=0;record *r=lookup(key);
  /* Other enabled preferences remain independently missing, never alias the
   * three power records. Reads of defaults must not create storage writes. */
  if(!r)return RISC_KEY_VALUE_NOT_FOUND;
  r->gets++;
  if(fault==FAULT_READBACK && r->puts && !strcmp(key,fault_key))return RISC_KEY_VALUE_IO;
  if(!r->size)return RISC_KEY_VALUE_NOT_FOUND;
  *size=r->size;if(cap<r->size)return RISC_KEY_VALUE_BUFFER_SMALL;
  memcpy(data,r->bytes,r->size);return RISC_KEY_VALUE_OK;
}
static int32_t profile_put(void *context,const char *key,const void *data,uint32_t size) {
  (void)context;record *r=lookup(key);assert(r && size<=sizeof(r->bytes));r->puts++;
  bool targeted=fault_key&&!strcmp(key,fault_key);
  if(targeted&&fault==FAULT_WRITE)return RISC_KEY_VALUE_IO;
  memcpy(r->bytes,data,size);r->size=size;
  return targeted&&fault==FAULT_COMMITTED_ERROR?RISC_KEY_VALUE_IO:RISC_KEY_VALUE_OK;
}
static const risc_key_value_v1 profile_kv={1,sizeof(profile_kv),NULL,profile_get,profile_put};
static bool profile_health(risc_runtime_health_v1 *h) {h->uptime_ms=ticks;assert(polls<80);return true;}
static bool power_events(void *context,uint32_t *events) {(void)context;key_reads++;*events=0;return true;}
static const risc_power_key_api_v1 power_key={1,sizeof(power_key),NULL,power_events};
static bool battery_read(void *context,risc_battery_sample_v1 *sample) {
  (void)context;*sample=(risc_battery_sample_v1){3900,70,0};return true;
}
static const risc_battery_gauge_api_v1 profile_battery={1,sizeof(profile_battery),NULL,battery_read};
static bool profile_display_info(void *c,risc_display_info_v1 *out) {
  bool ok=display_info(c,out);out->flags=RISC_DISPLAY_INFO_ASYNC_PRESENT;return ok;
}
static bool brightness(void *c,uint16_t level,uint16_t maximum) {
  (void)c;assert(maximum && level<=maximum);brightness_calls++;return true;
}
static risc_display_output_api_v1 profile_display;
static int32_t alarm_status(void *c,alarm_status_v1 *out) {
  (void)c;alarm_statuses++;*out=(alarm_status_v1){.api_version=1,.struct_size=sizeof(*out),.state=ALARM_STATE_READY};return ALARM_OK;
}
static int32_t alarm_step(void *c) {(void)c;alarm_steps++;return ALARM_OK;}
static int32_t alarm_noop(void *c) {(void)c;return ALARM_OK;}
static int32_t alarm_ack(void *c,const alarm_token_v1 *t) {(void)c;(void)t;assert(!"No alert is active");return ALARM_INVALID;}
static int32_t alarm_prepare(void *c,alarm_sleep_v1 *s) {(void)c;(void)s;assert(!"This UI fixture must not enter sleep");return ALARM_INVALID;}
static int32_t alarm_resume(void *c,const alarm_sleep_v1 *s) {(void)c;(void)s;assert(!"No native sleep in UI fixture");return ALARM_INVALID;}
static const alarm_service_sleep_v1 profile_alarm={
  .base={1,sizeof(profile_alarm),NULL,alarm_status,alarm_step,alarm_noop,alarm_ack,alarm_prepare,alarm_noop},.resume_sleep=alarm_resume};
static bool profile_acquire(const char *name,uint32_t version,uint64_t id,risc_runtime_capability_v1 *g) {
  assert(g->struct_size==sizeof(*g));const void *api=NULL;
  if(!strcmp(name,RISC_KEY_VALUE_CAPABILITY)){assert(version==1&&id==1);api=&profile_kv;}
  else if(!strcmp(name,"display.output")){assert(version==1&&!id);api=&profile_display;}
  else if(!strcmp(name,"input.touch.raw")){assert(version==1&&!id);api=&touch_api;}
  else if(!strcmp(name,"rtc.clock")){assert(version==2&&!id);api=&rtc_api;}
  else if(!strcmp(name,"board.battery")){assert(version==1&&!id);api=&profile_battery;}
  else if(!strcmp(name,RISC_POWER_KEY_CAPABILITY)){assert(version==1&&!id);api=&power_key;}
  else if(!strcmp(name,ALARM_SERVICE_CAPABILITY)){assert(version==1&&!id);api=&profile_alarm;}
  else if(!strcmp(name,RISC_APP_CATALOG_CAPABILITY)){assert(version==1&&!id);api=&fixture_catalog_api;}
  else {
    /* These independently optional capabilities are cleanly unavailable.
     * Full feature compilation is not a claim of live radio/context/motion
     * coexistence. The mode/timer interaction never requires them. */
    assert(!strcmp(name,"net.wifi")||!strcmp(name,"bluetooth.hci")||
           !strcmp(name,"contexts.service")||!strcmp(name,"telemetry.broadcast"));
    *g=(risc_runtime_capability_v1){.struct_size=sizeof(*g)};return false;
  }
  g->api=api;grants++;return true;
}
static bool profile_retain(void) {assert(!"Unexpected invocation retention");return false;}
static risc_runtime_api_v1 profile_runtime;
const risc_runtime_api_v1 *risc_runtime_get_api(uint32_t version) {return version==1?&profile_runtime:NULL;}
static void profile_setup(void) {
  profile_display=display_api;profile_display.get_info=profile_display_info;profile_display.set_brightness=brightness;
  profile_runtime=runtime_api;profile_runtime.acquire=profile_acquire;profile_runtime.health=profile_health;profile_runtime.retain_invocation=profile_retain;
  assert(!strcmp(PORTABLE_SETTINGS_VERSION,"1.3.24"));assert(!strcmp(PORTABLE_RETURN_APP,"springboard.elf"));assert(PORTABLE_TOUCH_ROTATION==0);
}
static void seed(unsigned initial_mode) {
  assert(portable_sleep_save(&profile_kv,initial_mode));
  assert(portable_sleep_timer_save(&profile_kv,false,60000));
  assert(portable_sleep_timer_save(&profile_kv,true,300000));
  for(unsigned i=0;i<3;i++)records[i].gets=records[i].puts=0;
}
static void open_app(void) {
  polls=0;assert(app_module_init()==0);assert(canvas_async);
  assert(settings_count(0)==10 && SETTINGS_ALERT_ROW==6 && SETTINGS_TAP_ROW==7 && SETTINGS_TIMER_ROW==8);
  const unsigned rows[]={4,8,9};const char *labels[]={"Clock Sleep Mode","Sleep Timer","Deep Sleep Timer"};
  for(unsigned i=0;i<3;i++){t5_app_setting_t item;assert(settings_get(0,rows[i],&item));assert(!strcmp(item.label,labels[i]));}
}
static void close_app(void) {
  assert(!failed && !writes);app_module_fini();assert(!grants&&!subscriptions&&!frame_count);
  assert(key_reads && !portable_input_navigation_retained());
}
static unsigned edit(unsigned which,unsigned mode,bool change,bool cancel) {
  input_count=0;polls=0;assert(!touch_previous.contact_count && !touch_edge_count);
  if(change){if(which==0)tap(3,100,(uint16_t)(mode==0?76:mode==1?116:152));else tap(3,190,100);}
  tap(7,cancel?60:170,213);tap(8,cancel?60:170,213);
  /* An unconfirmed save stays modal. A later real Cancel completes it. */
  tap(12,60,213);
  unsigned row=which==0?4:SETTINGS_TIMER_ROW+which-1;
  settings_render(0,(int32_t)row+1);return settings_activate(0,row);
}
static void verify(unsigned mode,uint32_t idle,uint32_t deep) {
  unsigned actual_mode;uint32_t actual_idle,actual_deep;
  assert(portable_sleep_load(&profile_kv,&actual_mode)==PORTABLE_SLEEP_LOADED && actual_mode==mode);
  assert(portable_sleep_timer_load(&profile_kv,false,&actual_idle)==PORTABLE_SLEEP_LOADED && actual_idle==idle);
  assert(portable_sleep_timer_load(&profile_kv,true,&actual_deep)==PORTABLE_SLEEP_LOADED && actual_deep==deep);
  assert(quick.idle_ms==idle && quick.deep_ms==deep && portable_idle_ms()==idle);
}
static void emit(const char *name,unsigned mode,uint32_t idle,uint32_t deep) {
  printf("{\"case\":\"%s\",\"mode\":%u,\"idle_ms\":%u,\"deep_ms\":%u,\"namespace\":1,\"records\":{",name,mode,idle,deep);
  for(unsigned i=0;i<3;i++){printf("%s\"%s\":\"",i?",":"",records[i].key);for(unsigned j=0;j<records[i].size;j++)printf("%02x",records[i].bytes[j]);printf("\"");}
  printf("},\"real_navigation_key_reads\":%u,\"alarm_steps\":%u,\"alarm_status_reads\":%u,\"async_submits\":%u}\n",key_reads,alarm_steps,alarm_statuses,displays);
}
int main(int argc,char **argv) {
  assert(argc==3);profile_setup();const char *action=argv[1];unsigned which=(unsigned)atoi(argv[2]);assert(which<3);
  if(!strcmp(action,"exchange")) {
    unsigned mode=which;seed(mode==2?0:2);open_app();
    assert(edit(0,mode,true,false)==T5_APP_SETTING_UPDATED);
    assert(edit(1,0,true,false)==T5_APP_SETTING_UPDATED);
    assert(edit(2,0,true,false)==T5_APP_SETTING_UPDATED);
    for(unsigned i=0;i<3;i++)assert(records[i].puts==1 && records[i].gets>1);
    close_app();open_app();verify(mode,65000,360000);close_app();emit(action,mode,65000,360000);return 0;
  }
  seed(2);open_app();fault_key=records[which].key;
  bool cancel=!strcmp(action,"cancel"),noop=!strcmp(action,"noop");
  if(!strcmp(action,"write-fail"))fault=FAULT_WRITE;
  if(!strcmp(action,"committed-error"))fault=FAULT_COMMITTED_ERROR;
  if(!strcmp(action,"readback-fail"))fault=FAULT_READBACK;
  unsigned result=edit(which,noop?2:1,!noop,cancel);
  /* Historical timer writers explicitly accept IO-after-commit only when
   * readback confirms the wanted value. Mode writers conservatively refuse. */
  bool confirmed=!cancel && (fault==FAULT_NONE || (fault==FAULT_COMMITTED_ERROR && which!=0));
  assert(result==(confirmed?T5_APP_SETTING_UPDATED:T5_APP_SETTING_NO_CHANGE));
  for(unsigned i=0;i<3;i++)assert(records[i].puts==((i==which&&!cancel&&!noop)?1u:0u));
  if(fault==FAULT_WRITE || fault==FAULT_READBACK || (fault==FAULT_COMMITTED_ERROR&&which==0))
    assert(!strcmp(which==0?sleep_message:timer_message,"Save unconfirmed - retry"));
  bool persisted=!cancel&&!noop&&fault!=FAULT_WRITE;fault=FAULT_NONE;
  close_app();open_app();
  unsigned mode=persisted&&which==0?1:2;uint32_t idle=persisted&&which==1?65000:60000,deep=persisted&&which==2?360000:300000;
  verify(mode,idle,deep);close_app();emit(action,mode,idle,deep);return 0;
}

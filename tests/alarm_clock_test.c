#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#define WATCH_CLOCK_LAUNCHER 1
#define WATCH_CLOCK_ALARMS 1
#define nova_watch_render test_face
#define watch_boot_render test_boot
#include "apps/clock/crown.c"
static uint16_t pixels[240*240];
static unsigned now,ready_at,frames,mode_diag,kv_reads,kv_grants,kv_releases;
static unsigned restored_picker_frames,modal_finished_at,deep_called_at;
static unsigned panel_prepares,pmu_prepares,panel_resumes,pmu_resumes,deep_calls,light_calls;
static unsigned grants,releases,subscriptions,closed,boot_frames,scenario;
static bool owned,pending,ready,retained,terminal_mode;
static unsigned alarm_steps,alarm_acks,alarm_stops,alarm_frames,modal_started,sequence;
static bool activated,post_ack;
static alarm_status_v1 av={.api_version=1,.struct_size=sizeof(av),.state=ALARM_STATE_READY};
static bool health(risc_runtime_health_v1 *h){h->uptime_ms=now;if(scenario==99)return !retained&&now<180000&&!deep_calls;return !retained && now<10000 && (!ready || now-ready_at<1500);}
static void yield_ms(uint32_t n){now+=n;}
bool test_face(risc_display_surface_v1 *s,const nova_watch_state *f){(void)f;memset(s->pixels,0x57,sizeof(pixels));return true;}
bool test_boot(const risc_display_surface_v1 *s,uint32_t ms){(void)ms;assert(!av.occurrence.generation);++boot_frames;memset(s->pixels,0,sizeof(pixels));return true;}
unsigned nova_watch_picker_pulse(uint32_t elapsed){(void)elapsed;return 256;}
bool nova_watch_face_render(risc_display_surface_v1*s,const nova_watch_state*f,unsigned id){(void)id;return test_face(s,f);}
bool nova_watch_picker_collections_render(risc_display_surface_v1*s,const nova_watch_state*f,unsigned id,int position,const int positions[WATCH_FACE_CATEGORY_COUNT],const char*status,unsigned pulse_face,unsigned pulse_scale,nova_watch_picker_cache*scratch){(void)pulse_face;(void)pulse_scale;(void)position;(void)positions;(void)status;assert(scratch==picker_scratch);if(scenario==99&&alarm_acks){assert(id==23);restored_picker_frames++;}return nova_watch_face_render(s,f,id);}
bool nova_watch_alarm_label_render(risc_display_surface_v1*s,const char*label,bool c,bool b,bool rtc_error,bool dismissing,bool uncertain,bool occurrence){
 (void)label;(void)c;(void)b;(void)rtc_error;(void)dismissing;(void)uncertain;(void)occurrence;assert(!pending);alarm_frames++;if(!modal_started)modal_started=now+1;memset(s->pixels,0xaa,sizeof(pixels));return true;}
static bool diagnostic(const char *s){
 if(strstr(s,"ready")){ready=true;ready_at=now;assert(kv_reads==1 && kv_grants==kv_releases);if(scenario==99){picker=(watch_face_picker){.open=true,.selected=23,.category=3,.target=7,.position=-7*WATCH_FACE_PITCH,.category_position=-3*WATCH_CATEGORY_PITCH};picker_scratch=calloc(1,sizeof(*picker_scratch));assert(picker_scratch);}}
 if(!strcmp(s,"WATCH_CLOCK mode=deep"))mode_diag=1;
 if(strstr(s,"retained"))retained=true;
 return true;
}
static bool get_info(void*c,risc_display_info_v1 *i){(void)c;i->width=i->height=240;return true;}
static bool frame_acquire(void*c,uint32_t f,risc_display_surface_v1*s){(void)c;assert(!owned&&!pending&&f==5);owned=true;*s=(risc_display_surface_v1){1,pixels,240,240,480,sizeof(pixels),5};return true;}
static void frame_release(void*c,uint64_t t){(void)c;assert(t==1&&owned);owned=false;}
static bool frame_submit(void*c,uint64_t f,const risc_display_rect_v1*d,size_t n,const risc_display_present_options_v1*o,uint64_t*t){(void)c;(void)d;(void)o;assert(f==1&&owned&&!pending&&!n);owned=false;pending=true;*t=++frames;return true;}
static bool frame_status(void*c,uint64_t t,risc_display_present_status_v1*s){(void)c;assert(t==frames&&pending);pending=false;s->state=RISC_DISPLAY_PRESENT_COMPLETE;return true;}
static bool brightness(void*c,uint16_t v,uint16_t m){(void)c;assert(!retained && (v==0||v==40)&&m==100);return true;}
static void prepared_invariants(void){assert(!owned&&!pending&&!touch.subscription&&kv_grants==kv_releases);for(unsigned i=0;i<240*240;++i)assert(!pixels[i]);}
static bool prepare_panel(void*c){(void)c;prepared_invariants();++panel_prepares;return true;}
static int32_t prepare_deep(void*c){(void)c;prepared_invariants();++panel_prepares;
 if(scenario==3)return RISC_DEEP_SLEEP_PLATFORM;
 if(scenario==4)return RISC_DEEP_SLEEP_RETAINED;
 return 0;
}
static bool resume_panel(void*c){(void)c;assert(!retained);++panel_resumes;return scenario!=6;}
static int32_t typed_resume(void*c){if(scenario==14){retained=true;return RISC_DEEP_SLEEP_RETAINED;}return resume_panel(c)?0:RISC_LIGHT_SLEEP_PLATFORM;}
static bool prepare_pmu(void*c){(void)c;prepared_invariants();++pmu_prepares;return scenario!=2;}
static bool resume_pmu(void*c){(void)c;assert(!retained);++pmu_resumes;return true;}
static bool key(void*c,uint32_t*events){(void)c;*events=0;
 if(clock_alarm_modal&&modal_started&&now-modal_started>=(scenario==99?61000:60))*events=1;
 else if(scenario!=99&&ready&&now-ready_at>=300&&now-ready_at<325)*events=2;
 return true;}
static int32_t light(void*c,risc_light_sleep_result_v1*r){(void)c;(void)r;prepared_invariants();++light_calls;return scenario==12?RISC_LIGHT_SLEEP_RETAINED:RISC_LIGHT_SLEEP_ACTIVE_WAKE;}
static int32_t deep(void*c);
static int32_t timed(void*c,uint32_t ms,risc_light_sleep_result_v1*r){(void)c;prepared_invariants();assert(ms>0&&ms<=RISC_TIMED_SLEEP_MAX_MS);light_calls++;now+=ms;r->wake_cause=RISC_LIGHT_SLEEP_WAKE_TIMER;return 0;}
static int32_t timed_deep(void*c,uint32_t ms){assert(ms>0&&ms<=RISC_TIMED_SLEEP_MAX_MS);return deep(c);}
static bool wake_pending(void*c,bool*p){(void)c;*p=false;return true;}
static int32_t deep(void*c){(void)c;prepared_invariants();++deep_calls;deep_called_at=now;
 if(terminal_mode){assert(boot_frames&&mode_diag&&panel_prepares==1&&pmu_prepares==1&&!panel_resumes&&!pmu_resumes);_exit(77);}
 if(scenario==5)return RISC_DEEP_SLEEP_RETAINED;
 return RISC_DEEP_SLEEP_ACTIVE_WAKE;
}
static bool read_clock(void*c,twatch_rtc_time_v1*t){(void)c;*t=(twatch_rtc_time_v1){2026,10,4,0,0,40,0};return true;}
static bool battery(void*c,risc_battery_sample_v1*b){(void)c;*b=(risc_battery_sample_v1){3900,55,0};return true;}
static uint64_t sub(void*c){(void)c;return ++subscriptions;}
static bool unsub(void*c,uint64_t t){(void)c;assert(t);++closed;return true;}
static bool touch_poll(void*c,size_t n){(void)c;assert(n==1);return true;}
static int32_t next(void*c,uint64_t t,risc_touch_event_v1*e){(void)c;(void)t;(void)e;return 0;}
static bool snapshot(void*c,risc_touch_snapshot_v1*s){(void)c;*s=(risc_touch_snapshot_v1){.width=240,.height=240};return true;}
static int32_t kv_get(void*c,const char*k,void*b,uint32_t cap,uint32_t*size){(void)c;
#ifdef WATCH_CLOCK_POINTS
 assert(!owned&&!pending&&!retained);
 if(!strcmp(k,POINTS_CONFIG_KEY)) {
  points_config c={.revision=1,.created=800000000};
  for(unsigned j=0;j<POINTS_MAX;j++)c.points[j].kind=POINTS_BREAK;
  c.points[0]=(points_item){.kind=POINTS_LUNCH,.enabled=1,.mode=0,.weekdays=127,.hour=12,.minute=0,.duration_minutes=30};assert(cap==64);
  points_config_encode(&c,b);*size=64;return RISC_KEY_VALUE_OK;
 }
#if WATCH_POINTS_EXTENDED
 if(!strcmp(k,POINTS_META_KEY)){assert(cap==64);*size=0;return RISC_KEY_VALUE_NOT_FOUND;}
#endif
#endif
if(!strcmp(k,PORTABLE_TIME_FORMAT_KEY)){*size=0;return RISC_KEY_VALUE_NOT_FOUND;}if(!strcmp(k,WATCH_FACE_KEY)){*size=0;return RISC_KEY_VALUE_NOT_FOUND;}assert(!strcmp(k,PORTABLE_SLEEP_KEY)&&cap==4);++kv_reads;*size=0;
 if(scenario==9||scenario==12)return RISC_KEY_VALUE_NOT_FOUND;
 if(scenario==10)return RISC_KEY_VALUE_IO;
 *size=4;memcpy(b,(uint8_t[]){0x53,1,scenario==1?0:1,scenario==1?0xa5:0xa4},4);return 0;
}
static int32_t kv_put(void*c,const char*k,const void*b,uint32_t size){(void)c;(void)k;(void)b;(void)size;assert(!"Clock never writes settings");return -1;}
static const risc_key_value_v1 kv={1,sizeof(kv),NULL,kv_get,kv_put};
static twatch_panel_power_v1 dp={{1,sizeof(dp),NULL,get_info,frame_acquire,frame_release,frame_submit,frame_status,NULL,brightness},prepare_panel,resume_panel,prepare_deep,typed_resume};
static twatch_pmu_api_v1 pp={{1,sizeof(pp),NULL,battery},key,prepare_pmu,resume_pmu,light,deep,timed,wake_pending,timed_deep};
static twatch_rtc_api_v1 rp={2,sizeof(rp),NULL,read_clock,NULL,NULL,NULL};
static risc_touch_api_v1 tp={1,sizeof(tp),NULL,sub,unsub,touch_poll,next,snapshot};
static int32_t alarm_status(void*c,alarm_status_v1*out){(void)c;*out=av;return ALARM_OK;}
static int32_t alarm_step(void*c){(void)c;assert(!pending&&!owned&&clock_display_settled);alarm_steps++;
#ifdef ALARM_STATUS_CUE_SUPPORTED
 if(av.state==ALARM_STATE_CUE){if(scenario!=202&&++sequence>=6){av.state=ALARM_STATE_LOADING;av.output_uncertain=0;post_ack=true;sequence=0;}return 0;}
#endif
 if(!activated&&((scenario==0&&!ready)||(scenario==1&&light_calls)||(scenario==99&&ready&&now-ready_at>=20))){av.state=ALARM_STATE_ALERT;av.occurrence=(alarm_token_v1){1,1,1,1};activated=true;}
 else if(av.state==ALARM_STATE_DISMISSING){av.state=ALARM_STATE_LOADING;av.occurrence=(alarm_token_v1){0};post_ack=true;sequence=0;}
 else if(post_ack&&++sequence>=3){av.state=ALARM_STATE_READY;post_ack=false;modal_finished_at=now;}
 return 0;}
static int32_t alarm_refresh(void*c){(void)c;assert(!retained);return ALARM_PENDING;}
static int32_t alarm_ack(void*c,const alarm_token_v1*t){(void)c;assert(!memcmp(t,&av.occurrence,sizeof(*t)));alarm_acks++;av.state=ALARM_STATE_DISMISSING;return ALARM_PENDING;}
static int32_t alarm_prepare(void*c,alarm_sleep_v1*out){(void)c;*out=(alarm_sleep_v1){sizeof(*out),1,now/1000,now/1000+1};return 0;}
static int32_t alarm_stop(void*c){(void)c;alarm_stops++;return ALARM_OK;}
static const alarm_service_v1 alarm_api={1,sizeof(alarm_api),NULL,alarm_status,alarm_step,alarm_refresh,alarm_ack,alarm_prepare,alarm_stop};
static bool acquire_cap(const char*k,uint32_t version,uint64_t id,risc_runtime_capability_v1*g){(void)version;
 if(!strcmp(k,ALARM_SERVICE_CAPABILITY)){assert(!id);g->api=&alarm_api;}
 else if(!strcmp(k,RISC_KEY_VALUE_CAPABILITY)){assert(id==1
#ifdef WATCH_CLOCK_POINTS
 ||id==5
#endif
 );++kv_grants;g->api=&kv;}
 else {assert(!id);if(!strcmp(k,"display.output"))g->api=&dp;else if(!strcmp(k,"board.battery"))g->api=&pp;else if(!strcmp(k,"rtc.clock"))g->api=&rp;else{assert(!strcmp(k,"input.touch.raw"));g->api=&tp;}}
 ++grants;return true;
}
static bool release_cap(risc_runtime_capability_v1*g){assert(!retained);assert(g->api&&!owned&&!pending);if(g->api==&kv)++kv_releases;g->api=NULL;++releases;return true;}
static bool launch(const char*s){(void)s;assert(!"No launcher gesture");return false;}
static const risc_runtime_api_v1 runtime={1,sizeof(runtime),health,yield_ms,diagnostic,launch,acquire_cap,release_cap};
const risc_runtime_api_v1 *risc_runtime_get_api(uint32_t v){assert(v==1);return &runtime;}
static void reset(unsigned test){scenario=test;restored_picker_frames=modal_finished_at=deep_called_at=0;now=ready_at=frames=mode_diag=kv_reads=kv_grants=kv_releases=0;panel_prepares=pmu_prepares=panel_resumes=pmu_resumes=deep_calls=light_calls=grants=releases=subscriptions=closed=boot_frames=0;owned=pending=ready=retained=terminal_mode=false;dp.base.struct_size=sizeof(dp);pp.base.struct_size=sizeof(pp);}
int main(void){
 for(unsigned i=0;i<2;i++){
  reset(i);alarm_steps=alarm_acks=alarm_stops=alarm_frames=modal_started=sequence=0;activated=post_ack=false;av=(alarm_status_v1){.api_version=1,.struct_size=sizeof(av),.state=ALARM_STATE_READY};
  app_main();assert(ready&&activated&&alarm_acks==1&&alarm_frames>=2&&!alarm_stops);
  assert(!owned&&!pending&&grants==releases&&subscriptions==closed);assert(i?light_calls==1:deep_calls==1);
 }
 for(unsigned i=0;i<3;i++){
  reset(i==0?4:i==1?5:14);alarm_steps=alarm_acks=alarm_stops=alarm_frames=modal_started=sequence=0;activated=post_ack=false;av=(alarm_status_v1){.api_version=1,.struct_size=sizeof(av),.state=ALARM_STATE_READY};
  app_main();assert(retained&&grants>releases&&!alarm_stops&&!owned&&!pending);
  assert(clock_alarm.grant.api); /* no cleanup before Runtime retention barrier */
 }
 /* A61-second alert must restore the live picker and start a complete new
  *60-second inactivity budget. Drive the actual app loop through its eventual
  * idle sleep, with the ordinary manual-sleep test event disabled. */
 reset(99);alarm_steps=alarm_acks=alarm_stops=alarm_frames=modal_started=sequence=0;
 activated=post_ack=false;av=(alarm_status_v1){.api_version=1,.struct_size=sizeof(av),.state=ALARM_STATE_READY};
 app_main();assert(alarm_acks==1&&restored_picker_frames>0&&deep_calls==1&&!light_calls);
 assert(modal_finished_at&&deep_called_at-modal_finished_at>=60000&&deep_called_at-modal_finished_at<=60020);
 assert(!owned&&!pending&&grants==releases&&subscriptions==closed);
 puts("Long alert: retained picker restored, full60-second dismissal inactivity interval passed");
 /* Interrupt either picker axis while a select/open/launch action is queued.
  * The alert owns only input and presentation; all32 global IDs and the entire
  * six-card allocation survive dismissal. No stale save or gesture can escape. */
 unsigned cases=0;
 for(unsigned selected=0;selected<WATCH_FACE_COUNT;selected++)for(unsigned axis=0;axis<=2;axis++)for(unsigned seam=0;seam<2;seam++){
  reset(20);rt=&runtime;display=&dp.base;pmu=&pp;rtc=&rp;
  clock_alarm=(portable_alarm_client){.api=&alarm_api};clock_display_settled=true;
  clock_alarm_failed_cleaned=clock_alarm_error_seen=clock_alarm_modal=false;
  touch=(watch_launcher_touch){.api=&tp,.subscription=1};
  alarm_steps=alarm_acks=alarm_stops=alarm_frames=modal_started=sequence=0;
  activated=true;post_ack=false;av=(alarm_status_v1){.api_version=1,.struct_size=sizeof(av),.state=ALARM_STATE_ALERT,.occurrence={1,1,1,1}};
  unsigned cat=watch_face_category_for(selected), index=watch_face_index_for(cat,selected);
  picker=(watch_face_picker){.open=true,.neutral=true,.down=true,.axis=axis,.selected=selected,.category=cat,.target=index,.position=-(int)index*WATCH_FACE_PITCH-4096,.velocity=811,.category_position=-(int)cat*WATCH_CATEGORY_PITCH+(seam?8192:-8192),.category_velocity=-932};
  for(unsigned i=0;i<WATCH_FACE_CATEGORY_COUNT;i++)picker.category_positions[i]=-(int)(i+1)*117;
  picker.category_positions[cat]=picker.position;
  watch_face_picker before=picker;
  picker_scratch=axis?malloc(sizeof(*picker_scratch)):NULL;assert(!axis||picker_scratch);
  if(picker_scratch)memset(picker_scratch,0x37,sizeof(*picker_scratch));
  nova_watch_picker_cache *saved_cache=picker_scratch;
  launcher_swipe_pending=launcher_activity_pending=picker_open_pending=picker_select_pending=true;
  picker_selection_pending=(selected+1)%WATCH_FACE_COUNT;
  assert(clock_alarm_foreground());
  assert(alarm_acks==1&&alarm_frames>=2&&!clock_alarm_modal&&!alarm_stops);
  assert(picker.open==(axis!=0)&&picker.selected==selected&&picker.category==before.category&&picker.target==before.target);
  assert(picker.position==before.position&&picker.category_position==before.category_position);
  assert(!memcmp(picker.category_positions,before.category_positions,sizeof(picker.category_positions)));
  assert(picker_scratch==saved_cache);for(size_t j=0;picker_scratch&&j<sizeof(*picker_scratch);j++)assert(((unsigned char*)picker_scratch)[j]==0x37);
  assert(!picker.down&&!picker.neutral&&picker.consume&&!picker.axis&&!picker.velocity&&!picker.category_velocity);
  assert(!launcher_swipe_pending&&launcher_activity_pending&&!picker_open_pending&&!picker_select_pending);
  assert(watch_face_input(&picker,now,true,1,1,120,90)==WATCH_FACE_NONE);
  assert(watch_face_input(&picker,now+1,true,0,0,0,0)==WATCH_FACE_NONE);
  assert(picker.selected==selected&&picker.neutral&&!picker.down&&!kv_grants);
  for(unsigned j=0;j<120;j++)watch_face_animate(&picker,now+2+j*20);
  assert(picker.selected==selected && picker.category<WATCH_FACE_CATEGORY_COUNT);
  free(picker_scratch);picker_scratch=NULL;cases++;
 }
 printf("Picker interrupt matrix: %u cases, all 32 global IDs, queued opening/horizontal/vertical, both category seams passed\n",cases);
#ifdef ALARM_STATUS_CUE_SUPPORTED
 /* A copied CUE reservation holds output custody but never paints an overlay.
  * Cleanup/ACK ending in LOADING returns to the caller between simultaneous
  * cues rather than consuming an unbounded loading-loop budget. */
 for(unsigned test=200;test<=202;test++) {
  reset(test);rt=&runtime;display=&dp.base;pmu=&pp;rtc=&rp;held=0;
  clock_alarm=(portable_alarm_client){.api=&alarm_api};clock_display_settled=true;
  clock_alarm_failed_cleaned=clock_alarm_error_seen=clock_alarm_modal=false;
  alarm_steps=alarm_acks=alarm_stops=alarm_frames=modal_started=sequence=0;activated=true;post_ack=false;
  av=(alarm_status_v1){.api_version=1,.struct_size=sizeof(av),.state=ALARM_STATE_CUE,.output_uncertain=1};
  memset(pixels,0x57,sizeof(pixels));launcher_swipe_pending=picker_select_pending=true;
  bool ok=clock_alarm_foreground();assert(ok==(test!=202));
  assert(!alarm_frames&&!alarm_acks&&!clock_alarm_modal);for(unsigned i=0;i<240*240;i++)assert(pixels[i]==0x5757);
  if(test==202)assert(alarm_stops==1&&clock_alarm_failed_cleaned);
  else {assert(!alarm_stops&&!launcher_swipe_pending&&!picker_select_pending);assert(now==100&&av.state==ALARM_STATE_LOADING);}
 }
 puts("Clock CUE: no overlay/frame replacement, settled one-cue budget, stale input cancellation and timeout cleanup passed");
#endif
 puts("Clock alarm: boot-before-intro, Light due-before-intro, exact ACK reconciliation, subscription/grant cleanup and queued-opening/both-axis picker custody passed");
}

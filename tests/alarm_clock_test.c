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
static unsigned panel_prepares,pmu_prepares,panel_resumes,pmu_resumes,deep_calls,light_calls;
static unsigned grants,releases,subscriptions,closed,boot_frames,scenario;
static bool owned,pending,ready,retained,terminal_mode;
static unsigned alarm_steps,alarm_acks,alarm_stops,alarm_frames,modal_started,sequence;
static bool activated,post_ack;
static alarm_status_v1 av={.api_version=1,.struct_size=sizeof(av),.state=ALARM_STATE_READY};
static bool health(risc_runtime_health_v1 *h){h->uptime_ms=now;return !retained && now<10000 && (!ready || now-ready_at<1500);}
static void yield_ms(uint32_t n){now+=n;}
bool test_face(risc_display_surface_v1 *s,const nova_watch_state *f){(void)f;memset(s->pixels,0x57,sizeof(pixels));return true;}
bool test_boot(const risc_display_surface_v1 *s,uint32_t ms){(void)ms;assert(!av.occurrence.generation);++boot_frames;memset(s->pixels,0,sizeof(pixels));return true;}
unsigned nova_watch_picker_pulse(uint32_t elapsed){(void)elapsed;return 256;}
bool nova_watch_face_render(risc_display_surface_v1*s,const nova_watch_state*f,unsigned id){(void)id;return test_face(s,f);}
bool nova_watch_picker_render(risc_display_surface_v1*s,const nova_watch_state*f,unsigned id,int position,const char*status,unsigned pulse_face,unsigned pulse_scale,uint16_t*scratch){(void)pulse_face;(void)pulse_scale;(void)position;(void)status;(void)scratch;return nova_watch_face_render(s,f,id);}
bool nova_watch_alarm_render(risc_display_surface_v1*s,bool c,bool b,bool rtc_error,bool dismissing,bool uncertain,bool occurrence){
 (void)c;(void)b;(void)rtc_error;(void)dismissing;(void)uncertain;(void)occurrence;assert(!pending);alarm_frames++;if(!modal_started)modal_started=now+1;memset(s->pixels,0xaa,sizeof(pixels));return true;}
static bool diagnostic(const char *s){
 if(strstr(s,"ready")){ready=true;ready_at=now;assert(kv_reads==1 && kv_grants==kv_releases);}
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
 if(clock_alarm_modal&&modal_started&&now-modal_started>=60)*events=1;
 else if(ready&&now-ready_at>=300&&now-ready_at<325)*events=2;
 return true;}
static int32_t light(void*c,risc_light_sleep_result_v1*r){(void)c;(void)r;prepared_invariants();++light_calls;return scenario==12?RISC_LIGHT_SLEEP_RETAINED:RISC_LIGHT_SLEEP_ACTIVE_WAKE;}
static int32_t deep(void*c);
static int32_t timed(void*c,uint32_t ms,risc_light_sleep_result_v1*r){(void)c;prepared_invariants();assert(ms>0&&ms<=RISC_TIMED_SLEEP_MAX_MS);light_calls++;now+=ms;r->wake_cause=RISC_LIGHT_SLEEP_WAKE_TIMER;return 0;}
static int32_t timed_deep(void*c,uint32_t ms){assert(ms>0&&ms<=RISC_TIMED_SLEEP_MAX_MS);return deep(c);}
static bool wake_pending(void*c,bool*p){(void)c;*p=false;return true;}
static int32_t deep(void*c){(void)c;prepared_invariants();++deep_calls;
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
static int32_t kv_get(void*c,const char*k,void*b,uint32_t cap,uint32_t*size){(void)c;if(!strcmp(k,WATCH_FACE_KEY)){*size=0;return RISC_KEY_VALUE_NOT_FOUND;}assert(!strcmp(k,PORTABLE_SLEEP_KEY)&&cap==4);++kv_reads;*size=0;
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
 if(!activated&&((scenario==0&&!ready)||(scenario==1&&light_calls))){av.state=ALARM_STATE_ALERT;av.occurrence=(alarm_token_v1){1,1,1,1};activated=true;}
 else if(av.state==ALARM_STATE_DISMISSING){av.state=ALARM_STATE_LOADING;av.occurrence=(alarm_token_v1){0};post_ack=true;sequence=0;}
 else if(post_ack&&++sequence>=3){av.state=ALARM_STATE_READY;post_ack=false;}
 return 0;}
static int32_t alarm_refresh(void*c){(void)c;assert(!retained);return ALARM_PENDING;}
static int32_t alarm_ack(void*c,const alarm_token_v1*t){(void)c;assert(!memcmp(t,&av.occurrence,sizeof(*t)));alarm_acks++;av.state=ALARM_STATE_DISMISSING;return ALARM_PENDING;}
static int32_t alarm_prepare(void*c,alarm_sleep_v1*out){(void)c;*out=(alarm_sleep_v1){sizeof(*out),1,now/1000,now/1000+1};return 0;}
static int32_t alarm_stop(void*c){(void)c;alarm_stops++;return ALARM_OK;}
static const alarm_service_v1 alarm_api={1,sizeof(alarm_api),NULL,alarm_status,alarm_step,alarm_refresh,alarm_ack,alarm_prepare,alarm_stop};
static bool acquire_cap(const char*k,uint32_t version,uint64_t id,risc_runtime_capability_v1*g){(void)version;
 if(!strcmp(k,ALARM_SERVICE_CAPABILITY)){assert(!id);g->api=&alarm_api;}
 else if(!strcmp(k,RISC_KEY_VALUE_CAPABILITY)){assert(id==1);++kv_grants;g->api=&kv;}
 else {assert(!id);if(!strcmp(k,"display.output"))g->api=&dp;else if(!strcmp(k,"board.battery"))g->api=&pp;else if(!strcmp(k,"rtc.clock"))g->api=&rp;else{assert(!strcmp(k,"input.touch.raw"));g->api=&tp;}}
 ++grants;return true;
}
static bool release_cap(risc_runtime_capability_v1*g){assert(!retained);assert(g->api&&!owned&&!pending);if(g->api==&kv)++kv_releases;g->api=NULL;++releases;return true;}
static bool launch(const char*s){(void)s;assert(!"No launcher gesture");return false;}
static const risc_runtime_api_v1 runtime={1,sizeof(runtime),health,yield_ms,diagnostic,launch,acquire_cap,release_cap};
const risc_runtime_api_v1 *risc_runtime_get_api(uint32_t v){assert(v==1);return &runtime;}
static void reset(unsigned test){scenario=test;now=ready_at=frames=mode_diag=kv_reads=kv_grants=kv_releases=0;panel_prepares=pmu_prepares=panel_resumes=pmu_resumes=deep_calls=light_calls=grants=releases=subscriptions=closed=boot_frames=0;owned=pending=ready=retained=terminal_mode=false;dp.base.struct_size=sizeof(dp);pp.base.struct_size=sizeof(pp);}
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
 puts("Clock alarm: boot-before-intro, Light due-before-intro, exact ACK reconciliation, subscription/grant cleanup passed");
}

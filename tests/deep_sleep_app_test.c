#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#define WATCH_CLOCK_LAUNCHER 1
#define nova_watch_render test_face
#define watch_boot_render test_boot
#include "apps/clock/crown.c"
static uint16_t pixels[240*240];
static unsigned now,ready_at,frames,mode_diag,kv_reads,kv_grants,kv_releases;
static unsigned panel_prepares,pmu_prepares,panel_resumes,pmu_resumes,deep_calls,light_calls;
static unsigned grants,releases,subscriptions,closed,boot_frames,scenario;
static bool owned,pending,ready,retained,terminal_mode;
static bool health(risc_runtime_health_v1 *h){h->uptime_ms=now;return !retained && (!ready || now-ready_at<(scenario==8?62500:1500));}
static void yield_ms(uint32_t n){now+=n;}
bool test_face(risc_display_surface_v1 *s,const nova_watch_state *f){(void)f;memset(s->pixels,0x57,sizeof(pixels));return true;}
bool test_boot(const risc_display_surface_v1 *s,uint32_t ms){(void)ms;assert(!ready);++boot_frames;memset(s->pixels,0,sizeof(pixels));return true;}
bool nova_watch_face_render(risc_display_surface_v1*s,const nova_watch_state*f,unsigned id){(void)id;return test_face(s,f);}
bool nova_watch_picker_collections_render(risc_display_surface_v1*s,const nova_watch_state*f,unsigned id,int position,const int positions[WATCH_FACE_CATEGORY_COUNT],const char*status,unsigned pulse_face,unsigned pulse_scale,nova_watch_picker_cache*scratch){(void)positions;(void)pulse_face;(void)pulse_scale;(void)position;(void)status;(void)scratch;return nova_watch_face_render(s,f,id);}
unsigned nova_watch_picker_pulse(uint32_t age){(void)age;return 256;}
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
static bool prepare_pmu(void*c){(void)c;prepared_invariants();++pmu_prepares;return scenario!=2;}
static bool resume_pmu(void*c){(void)c;assert(!retained);++pmu_resumes;return true;}
static bool key(void*c,uint32_t*events){(void)c;*events=ready && scenario!=8 && now-ready_at>=300 && now-ready_at<325?2:0;return true;}
static int32_t light(void*c,risc_light_sleep_result_v1*r){(void)c;(void)r;prepared_invariants();++light_calls;return scenario==12?RISC_LIGHT_SLEEP_RETAINED:RISC_LIGHT_SLEEP_ACTIVE_WAKE;}
static int32_t timed(void*c,uint32_t ms,risc_light_sleep_result_v1*r){assert(ms==300000);return light(c,r);}
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
static int32_t kv_get(void*c,const char*k,void*b,uint32_t cap,uint32_t*size){(void)c;if(!strcmp(k,WATCH_FACE_KEY)||!strcmp(k,PORTABLE_TIME_FORMAT_KEY)){*size=0;return RISC_KEY_VALUE_NOT_FOUND;}assert(!strcmp(k,PORTABLE_SLEEP_KEY)&&cap==4);++kv_reads;*size=0;
 if(scenario==9||scenario==12)return RISC_KEY_VALUE_NOT_FOUND;
 if(scenario==10)return RISC_KEY_VALUE_IO;
 *size=4;memcpy(b,(uint8_t[]){0x53,scenario==11?2:1,1,0xa4},4);return 0;
}
static int32_t kv_put(void*c,const char*k,const void*b,uint32_t size){(void)c;(void)k;(void)b;(void)size;assert(!"Clock never writes settings");return -1;}
static const risc_key_value_v1 kv={1,sizeof(kv),NULL,kv_get,kv_put};
static twatch_panel_power_v1 dp={{1,sizeof(dp),NULL,get_info,frame_acquire,frame_release,frame_submit,frame_status,NULL,brightness},prepare_panel,resume_panel,prepare_deep};
static twatch_pmu_api_v1 pp={{1,sizeof(pp),NULL,battery},key,prepare_pmu,resume_pmu,light,deep,timed,wake_pending};
static twatch_rtc_api_v1 rp={2,sizeof(rp),NULL,read_clock,NULL,NULL,NULL};
static risc_touch_api_v1 tp={1,sizeof(tp),NULL,sub,unsub,touch_poll,next,snapshot};
static bool acquire_cap(const char*k,uint32_t version,uint64_t id,risc_runtime_capability_v1*g){(void)version;
 if(!strcmp(k,RISC_KEY_VALUE_CAPABILITY)){assert(id==1);++kv_grants;g->api=&kv;}
 else {assert(!id);if(!strcmp(k,"display.output"))g->api=&dp;else if(!strcmp(k,"board.battery"))g->api=&pp;else if(!strcmp(k,"rtc.clock"))g->api=&rp;else{assert(!strcmp(k,"input.touch.raw"));g->api=&tp;}}
 ++grants;return true;
}
static bool release_cap(risc_runtime_capability_v1*g){assert(g->api&&!owned&&!pending);if(g->api==&kv)++kv_releases;g->api=NULL;++releases;return true;}
static bool launch(const char*s){(void)s;assert(!"No launcher gesture");return false;}
static const risc_runtime_api_v1 runtime={1,sizeof(runtime),health,yield_ms,diagnostic,launch,acquire_cap,release_cap};
const risc_runtime_api_v1 *risc_runtime_get_api(uint32_t v){assert(v==1);return &runtime;}
static void reset(unsigned test){scenario=test;now=ready_at=frames=mode_diag=kv_reads=kv_grants=kv_releases=0;panel_prepares=pmu_prepares=panel_resumes=pmu_resumes=deep_calls=light_calls=grants=releases=subscriptions=closed=boot_frames=0;owned=pending=ready=retained=terminal_mode=false;dp.base.struct_size=sizeof(dp);pp.base.struct_size=sizeof(pp);}
int main(void){
 for(unsigned test=0;test<13;++test){
  reset(test);if(test==7){dp.base.struct_size=TWATCH_PANEL_LIGHT_SLEEP_SIZE;pp.base.struct_size=TWATCH_PMU_LIGHT_SLEEP_SIZE;}
  app_main();assert(ready&&!owned&&!pending&&grants==releases&&subscriptions==closed);
  if(test>=9){assert(!mode_diag&&light_calls==1&&!deep_calls);if(test==12)assert(retained&&!panel_resumes&&!pmu_resumes);}
  else if(test==4){assert(retained&&!deep_calls&&!pmu_prepares&&!panel_resumes&&!pmu_resumes);}
  else if(test==5){assert(retained&&deep_calls==1&&!panel_resumes&&!pmu_resumes);}
  else if(test==2||test==3||test==7)assert(!deep_calls&&!light_calls&&panel_resumes==1&&pmu_resumes==1);
  else assert(deep_calls==1&&!light_calls&&panel_resumes==1&&pmu_resumes==1);
  if(test==8)assert(now-ready_at>=60000);
 }
 for(unsigned boot=0;boot<3;++boot){
  pid_t pid=fork();assert(pid>=0);
  if(!pid){reset(0);terminal_mode=true;app_main();_exit(99);}
  int status;assert(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==77);
 }
 puts("Watch deep app: persisted mode/defaults, manual/60s idle, old suffix, refusal/retained cleanup and three terminal fresh boots passed");
 return 0;
}

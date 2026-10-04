#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static void *test_picker_malloc(size_t n);
static void test_picker_free(void*p);
#define malloc test_picker_malloc
#define free test_picker_free
#define WATCH_CLOCK_LAUNCHER 1
#include "apps/clock/crown.c"
#undef malloc
#undef free
static unsigned allocations,cache_allocations;
static uint16_t pixels[240*240],completed_pixels[240*240],expected_pixels[240*240];
static unsigned last_complete,swipe_submitted,swipe_time;
static unsigned clock_ms,submitted,released,grants,ungrants,subscribed,unsubscribed,polls,launches,sleeps,scenario;
static bool ready,owned,pending,launched;
static unsigned touch_step,ready_time,face_writes,face_reads,frame_started;
static void*test_picker_malloc(size_t n){
 if(n==sizeof(nova_watch_picker_cache)){cache_allocations++;if(scenario==16)return NULL;}
 else assert(n==240u*240u*2u);
 void*p=malloc(n);if(p){allocations++;memset(p,0xa5,n);}return p;
}
static void test_picker_free(void*p){if(p){assert(allocations);allocations--;}free(p);}
static bool saved_face;static uint8_t saved_blob[4];
static bool health(risc_runtime_health_v1 *h){h->uptime_ms=clock_ms;return !launched && clock_ms<(scenario>=8?6000u:3000u);}
static void yield(uint32_t n){assert(n>=1&&n<=20);clock_ms+=n;}
static bool diagnostic(const char*s){if(strstr(s,"ready")){ready=true;ready_time=clock_ms;}return true;}
static bool info(void*c,risc_display_info_v1*i){(void)c;*i=(risc_display_info_v1){.width=240,.height=240};return true;}
static bool acquire_frame(void*c,uint32_t f,risc_display_surface_v1*s){(void)c;assert(f==5&&!owned&&!pending);owned=true;*s=(risc_display_surface_v1){1,pixels,240,240,480,sizeof(pixels),5};return true;}
static void release_frame(void*c,uint64_t f){(void)c;assert(f==1&&owned);owned=false;released++;}
static bool submit_frame(void*c,uint64_t f,const risc_display_rect_v1*d,size_t n,const risc_display_present_options_v1*o,uint64_t*t){(void)c;(void)d;(void)n;(void)o;assert(owned&&!pending&&f==1);
 if(face_writes&&scenario!=11&&scenario!=15){
  assert(!picker.open&&!picker_scratch);
  risc_display_surface_v1 expected={0,expected_pixels,240,240,480,sizeof(expected_pixels),5};
  assert(nova_watch_face_render(&expected,&face,picker.selected)&&!memcmp(pixels,expected_pixels,sizeof(pixels)));
 }
 owned=false;pending=true;frame_started=clock_ms;*t=++submitted;return true;}
static bool status(void*c,uint64_t t,risc_display_present_status_v1*s){(void)c;assert(t==submitted&&pending);if(scenario==14&&clock_ms-frame_started<95){s->state=RISC_DISPLAY_PRESENT_ACTIVE;return true;}pending=false;s->state=scenario==5 && touch_step>=2?RISC_DISPLAY_PRESENT_FAILED:RISC_DISPLAY_PRESENT_COMPLETE;
 if(s->state==RISC_DISPLAY_PRESENT_COMPLETE){memcpy(completed_pixels,pixels,sizeof(pixels));last_complete=submitted;}return true;}
static bool brightness(void*c,uint16_t a,uint16_t b){(void)c;assert((a==0||a==40)&&b==100);if(a)assert(submitted&&!pending);return true;}
static bool prepare(void*c){(void)c;assert(!owned&&!pending&&!touch.subscription);return true;}
static bool resume(void*c){(void)c;return true;}
static bool key(void*c,uint32_t*e){(void)c;*e=scenario==7&&ready&&!sleeps&&clock_ms>2400?2:scenario==10&&ready&&clock_ms-ready_time==2000?1:0;return true;}
static int32_t sleep_now(void*c,risc_light_sleep_result_v1*r){(void)c;(void)r;assert(!touch.subscription);sleeps++;return RISC_LIGHT_SLEEP_ACTIVE_WAKE;}
static int32_t sleep_timed(void*c,uint32_t ms,risc_light_sleep_result_v1*r){assert(ms==300000);return sleep_now(c,r);}
static bool wake_pending(void*c,bool*p){(void)c;*p=false;return true;}
static bool rtc_read(void*c,twatch_rtc_time_v1*t){(void)c;*t=(twatch_rtc_time_v1){2026,10,4,0,0,40,0};return true;}
static bool battery(void*c,risc_battery_sample_v1*s){(void)c;*s=(risc_battery_sample_v1){3900,55,0};return true;}
static uint64_t subscribe(void*c){(void)c;subscribed++;return subscribed;}
static bool unsubscribe(void*c,uint64_t h){(void)c;assert(h);unsubscribed++;return true;}
static bool poll(void*c,size_t n){(void)c;assert(n==1);polls++;touch_step++;return true;}
static int32_t next(void*c,uint64_t h,risc_touch_event_v1*e){(void)c;(void)h;(void)e;return scenario==3&&touch_step==3?-1:0;}
static bool snapshot(void*c,risc_touch_snapshot_v1*s){
 (void)c;*s=(risc_touch_snapshot_v1){.width=240,.height=240};
 unsigned step=touch_step;
 if(scenario>=8){
  if(!ready)return true;
  unsigned age=clock_ms-ready_time;
  unsigned x=120,y=92;bool down=false;
  if(age>=20&&age<660)down=true;
  if(scenario==14){
   if(age>=1000&&age<1009){down=true;x=120;}
   if(age>=1016&&age<1025){down=true;x=220;}
  }
  if(scenario==9||scenario==10||scenario==11||scenario==15){
   if(age>=720&&age<940){down=true;x=age<820?120:12;}
   if(age>=1800&&age<1840){down=true;x=120;}
  }
  if(down){s->contact_count=1;s->contacts[0]=(risc_touch_contact_v1){1,0,(uint16_t)x,(uint16_t)y};}
  return true;
 }
 if(scenario==7)return true;
 if(scenario==2 && step<3){s->contact_count=1;s->contacts[0]=(risc_touch_contact_v1){1,0,120,120};return true;}
 if(scenario==2)step-=3;
 if(step==3){swipe_submitted=submitted;swipe_time=clock_ms;}
 if(step<2)return true;
 if(scenario==1 && step>=3)return true;
 s->contact_count=scenario==4&&step>=3?2:1;
 s->contacts[0]=(risc_touch_contact_v1){1,0,step<3?120:80,120};return true;
}
static risc_touch_api_v1 ta={1,sizeof(ta),NULL,subscribe,unsubscribe,poll,next,snapshot};
static twatch_panel_power_v1 da={{1,TWATCH_PANEL_LIGHT_SLEEP_SIZE,NULL,info,acquire_frame,release_frame,submit_frame,status,NULL,brightness},prepare,resume,NULL};
static twatch_pmu_api_v1 pa={{1,sizeof(pa),NULL,battery},key,prepare,resume,sleep_now,NULL,sleep_timed,wake_pending};
static twatch_rtc_api_v1 ra={2,sizeof(ra),NULL,rtc_read,NULL,NULL,NULL};
static int32_t face_get(void*c,const char*k,void*b,uint32_t n,uint32_t*z){(void)c;*z=0;if(!strcmp(k,PORTABLE_TIME_FORMAT_KEY)){if(scenario==17||scenario==18){assert(n==4);uint8_t f[]={0x54,1,1,scenario==17?0xa4:0};memcpy(b,f,4);*z=4;return 0;}return RISC_KEY_VALUE_NOT_FOUND;}if(strcmp(k,WATCH_FACE_KEY))return RISC_KEY_VALUE_NOT_FOUND;face_reads++;if(scenario==15&&face_writes)return RISC_KEY_VALUE_IO;if(!saved_face)return RISC_KEY_VALUE_NOT_FOUND;assert(n==4);memcpy(b,saved_blob,4);*z=4;return 0;}
static int32_t face_put(void*c,const char*k,const void*b,uint32_t n){(void)c;assert(!strcmp(k,WATCH_FACE_KEY)&&n==4);face_writes++;if(scenario==11)return RISC_KEY_VALUE_IO;memcpy(saved_blob,b,4);saved_face=true;return 0;}
static const risc_key_value_v1 face_kv={1,sizeof(face_kv),NULL,face_get,face_put};
static bool acquire_cap(const char*n,uint32_t v,uint64_t id,risc_runtime_capability_v1*g){(void)v;if(!strcmp(n,RISC_KEY_VALUE_CAPABILITY)){if(scenario<8)return false;assert(id==1);grants++;g->api=&face_kv;return true;}assert(!id);grants++;if(!strcmp(n,"display.output"))g->api=&da;else if(!strcmp(n,"board.battery"))g->api=&pa;else if(!strcmp(n,"rtc.clock"))g->api=&ra;else{assert(!strcmp(n,"input.touch.raw"));g->api=&ta;}return true;}
static bool release_cap(risc_runtime_capability_v1*g){assert(g->api&&!owned&&!pending);g->api=NULL;ungrants++;return true;}
static bool launch(const char*p){assert(!strcmp(p,"springboard.elf")&&!owned&&!pending&&!touch.subscription);assert(submitted==last_complete&&submitted==swipe_submitted&&clock_ms==swipe_time);
 assert(!memcmp(completed_pixels,pixels,sizeof(pixels)));
 risc_display_surface_v1 expected={0,expected_pixels,240,240,480,sizeof(expected_pixels),5};
 assert(nova_watch_face_render(&expected,&face,picker.selected)&&!memcmp(pixels,expected_pixels,sizeof(pixels)));
 launches++;if(scenario==6)return false;launched=true;return true;}
static const risc_runtime_api_v1 runtime={1,sizeof(runtime),health,yield,diagnostic,launch,acquire_cap,release_cap};
const risc_runtime_api_v1*risc_runtime_get_api(uint32_t v){assert(v==1);return &runtime;}
int main(void){
 for(unsigned run=0;run<18;run++){
  scenario=run==10?12:run==11?10:run==12?11:run==13?14:run==14?15:run==15?16:run==16?17:run==17?18:run;
  face_writes=face_reads=ready_time=cache_allocations=0;assert(!allocations);
  if(scenario!=12)saved_face=false;
  clock_ms=submitted=released=grants=ungrants=subscribed=unsubscribed=polls=launches=sleeps=touch_step=0;
  ready=owned=pending=launched=false;last_complete=swipe_submitted=swipe_time=0;app_main();
  assert(ready&&!owned&&!pending&&grants==ungrants&&subscribed==unsubscribed&&!allocations);
  if(scenario==0||scenario==2)assert(launches==1&&launched);
  else if(scenario==6)assert(launches==1&&!launched);
  else assert(!launches);
  if(scenario==7)assert(sleeps==1&&subscribed==2);
  if(scenario==8)assert(picker.open&&!face_writes&&!picker_scratch);
  if(scenario==9)assert(!picker.open&&face_writes==1&&saved_face&&picker.selected>0&&!picker_save_failed&&!picker_scratch);
  if(scenario==10)assert(!picker.open&&face_writes==1&&saved_face&&!picker_scratch);
  if(scenario==11)assert(picker.open&&face_writes==1&&!saved_face&&picker.selected==0&&picker_save_failed);
  if(scenario==12)assert(face_reads>=1&&picker.selected>0&&!face_writes&&saved_face);
  if(scenario==17||scenario==18)assert(face.hour_24==(scenario==17));
  if(scenario==16)assert(cache_allocations==1&&!picker.open&&!picker_scratch&&!face_writes);
  if(scenario==15)assert(picker.open&&face_writes==1&&saved_face&&picker.selected==0&&picker_save_failed);
  if(scenario==14)assert(!picker.open&&!picker_scratch&&face_writes==1&&saved_blob[2]==0&&picker.selected==0&&picker.target==1);
 }
 puts("Production clock: sharp retained handoff without fade/delay, held swipe, taps, preheld entry, gap/multitouch, failed present/launch and sleep input cleanup passed");
}

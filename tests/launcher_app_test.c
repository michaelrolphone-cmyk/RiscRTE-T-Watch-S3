#include <assert.h>
#include <stdio.h>
#include <string.h>
#define WATCH_CLOCK_LAUNCHER 1
#include "apps/clock/crown.c"
static uint16_t pixels[240*240];
static unsigned clock_ms,submitted,released,grants,ungrants,subscribed,unsubscribed,polls,launches,sleeps,scenario;
static bool ready,owned,pending,launched;
static unsigned touch_step,dim_calls,dim_start,dim_end;
static bool health(risc_runtime_health_v1 *h){h->uptime_ms=clock_ms;return !launched && clock_ms<3000;}
static void yield(uint32_t n){assert(n>=1&&n<=20);clock_ms+=n;}
static bool diagnostic(const char*s){if(strstr(s,"ready"))ready=true;return true;}
static bool info(void*c,risc_display_info_v1*i){(void)c;*i=(risc_display_info_v1){.width=240,.height=240};return true;}
static bool acquire_frame(void*c,uint32_t f,risc_display_surface_v1*s){(void)c;assert(f==5&&!owned&&!pending);owned=true;*s=(risc_display_surface_v1){1,pixels,240,240,480,sizeof(pixels),5};return true;}
static void release_frame(void*c,uint64_t f){(void)c;assert(f==1&&owned);owned=false;released++;}
static bool submit_frame(void*c,uint64_t f,const risc_display_rect_v1*d,size_t n,const risc_display_present_options_v1*o,uint64_t*t){(void)c;(void)d;(void)n;(void)o;assert(owned&&!pending&&f==1);owned=false;pending=true;*t=++submitted;return true;}
static bool status(void*c,uint64_t t,risc_display_present_status_v1*s){(void)c;assert(t==submitted&&pending);pending=false;s->state=scenario==5 && touch_step>=4?RISC_DISPLAY_PRESENT_FAILED:RISC_DISPLAY_PRESENT_COMPLETE;return true;}
static bool brightness(void*c,uint16_t a,uint16_t b){(void)c;assert(a<=40&&a%8==0&&b==100);if(ready&&a<40){if(!dim_calls)dim_start=clock_ms;dim_calls++;if(!a)dim_end=clock_ms;if(scenario==5)return false;}return true;}
static bool prepare(void*c){(void)c;assert(!owned&&!pending&&!touch.subscription);return true;}
static bool resume(void*c){(void)c;return true;}
static bool key(void*c,uint32_t*e){(void)c;*e=scenario==7&&ready&&!sleeps&&clock_ms>2400?2:0;return true;}
static int32_t sleep_now(void*c,risc_light_sleep_result_v1*r){(void)c;(void)r;assert(!touch.subscription);sleeps++;return RISC_LIGHT_SLEEP_ACTIVE_WAKE;}
static bool rtc_read(void*c,twatch_rtc_time_v1*t){(void)c;*t=(twatch_rtc_time_v1){2026,10,4,0,0,40,0};return true;}
static bool battery(void*c,risc_battery_sample_v1*s){(void)c;*s=(risc_battery_sample_v1){3900,55,0};return true;}
static uint64_t subscribe(void*c){(void)c;subscribed++;return subscribed;}
static bool unsubscribe(void*c,uint64_t h){(void)c;assert(h);unsubscribed++;return true;}
static bool poll(void*c,size_t n){(void)c;assert(n==1);polls++;touch_step++;return true;}
static int32_t next(void*c,uint64_t h,risc_touch_event_v1*e){(void)c;(void)h;(void)e;return scenario==3&&touch_step==3?-1:0;}
static bool snapshot(void*c,risc_touch_snapshot_v1*s){
 (void)c;*s=(risc_touch_snapshot_v1){.width=240,.height=240};
 unsigned step=touch_step;
 if(scenario==7)return true;
 if(scenario==2 && step<3){s->contact_count=1;s->contacts[0]=(risc_touch_contact_v1){1,0,120,120};return true;}
 if(scenario==2)step-=3;
 if(step<2)return true;
 if(scenario==1 && step>=3)return true;
 s->contact_count=scenario==4&&step>=3?2:1;
 s->contacts[0]=(risc_touch_contact_v1){1,0,step<3?120:80,120};return true;
}
static risc_touch_api_v1 ta={1,sizeof(ta),NULL,subscribe,unsubscribe,poll,next,snapshot};
static twatch_panel_power_v1 da={{1,sizeof(da),NULL,info,acquire_frame,release_frame,submit_frame,status,NULL,brightness},prepare,resume};
static twatch_pmu_api_v1 pa={{1,sizeof(pa),NULL,battery},key,prepare,resume,sleep_now,NULL};
static twatch_rtc_api_v1 ra={2,sizeof(ra),NULL,rtc_read,NULL,NULL,NULL};
static bool acquire_cap(const char*n,uint32_t v,uint64_t id,risc_runtime_capability_v1*g){(void)v;assert(!id);grants++;if(!strcmp(n,"display.output"))g->api=&da;else if(!strcmp(n,"board.battery"))g->api=&pa;else if(!strcmp(n,"rtc.clock"))g->api=&ra;else{assert(!strcmp(n,"input.touch.raw"));g->api=&ta;}return true;}
static bool release_cap(risc_runtime_capability_v1*g){assert(g->api&&!owned&&!pending);g->api=NULL;ungrants++;return true;}
static bool launch(const char*p){assert(!strcmp(p,"springboard.elf")&&!owned&&!pending&&!touch.subscription);assert(dim_calls==5&&dim_end-dim_start==80);launches++;if(scenario==6)return false;launched=true;return true;}
static const risc_runtime_api_v1 runtime={1,sizeof(runtime),health,yield,diagnostic,launch,acquire_cap,release_cap};
const risc_runtime_api_v1*risc_runtime_get_api(uint32_t v){assert(v==1);return &runtime;}
int main(void){
 for(scenario=0;scenario<8;scenario++){
  clock_ms=submitted=released=grants=ungrants=subscribed=unsubscribed=polls=launches=sleeps=touch_step=0;
  dim_calls=dim_start=dim_end=0;ready=owned=pending=launched=false;app_main();
  assert(ready&&!owned&&!pending&&grants==ungrants&&subscribed==unsubscribed);
  if(scenario==0||scenario==2)assert(launches==1&&launched);
  else if(scenario==6)assert(launches==1&&!launched);
  else assert(!launches);
  if(scenario==7)assert(sleeps==1&&subscribed==2);
 }
 puts("Production clock: held swipe/fade, taps, preheld entry, gap/multitouch, failed present/launch and sleep input cleanup passed");
}

#include <assert.h>
#include <stdio.h>
#include <string.h>
#define WATCH_CLOCK_LAUNCHER 1
#define WATCH_CLOCK_RETURN 1
#ifndef CLOCK_SOURCE
#define CLOCK_SOURCE "apps/clock/crown.c"
#endif
#include CLOCK_SOURCE
static uint16_t pixels[240*240],completed[240*240];
static uint32_t ms,ready_at,frame_at,frame_cost,launch_at,last_poll,max_gap;
static unsigned frames,ready_frames,grants,ungrants,polls,first_down_at,trajectory;
static bool ready,owned,pending,launched;
static bool health(risc_runtime_health_v1*h){h->uptime_ms=ms;return !launched&&ms<20000&&(!ready||ms-ready_at<800);}
static void yield(uint32_t n){assert(n>=1&&n<=20);ms+=n;}
static bool diagnostic(const char*s){if(strstr(s,"ready")){ready=true;ready_at=ms;ready_frames=frames;}return true;}
static bool info(void*c,risc_display_info_v1*i){(void)c;i->width=i->height=240;return true;}
static bool acquire_frame(void*c,uint32_t f,risc_display_surface_v1*s){(void)c;assert(f==5&&!owned&&!pending);owned=true;*s=(risc_display_surface_v1){1,pixels,240,240,480,sizeof(pixels),5};return true;}
static void release_frame(void*c,uint64_t f){(void)c;assert(f==1&&owned&&!pending);owned=false;}
static bool submit_frame(void*c,uint64_t f,const risc_display_rect_v1*d,size_t n,const risc_display_present_options_v1*o,uint64_t*t){(void)c;(void)d;(void)o;assert(owned&&!pending&&f==1&&!n);owned=false;pending=true;frame_at=ms;*t=++frames;return true;}
static bool present_frame(void*c,uint64_t token,risc_display_present_status_v1*s){(void)c;assert(pending&&token==frames);if(ms-frame_at<frame_cost)s->state=RISC_DISPLAY_PRESENT_ACTIVE;else{pending=false;memcpy(completed,pixels,sizeof(pixels));s->state=RISC_DISPLAY_PRESENT_COMPLETE;}return true;}
static bool brightness(void*c,uint16_t v,uint16_t maximum){(void)c;assert((v==0||v==40)&&maximum==100);return true;}
static bool prepare(void*c){(void)c;assert(!"No sleep during input timing scenario");return false;}
static bool resume(void*c){(void)c;return true;}
static int32_t sleep_now(void*c,risc_light_sleep_result_v1*r){(void)c;(void)r;assert(0);return -1;}
static bool key(void*c,uint32_t*e){(void)c;*e=0;return true;}
static bool read_rtc(void*c,twatch_rtc_time_v1*t){(void)c;*t=(twatch_rtc_time_v1){2026,10,4,0,0,40,0};return true;}
static bool battery(void*c,risc_battery_sample_v1*b){(void)c;*b=(risc_battery_sample_v1){3900,55,0};return true;}
static uint64_t subscribe(void*c){(void)c;return 1;}
static bool unsubscribe(void*c,uint64_t h){(void)c;assert(h==1);return true;}
static bool poll(void*c,size_t n){(void)c;assert(n==1);if(ready){if(polls&&ms-last_poll>max_gap)max_gap=ms-last_poll;last_poll=ms;polls++;}return true;}
static int32_t next(void*c,uint64_t h,risc_touch_event_v1*e){(void)c;(void)h;(void)e;return 0;}
static bool snapshot(void*c,risc_touch_snapshot_v1*s){(void)c;*s=(risc_touch_snapshot_v1){.width=240,.height=240};if(!ready||ms-ready_at<5)return true;
 unsigned age=ms-ready_at;
 unsigned move=trajectory?(age>=17?40:0):(age-5)/4;
 if(move>80)move=80;
 s->contact_count=1;s->contacts[0]=(risc_touch_contact_v1){1,0,(uint16_t)(120-move),120};
 if(!first_down_at)first_down_at=age;
 return true;}
static risc_touch_api_v1 ta={1,sizeof(ta),NULL,subscribe,unsubscribe,poll,next,snapshot};
static twatch_panel_power_v1 da={{1,TWATCH_PANEL_LIGHT_SLEEP_SIZE,NULL,info,acquire_frame,release_frame,submit_frame,present_frame,NULL,brightness},prepare,resume,NULL};
static twatch_pmu_api_v1 pa={{1,TWATCH_PMU_LIGHT_SLEEP_SIZE,NULL,battery},key,prepare,resume,sleep_now,NULL,NULL,NULL};
static twatch_rtc_api_v1 ra={2,sizeof(ra),NULL,read_rtc,NULL,NULL,NULL};
static bool acquire_cap(const char*n,uint32_t v,uint64_t id,risc_runtime_capability_v1*g){(void)v;if(!strcmp(n,RISC_KEY_VALUE_CAPABILITY))return false;assert(!id);grants++;if(!strcmp(n,"display.output"))g->api=&da;else if(!strcmp(n,"board.battery"))g->api=&pa;else if(!strcmp(n,"rtc.clock"))g->api=&ra;else{assert(!strcmp(n,"input.touch.raw"));g->api=&ta;}return true;}
static bool release_cap(risc_runtime_capability_v1*g){assert(g->api&&!owned&&!pending);g->api=NULL;ungrants++;return true;}
static bool launch(const char*path){assert(!strcmp(path,"springboard.elf")&&!owned&&!pending&&!touch.subscription);assert(!memcmp(pixels,completed,sizeof(pixels)));assert(ms==frame_at+frame_cost);launch_at=ms;launched=true;return true;}
static const risc_runtime_api_v1 runtime={1,sizeof(runtime),health,yield,diagnostic,launch,acquire_cap,release_cap};
const risc_runtime_api_v1*risc_runtime_get_api(uint32_t v){assert(v==1);return &runtime;}
int main(void){
 for(trajectory=0;trajectory<2;trajectory++)for(unsigned cost=0;cost<3;cost++){
  ms=ready_at=frame_at=launch_at=last_poll=max_gap=frames=ready_frames=grants=ungrants=polls=first_down_at=0;
  frame_cost=cost==0?25:cost==1?50:95;ready=owned=pending=launched=false;app_main();
  assert(ready&&!owned&&!pending&&grants==ungrants);
#ifdef EXPECT_BETWEEN_FRAME_TOUCH
  if(trajectory)assert(!launched);else assert(launched&&launch_at-ready_at==(frame_cost==25?125:frame_cost==50?150:190));
#else
  assert(launched&&first_down_at<=8&&max_gap<=8);
  assert(launch_at-ready_at==(trajectory?frame_cost:frame_cost==95?95:100));
  assert(frames-ready_frames==(launch_at-ready_at)/frame_cost);
#endif
  printf("Clock touch trajectory=%s full-frame=%u ms down-sample=%u ms max-sample-gap=%u ms handoff=%s%u ms physical-threshold=%u ms\n",trajectory?"fast-held":"continuous",frame_cost,first_down_at,max_gap,launched?"":"missed/",launched?launch_at-ready_at:0,trajectory?17:85);
 }
}

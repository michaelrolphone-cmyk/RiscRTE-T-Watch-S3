#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "RiscRuntimeV1.h"
#include "twatch_caps.h"
#include "twatch_power.h"
void app_main(void);
static uint16_t pixels[240*240];
static uint32_t now,frames,grants,ungrants,sleeps,prepares,resumes,keys,events,mode;
static bool held,pending,panel_asleep,pmu_asleep;
static bool health(risc_runtime_health_v1*h){h->uptime_ms=now;return now<16000;}
static void yield(uint32_t n){assert(n==1||n==20);now+=n;}
static bool diagnostic(const char*s){assert(!strncmp(s,"WATCH_CLOCK ",12));return true;}
static bool info(void*c,risc_display_info_v1*s){(void)c;s->width=s->height=240;return true;}
static bool acquire_frame(void*c,uint32_t f,risc_display_surface_v1*s){(void)c;assert(!held&&!pending&&!panel_asleep&&f==5);held=true;*s=(risc_display_surface_v1){1,pixels,240,240,480,sizeof(pixels),5};return true;}
static void release_frame(void*c,uint64_t t){(void)c;assert(t==1&&held);held=false;}
static bool submit(void*c,uint64_t f,const risc_display_rect_v1*d,size_t n,const risc_display_present_options_v1*o,uint64_t*t){(void)c;(void)d;(void)n;(void)o;assert(f==1&&held&&!pending);held=false;pending=true;*t=++frames;return true;}
static bool present(void*c,uint64_t t,risc_display_present_status_v1*s){(void)c;assert(t==frames&&pending);pending=false;s->state=RISC_DISPLAY_PRESENT_COMPLETE;return true;}
static bool bright(void*c,uint16_t v,uint16_t m){(void)c;assert(v==40&&m==100);return true;}
static bool panel_prepare(void*c){(void)c;assert(!held&&!pending);panel_asleep=true;return mode!=2;}
static bool panel_resume(void*c){(void)c;panel_asleep=false;resumes++;return mode!=3;}
static bool pmu_prepare(void*c){(void)c;assert(panel_asleep);pmu_asleep=true;prepares++;return true;}
static bool pmu_resume(void*c){(void)c;pmu_asleep=false;return true;}
static int32_t sleep_now(void*c,risc_light_sleep_result_v1*r){(void)c;assert(!held&&!pending&&panel_asleep&&pmu_asleep&&r->struct_size==sizeof(*r));sleeps++;r->wake_cause=RISC_LIGHT_SLEEP_WAKE_GPIO;return mode==1?RISC_LIGHT_SLEEP_ACTIVE_WAKE:RISC_LIGHT_SLEEP_OK;}
static bool key(void*c,uint32_t*out){(void)c;keys++;*out=0;if(events<2 && now>=5000+events*5000){*out=2;events++;}return true;}
static bool rtc_read(void*c,twatch_rtc_time_v1*t){(void)c;*t=(twatch_rtc_time_v1){2026,10,3,6,12,30,0};return true;}
static twatch_panel_power_v1 d={{1,sizeof(d),NULL,info,acquire_frame,release_frame,submit,present,NULL,bright},panel_prepare,panel_resume};
static twatch_pmu_api_v1 p={{1,sizeof(p),NULL,NULL},key,pmu_prepare,pmu_resume,sleep_now};
static twatch_rtc_api_v1 r={2,sizeof(r),NULL,rtc_read,NULL,NULL,NULL};
static bool acquire(const char*n,uint32_t v,uint64_t id,risc_runtime_capability_v1*g){assert(!id&&g->struct_size==sizeof(*g));if(!strcmp(n,"display.output")){assert(v==1);g->api=&d;}else if(!strcmp(n,"board.battery")){assert(v==1);g->api=&p;}else{assert(!strcmp(n,"rtc.clock")&&v==2);g->api=&r;}grants++;return true;}
static bool release(risc_runtime_capability_v1*g){assert(g->api&&!held&&!pending);g->api=NULL;ungrants++;return true;}
static const risc_runtime_api_v1 api={1,sizeof(api),health,yield,diagnostic,NULL,acquire,release};
const risc_runtime_api_v1*risc_runtime_get_api(uint32_t v){assert(v==1);return &api;}
int main(void){for(mode=0;mode<4;mode++){
 now=frames=grants=ungrants=sleeps=prepares=resumes=keys=events=0;held=pending=panel_asleep=pmu_asleep=false;
 app_main();assert(grants==3&&ungrants==3&&!held&&!pending&&!pmu_asleep&&!panel_asleep);
 assert(frames>20&&keys>1);
 if(mode==0||mode==1)assert(sleeps==2&&resumes==2&&prepares==2);
 if(mode==2)assert(!sleeps&&resumes==2&&!prepares);
 if(mode==3)assert(sleeps==1&&resumes==1&&events==1);
 }puts("Crown app: repeat sleep/wake, refusal, partial preparation, restore failure passed");}

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "RiscRuntimeV1.h"
#include "apps/clock/nova/nova.h"
#include "apps/clock/effects/effects.h"
static void *return_alloc(size_t);
static void return_free(void *);
static bool return_boot(risc_display_surface_v1 *,uint32_t);
static bool return_face(risc_display_surface_v1 *,const nova_watch_state *);
#define WATCH_CLOCK_RETURN 1
#define malloc return_alloc
#define free return_free
#define watch_boot_render return_boot
#define nova_watch_render return_face
#include "apps/clock/crown.c"
#undef malloc
#undef free
#undef watch_boot_render
#undef nova_watch_render
static uint16_t pixels[240*240],outgoing[240*240],sharp[240*240],expected[240*240],scratch[240*240];
static uint32_t now,epoch,cost,submitted_at,ready_at,frames,complete,grants,ungrants;
static unsigned allocations,allocation_calls,fail_allocation,blank_calls,light_calls,boot_calls,face_calls,sleeps;
static unsigned fail_acquire,fail_submit,fail_present,acquire_calls,return_frames;
static bool owned,pending,ready,stop_ready,stalled,invalid_surface,wake_test,refuse;
static uint32_t stop_at;
static unsigned sleep_failure;
static void *return_alloc(size_t size){assert(size==sizeof(pixels));if(++allocation_calls==fail_allocation)return NULL;void*p=malloc(size);if(p)allocations++;return p;}
static void return_free(void *p){if(p){assert(allocations);allocations--;}free(p);}
static bool return_boot(risc_display_surface_v1*s,uint32_t age){assert(sleeps&&!refuse);boot_calls++;return watch_boot_render(s,age);}
static bool return_face(risc_display_surface_v1*s,const nova_watch_state*f){face_calls++;bool ok=nova_watch_render(s,f);if(ok)memcpy(sharp,s->pixels,sizeof(sharp));return ok;}
static bool health(risc_runtime_health_v1*h){h->uptime_ms=now;return !(ready&&stop_ready)&&(uint32_t)(now-epoch)<stop_at;}
static void yield(uint32_t ms){assert(ms>=1&&ms<=20);if(!stalled)now+=ms;}
static bool diagnostic(const char*s){if(strstr(s,"ready")){ready=true;ready_at=now;assert(!boot_calls&&complete&&return_frames);assert(!blank_calls&&!light_calls);}return true;}
static bool info(void*c,risc_display_info_v1*i){(void)c;i->width=i->height=240;return true;}
static bool acquire_frame(void*c,uint32_t format,risc_display_surface_v1*s){(void)c;assert(!owned&&!pending&&format==5);if(++acquire_calls==fail_acquire)return false;owned=true;*s=(risc_display_surface_v1){1,pixels,invalid_surface?239:240,240,480,sizeof(pixels),5};return true;}
static void release_frame(void*c,uint64_t f){(void)c;assert(owned&&!pending&&f==1);owned=false;}
static bool submit_frame(void*c,uint64_t f,const risc_display_rect_v1*d,size_t n,const risc_display_present_options_v1*o,uint64_t*t){(void)c;(void)d;(void)o;assert(owned&&!pending&&f==1&&!n);if(frames+1==fail_submit)return false;
 if(!ready){
  unsigned age=now-epoch,alpha=fail_allocation?256:age>=60?256:age*256/60;
  assert(alpha&&"Do not transfer the already-visible alpha-zero frame");
  memcpy(expected,sharp,sizeof(expected));assert(portable_transition_rgb565(expected,480,outgoing,480,scratch,sizeof(scratch),240,240,alpha));
  assert(!memcmp(expected,pixels,sizeof(pixels)));return_frames++;
 }
 owned=false;pending=true;submitted_at=now;*t=++frames;return true;}
static bool present_frame(void*c,uint64_t token,risc_display_present_status_v1*s){(void)c;assert(pending&&token==frames);if(frames==fail_present){pending=false;s->state=RISC_DISPLAY_PRESENT_FAILED;return true;}if((uint32_t)(now-submitted_at)<cost)s->state=RISC_DISPLAY_PRESENT_ACTIVE;else{pending=false;complete=frames;s->state=RISC_DISPLAY_PRESENT_COMPLETE;}return true;}
static bool brightness(void*c,uint16_t v,uint16_t maximum){(void)c;assert(wake_test&&ready&&maximum==100);if(!v)blank_calls++;else{assert(v==40&&!pending&&complete);light_calls++;}return true;}
static bool prepare(void*c){(void)c;assert(!owned&&!pending);return true;}
static bool resume(void*c){(void)c;return true;}
static bool key(void*c,uint32_t*events){(void)c;*events=0;if(wake_test&&ready&&sleeps<2&&(uint32_t)(now-ready_at)>=300u+sleeps*3000u){
 *events=2;
 if(sleep_failure==1)fail_submit=frames+1;
 if(sleep_failure==2)fail_present=frames+1;
 if(sleep_failure==3)fail_submit=frames+2;
 if(sleep_failure==4)fail_present=frames+2;
 }return true;}
static int32_t light_sleep(void*c,risc_light_sleep_result_v1*r){(void)c;(void)r;assert(!owned&&!pending);sleeps++;return refuse?RISC_LIGHT_SLEEP_ACTIVE_WAKE:RISC_LIGHT_SLEEP_OK;}
static bool read_rtc(void*c,twatch_rtc_time_v1*t){(void)c;*t=(twatch_rtc_time_v1){2026,10,4,0,0,40,0};return true;}
static bool read_battery(void*c,risc_battery_sample_v1*b){(void)c;*b=(risc_battery_sample_v1){3900,55,0};return true;}
static twatch_panel_power_v1 da={{1,TWATCH_PANEL_LIGHT_SLEEP_SIZE,NULL,info,acquire_frame,release_frame,submit_frame,present_frame,NULL,brightness},prepare,resume,NULL,NULL};
static twatch_pmu_api_v1 pa={{1,TWATCH_PMU_LIGHT_SLEEP_SIZE,NULL,read_battery},key,prepare,resume,light_sleep,NULL,NULL,NULL,NULL,NULL,NULL};
static twatch_rtc_api_v1 ra={2,sizeof(ra),NULL,read_rtc,NULL,NULL,NULL};
static bool acquire_cap(const char*n,uint32_t version,uint64_t id,risc_runtime_capability_v1*g){(void)version;assert(!id);grants++;if(!strcmp(n,"display.output"))g->api=&da;else if(!strcmp(n,"board.battery"))g->api=&pa;else{assert(!strcmp(n,"rtc.clock"));g->api=&ra;}return true;}
static bool release_cap(risc_runtime_capability_v1*g){assert(g->api&&!owned&&!pending);g->api=NULL;ungrants++;return true;}
static const risc_runtime_api_v1 runtime={1,sizeof(runtime),health,yield,diagnostic,NULL,acquire_cap,release_cap};
const risc_runtime_api_v1*risc_runtime_get_api(uint32_t v){assert(v==1);return &runtime;}
static void reset(uint32_t transfer_cost,uint32_t begin){
 assert(!allocations);now=epoch=begin;cost=transfer_cost;submitted_at=ready_at=frames=complete=grants=ungrants=0;
 allocation_calls=fail_allocation=blank_calls=light_calls=boot_calls=face_calls=sleeps=0;
 fail_acquire=fail_submit=fail_present=acquire_calls=return_frames=0;
 owned=pending=ready=stalled=invalid_surface=wake_test=refuse=false;stop_ready=true;stop_at=16000;sleep_failure=0;
 for(unsigned i=0;i<240*240;i++)pixels[i]=outgoing[i]=(uint16_t)((i*37u+1234u)%65536u);
}
static void clean(void){assert(!allocations&&!owned&&!pending&&grants==3&&ungrants==3);}
int main(void){
 for(unsigned wrap=0;wrap<2;wrap++)for(unsigned slow=0;slow<4;slow++){
  reset(slow==0?0:slow==1?7:slow==2?95:2000,wrap?UINT32_MAX-30:0);app_main();clean();
  assert(ready&&!boot_calls&&!blank_calls&&!light_calls&&return_frames<=4);
  assert((uint32_t)(ready_at-epoch)<=(cost>=60?cost*2+1:81));
 }
 for(unsigned failure=1;failure<=2;failure++){reset(7,0);fail_allocation=failure;app_main();clean();assert(ready&&return_frames==1&&!boot_calls);}
 for(unsigned failure=0;failure<7;failure++){
  reset(7,0);
  if(failure==0)fail_acquire=1;
  if(failure==1)fail_acquire=2;
  if(failure==2)fail_submit=1;
  if(failure==3)fail_present=2;
  if(failure==4)invalid_surface=true;
  if(failure==5)stop_at=3;
  if(failure==6)stalled=true;
  app_main();clean();assert(!ready&&!boot_calls&&!blank_calls&&!light_calls);
 }
 /* Reusing provider RAM must capture the current outgoing app every time. */
 for(unsigned entry=0;entry<3;entry++){reset(7,1000u*entry);app_main();clean();assert(ready&&!boot_calls);}
 /* Only a real wake runs the intro, including both repeated wakes in a
  * clock.elf invocation. Refused sleep preserves the normal Clock path. */
 for(unsigned denied=0;denied<2;denied++){reset(7,0);stop_ready=false;wake_test=true;refuse=denied;stop_at=6200;app_main();clean();assert(sleeps==2);if(denied)assert(!boot_calls&&blank_calls==4&&light_calls==2);else assert(boot_calls>100&&blank_calls==4&&light_calls==2);}
 for(unsigned failure=1;failure<=4;failure++){
  reset(7,0);stop_ready=false;wake_test=true;refuse=true;sleep_failure=failure;app_main();clean();
  assert(!boot_calls&&!light_calls&&sleeps==(failure<=2?0u:1u));
 }
 puts("Clock return: exact retained-to-live 60ms blend, no duplicate/blank/intro, async/wrap, allocation/failure/stall cleanup and repeated actual-wake intro passed");
}

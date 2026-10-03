#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "RiscRuntimeV1.h"
#include "twatch_caps.h"
#include "twatch_power.h"
#include "apps/clock/nova/nova.h"
void app_main(void);
static uint16_t pixels[240*240];
static uint32_t now,frames,grants,ungrants,sleeps,prepares,resumes,keys,events,mode;
static bool held,pending,panel_asleep,pmu_asleep;
static uint32_t epoch,frame_cost,present_started,present_polls,ready_at;
static bool ready,stop_on_ready,fail_present;
static uint32_t face_calls,rtc_reads,battery_reads,first_face_at,last_face_at,first_rtc_at,last_rtc_at,last_battery_at;
static uint32_t face_limit,rtc_kind,battery_kind,health_stop;
static uint32_t seen_valid,seen_invalid,seen_zero,seen_unknown,seen_phase;
static bool no_keys,refresh_needed;
static uint32_t rtc_before_resume,battery_before_resume;
bool test_nova_watch_render(risc_display_surface_v1*s,const nova_watch_state*f){
 nova_watch_labels labels; nova_watch_format(f,&labels);
 if(refresh_needed){assert(rtc_reads>rtc_before_resume&&battery_reads>battery_before_resume);refresh_needed=false;}
 if(!face_calls)first_face_at=now;
 face_calls++;last_face_at=now;
 assert(f->subsecond_ms<=999 && f->animation_ms==now);
 if(f->time_valid){seen_valid++;assert(!strcmp(labels.status,"RTC"));assert(!strcmp(labels.meridiem,"PM"));}
 else{seen_invalid++;assert(!strcmp(labels.status,"UNSET"));}
 if(f->battery_valid&&f->battery_percent==0){seen_zero++;assert(!strcmp(labels.battery,"0%"));}
 if(!f->battery_valid){seen_unknown++;assert(!strcmp(labels.battery,"--%"));}
 if(f->subsecond_ms>0 && f->subsecond_ms<999)seen_phase++;
 return nova_watch_render(s,f);
}
static uint32_t elapsed(void){return now-epoch;}
static bool health(risc_runtime_health_v1*h){h->uptime_ms=now;return elapsed()<(health_stop?health_stop:16000) && !(stop_on_ready&&ready) && !(face_limit&&face_calls>=face_limit);}
static void yield(uint32_t n){assert(n>=1&&n<=20);now+=n;}
static bool diagnostic(const char*s){
 assert(!strncmp(s,"WATCH_CLOCK ",12));
 if(!strcmp(s,"WATCH_CLOCK ready crown=enabled")){ready=true;ready_at=elapsed();}
 return true;
}
static bool info(void*c,risc_display_info_v1*s){(void)c;s->width=s->height=240;return true;}
static bool acquire_frame(void*c,uint32_t f,risc_display_surface_v1*s){(void)c;assert(!held&&!pending&&!panel_asleep&&f==5);held=true;*s=(risc_display_surface_v1){1,pixels,240,240,480,sizeof(pixels),5};return true;}
static void release_frame(void*c,uint64_t t){(void)c;assert(t==1&&held);held=false;}
static bool submit(void*c,uint64_t f,const risc_display_rect_v1*d,size_t n,const risc_display_present_options_v1*o,uint64_t*t){(void)c;(void)d;(void)n;(void)o;assert(f==1&&held&&!pending);if(stop_on_ready && frame_cost>=20 && frames)assert((uint32_t)(now-present_started)==frame_cost);held=false;pending=true;present_started=now;*t=++frames;return true;}
static bool present(void*c,uint64_t t,risc_display_present_status_v1*s){
 (void)c;assert(t==frames&&pending);present_polls++;
 if(fail_present&&present_polls==3){pending=false;s->state=RISC_DISPLAY_PRESENT_FAILED;}
 else if((uint32_t)(now-present_started)<frame_cost)s->state=RISC_DISPLAY_PRESENT_ACTIVE;
 else{pending=false;s->state=RISC_DISPLAY_PRESENT_COMPLETE;}
 return true;
}
static bool bright(void*c,uint16_t v,uint16_t m){(void)c;assert(v==40&&m==100);return true;}
static bool panel_prepare(void*c){
 (void)c;assert(!held&&!pending);
 for(unsigned i=0;i<240*240;i++)assert(pixels[i]==0);
 panel_asleep=true;return mode!=2;
}
static bool panel_resume(void*c){(void)c;panel_asleep=false;resumes++;refresh_needed=true;rtc_before_resume=rtc_reads;battery_before_resume=battery_reads;return mode!=3;}
static bool pmu_prepare(void*c){(void)c;assert(panel_asleep);pmu_asleep=true;prepares++;return true;}
static bool pmu_resume(void*c){(void)c;pmu_asleep=false;return true;}
static int32_t sleep_now(void*c,risc_light_sleep_result_v1*r){(void)c;assert(!held&&!pending&&panel_asleep&&pmu_asleep&&r->struct_size==sizeof(*r));sleeps++;r->wake_cause=RISC_LIGHT_SLEEP_WAKE_GPIO;return mode==1?RISC_LIGHT_SLEEP_ACTIVE_WAKE:RISC_LIGHT_SLEEP_OK;}
static bool key(void*c,uint32_t*out){(void)c;keys++;*out=0;if(!no_keys && events<2 && elapsed()>=5000+events*5000){*out=2;events++;}return true;}
static bool rtc_read(void*c,twatch_rtc_time_v1*t){
 (void)c;
 if(!rtc_reads)first_rtc_at=now;
 else if(no_keys)assert((uint32_t)(now-last_rtc_at)>=100);
 rtc_reads++;last_rtc_at=now;
 *t=(twatch_rtc_time_v1){2026,10,3,6,12,30,(uint8_t)((elapsed()/1000)%60)};
 if(rtc_kind==2)t->day=32;
 return rtc_kind!=1;
}
static bool battery_read(void*c,risc_battery_sample_v1*s){
 (void)c;
 if(battery_reads&&no_keys)assert((uint32_t)(now-last_battery_at)>=5000);
 battery_reads++;last_battery_at=now;
 *s=(risc_battery_sample_v1){3900,255,RISC_BATTERY_PROFILE_MISSING};
 if(battery_kind==1)*s=(risc_battery_sample_v1){3300,0,0};
 if(battery_kind==2)*s=(risc_battery_sample_v1){3300,0,RISC_BATTERY_PROFILE_MISSING};
 return battery_kind!=3;
}
static twatch_panel_power_v1 d={{1,sizeof(d),NULL,info,acquire_frame,release_frame,submit,present,NULL,bright},panel_prepare,panel_resume};
static twatch_pmu_api_v1 p={{1,sizeof(p),NULL,battery_read},key,pmu_prepare,pmu_resume,sleep_now};
static twatch_rtc_api_v1 r={2,sizeof(r),NULL,rtc_read,NULL,NULL,NULL};
static bool acquire(const char*n,uint32_t v,uint64_t id,risc_runtime_capability_v1*g){assert(!id&&g->struct_size==sizeof(*g));if(!strcmp(n,"display.output")){assert(v==1);g->api=&d;}else if(!strcmp(n,"board.battery")){assert(v==1);g->api=&p;}else{assert(!strcmp(n,"rtc.clock")&&v==2);g->api=&r;}grants++;return true;}
static bool release(risc_runtime_capability_v1*g){assert(g->api&&!held&&!pending);g->api=NULL;ungrants++;return true;}
static const risc_runtime_api_v1 api={1,sizeof(api),health,yield,diagnostic,NULL,acquire,release};
const risc_runtime_api_v1*risc_runtime_get_api(uint32_t v){assert(v==1);return &api;}
static void reset(uint32_t cost,uint32_t begin,bool stop){
 now=epoch=begin;frame_cost=cost;stop_on_ready=stop;
 frames=grants=ungrants=sleeps=prepares=resumes=keys=events=present_polls=ready_at=0;
 held=pending=panel_asleep=pmu_asleep=ready=fail_present=false;
 face_calls=rtc_reads=battery_reads=first_face_at=last_face_at=first_rtc_at=last_rtc_at=last_battery_at=0;
 face_limit=rtc_kind=battery_kind=health_stop=seen_valid=seen_invalid=seen_zero=seen_unknown=seen_phase=0;
 no_keys=refresh_needed=false;p.base.read=battery_read;
}
static void clean(void){assert(grants==3&&ungrants==3&&!held&&!pending&&!pmu_asleep&&!panel_asleep);}
int main(void){
 /* Preserve repeated sleep/wake and restoration coverage with genuinely async
  * completion too, rather than a status mock that always finishes immediately. */
 for(unsigned async=0;async<2;async++)for(mode=0;mode<4;mode++){
  reset(async?7:0,0,false);
  app_main();clean();assert(frames>20&&keys>1&&ready);
  if(async)assert(present_polls>frames);
  if(mode==0||mode==1)assert(sleeps==2&&resumes==2&&prepares==2);
  if(mode==2)assert(!sleeps&&resumes==2&&!prepares);
  if(mode==3)assert(sleeps==1&&resumes==1&&events==1);
 }
 /* A modeled two-second full-frame transfer used to spend 32 seconds on the
  * ripple alone. Now only the current scan and final scan are presented, then
  * the elapsed-time logo reaches its terminal frame. This is a host scenario,
  * not a hardware frame-rate measurement. Verify uptime wrap as well. */
 mode=0;
 for(unsigned wrap=0;wrap<2;wrap++){
  reset(2000,wrap?UINT32_MAX-200:0,true);
  app_main();clean();
  assert(ready&&ready_at<=8100&&frames==4&&present_polls>frames);
  assert(!sleeps&&!prepares&&!resumes);
 }
 reset(95,0,true);app_main();clean();
 assert(ready&&ready_at<2700&&frames<30&&present_polls>frames);
 /* A failed accepted async frame exits without sleeping or leaking its lease. */
 reset(20,0,false);fail_present=true;app_main();clean();
 assert(!ready&&frames==1&&present_polls==3&&!sleeps);
 /* Production NOVA is rendered continuously, not only when RTC seconds change.
  * Reads remain independently bounded; model slow presentation without adding
  * another 20ms delay. Wrap and failed/invalid telemetry preserve honest labels. */
 for(unsigned wrap=0;wrap<2;wrap++){
  reset(5,wrap?UINT32_MAX-2500:0,false);no_keys=true;face_limit=301;battery_kind=1;
  app_main();clean();
  assert(face_calls==301&&seen_valid==301&&seen_zero==301&&seen_phase>200);
  assert((uint32_t)(last_face_at-first_face_at)==6000);
  assert(rtc_reads==61&&battery_reads==2);
 }
 for(unsigned kind=0;kind<4;kind++){
  reset(95,0,false);no_keys=true;face_limit=25;rtc_kind=kind?kind%2+1:0;battery_kind=kind;
  app_main();clean();
  assert(face_calls==25&&(uint32_t)(last_face_at-first_face_at)==24*95);
  assert(battery_reads==1&&rtc_reads==13);
  if(rtc_kind)assert(seen_invalid==25);else assert(seen_valid==25);
  if(battery_kind==1)assert(seen_zero==25);else assert(seen_unknown==25);
 }
 reset(5,0,false);no_keys=true;face_limit=2;p.base.read=NULL;
 app_main();clean();assert(seen_unknown==2&&!battery_reads);
 /* Health loss inside an accepted frame drains that operation before release. */
 reset(7,0,false);no_keys=true;health_stop=3001;
 app_main();clean();assert(ready&&face_calls>20);
 puts("Crown/NOVA: continuous real frames, independent telemetry, 12h labels, unknown/zero battery, wake refresh, health drain, async pacing and failures passed");
}

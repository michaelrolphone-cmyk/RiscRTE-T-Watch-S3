#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "RiscRuntimeV1.h"
#include "twatch_caps.h"
#include "twatch_power.h"
#include "apps/clock/nova/nova.h"
#include "apps/clock/effects/effects.h"
void app_main(void);
static uint16_t pixels[240*240],sharp_pixels[240*240],logo_pixels[240*240],gram_pixels[240*240];
static unsigned black_frames,black_resume_checks;
static bool black_image(const uint16_t *p){for(unsigned i=0;i<240*240;i++)if(p[i])return false;return true;}
static unsigned allocated,allocation_calls,allocation_failure,mixed_frames,exact_clock_frames,exact_logo_frames;
static uint32_t transition_started;
static bool transition_started_valid;
void *test_clock_malloc(size_t n){assert(n==sizeof(pixels));allocation_calls++;if(allocation_calls==allocation_failure)return NULL;void*p=malloc(n);if(p)allocated++;return p;}
void test_clock_free(void*p){if(p){assert(allocated);allocated--;}free(p);}
static uint32_t now,frames,grants,ungrants,sleeps,prepares,resumes,keys,events,mode;
static bool held,pending,panel_asleep,pmu_asleep;
static uint32_t visible_level,blanked_after,last_complete,blank_calls,unblank_calls,brightness_failure;
static uint32_t epoch,frame_cost,present_started,present_polls,ready_at;
static bool ready,stop_on_ready,fail_present,fail_transition,freeze_transition;
static uint32_t face_calls,rtc_reads,battery_reads,first_face_at,last_face_at,first_rtc_at,last_rtc_at,last_battery_at;
static uint32_t face_limit,rtc_kind,battery_kind,health_stop;
static uint32_t seen_valid,seen_invalid,seen_zero,seen_unknown,seen_phase;
static bool no_keys,refresh_needed;
static uint32_t rtc_before_resume,battery_before_resume;
static bool frame_is_boot,frame_is_final_boot,expect_boot_hold,freeze_boot_hold;
static uint32_t final_boot_done,boot_calls,last_boot_age,panel_attempts,key_scenario;
static uint32_t sleep_times[8],attempt_times[8];
bool test_watch_boot_render(risc_display_surface_v1*s,uint32_t age){
 if(!s->frame)return watch_boot_render(s,age);
 if(frames==blanked_after)assert(visible_level==0);
 frame_is_boot=true;frame_is_final_boot=age==1800;boot_calls++;last_boot_age=age;
 bool ok=watch_boot_render(s,age);if(ok&&age==1800)memcpy(logo_pixels,s->pixels,sizeof(logo_pixels));return ok;
}
bool test_watch_ripple_render(risc_display_surface_v1*s,unsigned scan){
 (void)s;(void)scan;assert(!"Screen scrub must not run on startup or lock");return false;
}
bool test_nova_watch_render(risc_display_surface_v1*s,const nova_watch_state*f){
 nova_watch_labels labels; nova_watch_format(f,&labels);
 if(expect_boot_hold){assert((uint32_t)(now-final_boot_done)==250);expect_boot_hold=false;transition_started=now;transition_started_valid=true;}
 frame_is_boot=frame_is_final_boot=false;
 if(refresh_needed){assert(rtc_reads>rtc_before_resume&&battery_reads>battery_before_resume);refresh_needed=false;}
 if(!face_calls)first_face_at=now;
 face_calls++;last_face_at=now;
 assert(f->subsecond_ms<=999 && f->animation_ms==now);
 if(f->time_valid){seen_valid++;assert(!strcmp(labels.status,"RTC"));if(rtc_kind==4){assert(!strcmp(labels.meridiem,"AM"));assert(!strcmp(labels.hour_minute,"10:40"));assert(f->time.year==2026&&f->time.month==10&&f->time.day==3&&f->time.weekday==6);}
 else{assert(!strcmp(labels.meridiem,"PM"));assert(f->time.year==2026&&f->time.month==10&&f->time.day==2&&f->time.hour==22&&f->time.minute==30);}}
 else{seen_invalid++;assert(!strcmp(labels.status,"UNSET"));}
 if(f->battery_valid&&f->battery_percent==0){seen_zero++;assert(!strcmp(labels.battery,"0%"));}
 if(!f->battery_valid){seen_unknown++;assert(!strcmp(labels.battery,"--%"));}
 if(f->subsecond_ms>0 && f->subsecond_ms<999)seen_phase++;
 bool ok=nova_watch_render(s,f);if(ok)memcpy(sharp_pixels,s->pixels,sizeof(sharp_pixels));return ok;
}
static uint32_t elapsed(void){return now-epoch;}
static bool health(risc_runtime_health_v1*h){h->uptime_ms=now;return elapsed()<(health_stop?health_stop:16000) && !(stop_on_ready&&ready) && !(face_limit&&face_calls>=face_limit);}
static void yield(uint32_t n){assert(n>=1&&n<=20);if(!(freeze_boot_hold&&expect_boot_hold)&&!(freeze_transition&&transition_started_valid))now+=n;}
static bool diagnostic(const char*s){
 assert(!strncmp(s,"WATCH_CLOCK ",12));
 if(!strcmp(s,"WATCH_CLOCK ready crown=enabled")){ready=true;ready_at=elapsed();assert(last_boot_age==1800);assert((uint32_t)(now-final_boot_done)>=250);assert(exact_clock_frames);}
 return true;
}
static bool info(void*c,risc_display_info_v1*s){(void)c;s->width=s->height=240;return true;}
static bool acquire_frame(void*c,uint32_t f,risc_display_surface_v1*s){(void)c;assert(!held&&!pending&&!panel_asleep&&f==5);held=true;*s=(risc_display_surface_v1){1,pixels,240,240,480,sizeof(pixels),5};return true;}
static void release_frame(void*c,uint64_t t){(void)c;assert(t==1&&held);held=false;}
static bool submit(void*c,uint64_t f,const risc_display_rect_v1*d,size_t n,const risc_display_present_options_v1*o,uint64_t*t){(void)c;(void)d;(void)n;(void)o;assert(f==1&&held&&!pending);if(stop_on_ready && frame_cost>=20 && frames && !(transition_started_valid && now==transition_started))assert((uint32_t)(now-present_started)==frame_cost);
 if(!frame_is_boot && black_image(pixels)){assert(visible_level==0);black_frames++;}
 else if(!frame_is_boot){
  bool sharp=!memcmp(pixels,sharp_pixels,sizeof(pixels)),logo=!memcmp(pixels,logo_pixels,sizeof(pixels));
  if(transition_started_valid && (uint32_t)(now-transition_started)<180 && !allocation_failure){if(now==transition_started){assert(logo&&!sharp);exact_logo_frames++;}else{assert(!sharp&&!logo);mixed_frames++;}}
  else{assert(sharp);exact_clock_frames++;}
 }held=false;pending=true;present_started=now;*t=++frames;return true;}
static bool present(void*c,uint64_t t,risc_display_present_status_v1*s){
 (void)c;assert(t==frames&&pending);present_polls++;
 if((fail_present&&present_polls==3)||(fail_transition&&mixed_frames>=2)){pending=false;s->state=RISC_DISPLAY_PRESENT_FAILED;}
 else if((uint32_t)(now-present_started)<frame_cost)s->state=RISC_DISPLAY_PRESENT_ACTIVE;
 else{pending=false;last_complete=frames;memcpy(gram_pixels,pixels,sizeof(gram_pixels));s->state=RISC_DISPLAY_PRESENT_COMPLETE;if(frame_is_final_boot){final_boot_done=now;expect_boot_hold=true;}}
 return true;
}
static bool bright(void*c,uint16_t v,uint16_t m){
 (void)c;assert((v==0||v==40)&&m==100);
 if(!v){blank_calls++;if(brightness_failure==1)return false;blanked_after=frames;visible_level=0;}
 else{assert(!pending&&last_complete==frames&&frames>blanked_after);unblank_calls++;if(brightness_failure==2)return false;visible_level=40;}
 return true;
}
static bool panel_prepare(void*c){
 (void)c;assert(!held&&!pending);
 assert(!frame_is_boot&&visible_level==0&&black_image(gram_pixels));assert(panel_attempts<8);attempt_times[panel_attempts++]=elapsed();
 panel_asleep=true;return mode!=2;
}
static bool panel_resume(void*c){(void)c;
 /* Model an unwanted backlight pulse exposing retained panel RAM before the
  * resume hook takes control. Its visible contents must already be black. */
 visible_level=40;assert(black_image(gram_pixels));black_resume_checks++;visible_level=0;
 panel_asleep=false;resumes++;refresh_needed=true;rtc_before_resume=rtc_reads;battery_before_resume=battery_reads;return mode!=3;}
static bool pmu_prepare(void*c){(void)c;assert(panel_asleep);pmu_asleep=true;prepares++;return mode!=4;}
static bool pmu_resume(void*c){(void)c;pmu_asleep=false;return true;}
static int32_t sleep_now(void*c,risc_light_sleep_result_v1*r){(void)c;assert(!held&&!pending&&panel_asleep&&pmu_asleep&&r->struct_size==sizeof(*r));assert(sleeps<8);sleep_times[sleeps++]=elapsed();r->wake_cause=RISC_LIGHT_SLEEP_WAKE_GPIO;return mode==1?RISC_LIGHT_SLEEP_ACTIVE_WAKE:RISC_LIGHT_SLEEP_OK;}
static bool key(void*c,uint32_t*out){
 (void)c;keys++;*out=0;
 if(key_scenario==1 && ready && !events && elapsed()>=ready_at+30000){*out=1;events++;}
 else if(!no_keys && !key_scenario && events<2 && elapsed()>=5000+events*5000){*out=2;events++;}
 return true;
}
static bool rtc_read(void*c,twatch_rtc_time_v1*t){
 (void)c;
 if(!rtc_reads)first_rtc_at=now;
 else if(no_keys&&!refresh_needed)assert((uint32_t)(now-last_rtc_at)>=100);
 rtc_reads++;last_rtc_at=now;
 *t=(twatch_rtc_time_v1){2026,10,3,6,12,30,(uint8_t)((elapsed()/1000)%60)};
 if(rtc_kind==2)t->day=32;
 if(rtc_kind==4)*t=(twatch_rtc_time_v1){2026,10,4,0,0,40,0};
 return rtc_kind!=1;
}
static bool rtc_write(void*c,const twatch_rtc_time_v1*t){(void)c;(void)t;assert(!"Display offset must not write RTC");return false;}
static bool battery_read(void*c,risc_battery_sample_v1*s){
 (void)c;
 if(battery_reads&&no_keys&&!refresh_needed)assert((uint32_t)(now-last_battery_at)>=5000);
 battery_reads++;last_battery_at=now;
 *s=(risc_battery_sample_v1){3900,255,RISC_BATTERY_PROFILE_MISSING};
 if(battery_kind==1)*s=(risc_battery_sample_v1){3300,0,0};
 if(battery_kind==2)*s=(risc_battery_sample_v1){3300,0,RISC_BATTERY_PROFILE_MISSING};
 return battery_kind!=3;
}
static twatch_panel_power_v1 d={{1,TWATCH_PANEL_LIGHT_SLEEP_SIZE,NULL,info,acquire_frame,release_frame,submit,present,NULL,bright},panel_prepare,panel_resume,NULL,NULL};
static twatch_pmu_api_v1 p={{1,TWATCH_PMU_LIGHT_SLEEP_SIZE,NULL,battery_read},key,pmu_prepare,pmu_resume,sleep_now,NULL,NULL,NULL,NULL};
static twatch_rtc_api_v1 r={2,sizeof(r),NULL,rtc_read,rtc_write,NULL,NULL};
static bool acquire(const char*n,uint32_t v,uint64_t id,risc_runtime_capability_v1*g){assert(!id&&g->struct_size==sizeof(*g));if(!strcmp(n,"display.output")){assert(v==1);g->api=&d;}else if(!strcmp(n,"board.battery")){assert(v==1);g->api=&p;}else{assert(!strcmp(n,"rtc.clock")&&v==2);g->api=&r;}grants++;return true;}
static bool release(risc_runtime_capability_v1*g){assert(g->api&&!held&&!pending);g->api=NULL;ungrants++;return true;}
static const risc_runtime_api_v1 api={1,sizeof(api),health,yield,diagnostic,NULL,acquire,release};
const risc_runtime_api_v1*risc_runtime_get_api(uint32_t v){assert(v==1);return &api;}
static void reset(uint32_t cost,uint32_t begin,bool stop){
 now=epoch=begin;frame_cost=cost;stop_on_ready=stop;
 assert(!allocated);allocation_calls=allocation_failure=mixed_frames=exact_clock_frames=exact_logo_frames=0;transition_started=0;transition_started_valid=false;
 visible_level=40;blanked_after=last_complete=blank_calls=unblank_calls=brightness_failure=0;
 frames=grants=ungrants=sleeps=prepares=resumes=keys=events=present_polls=ready_at=0;
 held=pending=panel_asleep=pmu_asleep=ready=fail_present=fail_transition=freeze_transition=false;
 face_calls=rtc_reads=battery_reads=first_face_at=last_face_at=first_rtc_at=last_rtc_at=last_battery_at=0;
 face_limit=rtc_kind=battery_kind=health_stop=seen_valid=seen_invalid=seen_zero=seen_unknown=seen_phase=0;
 no_keys=refresh_needed=frame_is_boot=frame_is_final_boot=expect_boot_hold=freeze_boot_hold=false;p.base.read=battery_read;
 final_boot_done=boot_calls=last_boot_age=panel_attempts=key_scenario=black_frames=black_resume_checks=0;
}
static void clean(void){assert(black_frames==panel_attempts&&black_resume_checks==resumes);assert(!allocated);assert(grants==3&&ungrants==3&&!held&&!pending&&!pmu_asleep&&!panel_asleep);}
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
 /* Startup has no scrub. Slow asynchronous logo frames still end with exactly
  * 250ms holding the completed final frame. Verify uptime wrap as well. */
 mode=0;
 for(unsigned wrap=0;wrap<2;wrap++){
  reset(2000,wrap?UINT32_MAX-200:0,true);
  app_main();clean();
  assert(ready&&ready_at==8250&&frames==4&&present_polls>frames);
  assert(!sleeps&&!prepares&&!resumes);
 }
 reset(95,0,true);app_main();clean();
 assert(ready&&ready_at<3000&&frames<30&&present_polls>frames);
 /* A failed accepted async frame exits without sleeping or leaking its lease. */
 reset(20,0,false);fail_present=true;app_main();clean();
 assert(!ready&&frames==1&&present_polls==3&&!sleeps&&visible_level==0&&!unblank_calls);
 /* Failed blank or unblank never enables the retained image. */
 reset(7,0,false);brightness_failure=1;app_main();assert(grants==1&&ungrants==1&&!frames&&!unblank_calls);
 reset(7,0,false);brightness_failure=2;app_main();clean();assert(frames==1&&visible_level==0&&!ready);
 /* Either temporary allocation may fail. A completed sharp frame still
  * replaces the logo, and every successful allocation is freed. */
 for(unsigned fail=1;fail<=2;fail++){reset(7,0,true);allocation_failure=fail;app_main();clean();assert(ready&&exact_clock_frames==1&&!mixed_frames&&!exact_logo_frames);}
 reset(7,0,true);app_main();clean();assert(mixed_frames==8&&exact_logo_frames==1&&exact_clock_frames==1);
 /* Failed or interrupted blending releases both temporary images. A stalled
  * uptime cannot turn the transition into an unbounded loop. */
 reset(7,0,false);fail_transition=true;app_main();clean();assert(!ready&&mixed_frames==2);
 reset(7,0,false);health_stop=2141;app_main();clean();assert(!ready&&mixed_frames>0);
 reset(0,0,false);freeze_transition=true;app_main();clean();assert(!ready&&exact_logo_frames==100);
 /* Repeated invocations share the same provider/pixel storage. */
 for(unsigned entry=0;entry<3;entry++){reset(95,0,true);app_main();clean();assert(blank_calls==1&&unblank_calls==1&&ready);}
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
 /* The reported next-day RTC case reaches the actual NOVA labels as 10:40 AM Saturday. */
 reset(5,0,false);no_keys=true;face_limit=2;rtc_kind=4;app_main();clean();assert(seen_valid==2);
 /* Holding the completed logo is bounded under both shutdown and clock stall. */
 reset(7,0,false);no_keys=true;health_stop=1900;app_main();clean();assert(!ready&&!face_calls);
 reset(7,0,false);no_keys=true;freeze_boot_hold=true;app_main();clean();assert(!ready&&!face_calls);
 /* Inactivity begins after the final boot-frame hold, and restarts after wake
  * or refusal. No touch capability is acquired and no per-frame retry storm. */
 for(unsigned wrap=0;wrap<2;wrap++)for(unsigned failure=0;failure<4;failure++){
  mode=failure==3?4:failure;reset(7,wrap?UINT32_MAX-5000:0,false);
  no_keys=true;health_stop=132000;app_main();clean();
  assert(panel_attempts==2&&resumes==2);
  assert(attempt_times[0]>=ready_at+60000&&attempt_times[0]<ready_at+60040);
  uint32_t between=attempt_times[1]-attempt_times[0];
  if(mode==0){assert(sleeps==2&&between>=62250&&between<62300);}
  else{assert(between==60014);if(mode==1)assert(sleeps==2);else assert(!sleeps);}
 }
 /* The supported PMU long-press event resets idle time but does not request
  * manual sleep; a held key is rejected by PMU preparation (mode4 above). */
 mode=0;reset(7,0,false);no_keys=true;key_scenario=1;health_stop=96000;
 app_main();clean();assert(events==1&&sleeps==1);
 assert(sleep_times[0]>=ready_at+90000&&sleep_times[0]<ready_at+90040);
 puts("Crown/NOVA: gated startup, 250ms logo hold, 180ms joint blur/crossfade, allocation fallback, 60s inactivity/refusal/wrap, telemetry and lifecycle passed");
}

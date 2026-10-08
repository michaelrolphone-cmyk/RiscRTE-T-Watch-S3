/* Actual local adapter: retained state must survive with or without alarms. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "PortableAppSleep.h"
#include "twatch_power.h"
#include "twatch_caps.h"
static uint16_t pixels[240*240],saved_pixels[240*240];
static void *saved_allocation;
static bool native_retained,frame_owned,frame_pending;
static unsigned frees,acquires,submits,brightness_calls,light_calls,deep_calls;
static unsigned pmu_resumes,panel_resumes,key_calls,alarm_resumes,refreshes;
static int32_t light_result,deep_result,panel_prepare_result,panel_restore_result;
static bool timer_wake,crown_pending;
static uint32_t rtc_seconds;
static void *tracked_malloc(size_t bytes){assert(!native_retained&&!saved_allocation);saved_allocation=malloc(bytes);return saved_allocation;}
static void tracked_free(void *ptr){assert(!native_retained&&ptr==saved_allocation);frees++;free(ptr);saved_allocation=NULL;}
#define malloc tracked_malloc
#define free tracked_free
#include "apps/clock/portable_sleep.c"
#undef malloc
#undef free
#ifdef PORTABLE_LOW_BATTERY
uint32_t portable_quick_sleep_light_ms(void){return 60000;}
unsigned portable_quick_brightness(void){return 40;}
#endif
static void io_allowed(void){assert(!native_retained);}
static bool diagnostic(const char*s){assert(s);return true;}
static void yield_ms(uint32_t ms){io_allowed();assert(ms);}
static bool acquire_frame(void*c,uint32_t format,risc_display_surface_v1*out){(void)c;io_allowed();assert(!frame_owned&&!frame_pending&&format==RISC_DISPLAY_FORMAT_RGB565);frame_owned=true;acquires++;*out=(risc_display_surface_v1){1,pixels,240,240,480,sizeof(pixels),RISC_DISPLAY_FORMAT_RGB565};return true;}
static void release_frame(void*c,uint64_t token){(void)c;io_allowed();assert(token==1&&frame_owned);frame_owned=false;}
static bool submit_frame(void*c,uint64_t frame,const risc_display_rect_v1*d,size_t n,const risc_display_present_options_v1*o,uint64_t*t){(void)c;(void)d;(void)o;io_allowed();assert(frame==1&&frame_owned&&!n);frame_owned=false;frame_pending=true;*t=++submits;return true;}
static bool status_frame(void*c,uint64_t token,risc_display_present_status_v1*out){(void)c;io_allowed();assert(frame_pending&&token==submits);frame_pending=false;out->state=RISC_DISPLAY_PRESENT_COMPLETE;return true;}
static bool brightness(void*c,uint16_t value,uint16_t maximum){(void)c;io_allowed();assert((value==0||value==40)&&maximum==100);brightness_calls++;return true;}
static bool prepare_panel(void*c){(void)c;io_allowed();assert(!frame_owned&&!frame_pending&&submits==1);for(unsigned i=0;i<240*240;i++)assert(!pixels[i]);return true;}
static int32_t prepare_deep(void*c){(void)c;io_allowed();if(panel_prepare_result==RISC_DEEP_SLEEP_RETAINED)native_retained=true;return panel_prepare_result;}
static bool prepare_pmu(void*c){(void)c;io_allowed();return true;}
static bool resume_pmu(void*c){(void)c;io_allowed();pmu_resumes++;return true;}
static bool resume_panel(void*c){(void)c;io_allowed();panel_resumes++;return panel_restore_result==0;}
static int32_t resume_panel_status(void*c){(void)c;io_allowed();panel_resumes++;if(panel_restore_result==RISC_DEEP_SLEEP_RETAINED)native_retained=true;return panel_restore_result;}
static bool key_events(void*c,uint32_t*out){(void)c;io_allowed();key_calls++;*out=0;return true;}
static bool wake_pending(void*c,bool*out){(void)c;io_allowed();*out=crown_pending;return true;}
static int32_t light_sleep_for(void*c,uint32_t ms,risc_light_sleep_result_v1*out){(void)c;io_allowed();assert(ms==WATCH_SLEEP_LIGHT_MS);light_calls++;out->wake_cause=timer_wake?RISC_LIGHT_SLEEP_WAKE_TIMER:RISC_LIGHT_SLEEP_WAKE_GPIO;if(light_result==0)rtc_seconds+=ms/1000;if(light_result==RISC_LIGHT_SLEEP_RETAINED)native_retained=true;return light_result;}
static int32_t light_sleep(void*c,risc_light_sleep_result_v1*out){return light_sleep_for(c,WATCH_SLEEP_LIGHT_MS,out);}
static int32_t deep_sleep(void*c){(void)c;io_allowed();deep_calls++;if(deep_result>=0||deep_result==RISC_DEEP_SLEEP_RETAINED)native_retained=true;return deep_result;}
static int32_t deep_sleep_for(void*c,uint32_t ms){assert(ms==(2000-rtc_seconds)*1000u);return deep_sleep(c);}
#ifdef PORTABLE_ALARM_CLIENT
static int32_t alarm_prepare(void*c,alarm_sleep_v1*out){(void)c;io_allowed();*out=(alarm_sleep_v1){sizeof(*out),1,rtc_seconds,2000};return ALARM_OK;}
static int32_t alarm_resume(void*c,const alarm_sleep_v1*decision){(void)c;io_allowed();assert(decision->snapshot==1&&decision->rtc_seconds==1000&&decision->deadline==2000);alarm_resumes++;return ALARM_OK;}
static int32_t alarm_refresh(void*c){(void)c;io_allowed();refreshes++;return ALARM_PENDING;}
static alarm_service_sleep_v1 alarms={.base={.api_version=1,.struct_size=sizeof(alarms),.refresh=alarm_refresh,.prepare_sleep=alarm_prepare},.resume_sleep=alarm_resume};
#endif
static twatch_panel_power_v1 panel={.base={.api_version=1,.struct_size=sizeof(panel),.acquire=acquire_frame,.release=release_frame,.submit=submit_frame,.present_status=status_frame,.set_brightness=brightness},.prepare_sleep=prepare_panel,.resume=resume_panel,.prepare_deep_sleep=prepare_deep,.resume_status=resume_panel_status};
static const twatch_pmu_api_v1 pmu={.base={.api_version=1,.struct_size=sizeof(pmu)},.key_events=key_events,.prepare_sleep=prepare_pmu,.resume=resume_pmu,.light_sleep=light_sleep,.deep_sleep=deep_sleep,.light_sleep_for=light_sleep_for,.sleep_wake_pending=wake_pending,.deep_sleep_for=deep_sleep_for};
static const risc_runtime_api_v1 runtime={.api_version=1,.struct_size=sizeof(runtime),.yield_ms=yield_ms,.diagnostic=diagnostic};
static void reset(void){assert(!saved_allocation);native_retained=frame_owned=frame_pending=false;frees=acquires=submits=brightness_calls=light_calls=deep_calls=pmu_resumes=panel_resumes=key_calls=alarm_resumes=refreshes=0;light_result=0;deep_result=RISC_DEEP_SLEEP_ACTIVE_WAKE;panel_prepare_result=panel_restore_result=0;timer_wake=crown_pending=false;rtc_seconds=1000;panel.base.struct_size=sizeof(panel);for(unsigned i=0;i<240*240;i++)saved_pixels[i]=pixels[i]=(uint16_t)(i^0x5a5a);}
static void run(int expected){
#ifdef PORTABLE_ALARM_CLIENT
 int result=portable_app_alarm_sleep(&runtime,&panel.base,&pmu.base,&alarms.base);
#else
 int result=portable_app_sleep(&runtime,&panel.base,&pmu.base);
#endif
 assert(result==expected&&!frame_owned&&!frame_pending);
 if(expected==WATCH_SLEEP_RETAINED){
  assert(native_retained&&saved_allocation&&!frees&&submits==1&&brightness_calls==1&&!key_calls&&!refreshes);
  assert(!memcmp(saved_allocation,saved_pixels,sizeof(saved_pixels)));
  /* Harness simulates the eventual CPU reset; the production adapter did not
   * free the retained app image or perform any provider I/O after retention. */
  free(saved_allocation);saved_allocation=NULL;
 }else{
  assert(!native_retained&&!saved_allocation&&frees==1);
  if(expected>=0)assert(submits==2&&brightness_calls==3&&!memcmp(pixels,saved_pixels,sizeof(pixels)));
  else assert(submits==1&&brightness_calls==1);
 }
}
int main(void){
 for(unsigned cycle=0;cycle<3;cycle++){
  for(int32_t rc=RISC_LIGHT_SLEEP_UNSUPPORTED;rc<=RISC_LIGHT_SLEEP_OK;rc++){
   reset();light_result=rc;run(rc==RISC_LIGHT_SLEEP_RETAINED?WATCH_SLEEP_RETAINED:rc==0?WATCH_SLEEP_WOKE:WATCH_SLEEP_REFUSED);
   assert(light_calls==1&&!deep_calls);
   if(rc==RISC_LIGHT_SLEEP_RETAINED)assert(!pmu_resumes&&!panel_resumes&&!alarm_resumes);
   else assert(pmu_resumes==1&&panel_resumes==1);
  }
  for(int32_t rc=RISC_DEEP_SLEEP_UNSUPPORTED;rc<=1;rc++){
   reset();timer_wake=true;deep_result=rc;run(rc==RISC_DEEP_SLEEP_RETAINED||rc>=0?WATCH_SLEEP_RETAINED:WATCH_SLEEP_REFUSED);
   assert(light_calls==1&&deep_calls==1);
  }
  reset();timer_wake=true;panel_prepare_result=RISC_DEEP_SLEEP_RETAINED;run(WATCH_SLEEP_RETAINED);assert(!deep_calls&&!pmu_resumes&&!panel_resumes);
  reset();panel_restore_result=RISC_DEEP_SLEEP_RETAINED;run(WATCH_SLEEP_RETAINED);assert(pmu_resumes==1&&panel_resumes==1);
  reset();panel_restore_result=RISC_LIGHT_SLEEP_PLATFORM;run(WATCH_SLEEP_FAILED);assert(pmu_resumes==1&&panel_resumes==1&&!key_calls);
  reset();timer_wake=true;crown_pending=true;run(WATCH_SLEEP_WOKE);assert(!deep_calls);
  reset();panel.base.struct_size=TWATCH_PANEL_DEEP_SLEEP_SIZE;run(WATCH_SLEEP_WOKE);assert(pmu_resumes==1&&panel_resumes==1);
 }
 puts("Portable sleep lifecycle: repeated native statuses, unexpected Deep return, retained preparation/unhold, old ABI, crown priority and exact app image custody PASS");
 return 0;
}

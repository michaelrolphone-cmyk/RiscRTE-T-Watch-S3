#include <assert.h>
#include <string.h>
#include "RiscRuntimeV1.h"
#include "RiscDisplayOutputV1.h"
#include "twatch_caps.h"
void app_main(void);
static uint16_t pixels[240*240];
static uint32_t now,limit,submits,releases,reads,yields,frames_released,diagnostics;
static bool no_display,no_rtc,bad_rtc,submit_error,bad_surface,held,present_failure,stuck;
static risc_display_present_token_v1 latest;
static bool health(risc_runtime_health_v1 *h){assert(h->struct_size==sizeof(*h));h->uptime_ms=now;return now<limit;}
static void yield_ms(uint32_t ms){assert(ms==1 || ms==20);now+=ms;yields++;}
static bool log_line(const char *line){assert(strncmp(line,"WATCH_CLOCK ",12)==0);diagnostics++;return true;}
static bool info(void*c,risc_display_info_v1*out){(void)c;out->width=240;out->height=240;out->supported_formats=RISC_DISPLAY_FORMAT_BIT(RISC_DISPLAY_FORMAT_RGB565);return true;}
static bool acquire_frame(void*c,uint32_t fmt,risc_display_surface_v1*out){(void)c;assert(fmt==5 && !held);held=true;*out=(risc_display_surface_v1){1,pixels,240,240,480,bad_surface?10:sizeof(pixels),5};return true;}
static void release_frame(void*c,uint64_t frame){(void)c;assert(frame==1 && held);held=false;frames_released++;}
static bool submit(void*c,uint64_t frame,const risc_display_rect_v1*d,size_t count,const risc_display_present_options_v1*o,uint64_t*out){(void)c;assert(held&&frame==1&&!d&&!count&&o->queue_policy==0);if(submit_error)return false;held=false;*out=++latest;submits++;return true;}
static bool present(void*c,uint64_t token,risc_display_present_status_v1*out){(void)c;assert(token==latest);out->state=stuck?RISC_DISPLAY_PRESENT_ACTIVE:present_failure?RISC_DISPLAY_PRESENT_FAILED:RISC_DISPLAY_PRESENT_COMPLETE;return true;}
static bool brightness(void*c,uint16_t level,uint16_t maximum){(void)c;assert(level==40&&maximum==100);return true;}
static bool rtc_read(void*c,twatch_rtc_time_v1*out){(void)c;reads++;*out=(twatch_rtc_time_v1){2028,2,29,2,12,34,(uint8_t)((now/1000)%60)};if(bad_rtc)out->year=2027;return true;}
static bool forbidden_write(void*c,const twatch_rtc_time_v1*t){(void)c;(void)t;assert(!"clock app must never write RTC");return false;}
static risc_display_output_api_v1 display={1,sizeof(display),NULL,info,acquire_frame,release_frame,submit,present,NULL,brightness};
static twatch_rtc_api_v1 rtc={2,sizeof(rtc),NULL,rtc_read,forbidden_write,NULL,NULL};
static bool acquire(const char*name,uint32_t version,uint64_t instance,risc_runtime_capability_v1*out){assert(out->struct_size==sizeof(*out)&&instance==0);if(!strcmp(name,"display.output")){assert(version==1);if(no_display)return false;out->api=&display;out->slot=1;}else{assert(!strcmp(name,"rtc.clock")&&version==2);if(no_rtc)return false;out->api=&rtc;out->slot=2;}out->generation=1;return true;}
static bool release(risc_runtime_capability_v1*grant){assert(!held&&grant->generation==1);grant->generation=0;grant->api=NULL;releases++;return true;}
static risc_runtime_api_v1 api={1,sizeof(api),health,yield_ms,log_line,NULL,acquire,release};
const risc_runtime_api_v1*risc_runtime_get_api(uint32_t version){assert(version==1);return &api;}
static void reset(void){now=0;limit=2100;submits=releases=reads=yields=frames_released=diagnostics=0;no_display=no_rtc=bad_rtc=submit_error=bad_surface=held=present_failure=stuck=false;latest=0;api.struct_size=sizeof(api);display.struct_size=sizeof(display);rtc.struct_size=sizeof(rtc);}
static uint32_t checksum(void){uint32_t h=2166136261;for(unsigned i=0;i<240*240;i++)h=(h^pixels[i])*16777619;return h;}
int main(void){
 reset();app_main();assert(submits==3&&reads==3&&releases==2&&yields>0&&!held);
 reset();no_rtc=true;limit=1;app_main();assert(submits==1&&reads==0&&releases==1);uint32_t unset=checksum();
 reset();bad_rtc=true;limit=1;app_main();assert(checksum()==unset&&reads==1&&releases==2);
 reset();no_display=true;app_main();assert(!submits&&!releases&&diagnostics==1);
 reset();submit_error=true;app_main();assert(!submits&&frames_released==1&&releases==2&&!held);
 reset();bad_surface=true;app_main();assert(!submits&&frames_released==1&&releases==2&&!held);
 reset();present_failure=true;app_main();assert(submits==1&&releases==2&&!held);
 reset();stuck=true;limit=20000;app_main();assert(submits==1&&now>10000&&now<10003&&releases==2&&!held);
 reset();api.struct_size=RISC_RUNTIME_CAPABILITIES_V1_SIZE-1;app_main();assert(!submits&&!releases);
 reset();display.struct_size=sizeof(display)-1;app_main();assert(!submits&&releases==1);
 return 0;
}

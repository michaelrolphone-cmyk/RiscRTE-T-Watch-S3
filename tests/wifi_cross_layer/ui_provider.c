/* Bounded UI transports for executing the unmodified app under real Runtime.
 * The network provider and alarm service are the actual production ELFs. */
#include "RiscProviderV2.h"
#include "RiscDisplayOutputV1.h"
#include "RiscTouchV1.h"
#include "RiscInputNavigationV1.h"
#include <string.h>
#include <assert.h>
extern void wifi_ui_event(const char*);
extern uint32_t wifi_ui_buttons(void);
extern bool wifi_ui_fail_frame(void);
static bool start(const risc_provider_dependency_v1*d,size_t n){(void)d;return n==0;}
static bool quiet(void){return true;}
static void stop(void){}
#if UI_KIND==1
static uint16_t pixels[240*240];static bool held;static uint64_t present;
static bool info(void*c,risc_display_info_v1*i){(void)c;wifi_ui_event("display-open");*i=(risc_display_info_v1){.width=240,.height=240,.supported_formats=RISC_DISPLAY_FORMAT_BIT(RISC_DISPLAY_FORMAT_RGB565)};return true;}
static bool frame(void*c,uint32_t f,risc_display_surface_v1*s){(void)c;assert(!held);held=true;*s=(risc_display_surface_v1){.frame=1,.pixels=pixels,.width=240,.height=240,.stride_bytes=480,.size_bytes=sizeof(pixels),.pixel_format=f};return true;}
static void release_frame(void*c,risc_display_frame_v1 f){(void)c;assert(f==1&&held);held=false;}
static bool submit(void*c,risc_display_frame_v1 f,const risc_display_rect_v1*r,size_t n,const risc_display_present_options_v1*o,risc_display_present_token_v1*t){(void)c;(void)r;(void)n;(void)o;assert(f==1&&held);if(wifi_ui_fail_frame())return false;held=false;*t=++present;wifi_ui_event("frame");return true;}
static bool status(void*c,risc_display_present_token_v1 t,risc_display_present_status_v1*s){(void)c;assert(t);s->state=RISC_DISPLAY_PRESENT_COMPLETE;return true;}
static const risc_display_output_api_v1 api={.api_version=1,.struct_size=sizeof(api),.get_info=info,.acquire=frame,.release=release_frame,.submit=submit,.present_status=status};
#define ID "test-display"
#define CAP "display.output"
#elif UI_KIND==2
static uint64_t subscribe(void*c){(void)c;return 1;}
static bool unsubscribe(void*c,uint64_t t){(void)c;assert(t==1);return true;}
static bool poll(void*c,size_t n){(void)c;assert(n==1);wifi_ui_event("poll");return true;}
static int32_t next(void*c,uint64_t t,risc_touch_event_v1*e){(void)c;(void)t;(void)e;return 0;}
static bool snapshot(void*c,risc_touch_snapshot_v1*s){(void)c;*s=(risc_touch_snapshot_v1){.width=240,.height=240};return true;}
static const risc_touch_api_v1 api={1,sizeof(api),NULL,subscribe,unsubscribe,poll,next,snapshot};
#define ID "test-touch"
#define CAP "input.touch.raw"
#else
static bool poll(void*c,risc_input_navigation_frame_v1*f){(void)c;*f=(risc_input_navigation_frame_v1){0};f->pressed=f->released=wifi_ui_buttons();return true;}
static bool foreground(void*c,const risc_input_foreground_v1*a,size_t n){(void)c;(void)a;(void)n;return true;}
static bool reset(void*c){(void)c;return true;}
static const risc_input_navigation_api_v1 api={1,sizeof(api),NULL,poll,foreground,reset};
#define ID "test-navigation"
#define CAP "input.navigation"
#endif
static const risc_driver_v2 driver={2,sizeof(driver),ID,CAP,1,&api,start,stop,quiet};
__attribute__((visibility("default")))const risc_driver_v2*t5_driver_get(uint32_t a){return a==2?&driver:NULL;}

#include "fixture.h"
#include "RiscProviderV2.h"
#include <assert.h>
static bool start(const risc_provider_dependency_v1*d,size_t n){(void)d;return n==0;}
static bool quiesce(void){probe_event("dependency-quiesce");return true;}
static void stop(void){}
#if KIND == 1
static bool rtc_read(void*c,twatch_rtc_time_v1*t){(void)c;return probe_rtc(t);}
static const twatch_rtc_api_v1 api={.api_version=2,.struct_size=sizeof(api),.read=rtc_read};
#define ID "rtc-test"
#define CAP "rtc.clock"
#define VER 2
#elif KIND == 2
static bool effect(void*c,uint8_t e){(void)c;(void)e;assert(!"Future alarm cannot start haptic");return false;}
static bool quiet(void*c){(void)c;probe_event("output-stop");return true;}
static const twatch_haptic_api_v1 api={1,sizeof(api),NULL,effect,quiet};
#define ID "haptic-test"
#define CAP "haptic.effect"
#define VER 1
#else
static bool open_out(void*c,uint32_t r,uint8_t n){(void)c;(void)r;(void)n;assert(!"Future alarm cannot open audio");return false;}
static bool write_out(void*c,const int16_t*p,size_t n){(void)c;(void)p;(void)n;return false;}
static bool quiet(void*c){(void)c;probe_event("output-stop");return true;}
static const twatch_audio_out_api_v1 api={.api_version=1,.struct_size=sizeof(api),.open=open_out,.write=write_out,.silence=quiet,.close=quiet};
#define ID "audio-test"
#define CAP "audio.output"
#define VER 1
#endif
static const risc_driver_v2 driver={2,sizeof(driver),ID,CAP,VER,&api,start,stop,quiesce};
__attribute__((visibility("default"))) const risc_driver_v2*t5_driver_get(uint32_t n){return n==2?&driver:NULL;}

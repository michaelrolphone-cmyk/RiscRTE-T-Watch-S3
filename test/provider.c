#include "RiscProviderV2.h"
#include <stddef.h>
extern const void*scene_timing_provider(const char*);
extern bool scene_timing_provider_event(const char*,unsigned);
extern void scene_timing_provider_poll(const char*,uint32_t);
static bool start(const risc_provider_dependency_v1*d,size_t n){(void)d;return !n&&scene_timing_provider_event(TEST_CAP,1);}
static void stop(void){(void)scene_timing_provider_event(TEST_CAP,2);}
static bool quiesce(void){return scene_timing_provider_event(TEST_CAP,3);}
static void poll(uint32_t n){scene_timing_provider_poll(TEST_CAP,n);}
static risc_driver_poll_v2 driver={{{2,sizeof(driver),TEST_ID,TEST_CAP,1,0,start,stop,quiesce},0,0},poll};
__attribute__((visibility("default")))const risc_driver_v2*t5_driver_get(uint32_t abi){if(abi!=2)return 0;driver.streams.driver.capability=scene_timing_provider(TEST_CAP);return &driver.streams.driver;}

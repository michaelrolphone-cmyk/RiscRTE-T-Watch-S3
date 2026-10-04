#include "fixture.h"
#include "GardenPlatformV1.h"
#include <string.h>
static const garden_gpio_v1*g;static uint64_t token;
static int32_t light(void){risc_light_sleep_result_v1 r={.struct_size=sizeof(r)};return g->light_sleep_for(g->context,token,false,500,&r);}
static bool start(const risc_provider_dependency_v1*d,size_t n){for(size_t i=0;i<n;i++)if(!strcmp(d[i].capability_id,"platform.gpio"))g=d[i].api;return g&&g->claim(g->context,7,false,false,true,&token);}
static bool quiet(void){if(!token)return true;if(!g->release(g->context,token))return false;token=0;return true;}
static void stop(void){(void)quiet();}
static const test_sleep_v1 api={1,sizeof(api),light};
static const risc_driver_v2 driver={2,sizeof(driver),"test-sleep","test.sleep",1,&api,start,stop,quiet};
__attribute__((visibility("default")))const risc_driver_v2*t5_driver_get(uint32_t a){return a==2?&driver:0;}

#include "fixture.h"
#include "RiscProviderV2.h"
#include "RiscHardwareConfigV1.h"
#include "GardenPlatformV1.h"
#include <assert.h>
#include <string.h>
static const garden_gpio_v1 *gpio;
static uint64_t input,output;
static bool held,prepared;
static bool panel_prepare(void*c){(void)c;assert(!held);prepared=true;probe_event("panel-prepare");probe_delay(120);return true;}
static int32_t panel_deep(void*c){(void)c;assert(prepared);probe_event("panel-hold");if(!gpio->write(gpio->context,output,false))return RISC_DEEP_SLEEP_PLATFORM;int32_t rc=gpio->deep_sleep_hold(gpio->context,output,true);if(rc==0)held=true;return rc;}
static int32_t panel_resume_status(void*c){(void)c;probe_event("panel-resume");if(held){int32_t rc=gpio->deep_sleep_hold(gpio->context,output,false);if(rc)return rc;held=false;}prepared=false;if(!strcmp(probe_mode(),"resume-spi-error"))return RISC_DEEP_SLEEP_PLATFORM;probe_delay(120);return 0;}
static bool panel_resume(void*c){return panel_resume_status(c)==0;}
static bool pmu_prepare(void*c){(void)c;probe_event("pmu-prepare");probe_delay(50);return true;}
static bool pmu_resume(void*c){(void)c;probe_event("pmu-resume");return true;}
static bool key(void*c,uint32_t*e){(void)c;probe_event("key-drain");*e=0;return true;}
static bool pending(void*c,bool*p){(void)c;probe_event("crown-check");*p=held&&!strcmp(probe_mode(),"crown-after-hold");return true;}
static int32_t deep(void*c){(void)c;return gpio->deep_sleep(gpio->context,input,false);}
static int32_t timed_deep(void*c,uint32_t ms){(void)c;return gpio->deep_sleep_for(gpio->context,input,false,ms);}
static int32_t light(void*c,risc_light_sleep_result_v1*r){(void)c;return gpio->light_sleep(gpio->context,input,false,r);}
static int32_t timed_light(void*c,uint32_t ms,risc_light_sleep_result_v1*r){(void)c;return gpio->light_sleep_for(gpio->context,input,false,ms,r);}
static const twatch_panel_power_v1 panel={.base={.api_version=1,.struct_size=sizeof(panel)},.prepare_sleep=panel_prepare,.resume=panel_resume,.prepare_deep_sleep=panel_deep
#ifdef TWATCH_PANEL_RESUME_STATUS_SIZE
,.resume_status=panel_resume_status
#endif
};
static const twatch_pmu_api_v1 pmu={.base={.api_version=1,.struct_size=sizeof(pmu)},.key_events=key,.prepare_sleep=pmu_prepare,.resume=pmu_resume,.light_sleep=light,.deep_sleep=deep,.light_sleep_for=timed_light,.sleep_wake_pending=pending,.deep_sleep_for=timed_deep};
static const sleep_fixture_v1 api={1,sizeof(api),&panel,&pmu};
static bool start(const risc_provider_dependency_v1*d,size_t n){for(size_t i=0;i<n;i++)if(!strcmp(d[i].capability_id,"platform.gpio"))gpio=d[i].api;return gpio&&gpio->claim(gpio->context,7,false,false,true,&input)&&gpio->claim(gpio->context,6,true,false,false,&output);}
static bool quiesce(void){probe_event("sleep-quiesce");assert(!held);return gpio->release(gpio->context,output)&&gpio->release(gpio->context,input);}
static void stop(void){}
static const risc_driver_v2 driver={2,sizeof(driver),"sleep-test","test.sleep",1,&api,start,stop,quiesce};
__attribute__((visibility("default"))) const risc_driver_v2*t5_driver_get(uint32_t n){return n==2?&driver:NULL;}

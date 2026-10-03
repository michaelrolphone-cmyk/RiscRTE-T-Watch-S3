#include <assert.h>
#include <stdio.h>
#include "twatch_caps.h"
static uint32_t event;static unsigned reads;static bool fail;
static bool keys(void*c,uint32_t*out){(void)c;reads++;if(fail)return false;*out=event;event=0;return true;}
static const twatch_pmu_api_v1 pmu_mock={.base={1,sizeof(pmu_mock),NULL,NULL},.key_events=keys};
#include "drivers/pmu_navigation/driver.c"
int main(void){
 risc_provider_dependency_v1 deps[]={{"board.battery",1,&pmu_mock}};
 const risc_driver_v2*d=t5_driver_get(2);assert(d&&d->start(deps,1));
 const risc_input_navigation_api_v1*a=d->capability;risc_input_navigation_frame_v1 f;
 event=TWATCH_PMU_KEY_SHORT|TWATCH_PMU_KEY_UP;assert(a->reset(NULL));assert(a->poll(NULL,&f)&&!f.pressed);
 event=TWATCH_PMU_KEY_SHORT|TWATCH_PMU_KEY_UP;assert(a->poll(NULL,&f)&&!f.pressed);
 event=TWATCH_PMU_KEY_DOWN;assert(a->poll(NULL,&f)&&!f.pressed);
 event=TWATCH_PMU_KEY_SHORT|TWATCH_PMU_KEY_UP;assert(a->poll(NULL,&f)&&f.pressed==RISC_NAV_BACK&&f.released==RISC_NAV_BACK&&!f.buttons);
 assert(a->poll(NULL,&f)&&!f.pressed);
 event=TWATCH_PMU_KEY_DOWN;assert(a->poll(NULL,&f));assert(a->reset(NULL));
 event=TWATCH_PMU_KEY_SHORT|TWATCH_PMU_KEY_UP;assert(a->poll(NULL,&f)&&!f.pressed);
 const risc_input_foreground_v1 overlap[]={ {"input.navigation",1} };
 assert(a->foreground(NULL,overlap,1));unsigned before=reads;event=TWATCH_PMU_KEY_DOWN;
 assert(a->poll(NULL,&f)&&!f.pressed&&reads==before);
 assert(a->foreground(NULL,NULL,0));event=TWATCH_PMU_KEY_DOWN;assert(a->poll(NULL,&f));
 fail=true;assert(!a->poll(NULL,&f));fail=false;
 event=TWATCH_PMU_KEY_SHORT|TWATCH_PMU_KEY_UP;assert(a->poll(NULL,&f)&&!f.pressed);
 event=TWATCH_PMU_KEY_DOWN|TWATCH_PMU_KEY_SHORT|TWATCH_PMU_KEY_UP;
 assert(a->poll(NULL,&f)&&f.pressed==RISC_NAV_BACK);
 assert(d->quiesce());puts("PMU navigation: fresh release, stale/held reset, foreground and read failure passed");
}

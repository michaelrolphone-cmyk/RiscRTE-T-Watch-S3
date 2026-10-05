#pragma once
/* Current deployment only: explicit app-owned grant with retained cleanup.
 * Historical custody lanes keep their original single-source behavior. */
#include "RiscRuntimeV1.h"
#include "watch_alarm_sleep.h"
static int watch_motion_sleep(const risc_runtime_api_v1 *rt,const twatch_panel_power_v1 *panel,
        const twatch_pmu_api_v1 *pmu,unsigned mode,const alarm_service_v1 *alarms){
    risc_runtime_capability_v1 grant={.struct_size=sizeof(grant)};
    if(!rt->acquire || !rt->release || !rt->acquire(TWATCH_MOTION_CAPABILITY,1,7,&grant))return WATCH_SLEEP_REFUSED;
    const twatch_motion_api_v1 *motion=grant.api;
    if(!motion || !watch_motion_ready(motion) || pmu->base.struct_size<TWATCH_PMU_WAKE_SET_SIZE ||
       !pmu->light_sleep_set || !pmu->deep_sleep_set){
        return rt->release(&grant)?WATCH_SLEEP_REFUSED:WATCH_SLEEP_RETAINED;
    }
    int result=alarms?watch_alarm_sleep_motion_prepared(panel,pmu,motion,mode,alarms,rt->diagnostic):
        watch_sleep_motion_prepared(panel,pmu,motion,mode,rt->diagnostic);
    if(result==WATCH_SLEEP_RETAINED)return result;
    return rt->release(&grant)?result:WATCH_SLEEP_RETAINED;
}

#pragma once
/* Current deployment only: explicit app-owned grant with retained cleanup.
 * Historical custody lanes keep their original single-source behavior. */
#include "RiscRuntimeV1.h"
#include "watch_alarm_sleep.h"
#include "PortableTapSettings.h"
static int watch_motion_sleep(const risc_runtime_api_v1 *rt,const twatch_panel_power_v1 *panel,
        const twatch_pmu_api_v1 *pmu,unsigned mode,const alarm_service_v1 *alarms){
    watch_sleep_stage=7;watch_sleep_detail=0;
    portable_tap_settings preference;
    risc_runtime_capability_v1 storage={.struct_size=sizeof(storage)};
    if(!rt->acquire || !rt->release)return WATCH_SLEEP_REFUSED;
    if(!rt->acquire(RISC_KEY_VALUE_CAPABILITY,1,PORTABLE_TAP_STORE_INSTANCE,&storage))return WATCH_SLEEP_REFUSED;
    int loaded=portable_tap_load(storage.api,&preference);
    if(!rt->release(&storage))return WATCH_SLEEP_RETAINED;
    if(loaded==PORTABLE_TAP_UNAVAILABLE || loaded==PORTABLE_TAP_INVALID)
        rt->diagnostic("WATCH_SLEEP tap-setting=unreadable crown-only");
    if(!preference.enabled)return alarms?
        watch_alarm_sleep_prepared(panel,pmu,mode,alarms,rt->diagnostic):
        watch_sleep_prepared(panel,pmu,mode,rt->diagnostic);
    risc_runtime_capability_v1 grant={.struct_size=sizeof(grant)};
    if(!rt->acquire || !rt->release || !rt->acquire(TWATCH_MOTION_CAPABILITY,1,7,&grant))return WATCH_SLEEP_REFUSED;
    const twatch_motion_api_v1 *motion=grant.api;
    if(!motion || !watch_motion_ready(motion) || pmu->base.struct_size<TWATCH_PMU_WAKE_SET_SIZE ||
       !pmu->light_sleep_set || !pmu->deep_sleep_set){
        watch_sleep_stage=8;return rt->release(&grant)?WATCH_SLEEP_REFUSED:WATCH_SLEEP_RETAINED;
    }
    twatch_tap_info_v1 info={.struct_size=sizeof(info)};
    if(!portable_motion_tap_valid(motion) || !motion->tap_info(motion->context,&info) || info.struct_size<sizeof(info) ||
       (info.profile!=TWATCH_TAP_BMA423 && info.profile!=TWATCH_TAP_BMA456H) ||
       !motion->tap_configure(motion->context,portable_tap_value(&preference,info.profile))){
        watch_sleep_stage=8;return rt->release(&grant)?WATCH_SLEEP_REFUSED:WATCH_SLEEP_RETAINED;
    }
    int result=alarms?watch_alarm_sleep_motion_prepared(panel,pmu,motion,mode,alarms,rt->diagnostic):
        watch_sleep_motion_prepared(panel,pmu,motion,mode,rt->diagnostic);
    if(result==WATCH_SLEEP_RETAINED)return result;
    if(result==WATCH_SLEEP_REFUSED && watch_sleep_stage==1 && motion->struct_size>=TWATCH_MOTION_DIAGNOSTIC_SIZE && motion->wake_error)watch_sleep_detail=(int32_t)motion->wake_error(motion->context);
    return rt->release(&grant)?result:WATCH_SLEEP_RETAINED;
}

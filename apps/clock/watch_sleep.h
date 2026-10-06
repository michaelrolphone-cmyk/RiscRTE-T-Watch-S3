#pragma once
/* Application-owned sleep progression. The physical providers only expose
 * bounded preparation, observed IRQ state and generic owned sleep mechanism.
 * Every ordinary return is restored; retained native state forbids further I/O.
 * Caller drains touch and leases and commits a black frame before entry. */
#include "twatch_power.h"
#include "twatch_caps.h"
#include "PortableSleepPolicy.h"
enum { WATCH_SLEEP_REFUSED=0, WATCH_SLEEP_WOKE=1, WATCH_SLEEP_FAILED=-1,
       WATCH_SLEEP_RETAINED=-2 };
static unsigned watch_sleep_stage;
static int32_t watch_sleep_detail;
static bool watch_motion_ready(const twatch_motion_api_v1 *motion){
    return !motion || (motion->api_version==TWATCH_MOTION_API_V1 && motion->struct_size>=TWATCH_MOTION_WAKE_SIZE &&
        motion->prepare_wake && motion->wake_pending && motion->resume_wake);
}
static int32_t watch_enter_light(const twatch_pmu_api_v1 *pmu,const twatch_motion_api_v1 *motion,
        uint32_t ms,risc_light_sleep_result_v1 *result){
    if(motion)return pmu->base.struct_size>=TWATCH_PMU_WAKE_SET_SIZE && pmu->light_sleep_set?
        pmu->light_sleep_set(pmu->base.context,ms,result):RISC_LIGHT_SLEEP_UNSUPPORTED;
    if(ms)return pmu->base.struct_size>=TWATCH_PMU_TIMED_SLEEP_SIZE && pmu->light_sleep_for?
        pmu->light_sleep_for(pmu->base.context,ms,result):RISC_LIGHT_SLEEP_UNSUPPORTED;
    return pmu->light_sleep?pmu->light_sleep(pmu->base.context,result):RISC_LIGHT_SLEEP_UNSUPPORTED;
}
static int32_t watch_enter_deep(const twatch_pmu_api_v1 *pmu,const twatch_motion_api_v1 *motion,uint32_t ms){
    if(motion)return pmu->base.struct_size>=TWATCH_PMU_WAKE_SET_SIZE && pmu->deep_sleep_set?
        pmu->deep_sleep_set(pmu->base.context,ms):RISC_DEEP_SLEEP_UNSUPPORTED;
    if(ms)return pmu->base.struct_size>=TWATCH_PMU_TIMED_DEEP_SLEEP_SIZE && pmu->deep_sleep_for?
        pmu->deep_sleep_for(pmu->base.context,ms):RISC_DEEP_SLEEP_UNSUPPORTED;
    return pmu->deep_sleep?pmu->deep_sleep(pmu->base.context):RISC_DEEP_SLEEP_UNSUPPORTED;
}
static bool watch_wake_pending(const twatch_pmu_api_v1 *pmu,const twatch_motion_api_v1 *motion,bool *pending){
    bool sensor=false;
    if(!pmu->sleep_wake_pending || !pmu->sleep_wake_pending(pmu->base.context,pending))return false;
    if(motion && !motion->wake_pending(motion->context,&sensor))return false;
    *pending=*pending || sensor;return true;
}
static int watch_sleep_motion_prepared(const twatch_panel_power_v1 *panel,
                               const twatch_pmu_api_v1 *pmu,const twatch_motion_api_v1 *motion,unsigned mode,
                               bool (*diagnostic)(const char *)) {
    bool deep=mode==PORTABLE_SLEEP_DEEP, hybrid=mode==PORTABLE_SLEEP_HYBRID;
    int32_t rc=RISC_LIGHT_SLEEP_INVALID;
    if(!watch_motion_ready(motion))return WATCH_SLEEP_REFUSED;
    bool motion_ok=!motion || motion->prepare_wake(motion->context);
    bool panel_ok=false;
    if(motion_ok) {
    if (deep) {
        if(panel->base.struct_size<TWATCH_PANEL_DEEP_SLEEP_SIZE || !panel->prepare_deep_sleep ||
           pmu->base.struct_size<TWATCH_PMU_DEEP_SLEEP_SIZE || !pmu->deep_sleep) rc=RISC_DEEP_SLEEP_UNSUPPORTED;
        else {rc=panel->prepare_deep_sleep(panel->base.context);panel_ok=rc==0;}
    } else panel_ok=panel->prepare_sleep(panel->base.context);
    if(rc==RISC_DEEP_SLEEP_RETAINED) {
        diagnostic("WATCH_CLOCK error=deep-prepare-retained");return WATCH_SLEEP_RETAINED;
    }
    }
    bool pmu_ok=panel_ok && pmu->prepare_sleep(pmu->base.context);
    risc_light_sleep_result_v1 result={.struct_size=sizeof(result)};
    if(pmu_ok) {
        if(deep) {
            diagnostic("WATCH_CLOCK sleep=deep");
            rc=watch_enter_deep(pmu,motion,0);
            if(rc>=0)rc=RISC_DEEP_SLEEP_RETAINED;
        } else if(hybrid) {
            if(pmu->base.struct_size<TWATCH_PMU_TIMED_SLEEP_SIZE || !pmu->light_sleep_for ||
               !pmu->sleep_wake_pending) rc=RISC_LIGHT_SLEEP_UNSUPPORTED;
            else {
                diagnostic("WATCH_SLEEP phase=light duration_ms=300000");
                rc=watch_enter_light(pmu,motion,PORTABLE_SLEEP_LIGHT_MS,&result);
                if(rc==RISC_LIGHT_SLEEP_OK && result.wake_cause==RISC_LIGHT_SLEEP_WAKE_TIMER) {
                    bool pending=true;
                    /* Never infer timer-only completion from time or UI. Key
                     * edges stay latched while the short-press wake is armed. */
                    if(!watch_wake_pending(pmu,motion,&pending))rc=RISC_LIGHT_SLEEP_PLATFORM;
                    else if(!pending) {
                        if(panel->base.struct_size<TWATCH_PANEL_DEEP_SLEEP_SIZE || !panel->prepare_deep_sleep ||
                           pmu->base.struct_size<TWATCH_PMU_DEEP_SLEEP_SIZE || !pmu->deep_sleep)rc=RISC_DEEP_SLEEP_UNSUPPORTED;
                        else {
                            rc=panel->prepare_deep_sleep(panel->base.context);
                            if(rc==0) {
                                /* A crown edge arriving during panel hold wins
                                 * too. No panel resume or visible frame intervenes. */
                                diagnostic("WATCH_SLEEP phase=deep timer=expired");
                                if(!watch_wake_pending(pmu,motion,&pending))rc=RISC_LIGHT_SLEEP_PLATFORM;
                                else if(!pending) {
                                    rc=watch_enter_deep(pmu,motion,0);
                                    if(rc>=0)rc=RISC_DEEP_SLEEP_RETAINED;
                                }
                            }
                        }
                    }
                }
            }
        } else rc=watch_enter_light(pmu,motion,0,&result);
    }
    if(rc==RISC_LIGHT_SLEEP_RETAINED) {
        diagnostic("WATCH_CLOCK error=sleep-retained");return WATCH_SLEEP_RETAINED;
    }
    if(motion && !motion->resume_wake(motion->context)) {diagnostic("WATCH_SLEEP motion=restore-retained");return WATCH_SLEEP_RETAINED;}
    bool pmu_restored=pmu->resume(pmu->base.context);
    bool panel_restored=panel->resume(panel->base.context);
    if(!pmu_restored || !panel_restored) {
        diagnostic("WATCH_CLOCK error=sleep-restore");return WATCH_SLEEP_FAILED;
    }
    uint32_t ignored=0;
    if(!pmu->key_events(pmu->base.context,&ignored))return WATCH_SLEEP_FAILED;
    return rc==RISC_LIGHT_SLEEP_OK && !deep?WATCH_SLEEP_WOKE:WATCH_SLEEP_REFUSED;
}

static int watch_sleep_prepared(const twatch_panel_power_v1 *panel,const twatch_pmu_api_v1 *pmu,
        unsigned mode,bool (*diagnostic)(const char *)){
    return watch_sleep_motion_prepared(panel,pmu,NULL,mode,diagnostic);
}

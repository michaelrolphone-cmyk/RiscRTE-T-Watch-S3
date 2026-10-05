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
static int watch_sleep_prepared(const twatch_panel_power_v1 *panel,
                               const twatch_pmu_api_v1 *pmu,unsigned mode,
                               bool (*diagnostic)(const char *)) {
    bool deep=mode==PORTABLE_SLEEP_DEEP, hybrid=mode==PORTABLE_SLEEP_HYBRID;
    int32_t rc=RISC_LIGHT_SLEEP_INVALID;
    bool panel_ok=false;
    if (deep) {
        if(panel->base.struct_size<TWATCH_PANEL_DEEP_SLEEP_SIZE || !panel->prepare_deep_sleep ||
           pmu->base.struct_size<TWATCH_PMU_DEEP_SLEEP_SIZE || !pmu->deep_sleep) rc=RISC_DEEP_SLEEP_UNSUPPORTED;
        else {rc=panel->prepare_deep_sleep(panel->base.context);panel_ok=rc==0;}
    } else panel_ok=panel->prepare_sleep(panel->base.context);
    if(rc==RISC_DEEP_SLEEP_RETAINED) {
        diagnostic("WATCH_CLOCK error=deep-prepare-retained");return WATCH_SLEEP_RETAINED;
    }
    bool pmu_ok=panel_ok && pmu->prepare_sleep(pmu->base.context);
    risc_light_sleep_result_v1 result={.struct_size=sizeof(result)};
    if(pmu_ok) {
        if(deep) {
            diagnostic("WATCH_CLOCK sleep=deep");
            rc=pmu->deep_sleep(pmu->base.context);
            if(rc>=0)rc=RISC_DEEP_SLEEP_RETAINED;
        } else if(hybrid) {
            if(pmu->base.struct_size<TWATCH_PMU_TIMED_SLEEP_SIZE || !pmu->light_sleep_for ||
               !pmu->sleep_wake_pending) rc=RISC_LIGHT_SLEEP_UNSUPPORTED;
            else {
                diagnostic("WATCH_SLEEP phase=light duration_ms=300000");
                rc=pmu->light_sleep_for(pmu->base.context,PORTABLE_SLEEP_LIGHT_MS,&result);
                if(rc==RISC_LIGHT_SLEEP_OK && result.wake_cause==RISC_LIGHT_SLEEP_WAKE_TIMER) {
                    bool pending=true;
                    /* Never infer timer-only completion from time or UI. Key
                     * edges stay latched while the short-press wake is armed. */
                    if(!pmu->sleep_wake_pending(pmu->base.context,&pending))rc=RISC_LIGHT_SLEEP_PLATFORM;
                    else if(!pending) {
                        if(panel->base.struct_size<TWATCH_PANEL_DEEP_SLEEP_SIZE || !panel->prepare_deep_sleep ||
                           pmu->base.struct_size<TWATCH_PMU_DEEP_SLEEP_SIZE || !pmu->deep_sleep)rc=RISC_DEEP_SLEEP_UNSUPPORTED;
                        else {
                            rc=panel->prepare_deep_sleep(panel->base.context);
                            if(rc==0) {
                                /* A crown edge arriving during panel hold wins
                                 * too. No panel resume or visible frame intervenes. */
                                diagnostic("WATCH_SLEEP phase=deep timer=expired");
                                if(!pmu->sleep_wake_pending(pmu->base.context,&pending))rc=RISC_LIGHT_SLEEP_PLATFORM;
                                else if(!pending) {
                                    rc=pmu->deep_sleep(pmu->base.context);
                                    if(rc>=0)rc=RISC_DEEP_SLEEP_RETAINED;
                                }
                            }
                        }
                    }
                }
            }
        } else rc=pmu->light_sleep(pmu->base.context,&result);
    }
    if(rc==RISC_LIGHT_SLEEP_RETAINED) {
        diagnostic("WATCH_CLOCK error=sleep-retained");return WATCH_SLEEP_RETAINED;
    }
    bool pmu_restored=pmu->resume(pmu->base.context);
    bool panel_restored=panel->resume(panel->base.context);
    if(!pmu_restored || !panel_restored) {
        diagnostic("WATCH_CLOCK error=sleep-restore");return WATCH_SLEEP_FAILED;
    }
    uint32_t ignored=0;
    if(!pmu->key_events(pmu->base.context,&ignored))return WATCH_SLEEP_FAILED;
    return rc==RISC_LIGHT_SLEEP_OK && !deep?WATCH_SLEEP_WOKE:WATCH_SLEEP_REFUSED;
}

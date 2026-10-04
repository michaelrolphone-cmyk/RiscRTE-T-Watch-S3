/* Watch deployment's local app sleep adapter. Keeps app state and the last
 * completed image in RAM; never acquires Settings storage or reconstructs apps.
 * Deep wake is the runtime's ordinary fresh default Clock boot. */
#include "PortableAppSleep.h"
#include "watch_sleep.h"
#include <stdlib.h>
#include <string.h>
static bool transfer(const risc_runtime_api_v1 *rt,const risc_display_output_api_v1 *d,
                     const uint16_t *pixels) {
    risc_display_surface_v1 s={0};
    if(!d->acquire(d->context,RISC_DISPLAY_FORMAT_RGB565,&s))return false;
    if(!s.frame || !s.pixels || s.width!=240 || s.height!=240 || s.stride_bytes<480 ||
       s.stride_bytes>UINT32_MAX/240u || s.size_bytes<s.stride_bytes*240u || s.pixel_format!=RISC_DISPLAY_FORMAT_RGB565) {
        if(s.frame)d->release(d->context,s.frame);
        return false;
    }
    for(unsigned y=0;y<240;y++) {
        void *row=(uint8_t *)s.pixels+(size_t)y*s.stride_bytes;
        if(pixels)memcpy(row,pixels+y*240,480);else memset(row,0,480);
    }
    const risc_display_present_options_v1 options={0,0,0};
    risc_display_present_token_v1 token=0;
    if(!d->submit(d->context,s.frame,NULL,0,&options,&token)) {
        d->release(d->context,s.frame);return false;
    }
    for(unsigned n=0;n<10000;n++) {
        risc_display_present_status_v1 status={0};
        if(!d->present_status(d->context,token,&status))return false;
        if(status.state==RISC_DISPLAY_PRESENT_COMPLETE)return true;
        if(status.state==RISC_DISPLAY_PRESENT_FAILED || status.state==RISC_DISPLAY_PRESENT_SUPERSEDED)return false;
        rt->yield_ms(1);
    }
    return false;
}
int portable_app_sleep(const risc_runtime_api_v1 *rt,const risc_display_output_api_v1 *d,
                       const risc_battery_gauge_api_v1 *gauge) {
    const twatch_panel_power_v1 *panel=(const twatch_panel_power_v1 *)d;
    const twatch_pmu_api_v1 *pmu=(const twatch_pmu_api_v1 *)gauge;
    if(!d || d->struct_size<TWATCH_PANEL_LIGHT_SLEEP_SIZE || !d->set_brightness ||
       !panel->prepare_sleep || !panel->resume || !pmu || pmu->base.struct_size<TWATCH_PMU_TIMED_SLEEP_SIZE ||
       !pmu->key_events || !pmu->prepare_sleep || !pmu->resume || !pmu->light_sleep_for || !pmu->sleep_wake_pending) {
        rt->diagnostic("PORTABLE_APP sleep=unsupported");return 0;
    }
    uint16_t *saved=malloc(240u*240u*2u);
    if(!saved){rt->diagnostic("PORTABLE_APP sleep=memory-refused");return 0;}
    risc_display_surface_v1 s={0};
    if(!d->acquire(d->context,RISC_DISPLAY_FORMAT_RGB565,&s)){free(saved);return -1;}
    bool valid=s.frame && s.pixels && s.width==240 && s.height==240 && s.stride_bytes>=480 &&
        s.stride_bytes<=UINT32_MAX/240u && s.size_bytes>=s.stride_bytes*240u && s.pixel_format==RISC_DISPLAY_FORMAT_RGB565;
    if(valid)for(unsigned y=0;y<240;y++)memcpy(saved+y*240,(uint8_t *)s.pixels+(size_t)y*s.stride_bytes,480);
    if(s.frame)d->release(d->context,s.frame);
    if(!valid){free(saved);return -1;}
    int rc=-1;
    if(d->set_brightness(d->context,0,100) && transfer(rt,d,NULL)) {
        rc=watch_sleep_prepared(panel,pmu,PORTABLE_SLEEP_HYBRID,rt->diagnostic);
        if(rc>=0) {
            /* Resume stays dark until a complete previous-app frame arrives.
             * The caller then continues in its original stack and app state. */
            if(!d->set_brightness(d->context,0,100) || !transfer(rt,d,saved) ||
               !d->set_brightness(d->context,40,100))rc=-1;
        }
    }
    free(saved);
    return rc<0?-1:rc;
}

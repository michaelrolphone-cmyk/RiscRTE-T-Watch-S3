#include "RiscRuntimeV1.h"
#include "render.h"

static bool display_valid(const risc_display_output_api_v1 *d) {
    return d && d->api_version==1 && d->struct_size>=sizeof(*d) && d->get_info &&
           d->acquire && d->release && d->submit && d->present_status;
}
static bool rtc_valid(const twatch_rtc_api_v1 *r) {
    return r && r->api_version==2 && r->struct_size>=sizeof(*r) && r->read;
}
__attribute__((visibility("default"))) void app_main(void) {
    const risc_runtime_api_v1 *runtime=risc_runtime_get_api(1);
    if(!runtime || runtime->api_version!=1 || runtime->struct_size<RISC_RUNTIME_CAPABILITIES_V1_SIZE ||
       !runtime->health || !runtime->yield_ms || !runtime->diagnostic ||
       !runtime->acquire || !runtime->release) return;
    risc_runtime_capability_v1 display_grant={.struct_size=sizeof(display_grant)};
    risc_runtime_capability_v1 rtc_grant={.struct_size=sizeof(rtc_grant)};
    bool has_display=runtime->acquire("display.output",1,0,&display_grant);
    const risc_display_output_api_v1 *display=has_display?display_grant.api:NULL;
    bool has_rtc=false;
    risc_display_frame_v1 held=0;
    if(!display_valid(display)) {
        runtime->diagnostic("WATCH_CLOCK error=display-grant-or-api");goto cleanup;
    }
    risc_display_info_v1 info={0};
    if(!display->get_info(display->context,&info) || info.width!=240 || info.height!=240 ||
       !(info.supported_formats&RISC_DISPLAY_FORMAT_BIT(RISC_DISPLAY_FORMAT_RGB565))) {
        runtime->diagnostic("WATCH_CLOCK error=display-format");goto cleanup;
    }
    has_rtc=runtime->acquire("rtc.clock",2,0,&rtc_grant);
    const twatch_rtc_api_v1 *rtc=has_rtc?rtc_grant.api:NULL;
    if(!rtc_valid(rtc))rtc=NULL;
    if(display->set_brightness && !display->set_brightness(display->context,40,100)) {
        runtime->diagnostic("WATCH_CLOCK error=brightness");goto cleanup;
    }
    bool first=true,last_valid=false,pending=false,reported=false;
    uint32_t last_draw=0,present_started=0;
    risc_display_present_token_v1 token=0;
    for(;;) {
        risc_runtime_health_v1 health={.struct_size=sizeof(health)};
        if(!runtime->health(&health))break;
        if(pending) {
            risc_display_present_status_v1 status={0};
            if(!display->present_status(display->context,token,&status) ||
               status.state==RISC_DISPLAY_PRESENT_FAILED ||
               status.state==RISC_DISPLAY_PRESENT_SUPERSEDED) {
                runtime->diagnostic("WATCH_CLOCK error=present");break;
            }
            if(status.state==RISC_DISPLAY_PRESENT_COMPLETE) {
                pending=false;
                if(!reported){runtime->diagnostic(last_valid?"WATCH_CLOCK ready time=rtc":"WATCH_CLOCK ready time=unset");reported=true;}
            } else if((uint32_t)(health.uptime_ms-present_started)>10000) {
                /* Submit consumed the frame. No app buffer remains borrowed;
                 * runtime/provider quiescence owns any still-pending transfer. */
                runtime->diagnostic("WATCH_CLOCK error=present-timeout");break;
            }
        }
        if(!pending && (first || (uint32_t)(health.uptime_ms-last_draw)>=1000)) {
            twatch_rtc_time_v1 time={0};
            bool valid=rtc && rtc->read(rtc->context,&time) && tw_valid_time(&time);
            if(first || valid!=last_valid)reported=false;
            last_valid=valid;
            risc_display_surface_v1 surface={0};
            if(!display->acquire(display->context,RISC_DISPLAY_FORMAT_RGB565,&surface)) {
                runtime->diagnostic("WATCH_CLOCK error=frame-acquire");break;
            }
            held=surface.frame;
            if(!held || !watch_clock_render(&surface,&time,valid,health.uptime_ms/1000)) {
                runtime->diagnostic("WATCH_CLOCK error=frame-layout");break;
            }
            const risc_display_present_options_v1 options={RISC_DISPLAY_PRESENT_DEFAULT,RISC_DISPLAY_QUEUE_FIFO,0};
            if(!display->submit(display->context,held,NULL,0,&options,&token)) {
                runtime->diagnostic("WATCH_CLOCK error=frame-submit");break;
            }
            held=0; /* successful submit consumes the lease */
            pending=true;first=false;last_draw=health.uptime_ms;present_started=health.uptime_ms;
        }
        /* Pending display work needs frequent provider polls; idle waits yield
         * in20ms slices. No direct calls to driver poll or raw CPU APIs. */
        runtime->yield_ms(pending?1:20);
    }
cleanup:
    if(held && display && display->release)display->release(display->context,held);
    if(has_rtc && !runtime->release(&rtc_grant))runtime->diagnostic("WATCH_CLOCK error=rtc-release");
    if(has_display && !runtime->release(&display_grant))runtime->diagnostic("WATCH_CLOCK error=display-release");
}

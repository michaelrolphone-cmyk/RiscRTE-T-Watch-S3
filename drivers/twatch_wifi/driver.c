#include "WifiApi.h"
#include "GardenRadioAsyncV1.h"
#include "twatch_support.h"
#define hardware_config tw_config
#define garden_dependency tw_dep
static risc_hw_radio_v1 hardware;
static const garden_radio_v1 *radio;
static uint64_t claim;
static bool running;
static uint32_t operation, completed, service_lease;
static const garden_radio_async_v1 *async_radio;
static bool bounded(const char *s, size_t maximum) {
    if (!s)
        return false;
    for (size_t i = 0; i <= maximum; i++)
        if (!s[i])
            return true;
    return false;
}
static int32_t async_begin(void *c,const risc_radio_request_v1 *request,uint32_t *out) {
    (void)c;if(out)*out=0;
    if(!running || !async_radio || !(hardware.features&1))return RISC_RADIO_UNAVAILABLE;
    if(operation)return RISC_RADIO_BUSY;
    int32_t result=async_radio->begin(radio->context,claim,request,out);
    if(result==RISC_RADIO_ACCEPTED && out && *out){operation=*out;completed=0;}
    return result;
}
static int32_t async_poll(void *c,uint32_t id,risc_radio_progress_v1 *out) {
    (void)c;
    if(!running || !async_radio)return RISC_RADIO_UNAVAILABLE;
    if(!id || (id!=operation && id!=completed))return RISC_RADIO_STALE;
    int32_t result=async_radio->poll(radio->context,claim,id,out);
    if(result==RISC_RADIO_QUIESCENT){operation=0;completed=id;}
    return result;
}
static int32_t async_cancel(void *c,uint32_t id) {
    (void)c;
    if(!running || !async_radio)return RISC_RADIO_UNAVAILABLE;
    if(!id || (id!=operation && id!=completed))return RISC_RADIO_STALE;
    int32_t result=async_radio->cancel(radio->context,claim,id);
    if(result==RISC_RADIO_QUIESCENT){operation=0;completed=id;}
    return result;
}
static int32_t service_begin(void *c,uint32_t *out) {
    (void)c;if(out)*out=0;
    if(!running || !async_radio)return RISC_RADIO_UNAVAILABLE;
    if(service_lease)return RISC_RADIO_BUSY;
    int32_t result=async_radio->service_begin(radio->context,claim,out);
    if(result==RISC_RADIO_ACCEPTED && out && *out)service_lease=*out;
    return result;
}
static int32_t service_end(void *c,uint32_t id) {
    (void)c;
    if(!running || !async_radio)return RISC_RADIO_UNAVAILABLE;
    if(!id || id!=service_lease)return RISC_RADIO_STALE;
    int32_t result=async_radio->service_end(radio->context,claim,id);
    if(result==RISC_RADIO_ACCEPTED)service_lease=0;
    return result;
}
static bool connect(void *c, const char *ssid, const char *password) {
    (void)c;
    return running && !operation && (hardware.features & 1) && ssid && ssid[0] && bounded(ssid, 32) &&
           bounded(password, 63) && radio->join(radio->context, claim, ssid, password);
}
static bool scan_available(void) {
    return radio && radio->struct_size >= GARDEN_RADIO_SCAN_V1_SIZE &&
           radio->scan_start && radio->scan_poll && radio->scan_cancel;
}
static bool scan_cancel(void *c) {
    (void)c;
    if(operation)return async_cancel(NULL,operation)==RISC_RADIO_QUIESCENT;
    return running && scan_available() && radio->scan_cancel(radio->context, claim);
}
static bool disconnect_checked(void *c) {
    (void)c;
    if (!running) return false;
    if(operation && async_cancel(NULL,operation)!=RISC_RADIO_QUIESCENT)return false;
    /* Call leave even if cancel failed: independent cleanup attempts must not
     * be skipped. False keeps the token and app cleanup obligation alive. */
    bool cancelled = !scan_available() || radio->scan_cancel(radio->context, claim);
    bool left = radio->leave(radio->context, claim);
    return cancelled && left;
}
static void disconnect(void *c) { (void)disconnect_checked(c); }
static bool scan_start(void *c) {
    (void)c;
    return running && !operation && (hardware.features & 1) && scan_available() &&
           radio->scan_start(radio->context, claim);
}
static bool scan_poll(void *c, garden_radio_scan_result_v1 *result) {
    (void)c;
    if (!running || !result || result->struct_size < sizeof(*result) || !scan_available()) return false;
    garden_radio_scan_result_v1 next = {.struct_size = sizeof(next)};
    if (!radio->scan_poll(radio->context, claim, &next) ||
        next.struct_size != sizeof(next) || next.count > GARDEN_RADIO_SCAN_MAX ||
        next.state > GARDEN_RADIO_SCAN_FAILED || next.reserved) return false;
    for (unsigned i=0; i<next.count; ++i)
        if (!bounded(next.entries[i].ssid,32) || next.entries[i].reserved ||
            next.entries[i].channel > 14) return false;
    *result=next;
    return true;
}
static wifi_link_t status(void *c) {
    (void)c;
    uint8_t state = 0;
    int8_t rssi = -127;
    if (!running || !radio->state(radio->context, claim, &state, &rssi) || state > WIFI_LINK_UP)
        return WIFI_LINK_DOWN;
    return (wifi_link_t)state;
}
static int8_t rssi(void *c) {
    (void)c;
    uint8_t state = 0;
    int8_t value = -127;
    return running && radio->state(radio->context, claim, &state, &value) && state == WIFI_LINK_UP
               ? value
               : -127;
}
static bool start_ap(void *c, const char *ssid, const char *password, const wifi_ipv4_v1 *config) {
    (void)c;
    if (!running || !(hardware.features & 2) || !ssid || !ssid[0] || !bounded(ssid, 32) ||
        !bounded(password, 63) || !config)
        return false;
    size_t length = strlen(password);
    if (length && length < 8)
        return false;
    return radio->start_ap(radio->context, claim, ssid, password, config->address, config->gateway,
                           config->netmask);
}
static bool stop_ap(void *c) {
    (void)c;
    return running && radio->stop_ap(radio->context, claim);
}
static bool addresses(void *c, wifi_ipv4_v1 *station, wifi_ipv4_v1 *ap) {
    (void)c;
    return running && station && ap &&
           radio->addresses(radio->context, claim, (uint8_t *)station, (uint8_t *)ap);
}
static wifi_async_v1 api = { .base = {
    .api_version=1, .struct_size=sizeof(wifi_api_v1), .context=NULL, .connect=connect,
    .disconnect=disconnect, .status=status, .rssi=rssi, .start_ap=start_ap,
    .stop_ap=stop_ap, .addresses=addresses, .scan_start=scan_start,
    .scan_poll=scan_poll, .scan_cancel=scan_cancel, .disconnect_checked=disconnect_checked
}, .async_tag=RISC_RADIO_ASYNC_TAG, .async_version=RISC_RADIO_ASYNC_VERSION,
   .begin=async_begin, .poll=async_poll, .cancel=async_cancel, .service_begin=service_begin, .service_end=service_end
};
static bool start(const risc_provider_dependency_v1 *d, size_t n) {
    if (claim || running)
        return false;
    const risc_hw_radio_v1 *next =
        hardware_config(d, n, "espressif,esp32s3-wifi", "radio.integrated", sizeof(*next));
    if (!next || next->unit > 3 || !next->features || (next->features & ~3u))
        return false;
    hardware = *next;
    radio = garden_dependency(d, n, "platform.radio", GARDEN_RADIO_PREFIX_V1_SIZE);
    if (!radio || !radio->claim || !radio->join || !radio->state || !radio->leave ||
        !radio->release || !radio->start_ap || !radio->stop_ap || !radio->addresses)
        return false;
    async_radio=NULL;api.base.struct_size=sizeof(wifi_api_v1);
    if(radio->struct_size>=sizeof(garden_radio_async_v1)){
        const garden_radio_async_v1 *next_async=(const garden_radio_async_v1*)radio;
        if(next_async->async_tag==RISC_RADIO_ASYNC_TAG && next_async->async_version==RISC_RADIO_ASYNC_VERSION &&
           next_async->begin && next_async->poll && next_async->cancel && next_async->service_begin && next_async->service_end){async_radio=next_async;api.base.struct_size=sizeof(api);}
    }
    operation=completed=service_lease=0;
    running = radio->claim(radio->context, &claim) && claim;
    return running;
}
static bool quiesce(void) {
    if(service_lease)return false;
    if(operation && async_cancel(NULL,operation)!=RISC_RADIO_QUIESCENT)return false;
    running = false;
    if (!claim)
        return true;
    bool cancelled = !scan_available() || radio->scan_cancel(radio->context, claim);
    bool stopped = radio->stop_ap(radio->context, claim);
    bool left = radio->leave(radio->context, claim);
    if (!cancelled || !stopped || !left || !radio->release(radio->context, claim)) return false;
    claim = 0;
    return true;
}
static void stop(void) {
    if (quiesce())
        radio = NULL;
}
static const risc_driver_v2 driver = {2,    sizeof(driver), "wifi", "net.wifi", 1,
                                      &api, start,          stop,   quiesce};
__attribute__((visibility("default"))) const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == 2 ? &driver : NULL;
}

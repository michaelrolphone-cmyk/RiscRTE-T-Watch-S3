#pragma once
#include "WifiApi.h"
#include "RiscWifiStationV1.h"
/* App-facing extension of net.wifi@1. Same operation IDs, progress/cancel and
 * service leases as wifi_async_v1. No direct SDK APIs or borrowed credentials. */
typedef struct {
    wifi_async_v1 base;
    uint32_t station_tag, station_version;
    int32_t (*begin_station)(void *,const risc_wifi_station_request_v1 *,uint32_t *);
    int32_t (*observe)(void *,uint32_t,risc_wifi_station_observation_v1 *);
    int32_t (*request)(void *,uint32_t,uint32_t);
} risc_wifi_manager_v1;
static inline const risc_wifi_manager_v1 *risc_wifi_manager_get_v1(const wifi_api_v1 *base) {
    if(!base||base->api_version!=1||base->struct_size<sizeof(risc_wifi_manager_v1))return NULL;
    const risc_wifi_manager_v1 *api=(const risc_wifi_manager_v1 *)base;
    return api->station_tag==RISC_WIFI_STATION_TAG&&api->station_version==1&&api->begin_station&&api->observe&&api->request?api:NULL;
}

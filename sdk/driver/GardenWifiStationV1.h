#pragma once
#include "GardenRadioAsyncV1.h"
#include "RiscWifiStationV1.h"
typedef struct {
    garden_radio_async_v1 base;
    uint32_t station_tag, station_version;
    int32_t (*begin_station)(void *,uint64_t,const risc_wifi_station_request_v1 *,uint32_t *);
    int32_t (*observe)(void *,uint64_t,uint32_t,risc_wifi_station_observation_v1 *);
    int32_t (*request)(void *,uint64_t,uint32_t,uint32_t);
} garden_wifi_station_v1;
static inline const garden_wifi_station_v1 *garden_wifi_station_get_v1(const garden_radio_v1 *base) {
    if(!base||base->struct_size<sizeof(garden_wifi_station_v1))return NULL;
    const garden_wifi_station_v1 *api=(const garden_wifi_station_v1 *)base;
    return api->station_tag==RISC_WIFI_STATION_TAG&&api->station_version==1&&api->begin_station&&api->observe&&api->request?api:NULL;
}

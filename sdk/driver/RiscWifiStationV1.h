#pragma once
#include "RiscRadioAsyncV1.h"
/* Optional station-management extension. All inputs/outputs are copied. The
 * native worker owns SDK work; GUI clients never receive SDK or task pointers.
 * Existing scan, join, progress, and lease tables keep their exact layouts. */
#define RISC_WIFI_STATION_TAG UINT32_C(0x57535431)
#define RISC_WIFI_FEATURE_DETAILS 1u
#define RISC_WIFI_FEATURE_STATIC_IPV4 2u
#define RISC_WIFI_FEATURE_CONNECTED_SCAN 4u
#define RISC_WIFI_FEATURE_INTERNET_CHECK 8u
#define RISC_WIFI_USE_BSSID 1u
#define RISC_WIFI_HIDDEN_SSID 2u
#define RISC_WIFI_OBSERVATION_ASSOCIATED 1u
#define RISC_WIFI_OBSERVATION_ADDRESSED 2u
#define RISC_WIFI_OBSERVATION_DETAILS 4u
#define RISC_WIFI_OBSERVATION_DNS 8u
#define RISC_WIFI_OBSERVATION_SPEED 16u
#define RISC_WIFI_COMMAND_SCAN 1u
#define RISC_WIFI_COMMAND_CHECK_INTERNET 2u
enum { RISC_WIFI_INTERNET_UNKNOWN, RISC_WIFI_INTERNET_CHECKING,
       RISC_WIFI_INTERNET_REACHABLE, RISC_WIFI_INTERNET_PORTAL,
       RISC_WIFI_INTERNET_UNREACHABLE };
enum { RISC_WIFI_ERROR_NONE, RISC_WIFI_ERROR_AUTH, RISC_WIFI_ERROR_NO_AP,
       RISC_WIFI_ERROR_ADDRESS, RISC_WIFI_ERROR_TIMEOUT, RISC_WIFI_ERROR_SETUP,
       RISC_WIFI_ERROR_LINK_LOST };
typedef struct {
    uint32_t struct_size, flags;
    uint8_t security, channel, static_ipv4, reserved;
    uint8_t bssid[6], reserved2[2];
    uint8_t address[4], gateway[4], netmask[4], dns[4];
} risc_wifi_station_config_v1;
typedef struct {
    uint32_t struct_size;
    risc_radio_request_v1 operation;
    risc_wifi_station_config_v1 config;
} risc_wifi_station_request_v1;
typedef struct {
    uint32_t struct_size, operation_id, features, flags;
    uint32_t failure, sdk_reason, internet, http_status, link_kbps;
    uint32_t scan_revision, probe_revision;
    uint8_t channel, security; int8_t rssi; uint8_t reserved;
    uint8_t bssid[6], reserved2[2];
    char ssid[33]; uint8_t reserved3[3];
    uint8_t address[4], gateway[4], netmask[4], dns[4];
    garden_radio_scan_result_v1 scan;
    uint8_t scan_bssid[GARDEN_RADIO_SCAN_MAX][6];
} risc_wifi_station_observation_v1;
/* Network-order octets; no platform inet functions or endian assumptions. */
static inline uint32_t risc_wifi_ip_number(const uint8_t p[4]) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static inline bool risc_wifi_unicast(const uint8_t p[4]) { return p[0]&&p[0]!=127&&p[0]<224; }
static inline bool risc_wifi_static_valid(const risc_wifi_station_config_v1 *p) {
    uint32_t mask=risc_wifi_ip_number(p->netmask),host=~mask;
    uint32_t ip=risc_wifi_ip_number(p->address),gateway=risc_wifi_ip_number(p->gateway);
    return risc_wifi_unicast(p->address)&&risc_wifi_unicast(p->gateway)&&risc_wifi_unicast(p->dns)&&
        mask&&host>=3&&!(host&(host+1))&&(ip&host)&&(ip&host)!=host&&
        (gateway&host)&&(gateway&host)!=host&&(ip&mask)==(gateway&mask)&&ip!=gateway;
}
static inline bool risc_wifi_config_valid(const risc_wifi_station_config_v1 *p) {
    if(!p||p->struct_size!=sizeof(*p)||p->flags&~3u||p->channel>14||p->static_ipv4>1||p->reserved||p->reserved2[0]||p->reserved2[1]||p->security>GARDEN_RADIO_AUTH_WPA2_WPA3_PSK)return false;
    unsigned nonzero=0;for(unsigned i=0;i<6;i++)nonzero|=p->bssid[i];
    if(p->flags&RISC_WIFI_USE_BSSID){if(!nonzero||(p->bssid[0]&1u))return false;}else if(nonzero)return false;
    if(p->static_ipv4)return risc_wifi_static_valid(p);
    for(unsigned i=0;i<4;i++)if(p->address[i]||p->gateway[i]||p->netmask[i]||p->dns[i])return false;
    return true;
}
typedef struct {
    risc_native_radio_async_v1 base;
    uint32_t station_tag, station_version;
    int32_t (*begin_station)(const risc_wifi_station_request_v1 *,uint32_t *);
    int32_t (*observe)(uint32_t,risc_wifi_station_observation_v1 *);
    int32_t (*request)(uint32_t,uint32_t);
} risc_native_wifi_station_v1;
static inline const risc_native_wifi_station_v1 *risc_native_wifi_station_get_v1(const risc_native_radio_async_v1 *base) {
    if(!base||base->struct_size<sizeof(risc_native_wifi_station_v1))return NULL;
    const risc_native_wifi_station_v1 *api=(const risc_native_wifi_station_v1 *)base;
    return api->station_tag==RISC_WIFI_STATION_TAG&&api->station_version==1&&api->begin_station&&api->observe&&api->request?api:NULL;
}

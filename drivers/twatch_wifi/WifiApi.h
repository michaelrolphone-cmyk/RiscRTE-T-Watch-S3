#pragma once
/* net.wifi@1. Generic station link. Radio comes from a provider. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "RiscRadioScanV1.h"
#define WIFI_API_V1 1u
typedef enum { WIFI_LINK_DOWN = 0, WIFI_LINK_JOINING, WIFI_LINK_UP } wifi_link_t;
typedef struct {
    uint8_t address[4], gateway[4], netmask[4];
} wifi_ipv4_v1;
typedef struct {
    uint32_t api_version;
    uint32_t struct_size;
    void *context;
    bool (*connect)(void *context, const char *ssid, const char *password);
    void (*disconnect)(void *context);
    wifi_link_t (*status)(void *context);
    int8_t (*rssi)(void *context);
    bool (*start_ap)(void *context, const char *ssid, const char *password, const wifi_ipv4_v1 *config);
    bool (*stop_ap)(void *context);
    bool (*addresses)(void *context, wifi_ipv4_v1 *station, wifi_ipv4_v1 *access_point);
    /* Append-only station-management suffix. Check WIFI_MANAGEMENT_V1_SIZE.
     * Results are bounded copied snapshots. join is not a successful link.
     * disconnect_checked drains station/scan state before it reports success;
     * false retains native ownership and forbids sleep or app exit. */
    bool (*scan_start)(void *context);
    bool (*scan_poll)(void *context, garden_radio_scan_result_v1 *result);
    bool (*scan_cancel)(void *context);
    bool (*disconnect_checked)(void *context);
} wifi_api_v1;
#define WIFI_PREFIX_V1_SIZE offsetof(wifi_api_v1, scan_start)
#define WIFI_SCAN_V1_SIZE (offsetof(wifi_api_v1, scan_cancel) + sizeof(((wifi_api_v1*)0)->scan_cancel))
#define WIFI_MANAGEMENT_V1_SIZE (offsetof(wifi_api_v1, disconnect_checked) + sizeof(((wifi_api_v1*)0)->disconnect_checked))

/* The append-only v1 extension is declared in the structure above; IPv4 values
 * are byte arrays in network order. SSIDs max 32, WPA passwords 8..63 (or empty
 * for an explicitly requested open AP). Callers serialize link operations. */

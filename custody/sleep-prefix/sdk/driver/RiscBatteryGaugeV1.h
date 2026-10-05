#pragma once
#include "RiscProviderV2.h"
#ifdef __cplusplus
extern "C" {
#endif
#define RISC_BATTERY_GAUGE_API_V1 1u
#define RISC_BATTERY_GAUGE_CAPABILITY "board.battery"
enum { RISC_BATTERY_CHARGING = 1u << 0, RISC_BATTERY_PROFILE_MISSING = 1u << 1 };
typedef struct { uint16_t millivolts; uint8_t percent, flags; } risc_battery_sample_v1;
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*read)(void *context, risc_battery_sample_v1 *out);
} risc_battery_gauge_api_v1;
#ifdef __cplusplus
}
#endif

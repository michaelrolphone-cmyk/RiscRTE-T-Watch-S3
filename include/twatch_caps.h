#pragma once
#include "RiscProviderV2.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Board-local capabilities. Runtime treats the id as opaque. These are not
 * upstream RiscRTE capabilities until a later ABI promotion. */
#define TWATCH_MOTION_API_V1 1u
#define TWATCH_MOTION_CAPABILITY "motion.accel"
typedef struct { int16_t x, y, z; } twatch_accel_sample_v1;
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*read)(void *context, twatch_accel_sample_v1 *out);
    bool (*chip_id)(void *context, uint8_t *out);
} twatch_motion_api_v1;

#define TWATCH_RTC_API_V1 1u
#define TWATCH_RTC_CAPABILITY "rtc.clock"
typedef struct {
    uint16_t year; uint8_t month, day, weekday, hour, minute, second;
} twatch_rtc_time_v1;
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*read)(void *context, twatch_rtc_time_v1 *out);
    bool (*write)(void *context, const twatch_rtc_time_v1 *in);
} twatch_rtc_api_v1;

#define TWATCH_HAPTIC_API_V1 1u
#define TWATCH_HAPTIC_CAPABILITY "haptic.effect"
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*effect)(void *context, uint8_t effect_id);
    bool (*stop)(void *context);
} twatch_haptic_api_v1;

#define TWATCH_RADIO_API_V1 1u
#define TWATCH_RADIO_CAPABILITY "radio.lora"
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*probe)(void *context, uint8_t *status_out);
    bool (*read_register)(void *context, uint16_t address, uint8_t *out, size_t length);
    /* Packet TX/RX is intentionally absent. A false probe is not a radio. */
} twatch_radio_api_v1;

#define TWATCH_AUDIO_API_V1 1u
#define TWATCH_AUDIO_CAPABILITY "audio.sink"
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*silence)(void *context);
} twatch_audio_api_v1;
#ifdef __cplusplus
}
#endif

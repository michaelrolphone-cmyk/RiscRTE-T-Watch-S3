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

/* Speaker and microphone are separate providers. ESP32-S3 PDM exists only on
 * I2S0, and the S3 I2S FIFO has no CPU port, so these ELFs bit-bang the pads
 * instead of taking a GDMA channel the firmware may already own. */
#define TWATCH_AUDIO_OUT_API_V1 1u
#define TWATCH_AUDIO_OUT_CAPABILITY "audio.output"
#define TWATCH_AUDIO_IN_API_V1 1u
#define TWATCH_AUDIO_IN_CAPABILITY "audio.input"
#define TWATCH_AUDIO_MAX_FRAMES 256u
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    /* rate_hz is the requested PCM rate. channels is 1 or 2. Software bit-bang
     * does not lock to a PLL; a false return means the rate was rejected. */
    bool (*open)(void *context, uint32_t rate_hz, uint8_t channels);
    /* frames are s16le. Mono is written to both MAX98357A slots. */
    bool (*write)(void *context, const int16_t *pcm, size_t frames);
    bool (*set_gain)(void *context, uint16_t level, uint16_t maximum);
    bool (*silence)(void *context);
    bool (*close)(void *context);
} twatch_audio_out_api_v1;
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*open)(void *context, uint32_t rate_hz);
    /* Decimated s16le PCM. *got is the number of frames written. */
    bool (*read)(void *context, int16_t *pcm, size_t frames, size_t *got);
    bool (*level)(void *context, uint16_t *rms_out);
    bool (*close)(void *context);
} twatch_audio_in_api_v1;

#define TWATCH_IR_API_V1 1u
#define TWATCH_IR_CAPABILITY "ir.transmit"
#define TWATCH_IR_MAX_RAW 128u
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    /* Standard NEC: 8-bit address, 8-bit command, both sent with complements. */
    bool (*send_nec)(void *context, uint8_t address, uint8_t command);
    /* 32-bit NEC frame, LSB first, as used by LilyGO IRsend.sendNEC. */
    bool (*send_nec32)(void *context, uint32_t frame);
    /* Even entries are marks, odd entries are spaces, microseconds. */
    bool (*send_raw)(void *context, const uint16_t *microseconds, size_t count, uint16_t carrier_hz);
    bool (*idle)(void *context);
} twatch_ir_api_v1;
#ifdef __cplusplus
}
#endif

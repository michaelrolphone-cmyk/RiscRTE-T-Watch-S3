#pragma once
#include "RiscProviderV2.h"
#include "RiscBatteryGaugeV1.h"
#include "RiscLightSleepV1.h"
#include "RiscDeepSleepV1.h"
typedef struct {
    risc_battery_gauge_api_v1 base;
    bool (*key_events)(void *, uint32_t *events);
    /* Append-only crown sleep preparation. See docs/CROWN_SLEEP.md. */
    bool (*prepare_sleep)(void *);
    bool (*resume)(void *);
    int32_t (*light_sleep)(void *, risc_light_sleep_result_v1 *);
    /* Successful terminal entry never returns; old light-sleep prefix intact. */
    int32_t (*deep_sleep)(void *);
    /* Optional owned timer; no application schedule in this driver. */
    int32_t (*light_sleep_for)(void *, uint32_t duration_ms, risc_light_sleep_result_v1 *);
    /* Observe latched key bits AND physical IRQ without acknowledging either.
     * A key at the timer boundary takes priority over application deep entry. */
    bool (*sleep_wake_pending)(void *, bool *pending);
    /* Optional owned timer Deep entry; successful entry remains terminal. */
    int32_t (*deep_sleep_for)(void *, uint32_t duration_ms);
} twatch_pmu_api_v1;
#define TWATCH_PMU_LIGHT_SLEEP_SIZE offsetof(twatch_pmu_api_v1, deep_sleep)
#define TWATCH_PMU_DEEP_SLEEP_SIZE offsetof(twatch_pmu_api_v1, light_sleep_for)
#define TWATCH_PMU_TIMED_SLEEP_SIZE offsetof(twatch_pmu_api_v1, deep_sleep_for)
#define TWATCH_PMU_TIMED_DEEP_SLEEP_SIZE sizeof(twatch_pmu_api_v1)
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
typedef struct {
    int16_t x, y, z;
} twatch_accel_sample_v1;
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*read)(void *context, twatch_accel_sample_v1 *out);
    bool (*chip_id)(void *context, uint8_t *out);
} twatch_motion_api_v1;

#define TWATCH_RTC_API_V1 2u
#define TWATCH_RTC_CAPABILITY "rtc.clock"
typedef struct {
    uint16_t year;
    uint8_t month, day, weekday, hour, minute, second;
} twatch_rtc_time_v1;
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*read)(void *context, twatch_rtc_time_v1 *out);
    bool (*write)(void *context, const twatch_rtc_time_v1 *in);
    bool (*alarm)(void *, uint8_t minute, uint8_t hour, uint8_t day, uint8_t weekday, bool enable);
    bool (*alarm_pending)(void *, bool *pending, bool acknowledge);
} twatch_rtc_api_v1;

#define TWATCH_HAPTIC_API_V1 1u
#define TWATCH_HAPTIC_CAPABILITY "haptic.effect"
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*effect)(void *context, uint8_t effect_id);
    bool (*stop)(void *context);
} twatch_haptic_api_v1;

/* Complete LoRa packet contract, distinct version from the former probe API. */
#define TWATCH_RADIO_API_V1 2u
#define TWATCH_RADIO_CAPABILITY "radio.lora"
typedef struct {
    uint32_t frequency_hz, bandwidth_hz;
    uint16_t preamble;
    uint8_t sf, coding_rate;
    int8_t power_dbm;
    uint8_t reserved[3];
} twatch_lora_config_v2;
typedef struct {
    uint8_t state, length;
    int16_t rssi_dbm;
    int8_t snr_quarter_db;
    uint8_t reserved[3];
} twatch_lora_status_v2;
enum {
    TW_LORA_IDLE,
    TW_LORA_TX,
    TW_LORA_RX,
    TW_LORA_SENT,
    TW_LORA_RECEIVED,
    TW_LORA_TIMEOUT,
    TW_LORA_CRC_ERROR,
    TW_LORA_IO_ERROR
};
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*configure)(void *, const twatch_lora_config_v2 *);
    bool (*send)(void *, const uint8_t *, size_t, uint32_t timeout_ms);
    bool (*receive)(void *, uint32_t timeout_ms);
    bool (*poll)(void *, twatch_lora_status_v2 *);
    bool (*read)(void *, uint8_t *, size_t, size_t *);
    bool (*cancel)(void *);
} twatch_radio_api_v2;

/* Speaker and microphone are separate providers backed by clocked I2S DMA. */
#define TWATCH_AUDIO_OUT_API_V1 1u
#define TWATCH_AUDIO_OUT_CAPABILITY "audio.output"
#define TWATCH_AUDIO_IN_API_V1 1u
#define TWATCH_AUDIO_IN_CAPABILITY "audio.input"
#define TWATCH_AUDIO_MAX_FRAMES 256u
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    /* Clocked PCM rate, channels 1 or 2; false means no open stream. */
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
    bool (*send_raw)(void *context, const uint16_t *microseconds, size_t count,
                     uint16_t carrier_hz);
    bool (*idle)(void *context);
} twatch_ir_api_v1;
#ifdef __cplusplus
}
#endif

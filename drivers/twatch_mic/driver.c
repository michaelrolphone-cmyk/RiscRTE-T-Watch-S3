/* SPM1423HM4H-B PDM microphone on GPIO44 clock and GPIO47 data.
 * PDM-to-PCM on the ESP32-S3 exists only on I2S0 and its FIFO is DMA-only.
 * This ELF clocks the mic and decimates in software. Not captured on a watch. */
#include "RiscGpioBankV1.h"
#include "twatch_caps.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
#define DECIMATE 64u
static const risc_gpio_bank_api_v1 *gpio_api;
static uint64_t clk, data;
static bool started, opened;
static uint32_t rate_hz;
static uint16_t last_rms;
static char error[72];
static void set_error(const char *msg) { twatch_copy_error(error, sizeof error, msg); }
static bool pdm_bit(void) {
    bool level = false;
    (void)gpio_api->write(gpio_api->context, clk, true);
    (void)gpio_api->read(gpio_api->context, data, &level);
    (void)gpio_api->write(gpio_api->context, clk, false);
    return level;
}
static int16_t decimate_one(void) {
    int32_t acc = 0;
    for (uint32_t i = 0; i < DECIMATE; ++i) acc += pdm_bit() ? 1 : -1;
    /* 64 ones -> 32767. First-order, no CIC compensation. */
    int32_t sample = acc * (32767 / (int32_t)DECIMATE);
    if (sample > 32767) sample = 32767;
    if (sample < -32768) sample = -32768;
    return (int16_t)sample;
}
static bool open_in(void *context, uint32_t rate) {
    (void)context;
    if (!started || opened) return false;
    if (rate != 8000u && rate != 16000u) {
        set_error("mic rate must be 8000 or 16000");
        return false;
    }
    rate_hz = rate;
    opened = true;
    last_rms = 0;
    return gpio_api->write(gpio_api->context, clk, false);
}
static bool read_pcm(void *context, int16_t *pcm, size_t frames, size_t *got) {
    (void)context;
    if (!opened || !pcm || !got || !frames || frames > TWATCH_AUDIO_MAX_FRAMES) return false;
    uint32_t sum = 0;
    for (size_t i = 0; i < frames; ++i) {
        pcm[i] = decimate_one();
        int32_t v = pcm[i] < 0 ? -pcm[i] : pcm[i];
        sum += (uint32_t)v;
    }
    last_rms = (uint16_t)(sum / frames);
    *got = frames;
    return true;
}
static bool level(void *context, uint16_t *rms_out) {
    (void)context;
    if (!opened || !rms_out) return false;
    *rms_out = last_rms;
    return true;
}
static bool close_in(void *context) {
    (void)context;
    if (!opened) return false;
    opened = false;
    rate_hz = 0;
    return gpio_api->write(gpio_api->context, clk, false);
}
static bool last_error(char *dst, size_t cap) {
    if (!error[0]) return false;
    twatch_copy_error(dst, cap, error);
    return true;
}
static bool quiesce(void) {
    if (opened) (void)close_in(NULL);
    bool ok = true;
    if (clk && gpio_api && !gpio_api->release(gpio_api->context, clk)) ok = false;
    if (data && gpio_api && !gpio_api->release(gpio_api->context, data)) ok = false;
    clk = data = 0;
    gpio_api = NULL;
    started = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 1u) return false;
    if (!twatch_equal(deps[0].capability_id, RISC_GPIO_BANK_CAPABILITY)) return false;
    gpio_api = deps[0].api;
    if (!gpio_api ||
        !gpio_api->claim(gpio_api->context, TWATCH_PIN_MIC_SCK, RISC_GPIO_OUTPUT, &clk) ||
        !gpio_api->claim(gpio_api->context, TWATCH_PIN_MIC_DAT, RISC_GPIO_INPUT, &data)) {
        set_error("SPM1423 pin claim failed");
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const twatch_audio_in_api_v1 api = {
    TWATCH_AUDIO_IN_API_V1, sizeof(api), NULL, open_in, read_pcm, level, close_in
};
static const risc_driver_diagnostics_v2 driver = {
    { RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-mic",
      TWATCH_AUDIO_IN_CAPABILITY, TWATCH_AUDIO_IN_API_V1,
      &api, start, stop, quiesce },
    last_error
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver.base : NULL;
}

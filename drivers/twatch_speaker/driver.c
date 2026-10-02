/* MAX98357A Philips I2S playback on GPIO48 BCLK, GPIO15 WCLK, GPIO46 DIN.
 * The S3 I2S FIFO is DMA-only. This ELF bit-bangs the pads so it does not
 * take a GDMA channel. Not heard on a watch in this tree. */
#include "RiscGpioBankV1.h"
#include "twatch_caps.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
static const risc_gpio_bank_api_v1 *gpio_api;
static uint64_t bclk, wclk, dout;
static bool started, opened;
static uint32_t rate_hz;
static uint8_t channels;
static uint16_t gain = 256, gain_max = 256;
static char error[72];
static void set_error(const char *msg) { twatch_copy_error(error, sizeof error, msg); }
static bool pin(uint64_t claim, bool level) {
    return gpio_api->write(gpio_api->context, claim, level);
}
static void bit(bool data) {
    (void)pin(dout, data);
    (void)pin(bclk, false);
    (void)pin(bclk, true);
}
static void slot(int16_t sample) {
    uint16_t bits = (uint16_t)sample;
    for (int i = 15; i >= 0; --i) bit((bits >> i) & 1u);
}
static int16_t apply_gain(int16_t sample) {
    int32_t scaled = ((int32_t)sample * (int32_t)gain) / (int32_t)gain_max;
    if (scaled > 32767) return 32767;
    if (scaled < -32768) return -32768;
    return (int16_t)scaled;
}
static bool open_out(void *context, uint32_t rate, uint8_t ch) {
    (void)context;
    if (!started || opened || (ch != 1u && ch != 2u)) return false;
    if (rate != 8000u && rate != 16000u && rate != 22050u && rate != 44100u) {
        set_error("speaker rate must be 8000, 16000, 22050, or 44100");
        return false;
    }
    rate_hz = rate;
    channels = ch;
    opened = true;
    (void)pin(wclk, false);
    (void)pin(bclk, false);
    (void)pin(dout, false);
    return true;
}
static bool write_pcm(void *context, const int16_t *pcm, size_t frames) {
    (void)context;
    if (!opened || !pcm || !frames || frames > TWATCH_AUDIO_MAX_FRAMES) return false;
    for (size_t i = 0; i < frames; ++i) {
        int16_t left = apply_gain(pcm[channels == 1u ? i : i * 2u]);
        int16_t right = apply_gain(channels == 1u ? left : pcm[i * 2u + 1u]);
        /* Philips: WS low is left, MSB one BCLK after the WS edge. */
        (void)pin(wclk, false);
        (void)pin(bclk, false);
        slot(left);
        (void)pin(wclk, true);
        (void)pin(bclk, false);
        slot(right);
    }
    (void)pin(bclk, false);
    return true;
}
static bool set_gain(void *context, uint16_t level, uint16_t maximum) {
    (void)context;
    if (!started || !maximum || level > maximum) return false;
    gain = level;
    gain_max = maximum;
    return true;
}
static bool silence(void *context) {
    (void)context;
    if (!started) return false;
    int16_t zeros[8] = {0};
    if (opened) {
        uint8_t saved = channels;
        channels = 1;
        (void)write_pcm(NULL, zeros, 8);
        channels = saved;
    }
    return pin(bclk, false) && pin(wclk, false) && pin(dout, false);
}
static bool close_out(void *context) {
    if (!opened) return false;
    (void)silence(context);
    opened = false;
    rate_hz = 0;
    channels = 0;
    return true;
}
static bool last_error(char *dst, size_t cap) {
    if (!error[0]) return false;
    twatch_copy_error(dst, cap, error);
    return true;
}
static bool quiesce(void) {
    if (opened) (void)close_out(NULL);
    bool ok = true;
    uint64_t *all[] = {&bclk, &wclk, &dout};
    for (size_t i = 0; i < 3; ++i) {
        if (*all[i] && gpio_api && !gpio_api->release(gpio_api->context, *all[i])) ok = false;
        *all[i] = 0;
    }
    gpio_api = NULL;
    started = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 1u) return false;
    if (!twatch_equal(deps[0].capability_id, RISC_GPIO_BANK_CAPABILITY)) return false;
    gpio_api = deps[0].api;
    if (!gpio_api ||
        !gpio_api->claim(gpio_api->context, TWATCH_PIN_I2S_BCLK, RISC_GPIO_OUTPUT, &bclk) ||
        !gpio_api->claim(gpio_api->context, TWATCH_PIN_I2S_WCLK, RISC_GPIO_OUTPUT, &wclk) ||
        !gpio_api->claim(gpio_api->context, TWATCH_PIN_I2S_DOUT, RISC_GPIO_OUTPUT, &dout) ||
        !silence(NULL)) {
        set_error("MAX98357A pin claim failed");
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const twatch_audio_out_api_v1 api = {
    TWATCH_AUDIO_OUT_API_V1, sizeof(api), NULL,
    open_out, write_pcm, set_gain, silence, close_out
};
static const risc_driver_diagnostics_v2 driver = {
    { RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-speaker",
      TWATCH_AUDIO_OUT_CAPABILITY, TWATCH_AUDIO_OUT_API_V1,
      &api, start, stop, quiesce },
    last_error
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver.base : NULL;
}

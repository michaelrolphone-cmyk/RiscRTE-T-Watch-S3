/* MAX98357A consumes clocked Philips I2S. Device policy (gain/channel mapping)
 * stays here; the raw I2S controller owns DMA, timing and pin arbitration. */
#include "twatch_support.h"
#include "twatch_caps.h"
static const twatch_i2s_controller_v1 *hw;
static uint64_t stream;
static bool started;
static uint8_t channels;
static uint16_t gain = 256, maximum = 256;
static uint8_t controller_no, clock_pin, data_pin;
static int8_t ws_pin;
static bool open_out(void *c, uint32_t rate, uint8_t ch) {
    (void)c;
    if (!started || stream || (ch != 1 && ch != 2) ||
        (rate != 8000 && rate != 16000 && rate != 22050 && rate != 44100))
        return false;
    if (!hw->open(hw->context, controller_no, false, clock_pin, ws_pin, data_pin, rate, 2,
                  &stream) ||
        !stream)
        return false;
    channels = ch;
    return true;
}
static int16_t scale(int16_t x) {
    return (int16_t)((int32_t)x * gain / maximum);
}
static bool write_pcm(void *c, const int16_t *pcm, size_t frames) {
    (void)c;
    if (!started || !stream || !pcm || !frames || frames > 256)
        return false;
    int16_t wire[512];
    for (size_t i = 0; i < frames; i++) {
        wire[2 * i] = scale(pcm[i * channels]);
        wire[2 * i + 1] = channels == 1 ? wire[2 * i] : scale(pcm[2 * i + 1]);
    }
    size_t done = 0;
    return hw->write(hw->context, stream, wire, frames, &done, 40) && done == frames;
}
static bool set_gain(void *c, uint16_t g, uint16_t m) {
    (void)c;
    if (!started || !m || g > m)
        return false;
    gain = g;
    maximum = m;
    return true;
}
static bool silence(void *c) {
    (void)c;
    if (!started)
        return false;
    if (!stream)
        return true;
    int16_t zeros[64] = {0};
    size_t done = 0;
    return hw->write(hw->context, stream, zeros, 32, &done, 40) && done == 32;
}
static bool close_out(void *c) {
    (void)c;
    if (!stream)
        return started;
    if (!hw->close(hw->context, stream))
        return false;
    stream = 0;
    channels = 0;
    return true;
}
static bool quiesce(void) {
    if (stream && !close_out(NULL))
        return false;
    started = false;
    hw = NULL;
    return true;
}
static bool start(const risc_provider_dependency_v1 *d, size_t n) {
    if (started || stream)
        return false;
    hw = tw_dep(d, n, "platform.i2s.controller", sizeof(*hw));
    if (!hw || !hw->open || !hw->write || !hw->read || !hw->close)
        return false;
    /* Config is supplied by the matched hardware entry; populated below. */
    if (!tw_audio_config(d, n, "maxim,max98357a", &controller_no, &clock_pin, &ws_pin, &data_pin))
        return false;
    gain = maximum = 256;
    started = true;
    return true;
}
static const twatch_audio_out_api_v1 api = {1,         sizeof(api), NULL,    open_out,
                                            write_pcm, set_gain,    silence, close_out};
TW_DRIVER("twatch-speaker", "audio.output", 1, api)

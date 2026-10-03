/* SPM1423 PDM input: hardware PDM-to-PCM conversion on an authorized controller. */
#include "twatch_support.h"
#include "twatch_caps.h"
static const twatch_i2s_controller_v1 *hw;
static uint64_t stream;
static bool started;
static uint16_t mean_absolute;
static uint8_t controller_no, clock_pin, data_pin;
static int8_t ws_pin;
static bool open_in(void *c, uint32_t rate) {
    (void)c;
    if (!started || stream || (rate != 8000 && rate != 16000))
        return false;
    return hw->open(hw->context, controller_no, true, clock_pin, -1, data_pin, rate, 1, &stream) &&
           stream;
}
static bool read_pcm(void *c, int16_t *pcm, size_t frames, size_t *got) {
    (void)c;
    if (got)
        *got = 0;
    if (!started || !stream || !pcm || !got || !frames || frames > 256)
        return false;
    bool ok = hw->read(hw->context, stream, pcm, frames, got, 40);
    if (*got > frames) {
        *got = 0;
        return false;
    }
    uint32_t sum = 0;
    for (size_t i = 0; i < *got; i++)
        sum += pcm[i] < 0 ? -(int32_t)pcm[i] : pcm[i];
    mean_absolute = *got ? (uint16_t)(sum / *got) : 0;
    return ok;
}
static bool level(void *c, uint16_t *out) {
    (void)c;
    if (!started || !stream || !out)
        return false;
    *out = mean_absolute;
    return true;
}
static bool close_in(void *c) {
    (void)c;
    if (!stream)
        return started;
    if (!hw->close(hw->context, stream))
        return false;
    stream = 0;
    return true;
}
static bool quiesce(void) {
    if (stream && !close_in(NULL))
        return false;
    started = false;
    hw = NULL;
    return true;
}
static bool start(const risc_provider_dependency_v1 *d, size_t n) {
    if (started || stream)
        return false;
    hw = tw_dep(d, n, "platform.i2s.controller", sizeof(*hw));
    if (!hw || !hw->open || !hw->read || !hw->write || !hw->close ||
        !tw_audio_config(d, n, "knowles,spm1423", &controller_no, &clock_pin, &ws_pin, &data_pin))
        return false;
    mean_absolute = 0;
    started = true;
    return true;
}
static const twatch_audio_in_api_v1 api = {1,        sizeof(api), NULL,    open_in,
                                           read_pcm, level,       close_in};
TW_DRIVER("twatch-mic", "audio.input", 1, api)

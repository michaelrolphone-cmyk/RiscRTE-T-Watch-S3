/* Holds the MAX98357A I2S pads low so the amp does not play a floating DIN.
 * PCM playback is not implemented; silence() is the whole capability. */
#include "RiscGpioBankV1.h"
#include "twatch_caps.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
static const risc_gpio_bank_api_v1 *gpio_api;
static uint64_t bclk, wclk, dout;
static bool started;
static bool silence(void *context) {
    (void)context;
    return started &&
           gpio_api->write(gpio_api->context, bclk, false) &&
           gpio_api->write(gpio_api->context, wclk, false) &&
           gpio_api->write(gpio_api->context, dout, false);
}
static bool quiesce(void) {
    bool ok = true;
    uint64_t *all[] = {&bclk, &wclk, &dout};
    for (size_t i = 0; i < 3; ++i) {
        if (*all[i] && gpio_api && !gpio_api->release(gpio_api->context, *all[i])) ok = false;
        *all[i] = 0;
    }
    gpio_api = NULL; started = false;
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
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const twatch_audio_api_v1 api = {
    TWATCH_AUDIO_API_V1, sizeof(api), NULL, silence
};
static const risc_driver_v2 driver = {
    RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-audio",
    TWATCH_AUDIO_CAPABILITY, TWATCH_AUDIO_API_V1, &api, start, stop, quiesce
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

/* BOOT is GPIO0, active low. The POWER key is the AXP2101 PWRON pin, already
 * claimed by twatch-pmu, and is the hardware 2 s on / 6 s off control. This
 * ELF does not pretend that key is an ESP32 GPIO. */
#include "RiscGpioBankV1.h"
#include "RiscInputNavigationV1.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
static const risc_gpio_bank_api_v1 *gpio_api;
static uint64_t boot;
static bool started, armed, last;
static bool poll(void *context, risc_input_navigation_frame_v1 *out) {
    (void)context;
    if (!started || !out) return false;
    *out = (risc_input_navigation_frame_v1){0};
    bool level = true;
    if (!gpio_api->read(gpio_api->context, boot, &level)) return false;
    bool down = !level;
    if (!armed) {
        if (!down) armed = true;
        return true;
    }
    out->buttons = down ? RISC_NAV_BACK : 0;
    if (down && !last) out->pressed = RISC_NAV_BACK;
    if (!down && last) out->released = RISC_NAV_BACK;
    last = down;
    return true;
}
static bool foreground(void *context, const risc_input_foreground_v1 *claims, size_t count) {
    (void)context;
    (void)claims;
    return started && count == 0;
}
static bool reset(void *context) {
    (void)context;
    armed = false;
    last = false;
    return started;
}
static bool quiesce(void) {
    bool ok = !boot || !gpio_api || gpio_api->release(gpio_api->context, boot);
    boot = 0; gpio_api = NULL; started = false; armed = false; last = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 1u) return false;
    if (!twatch_equal(deps[0].capability_id, RISC_GPIO_BANK_CAPABILITY)) return false;
    gpio_api = deps[0].api;
    if (!gpio_api || !gpio_api->claim(gpio_api->context, TWATCH_PIN_BOOT,
                                     RISC_GPIO_INPUT | RISC_GPIO_PULLUP, &boot))
        return false;
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const risc_input_navigation_api_v1 api = {
    RISC_INPUT_NAVIGATION_API_V1, sizeof(api), NULL, poll, foreground, reset
};
static const risc_driver_v2 driver = {
    RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-button",
    RISC_INPUT_NAVIGATION_CAPABILITY, RISC_INPUT_NAVIGATION_API_V1,
    &api, start, stop, quiesce
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

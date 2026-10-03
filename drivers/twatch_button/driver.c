/* Debounced generic GPIO key, canonical navigation contract. */
#include "twatch_support.h"
#include "RiscInputNavigationV1.h"
static const garden_gpio_v1 *gpio;
static const risc_platform_clock_api_v1 *clock_api;
static const risc_hw_gpio_bank_v1 *config;
static uint64_t key, changed;
static bool started, armed, last, candidate, suppressed;
static bool poll(void *c, risc_input_navigation_frame_v1 *out) {
    (void)c;
    if (!started || !out)
        return false;
    *out = (risc_input_navigation_frame_v1){0};
    if (suppressed)
        return true;
    bool level;
    if (!gpio->read(gpio->context, key, &level))
        return false;
    bool down = level == (config->active_high != 0);
    uint64_t now = clock_api->monotonic_ms(clock_api->context);
    if (down != candidate) {
        candidate = down;
        changed = now;
    }
    if (now - changed < (config->debounce_us + 999) / 1000)
        return true;
    if (!armed) {
        if (!down)
            armed = true;
        return true;
    }
    out->buttons = down ? RISC_NAV_BACK : 0;
    out->pressed = down && !last ? RISC_NAV_BACK : 0;
    out->released = !down && last ? RISC_NAV_BACK : 0;
    last = down;
    return true;
}
static bool foreground(void *c, const risc_input_foreground_v1 *claims, size_t n) {
    (void)c;
    if (!started)
        return false;
    suppressed = true;
    armed = last = false;
    if (n > 4 || (n && !claims))
        return false;
    for (size_t i = 0; i < n; i++)
        if (!claims[i].capability || !claims[i].api_version)
            return false;
    suppressed = false;
    for (size_t i = 0; i < n; i++)
        if (twatch_equal(claims[i].capability, "input.navigation"))
            suppressed = true;
    return true;
}
static bool reset(void *c) {
    (void)c;
    if (!started)
        return false;
    armed = last = candidate = false;
    changed = clock_api->monotonic_ms(clock_api->context);
    return true;
}
static bool quiesce(void) {
    if (key) {
        if (!gpio->release(gpio->context, key))
            return false;
        key = 0;
    }
    started = false;
    gpio = NULL;
    return true;
}
static bool start(const risc_provider_dependency_v1 *d, size_t n) {
    if (started || key)
        return false;
    config = tw_config(d, n, "generic,gpio-button-bank", "gpio.bank", sizeof(*config));
    if (!config || config->count != 1 || !tw_pin(config->pins[0]) || config->active_high > 1 ||
        config->pull_up > 1 || config->reserved || !config->debounce_us ||
        config->debounce_us > 1000000)
        return false;
    gpio = tw_dep(d, n, "platform.gpio", sizeof(*gpio));
    clock_api = tw_dep(d, n, "platform.clock", sizeof(*clock_api));
    if (!gpio || !gpio->claim || !gpio->read || !gpio->release || !tw_clock_valid(clock_api))
        return false;
    if (!gpio->claim(gpio->context, config->pins[0], false, false, config->pull_up, &key) || !key)
        return false;
    started = true;
    suppressed = false;
    return reset(NULL);
}
static const risc_input_navigation_api_v1 api = {1, sizeof(api), NULL, poll, foreground, reset};
TW_DRIVER("twatch-button", "input.navigation", 1, api)

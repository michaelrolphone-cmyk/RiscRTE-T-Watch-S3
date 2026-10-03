/* Compatibility GPIO bank over the shared raw GPIO owner. No MMIO bypass. */
#include "twatch_support.h"
static const garden_gpio_v1 *hw;
static bool started;
static uint64_t serial;
static struct {
    uint64_t token, raw;
    uint32_t flags;
} slots[48];
static bool claim_pin(void *c, uint8_t pin, uint32_t flags, uint64_t *out) {
    (void)c;
    if (out)
        *out = 0;
    if (!started || !out || !tw_pin(pin) || serial == UINT64_MAX || !(flags & 3) || flags & ~7u)
        return false;
    for (size_t i = 0; i < 48; i++)
        if (!slots[i].token) {
            uint64_t raw = 0;
            if (!hw->claim(hw->context, pin, (flags & RISC_GPIO_OUTPUT) != 0, false,
                           (flags & RISC_GPIO_PULLUP) != 0, &raw) ||
                !raw)
                return false;
            slots[i].token = ++serial;
            slots[i].raw = raw;
            slots[i].flags = flags;
            *out = serial;
            return true;
        }
    return false;
}
static bool write_pin(void *c, uint64_t t, bool value) {
    (void)c;
    if (!started || !t)
        return false;
    for (size_t i = 0; i < 48; i++)
        if (slots[i].token == t && slots[i].flags & RISC_GPIO_OUTPUT)
            return hw->write(hw->context, slots[i].raw, value);
    return false;
}
static bool read_pin(void *c, uint64_t t, bool *value) {
    (void)c;
    if (!started || !t || !value)
        return false;
    for (size_t i = 0; i < 48; i++)
        if (slots[i].token == t)
            return hw->read(hw->context, slots[i].raw, value);
    return false;
}
static bool release_pin(void *c, uint64_t t) {
    (void)c;
    if (!started || !t)
        return false;
    for (size_t i = 0; i < 48; i++)
        if (slots[i].token == t) {
            if (!hw->release(hw->context, slots[i].raw))
                return false;
            slots[i].token = slots[i].raw = 0;
            return true;
        }
    return false;
}
static bool quiesce(void) {
    for (size_t i = 0; i < 48; i++)
        if (slots[i].token)
            return false;
    started = false;
    hw = NULL;
    return true;
}
static bool start(const risc_provider_dependency_v1 *d, size_t n) {
    if (started)
        return false;
    const tw_hw_gpio_controller_v1 *config =
        tw_config(d, n, "espressif,esp32s3-gpio", "controller.gpio", sizeof(*config));
    if (!config || config->unit || config->features)
        return false;
    hw = tw_dep(d, n, "platform.gpio", sizeof(*hw));
    if (!hw || !hw->claim || !hw->write || !hw->read || !hw->release)
        return false;
    started = true;
    return true;
}
static const risc_gpio_bank_api_v1 api = {1,         sizeof(api), NULL,       claim_pin,
                                          write_pin, read_pin,    release_pin};
TW_DRIVER("twatch-gpio", "gpio.bank", 1, api)

/* Device-independent NEC encoding over a bounded hardware carrier envelope. */
#include "twatch_support.h"
#include "twatch_caps.h"
static const twatch_carrier_v1 *hw;
static uint64_t led;
static bool started;
static bool send_raw(void *c, const uint16_t *us, size_t n, uint16_t hz) {
    (void)c;
    if (!started || !us || !n || n > 128 || !(n & 1) || hz < 20000 || hz > 56000)
        return false;
    uint32_t total = 0;
    for (size_t i = 0; i < n; i++) {
        if (!us[i])
            return false;
        total += us[i];
    }
    if (total > 150000)
        return false;
    return hw->send(hw->context, led, hz, us, n);
}
static bool send_nec32(void *c, uint32_t bits) {
    uint16_t us[67] = {9000, 4500};
    for (size_t i = 0; i < 32; i++) {
        us[2 + 2 * i] = 560;
        us[3 + 2 * i] = (bits & (1u << i)) ? 1690 : 560;
    }
    us[66] = 560;
    return send_raw(c, us, 67, 38000);
}
static bool send_nec(void *c, uint8_t a, uint8_t v) {
    return send_nec32(c, (uint32_t)a | ((uint32_t)(uint8_t)~a << 8) | ((uint32_t)v << 16) |
                             ((uint32_t)(uint8_t)~v << 24));
}
static bool idle(void *c) {
    (void)c;
    return started && hw->idle(hw->context, led);
}
static bool quiesce(void) {
    if (led) {
        if (!hw->idle(hw->context, led) || !hw->release(hw->context, led))
            return false;
        led = 0;
    }
    started = false;
    hw = NULL;
    return true;
}
static bool start(const risc_provider_dependency_v1 *d, size_t n) {
    if (started || led)
        return false;
    uint8_t pin;
    hw = tw_dep(d, n, "platform.carrier", sizeof(*hw));
    if (!hw || !hw->claim || !hw->send || !hw->idle || !hw->release ||
        !tw_output_config(d, n, "everlight,ir12-21c", &pin))
        return false;
    if (!hw->claim(hw->context, pin, &led) || !led)
        return false;
    started = true;
    return true;
}
static const twatch_ir_api_v1 api = {1, sizeof(api), NULL, send_nec, send_nec32, send_raw, idle};
TW_DRIVER("twatch-ir", "ir.transmit", 1, api)

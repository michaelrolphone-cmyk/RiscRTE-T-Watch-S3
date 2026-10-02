/* IR12-21C transmitter on GPIO2 through the board transistor. LilyGO IRsend
 * uses this pin active-high. The pin map has no IR receiver, so this ELF
 * does not decode. Carrier timing is a busy loop, not RMT, and has not been
 * received by a target in this tree. */
#include "RiscGpioBankV1.h"
#include "twatch_caps.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
static const risc_gpio_bank_api_v1 *gpio_api;
static uint64_t led;
static bool started;
static char error[72];
static void set_error(const char *msg) { twatch_copy_error(error, sizeof error, msg); }
static bool pin(bool level) { return gpio_api->write(gpio_api->context, led, level); }
/* Uncalibrated 240 MHz estimate. Not a measured microsecond. */
static void delay_us(uint32_t us) {
    for (volatile uint32_t i = 0; i < us * 40u; ++i) { }
}
static void mark(uint32_t us, uint16_t carrier_hz) {
    if (carrier_hz < 20000u || carrier_hz > 56000u) carrier_hz = 38000u;
    uint32_t period = 1000000u / carrier_hz;
    uint32_t high = period / 3u;
    uint32_t low = period - high;
    uint32_t cycles = us / period;
    if (!cycles) cycles = 1;
    for (uint32_t i = 0; i < cycles; ++i) {
        (void)pin(true);
        delay_us(high);
        (void)pin(false);
        delay_us(low);
    }
}
static void space(uint32_t us) {
    (void)pin(false);
    if (us) delay_us(us);
}
static bool frame(uint32_t data, uint8_t bits, uint16_t carrier_hz) {
    mark(9000u, carrier_hz);
    space(4500u);
    for (uint8_t i = 0; i < bits; ++i) {
        mark(560u, carrier_hz);
        space((data & 1u) ? 1690u : 560u);
        data >>= 1;
    }
    mark(560u, carrier_hz);
    return pin(false);
}
static bool send_nec(void *context, uint8_t address, uint8_t command) {
    (void)context;
    if (!started) return false;
    uint32_t data = (uint32_t)address | ((uint32_t)(uint8_t)~address << 8) |
                    ((uint32_t)command << 16) | ((uint32_t)(uint8_t)~command << 24);
    return frame(data, 32u, 38000u);
}
static bool send_nec32(void *context, uint32_t data) {
    (void)context;
    if (!started) return false;
    return frame(data, 32u, 38000u);
}
static bool send_raw(void *context, const uint16_t *us, size_t count, uint16_t carrier_hz) {
    (void)context;
    if (!started || !us || !count || count > TWATCH_IR_MAX_RAW || (count & 1u) == 0u) {
        set_error("raw IR needs an odd mark/space/mark count up to 128");
        return false;
    }
    if (carrier_hz < 20000u || carrier_hz > 56000u) {
        set_error("carrier must be 20000 to 56000 Hz");
        return false;
    }
    for (size_t i = 0; i < count; ++i) {
        if ((i & 1u) == 0u) mark(us[i], carrier_hz);
        else space(us[i]);
    }
    return pin(false);
}
static bool idle(void *context) {
    (void)context;
    return started && pin(false);
}
static bool last_error(char *dst, size_t cap) {
    if (!error[0]) return false;
    twatch_copy_error(dst, cap, error);
    return true;
}
static bool quiesce(void) {
    bool ok = true;
    if (led && gpio_api) {
        (void)pin(false);
        if (!gpio_api->release(gpio_api->context, led)) ok = false;
    }
    led = 0;
    gpio_api = NULL;
    started = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 1u) return false;
    if (!twatch_equal(deps[0].capability_id, RISC_GPIO_BANK_CAPABILITY)) return false;
    gpio_api = deps[0].api;
    if (!gpio_api || !gpio_api->claim(gpio_api->context, TWATCH_PIN_IR, RISC_GPIO_OUTPUT, &led) ||
        !pin(false)) {
        set_error("IR12-21C pin claim failed");
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const twatch_ir_api_v1 api = {
    TWATCH_IR_API_V1, sizeof(api), NULL, send_nec, send_nec32, send_raw, idle
};
static const risc_driver_diagnostics_v2 driver = {
    { RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-ir",
      TWATCH_IR_CAPABILITY, TWATCH_IR_API_V1, &api, start, stop, quiesce },
    last_error
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver.base : NULL;
}

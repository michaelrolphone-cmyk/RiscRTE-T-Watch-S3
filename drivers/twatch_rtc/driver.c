/* PCF8563 on the system bus. Time is BCD. This ELF does not enable the clock-out
 * pin or the alarm, and it does not touch VL beyond reporting a failed read. */
#include "RiscI2cBusV1.h"
#include "twatch_caps.h"
#include "twatch_support.h"
#include "twatch_calendar.h"
#include <stddef.h>
static const risc_i2c_bus_api_v1 *bus;
static uint64_t claim, irq_claim;
static const risc_gpio_bank_api_v1 *gpio_api;
static bool started;
static const tw_hw_i2c_device_v1 *config;
static uint8_t bcd(uint8_t v) {
    return (uint8_t)(((v / 10u) << 4) | (v % 10u));
}
static uint8_t dec(uint8_t v) {
    return (uint8_t)((v >> 4) * 10u + (v & 0x0fu));
}
static bool write_regs(uint8_t reg, const uint8_t *bytes, size_t n) {
    uint8_t buf[8];
    if (n > 7u)
        return false;
    buf[0] = reg;
    for (size_t i = 0; i < n; ++i)
        buf[i + 1u] = bytes[i];
    return bus->transact(bus->context, claim, buf, n + 1u, NULL, 0, 30);
}
static bool read_regs(uint8_t reg, uint8_t *out, size_t n) {
    return bus->transact(bus->context, claim, &reg, 1, out, n, 30);
}
static bool read_time(void *context, twatch_rtc_time_v1 *out) {
    (void)context;
    if (!started || !out)
        return false;
    uint8_t raw[7] = {0};
    if (!read_regs(0x02u, raw, 7))
        return false;
    if ((raw[0] & 0x80u) || (raw[5] & 0x80u))
        return false;
    for (size_t i = 0; i < 7; i++)
        if (i != 4 && !tw_valid_bcd(raw[i] & (i == 0 || i == 1   ? 0x7f
                                              : i == 2 || i == 3 ? 0x3f
                                              : i == 5           ? 0x1f
                                                                 : 0xff)))
            return false; /* VL: clock integrity lost */
    out->second = dec(raw[0] & 0x7fu);
    out->minute = dec(raw[1] & 0x7fu);
    out->hour = dec(raw[2] & 0x3fu);
    out->day = dec(raw[3] & 0x3fu);
    out->weekday = raw[4] & 0x07u;
    out->month = dec(raw[5] & 0x1fu);
    out->year = (uint16_t)(2000u + dec(raw[6]));
    return tw_valid_time(out);
}
static bool write_time(void *context, const twatch_rtc_time_v1 *in) {
    (void)context;
    if (!started || !tw_valid_time(in))
        return false;
    uint8_t raw[7] = {bcd(in->second),
                      bcd(in->minute),
                      bcd(in->hour),
                      bcd(in->day),
                      in->weekday & 0x07u,
                      bcd(in->month),
                      bcd((uint8_t)(in->year - 2000u))};
    return write_regs(0x02u, raw, 7);
}
/* 255 disables that alarm compare field. PCF8563 minute-resolution alarm. */
static bool alarm(void *c, uint8_t minute, uint8_t hour, uint8_t day, uint8_t weekday,
                  bool enable) {
    (void)c;
    if (!started || (minute != 255 && minute > 59) || (hour != 255 && hour > 23) ||
        (day != 255 && (!day || day > 31)) || (weekday != 255 && weekday > 6))
        return false;
    uint8_t fields[] = {minute == 255 ? 0x80 : bcd(minute), hour == 255 ? 0x80 : bcd(hour),
                        day == 255 ? 0x80 : bcd(day), weekday == 255 ? 0x80 : weekday},
            status;
    if (!read_regs(1, &status, 1))
        return false;
    uint8_t off = status & ~0x0a;
    if (!write_regs(1, &off, 1) || !write_regs(9, fields, 4))
        return false;
    off |= enable ? 2 : 0;
    return write_regs(1, &off, 1);
}
static bool alarm_pending(void *c, bool *pending, bool ack) {
    (void)c;
    if (!started || !pending)
        return false;
    uint8_t v;
    if (!read_regs(1, &v, 1))
        return false;
    *pending = (v & 8) != 0;
    if (ack) {
        v &= ~8;
        return write_regs(1, &v, 1);
    }
    return true;
}
static bool quiesce(void) {
    if (started && claim) {
        uint8_t v;
        if (!read_regs(1, &v, 1))
            return false;
        v &= ~2;
        if (!write_regs(1, &v, 1))
            return false;
    }
    bool ok = !claim || (bus && bus->release_device(bus->context, claim));
    if (!ok)
        return false;
    claim = 0;
    if (irq_claim) {
        if (!gpio_api->release(gpio_api->context, irq_claim))
            return false;
        irq_claim = 0;
    }
    claim = 0;
    bus = NULL;
    started = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || claim || irq_claim)
        return false;
    config = tw_config(deps, count, "nxp,pcf8563", "peripheral.i2c", sizeof(*config));
    if (!tw_i2c_config_valid(config))
        return false;
    gpio_api = tw_dep(deps, count, "gpio.bank", sizeof(*gpio_api));
    if (config->irq != -1 && !tw_gpio_valid(gpio_api))
        return false;
    bus = tw_dep(deps, count, "i2c.bus", sizeof(*bus));
    if (!tw_i2c_valid(bus))
        return false;
    if (config->irq != -1 &&
        !gpio_api->claim(gpio_api->context, config->irq,
                         RISC_GPIO_INPUT | (config->irq_pull_up ? RISC_GPIO_PULLUP : 0),
                         &irq_claim))
        return false;
    if (!bus || !bus->claim_device(bus->context, config->address, &claim))
        return false;
    uint8_t control = 0, clkout = 0;
    if (!read_regs(0, &control, 1)) {
        (void)quiesce();
        return false;
    }
    control &= ~0x20;
    if (!write_regs(0, &control, 1) || !write_regs(0x0d, &clkout, 1)) {
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) {
    (void)quiesce();
}
static const twatch_rtc_api_v1 api = {TWATCH_RTC_API_V1, sizeof(api), NULL,         read_time,
                                      write_time,        alarm,       alarm_pending};
static const risc_driver_v2 driver = {RISC_PROVIDER_DRIVER_ABI_V2,
                                      sizeof(driver),
                                      "twatch-rtc",
                                      TWATCH_RTC_CAPABILITY,
                                      TWATCH_RTC_API_V1,
                                      &api,
                                      start,
                                      stop,
                                      quiesce};
__attribute__((visibility("default"))) const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

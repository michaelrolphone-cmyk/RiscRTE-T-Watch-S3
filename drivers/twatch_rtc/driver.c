/* PCF8563 on the system bus. Time is BCD. This ELF does not enable the clock-out
 * pin or the alarm, and it does not touch VL beyond reporting a failed read. */
#include "RiscI2cBusV1.h"
#include "twatch_caps.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
static const risc_i2c_bus_api_v1 *bus;
static uint64_t claim;
static bool started;
static uint8_t bcd(uint8_t v) { return (uint8_t)(((v / 10u) << 4) | (v % 10u)); }
static uint8_t dec(uint8_t v) { return (uint8_t)((v >> 4) * 10u + (v & 0x0fu)); }
static bool write_regs(uint8_t reg, const uint8_t *bytes, size_t n) {
    uint8_t buf[8];
    if (n > 7u) return false;
    buf[0] = reg;
    for (size_t i = 0; i < n; ++i) buf[i + 1u] = bytes[i];
    return bus->transact(bus->context, claim, buf, n + 1u, NULL, 0, 30);
}
static bool read_regs(uint8_t reg, uint8_t *out, size_t n) {
    return bus->transact(bus->context, claim, &reg, 1, out, n, 30);
}
static bool read_time(void *context, twatch_rtc_time_v1 *out) {
    (void)context;
    if (!started || !out) return false;
    uint8_t raw[7] = {0};
    if (!read_regs(0x02u, raw, 7)) return false;
    if (raw[0] & 0x80u) return false; /* VL: clock integrity lost */
    out->second = dec(raw[0] & 0x7fu);
    out->minute = dec(raw[1] & 0x7fu);
    out->hour = dec(raw[2] & 0x3fu);
    out->day = dec(raw[3] & 0x3fu);
    out->weekday = raw[4] & 0x07u;
    out->month = dec(raw[5] & 0x1fu);
    out->year = (uint16_t)(2000u + dec(raw[6]));
    return out->second < 60u && out->minute < 60u && out->hour < 24u &&
           out->day >= 1u && out->day <= 31u && out->month >= 1u && out->month <= 12u;
}
static bool write_time(void *context, const twatch_rtc_time_v1 *in) {
    (void)context;
    if (!started || !in || in->year < 2000u || in->year > 2099u) return false;
    uint8_t raw[7] = {
        bcd(in->second), bcd(in->minute), bcd(in->hour), bcd(in->day),
        in->weekday & 0x07u, bcd(in->month), bcd((uint8_t)(in->year - 2000u))
    };
    return write_regs(0x02u, raw, 7);
}
static bool quiesce(void) {
    bool ok = !claim || !bus || bus->release_device(bus->context, claim);
    claim = 0; bus = NULL; started = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 1u) return false;
    if (!twatch_equal(deps[0].capability_id, RISC_I2C_BUS_CAPABILITY)) return false;
    bus = deps[0].api;
    if (!bus || !bus->claim_device(bus->context, TWATCH_I2C_PCF8563, &claim)) return false;
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const twatch_rtc_api_v1 api = {
    TWATCH_RTC_API_V1, sizeof(api), NULL, read_time, write_time
};
static const risc_driver_v2 driver = {
    RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-rtc",
    TWATCH_RTC_CAPABILITY, TWATCH_RTC_API_V1, &api, start, stop, quiesce
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

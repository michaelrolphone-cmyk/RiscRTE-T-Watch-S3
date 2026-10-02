/* AXP2101 bring-up and battery sample for the 470 mAh T-Watch-S3 cell.
 * Charge current is hardcoded to the XPowersLib 100 mA code. There is no
 * setter. LilyGO: keep charge current below 130 mA. Amazon listing notes:
 * do not set the library default above 125 mA. percent is 255 because this
 * PMIC has no profiled fuel gauge in this ELF. */
#include "RiscBatteryGaugeV1.h"
#include "RiscGpioBankV1.h"
#include "RiscI2cBusV1.h"
#include "RiscPlatformClockV1.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
#define AXP_STATUS2 0x01u
#define AXP_DC_ON 0x80u
#define AXP_LDO_ON 0x90u
#define AXP_ALDO2_V 0x93u
#define AXP_ALDO3_V 0x94u
#define AXP_ALDO4_V 0x95u
#define AXP_BLDO2_V 0x97u
#define AXP_ADC_EN 0x30u
#define AXP_VBAT_H 0x34u
#define AXP_ICC 0x62u
#define AXP_V_3V3 28u
#define AXP_LDO_MASK ((1u << 1) | (1u << 2) | (1u << 3) | (1u << 5))
static const risc_i2c_bus_api_v1 *bus;
static const risc_platform_clock_api_v1 *clock_api;
static const risc_gpio_bank_api_v1 *gpio_api;
static uint64_t claim, irq_claim;
static bool started;
static char error[80];
static void set_error(const char *msg) { twatch_copy_error(error, sizeof error, msg); }
static bool write_reg(uint8_t reg, uint8_t value) {
    uint8_t buf[2] = {reg, value};
    return bus->transact(bus->context, claim, buf, 2, NULL, 0, 40);
}
static bool read_reg(uint8_t reg, uint8_t *out, size_t n) {
    return bus->transact(bus->context, claim, &reg, 1, out, n, 40);
}
static bool rails(void) {
    /* 3.3 V on ALDO2 backlight, ALDO3 display+touch, ALDO4 LoRa, BLDO2 haptic.
     * ALDO1 stays off: LilyGO marks it unused. DC1 (ESP32) is left as found. */
    if (!write_reg(AXP_ALDO2_V, AXP_V_3V3) || !write_reg(AXP_ALDO3_V, AXP_V_3V3) ||
        !write_reg(AXP_ALDO4_V, AXP_V_3V3) || !write_reg(AXP_BLDO2_V, AXP_V_3V3))
        return false;
    uint8_t ldo = 0;
    if (!read_reg(AXP_LDO_ON, &ldo, 1)) return false;
    ldo = (uint8_t)((ldo & (uint8_t)~AXP_LDO_MASK) | AXP_LDO_MASK);
    if (!write_reg(AXP_LDO_ON, ldo)) return false;
    if (!write_reg(AXP_ICC, TWATCH_AXP_CHG_100MA)) return false;
    uint8_t icc = 0xff;
    if (!read_reg(AXP_ICC, &icc, 1) || (icc & 0x1fu) != TWATCH_AXP_CHG_100MA) {
        set_error("charge current readback is not 100 mA code");
        return false;
    }
    return write_reg(AXP_ADC_EN, 0x01u);
}
static bool read_sample(void *context, risc_battery_sample_v1 *out) {
    (void)context;
    if (!started || !out) return false;
    *out = (risc_battery_sample_v1){0, 255, RISC_BATTERY_PROFILE_MISSING};
    uint8_t raw[2] = {0}, status = 0;
    if (!read_reg(AXP_VBAT_H, raw, 2) || !read_reg(AXP_STATUS2, &status, 1)) {
        set_error("AXP2101 battery read failed");
        return false;
    }
    uint16_t mv = (uint16_t)((((uint16_t)raw[0] & 0x3fu) << 8) | raw[1]);
    out->millivolts = mv;
    uint8_t chg = status & 0x07u;
    if (chg == 1u || chg == 2u || chg == 3u) out->flags |= RISC_BATTERY_CHARGING;
    return true;
}
static bool last_error(char *dst, size_t cap) {
    if (!error[0]) return false;
    twatch_copy_error(dst, cap, error);
    return true;
}
static bool quiesce(void) {
    bool ok = true;
    if (claim && bus && !bus->release_device(bus->context, claim)) ok = false;
    if (irq_claim && gpio_api && !gpio_api->release(gpio_api->context, irq_claim)) ok = false;
    claim = irq_claim = 0;
    bus = NULL;
    clock_api = NULL;
    gpio_api = NULL;
    started = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 3u) return false;
    for (size_t i = 0; i < count; ++i) {
        if (twatch_equal(deps[i].capability_id, RISC_I2C_BUS_CAPABILITY)) bus = deps[i].api;
        else if (twatch_equal(deps[i].capability_id, RISC_PLATFORM_CLOCK_CAPABILITY)) clock_api = deps[i].api;
        else if (twatch_equal(deps[i].capability_id, RISC_GPIO_BANK_CAPABILITY)) gpio_api = deps[i].api;
    }
    if (!bus || !clock_api || !gpio_api) return false;
    if (!bus->claim_device(bus->context, TWATCH_I2C_AXP2101, &claim) ||
        !gpio_api->claim(gpio_api->context, TWATCH_PIN_PMU_INT, RISC_GPIO_INPUT, &irq_claim)) {
        set_error("AXP2101 claim failed");
        (void)quiesce();
        return false;
    }
    if (!rails()) {
        if (!error[0]) set_error("AXP2101 rail or charge setup failed");
        (void)quiesce();
        return false;
    }
    if (clock_api->sleep_ms) clock_api->sleep_ms(clock_api->context, 5);
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const risc_battery_gauge_api_v1 api = {
    RISC_BATTERY_GAUGE_API_V1, sizeof(api), NULL, read_sample
};
static const risc_driver_diagnostics_v2 driver = {
    { RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-pmu",
      RISC_BATTERY_GAUGE_CAPABILITY, RISC_BATTERY_GAUGE_API_V1,
      &api, start, stop, quiesce },
    last_error
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver.base : NULL;
}

/* BMA423/BMA456 accelerometer on the system bus. Enables the accelerometer
 * and reads the data registers. Feature/FIFO firmware is not loaded. */
#include "RiscI2cBusV1.h"
#include "RiscPlatformClockV1.h"
#include "twatch_caps.h"
#include "twatch_support.h"
#include <stddef.h>
static const risc_i2c_bus_api_v1 *bus;
static const risc_platform_clock_api_v1 *clock_api;
static uint64_t claim, irq_claim;
static const risc_gpio_bank_api_v1 *gpio_api;
static bool started;
static const tw_hw_i2c_device_v1 *config;
static uint8_t chip;
static bool write_reg(uint8_t reg, uint8_t value) {
    uint8_t buf[2] = {reg, value};
    return bus->transact(bus->context, claim, buf, 2, NULL, 0, 30);
}
static bool read_reg(uint8_t reg, uint8_t *out, size_t n) {
    return bus->transact(bus->context, claim, &reg, 1, out, n, 30);
}
static bool chip_id(void *context, uint8_t *out) {
    (void)context;
    if (!started || !out || !chip)
        return false;
    *out = chip;
    return true;
}
static bool read_sample(void *context, twatch_accel_sample_v1 *out) {
    (void)context;
    if (!started || !out)
        return false;
    uint8_t raw[6] = {0};
    if (!read_reg(0x12u, raw, 6))
        return false;
    out->x = (int16_t)((raw[1] << 8) | raw[0]);
    out->y = (int16_t)((raw[3] << 8) | raw[2]);
    out->z = (int16_t)((raw[5] << 8) | raw[4]);
    return true;
}
static bool quiesce(void) {
    bool ok = true;
    if (started && claim && !write_reg(0x7d, 0))
        return false;
    if (claim && bus) {
        if (!bus->release_device(bus->context, claim))
            return false;
        claim = 0;
    }
    if (irq_claim) {
        if (!gpio_api->release(gpio_api->context, irq_claim))
            return false;
        irq_claim = 0;
    }
    claim = 0;
    bus = NULL;
    clock_api = NULL;
    started = false;
    chip = 0;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || claim || irq_claim)
        return false;
    config = tw_config(deps, count, "bosch,bma4xx", "peripheral.i2c", sizeof(*config));
    if (!tw_i2c_config_valid(config) || (config->chip_id != 0x13 && config->chip_id != 0x16))
        return false;
    gpio_api = tw_dep(deps, count, "gpio.bank", sizeof(*gpio_api));
    if (config->irq != -1 && !tw_gpio_valid(gpio_api))
        return false;
    bus = tw_dep(deps, count, "i2c.bus", sizeof(*bus));
    clock_api = tw_dep(deps, count, "platform.clock", sizeof(*clock_api));
    if (!tw_clock_valid(clock_api))
        return false;
    if (!tw_i2c_valid(bus))
        return false;
    if (config->irq != -1 &&
        !gpio_api->claim(gpio_api->context, config->irq,
                         RISC_GPIO_INPUT | (config->irq_pull_up ? RISC_GPIO_PULLUP : 0),
                         &irq_claim))
        return false;
    if (!bus || !clock_api || !bus->claim_device(bus->context, config->address, &claim)) {
        (void)quiesce();
        return false;
    }
    if (!read_reg(0x00u, &chip, 1) ||
        (chip != config->chip_id || (chip != 0x13u && chip != 0x16u))) {
        (void)quiesce();
        return false;
    }
    if (!write_reg(0x7Eu, 0xB6u)) {
        (void)quiesce();
        return false;
    }
    if (clock_api->sleep_ms)
        clock_api->sleep_ms(clock_api->context, 10);
    if (!write_reg(0x7Cu, 0x00u) || !write_reg(0x40u, 0xA8u) || !write_reg(0x41u, 0x01u) ||
        !write_reg(0x7Du, 0x04u)) {
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) {
    (void)quiesce();
}
static const twatch_motion_api_v1 api = {TWATCH_MOTION_API_V1, sizeof(api), NULL, read_sample,
                                         chip_id};
static const risc_driver_v2 driver = {RISC_PROVIDER_DRIVER_ABI_V2,
                                      sizeof(driver),
                                      "twatch-imu",
                                      TWATCH_MOTION_CAPABILITY,
                                      TWATCH_MOTION_API_V1,
                                      &api,
                                      start,
                                      stop,
                                      quiesce};
__attribute__((visibility("default"))) const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

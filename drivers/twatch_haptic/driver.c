/* DRV2605 ERM click. BLDO2 must already be on; twatch-pmu does that.
 * effect() writes the ROM library effect and the GO bit. It does not invent
 * a waveform. */
#include "RiscI2cBusV1.h"
#include "twatch_caps.h"
#include "twatch_support.h"
#include <stddef.h>
static const risc_i2c_bus_api_v1 *bus;
static uint64_t claim, irq_claim;
static const risc_gpio_bank_api_v1 *gpio_api;
static bool started;
static const tw_hw_i2c_device_v1 *config;
static bool write_reg(uint8_t reg, uint8_t value) {
    uint8_t buf[2] = {reg, value};
    return bus->transact(bus->context, claim, buf, 2, NULL, 0, 30);
}
static bool effect(void *context, uint8_t effect_id) {
    (void)context;
    if (!started || !effect_id || effect_id > 123)
        return false;
    return write_reg(0x01u, 0x00u) && write_reg(0x03u, 0x01u) && write_reg(0x04u, effect_id) &&
           write_reg(0x05u, 0) && write_reg(0x0Cu, 0x01u);
}
static bool stop_effect(void *context) {
    (void)context;
    return started && write_reg(0x0Cu, 0x00u);
}
static bool quiesce(void) {
    if (started && claim && !write_reg(0x0Cu, 0))
        return false;
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
    config = tw_config(deps, count, "ti,drv2605", "peripheral.i2c", sizeof(*config));
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
    uint8_t reg = 0, status = 0;
    if (!bus->transact(bus->context, claim, &reg, 1, &status, 1, 30) ||
        ((status >> 5) != 3 && (status >> 5) != 7)) {
        (void)quiesce();
        return false;
    }
    if (!write_reg(0x01u, 0x00u) || !write_reg(0x03u, 1) ||
        !write_reg(0x05u, 0)) { /* Library 1, internal trigger, terminated sequence; preserve
                                   factory motor calibration. */
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) {
    (void)quiesce();
}
static const twatch_haptic_api_v1 api = {TWATCH_HAPTIC_API_V1, sizeof(api), NULL, effect,
                                         stop_effect};
static const risc_driver_v2 driver = {RISC_PROVIDER_DRIVER_ABI_V2,
                                      sizeof(driver),
                                      "twatch-haptic",
                                      TWATCH_HAPTIC_CAPABILITY,
                                      TWATCH_HAPTIC_API_V1,
                                      &api,
                                      start,
                                      stop,
                                      quiesce};
__attribute__((visibility("default"))) const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

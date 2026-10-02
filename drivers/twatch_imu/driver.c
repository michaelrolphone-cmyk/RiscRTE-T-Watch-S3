/* BMA423/BMA456 accelerometer on the system bus. Enables the accelerometer
 * and reads the data registers. Feature/FIFO firmware is not loaded. */
#include "RiscI2cBusV1.h"
#include "RiscPlatformClockV1.h"
#include "twatch_caps.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
static const risc_i2c_bus_api_v1 *bus;
static const risc_platform_clock_api_v1 *clock_api;
static uint64_t claim;
static bool started;
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
    if (!started || !out || !chip) return false;
    *out = chip;
    return true;
}
static bool read_sample(void *context, twatch_accel_sample_v1 *out) {
    (void)context;
    if (!started || !out) return false;
    uint8_t raw[6] = {0};
    if (!read_reg(0x12u, raw, 6)) return false;
    out->x = (int16_t)((raw[1] << 8) | raw[0]);
    out->y = (int16_t)((raw[3] << 8) | raw[2]);
    out->z = (int16_t)((raw[5] << 8) | raw[4]);
    return true;
}
static bool quiesce(void) {
    bool ok = true;
    if (claim && bus && !bus->release_device(bus->context, claim)) ok = false;
    claim = 0; bus = NULL; clock_api = NULL; started = false; chip = 0;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 2u) return false;
    for (size_t i = 0; i < count; ++i) {
        if (twatch_equal(deps[i].capability_id, RISC_I2C_BUS_CAPABILITY)) bus = deps[i].api;
        else if (twatch_equal(deps[i].capability_id, RISC_PLATFORM_CLOCK_CAPABILITY)) clock_api = deps[i].api;
    }
    if (!bus || !clock_api || !bus->claim_device(bus->context, TWATCH_I2C_BMA423, &claim)) {
        (void)quiesce();
        return false;
    }
    if (!read_reg(0x00u, &chip, 1) || (chip != 0x13u && chip != 0x16u)) {
        (void)quiesce();
        return false;
    }
    (void)write_reg(0x7Eu, 0xB6u);
    if (clock_api->sleep_ms) clock_api->sleep_ms(clock_api->context, 10);
    if (!write_reg(0x7Cu, 0x00u) || !write_reg(0x40u, 0xA8u) || !write_reg(0x41u, 0x01u) ||
        !write_reg(0x7Du, 0x04u)) {
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const twatch_motion_api_v1 api = {
    TWATCH_MOTION_API_V1, sizeof(api), NULL, read_sample, chip_id
};
static const risc_driver_v2 driver = {
    RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-imu",
    TWATCH_MOTION_CAPABILITY, TWATCH_MOTION_API_V1, &api, start, stop, quiesce
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

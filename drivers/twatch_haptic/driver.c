/* DRV2605 ERM click. BLDO2 must already be on; twatch-pmu does that.
 * effect() writes the ROM library effect and the GO bit. It does not invent
 * a waveform. */
#include "RiscI2cBusV1.h"
#include "twatch_caps.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
static const risc_i2c_bus_api_v1 *bus;
static uint64_t claim;
static bool started;
static bool write_reg(uint8_t reg, uint8_t value) {
    uint8_t buf[2] = {reg, value};
    return bus->transact(bus->context, claim, buf, 2, NULL, 0, 30);
}
static bool effect(void *context, uint8_t effect_id) {
    (void)context;
    if (!started || !effect_id) return false;
    return write_reg(0x01u, 0x00u) && write_reg(0x03u, 0x01u) &&
           write_reg(0x04u, effect_id) && write_reg(0x0Cu, 0x01u);
}
static bool stop_effect(void *context) {
    (void)context;
    return started && write_reg(0x0Cu, 0x00u);
}
static bool quiesce(void) {
    if (started) (void)write_reg(0x0Cu, 0x00u);
    bool ok = !claim || !bus || bus->release_device(bus->context, claim);
    claim = 0; bus = NULL; started = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 1u) return false;
    if (!twatch_equal(deps[0].capability_id, RISC_I2C_BUS_CAPABILITY)) return false;
    bus = deps[0].api;
    if (!bus || !bus->claim_device(bus->context, TWATCH_I2C_DRV2605, &claim)) return false;
    if (!write_reg(0x01u, 0x00u) || !write_reg(0x1Au, 0xB6u)) { /* ERM library, rated voltage default-ish */
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const twatch_haptic_api_v1 api = {
    TWATCH_HAPTIC_API_V1, sizeof(api), NULL, effect, stop_effect
};
static const risc_driver_v2 driver = {
    RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-haptic",
    TWATCH_HAPTIC_CAPABILITY, TWATCH_HAPTIC_API_V1, &api, start, stop, quiesce
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

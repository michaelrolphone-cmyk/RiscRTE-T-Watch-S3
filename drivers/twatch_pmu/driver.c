/* AXP2101 bring-up and battery sample for the 470 mAh T-Watch-S3 cell.
 * Charge current is hardcoded to the XPowersLib 100 mA code. There is no
 * setter. LilyGO: keep charge current below 130 mA. Amazon listing notes:
 * do not set the library default above 125 mA. percent is 255 because this
 * PMIC has no profiled fuel gauge in this ELF. */
#include "RiscBatteryGaugeV1.h"
#include "twatch_caps.h"
#include "RiscGpioBankV1.h"
#include "RiscI2cBusV1.h"
#include "RiscPlatformClockV1.h"
#include "twatch_support.h"
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
static const tw_hw_i2c_device_v1 *config;
static char error[80];
static void set_error(const char *msg) {
    twatch_copy_error(error, sizeof error, msg);
}
static bool write_reg(uint8_t reg, uint8_t value) {
    uint8_t buf[2] = {reg, value};
    return bus->transact(bus->context, claim, buf, 2, NULL, 0, 40);
}
static bool read_reg(uint8_t reg, uint8_t *out, size_t n) {
    return bus->transact(bus->context, claim, &reg, 1, out, n, 40);
}
static const tw_hw_axp2101_v1 *power;
static uint8_t saved_enable, saved_voltage[4], saved_irq;
static bool changed;
static uint8_t sleep_irq[3];
static bool sleep_changed, sleep_prepared, key_released;
static bool rails(void) {
    if (!read_reg(0x03, &saved_enable, 1) || saved_enable != 0x4a)
        return false;
    if (!read_reg(AXP_LDO_ON, &saved_enable, 1))
        return false;
    for (size_t i = 0; i < power->rail_count; i++)
        if (!read_reg((uint8_t)(0x92 + power->rails[i].id), &saved_voltage[i], 1))
            return false;
    if (!read_reg(0x41, &saved_irq, 1))
        return false;
    uint8_t mask = 0;
    changed = true;
    for (size_t i = 0; i < power->rail_count; i++) {
        uint8_t id = power->rails[i].id;
        mask |= (uint8_t)(1u << id);
        if (!write_reg((uint8_t)(0x92 + id), (uint8_t)((power->rails[i].millivolts - 500) / 100)))
            return false;
    }
    if (!write_reg(AXP_LDO_ON, saved_enable | mask) || !write_reg(AXP_ICC, 4))
        return false;
    uint8_t value = 0;
    if (!read_reg(AXP_ICC, &value, 1) || (value & 0x1f) != 4)
        return false;
    if (!read_reg(AXP_ADC_EN, &value, 1) || !write_reg(AXP_ADC_EN, value | 1))
        return false;
    return write_reg(0x41, saved_irq | 0x0f);
}
static bool key_events(void *context, uint32_t *events) {
    (void)context;
    if (!started || !events)
        return false;
    uint8_t v = 0;
    if (!read_reg(0x49, &v, 1))
        return false;
    /* Rising edge/short press is released; falling alone is held. Wake and
     * startup events are drained by the app before it arms sleep requests. */
    if (v & 0x09) key_released = true;
    else if (v & 0x02) key_released = false;
    /* Return the PMIC's latched key events; ACK only the key bits. */
    if (!write_reg(0x49, v & 0x0f))
        return false;
    *events = (v >> 2) & 3;
    return true;
}
/* Snapshot all interrupt masks before mutation. Never alter charging, CPU,
 * LCD/touch, or RTC rails. An incomplete restore retains the state for retry. */
static bool resume_sleep(void *context) {
    (void)context;
    if (!started) return false;
    if (!sleep_changed) return true;
    bool ok = true;
    for (unsigned i=0;i<3;i++) {
        if (!write_reg((uint8_t)(0x40+i),sleep_irq[i])) ok=false;
    }
    if (ok) {sleep_changed=sleep_prepared=false;key_released=false;}
    return ok;
}
static bool prepare_sleep(void *context) {
    (void)context;
    if (!started || !key_released) return false;
    if (sleep_changed) return sleep_prepared;
    if (!read_reg(0x40,sleep_irq,3)) return false;
    sleep_changed=true;
    if (!write_reg(0x40,0) || !write_reg(0x41,0x08) || !write_reg(0x42,0)) return false;
    /* This sole PMU IRQ owner clears latched status as in vendor lightSleep. */
    uint32_t ignored;
    if (!key_events(NULL,&ignored) || !key_released) return false;
    for(unsigned i=0;i<3;i++)if(!write_reg((uint8_t)(0x48+i),0xff))return false;
    for(unsigned i=0;i<5;i++) {
        bool high=false;
        if (!gpio_api->read(gpio_api->context,irq_claim,&high) || !high) return false;
        clock_api->sleep_ms(clock_api->context,10);
        uint8_t status;
        if (!read_reg(0x49,&status,1) || (status&0x0f)) return false;
    }
    sleep_prepared=true;
    return true;
}
static int32_t light_sleep(void *context,risc_light_sleep_result_v1 *result) {
    (void)context;
    if (!started || !sleep_prepared || !result || result->struct_size<sizeof(*result)) return RISC_LIGHT_SLEEP_INVALID;
    if (gpio_api->struct_size<RISC_GPIO_BANK_LIGHT_SLEEP_V1_SIZE || !gpio_api->light_sleep) return RISC_LIGHT_SLEEP_UNSUPPORTED;
    return gpio_api->light_sleep(gpio_api->context,irq_claim,false,result);
}
static bool read_sample(void *context, risc_battery_sample_v1 *out) {
    (void)context;
    if (!started || !out)
        return false;
    *out = (risc_battery_sample_v1){0, 255, RISC_BATTERY_PROFILE_MISSING};
    uint8_t raw[2] = {0}, status = 0;
    if (!read_reg(AXP_VBAT_H, raw, 2) || !read_reg(AXP_STATUS2, &status, 1)) {
        set_error("AXP2101 battery read failed");
        return false;
    }
    uint16_t mv = (uint16_t)((((uint16_t)raw[0] & 0x3fu) << 8) | raw[1]);
    out->millivolts = mv;
    if ((status & 0x60u) == 0x20u)
        out->flags |= RISC_BATTERY_CHARGING;
    return true;
}
static bool last_error(char *dst, size_t cap) {
    if (!error[0])
        return false;
    twatch_copy_error(dst, cap, error);
    return true;
}
static bool quiesce(void) {
    bool ok = true;
    if (sleep_changed && !resume_sleep(NULL)) return false;
    if (changed && claim) {
        if (!write_reg(0x41, saved_irq) || !write_reg(AXP_LDO_ON, saved_enable))
            return false;
        for (size_t i = 0; i < power->rail_count; i++)
            if (!write_reg((uint8_t)(0x92 + power->rails[i].id), saved_voltage[i]))
                return false;
        changed = false;
    }
    if (claim && bus) {
        if (!bus->release_device(bus->context, claim))
            return false;
        claim = 0;
    }
    if (irq_claim && gpio_api && !gpio_api->release(gpio_api->context, irq_claim))
        return false;
    claim = irq_claim = 0;
    bus = NULL;
    clock_api = NULL;
    gpio_api = NULL;
    started = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || claim || irq_claim)
        return false;
    power = tw_config(deps, count, "x-powers,axp2101", "power.axp2101", sizeof(*power));
    if (!power || power->charge_ma != 100 || !power->rail_count || power->rail_count > 4 ||
        power->reserved)
        return false;
    for (size_t i = 0; i < power->rail_count; i++) {
        if (power->rails[i].id > 5 || power->rails[i].reserved ||
            power->rails[i].millivolts < 500 || power->rails[i].millivolts > 3500 ||
            power->rails[i].millivolts % 100)
            return false;
        for (size_t j = 0; j < i; j++)
            if (power->rails[j].id == power->rails[i].id)
                return false;
    }
    config = &power->device;
    if (!tw_i2c_config_valid(config) || config->irq < 0 || config->chip_id != 0x4a)
        return false;
    bus = tw_dep(deps, count, "i2c.bus", sizeof(*bus));
    clock_api = tw_dep(deps, count, "platform.clock", sizeof(*clock_api));
    if (!tw_clock_valid(clock_api))
        return false;
    gpio_api = tw_dep(deps, count, "gpio.bank", offsetof(risc_gpio_bank_api_v1,light_sleep));
    if (!tw_gpio_valid(gpio_api))
        return false;
    if (!tw_i2c_valid(bus))
        return false;
    if (!bus || !clock_api || !gpio_api)
        return false;
    if (!bus->claim_device(bus->context, config->address, &claim) ||
        !gpio_api->claim(gpio_api->context, config->irq,
                         RISC_GPIO_INPUT | (config->irq_pull_up ? RISC_GPIO_PULLUP : 0),
                         &irq_claim)) {
        set_error("AXP2101 claim failed");
        (void)quiesce();
        return false;
    }
    if (!rails()) {
        if (!error[0])
            set_error("AXP2101 rail or charge setup failed");
        (void)quiesce();
        return false;
    }
    if (clock_api->sleep_ms)
        clock_api->sleep_ms(clock_api->context, 5);
    key_released = false;
    started = true;
    return true;
}
static void stop(void) {
    (void)quiesce();
}
static const twatch_pmu_api_v1 api = {{RISC_BATTERY_GAUGE_API_V1, sizeof(api), NULL, read_sample},
                                      key_events, prepare_sleep, resume_sleep, light_sleep};
static const risc_driver_diagnostics_v2 driver = {
    {RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-pmu", RISC_BATTERY_GAUGE_CAPABILITY,
     RISC_BATTERY_GAUGE_API_V1, &api, start, stop, quiesce},
    last_error};
__attribute__((visibility("default"))) const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver.base : NULL;
}

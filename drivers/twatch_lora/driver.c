/* SX1262/SX1280 pad owner. Reset, BUSY wait, and SX126x GET_STATUS / read
 * register are implemented. Packet TX and RX are not in this capability:
 * a probe that fails is not reported as a radio. ALDO4 must already be on. */
#include "RiscGpioBankV1.h"
#include "RiscPlatformClockV1.h"
#include "twatch_caps.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
#define SX126X_GET_STATUS 0xC0u
#define SX126X_READ_REGISTER 0x1Du
static const risc_gpio_bank_api_v1 *gpio_api;
static const risc_platform_clock_api_v1 *clock_api;
static uint64_t cs, mosi, miso, sck, rst, busy;
static bool started;
static char error[72];
static void set_error(const char *msg) { twatch_copy_error(error, sizeof error, msg); }
static bool pin(uint64_t claim, bool level) {
    return gpio_api->write(gpio_api->context, claim, level);
}
static bool read_pin(uint64_t claim, bool *level) {
    return gpio_api->read(gpio_api->context, claim, level);
}
static uint8_t spi(uint8_t value) {
    uint8_t out = 0;
    for (int i = 7; i >= 0; --i) {
        (void)pin(sck, false);
        (void)pin(mosi, (value >> i) & 1);
        (void)pin(sck, true);
        bool bit = false;
        (void)read_pin(miso, &bit);
        out = (uint8_t)((out << 1) | (bit ? 1u : 0u));
    }
    (void)pin(sck, false);
    return out;
}
static bool wait_ready(void) {
    for (int i = 0; i < 200; ++i) {
        bool level = true;
        if (!read_pin(busy, &level)) return false;
        if (!level) return true;
        if (clock_api && clock_api->sleep_ms) clock_api->sleep_ms(clock_api->context, 1);
    }
    set_error("LoRa BUSY did not clear");
    return false;
}
static bool command(uint8_t opcode, const uint8_t *tx, size_t tx_n, uint8_t *rx, size_t rx_n) {
    if (!wait_ready()) return false;
    if (!pin(cs, false)) return false;
    (void)spi(opcode);
    for (size_t i = 0; i < tx_n; ++i) (void)spi(tx[i]);
    for (size_t i = 0; i < rx_n; ++i) rx[i] = spi(0);
    return pin(cs, true);
}
static bool probe(void *context, uint8_t *status_out) {
    (void)context;
    if (!started || !status_out) return false;
    uint8_t status = 0;
    if (!command(SX126X_GET_STATUS, NULL, 0, &status, 1)) return false;
    if ((status & 0x0eu) == 0) {
        set_error("SX126x status is empty; SX1280 boards need a different opcode");
        return false;
    }
    *status_out = status;
    return true;
}
static bool read_register(void *context, uint16_t address, uint8_t *out, size_t length) {
    (void)context;
    if (!started || !out || !length || length > 16u) return false;
    uint8_t tx[3] = {(uint8_t)(address >> 8), (uint8_t)address, 0};
    uint8_t rx[19] = {0};
    if (!command(SX126X_READ_REGISTER, tx, 3, rx, length)) return false;
    for (size_t i = 0; i < length; ++i) out[i] = rx[i];
    return true;
}
static bool last_error(char *dst, size_t cap) {
    if (!error[0]) return false;
    twatch_copy_error(dst, cap, error);
    return true;
}
static bool claim_io(uint8_t pin_no, uint32_t flags, uint64_t *out) {
    return gpio_api->claim(gpio_api->context, pin_no, flags, out);
}
static bool quiesce(void) {
    bool ok = true;
    uint64_t *all[] = {&cs, &mosi, &miso, &sck, &rst, &busy};
    for (size_t i = 0; i < 6; ++i) {
        if (*all[i] && gpio_api && !gpio_api->release(gpio_api->context, *all[i])) ok = false;
        *all[i] = 0;
    }
    gpio_api = NULL; clock_api = NULL; started = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 2u) return false;
    for (size_t i = 0; i < count; ++i) {
        if (twatch_equal(deps[i].capability_id, RISC_GPIO_BANK_CAPABILITY)) gpio_api = deps[i].api;
        else if (twatch_equal(deps[i].capability_id, RISC_PLATFORM_CLOCK_CAPABILITY)) clock_api = deps[i].api;
    }
    if (!gpio_api || !clock_api) return false;
    if (!claim_io(TWATCH_PIN_LORA_CS, RISC_GPIO_OUTPUT, &cs) ||
        !claim_io(TWATCH_PIN_LORA_MOSI, RISC_GPIO_OUTPUT, &mosi) ||
        !claim_io(TWATCH_PIN_LORA_MISO, RISC_GPIO_INPUT, &miso) ||
        !claim_io(TWATCH_PIN_LORA_SCK, RISC_GPIO_OUTPUT, &sck) ||
        !claim_io(TWATCH_PIN_LORA_RST, RISC_GPIO_OUTPUT, &rst) ||
        !claim_io(TWATCH_PIN_LORA_BUSY, RISC_GPIO_INPUT, &busy)) {
        set_error("LoRa pin claim failed");
        (void)quiesce();
        return false;
    }
    (void)pin(cs, true);
    (void)pin(rst, false);
    if (clock_api->sleep_ms) clock_api->sleep_ms(clock_api->context, 5);
    (void)pin(rst, true);
    if (clock_api->sleep_ms) clock_api->sleep_ms(clock_api->context, 5);
    if (!wait_ready()) { (void)quiesce(); return false; }
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const twatch_radio_api_v1 api = {
    TWATCH_RADIO_API_V1, sizeof(api), NULL, probe, read_register
};
static const risc_driver_diagnostics_v2 driver = {
    { RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-lora",
      TWATCH_RADIO_CAPABILITY, TWATCH_RADIO_API_V1, &api, start, stop, quiesce },
    last_error
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver.base : NULL;
}

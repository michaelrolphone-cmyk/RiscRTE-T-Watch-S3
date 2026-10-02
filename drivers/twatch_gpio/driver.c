/* ESP32-S3 GPIO bank for the LILYGO T-Watch-S3. Register map follows the
 * public ESP32-S3 TRM. Not executed on a watch in this tree. */
#include "RiscGpioBankV1.h"
#include <stddef.h>
#include <stdint.h>
#define GPIO_BASE 0x60004000u
#define IOMUX_BASE 0x60009000u
#define GPIO_OUT_W1TS 0x08u
#define GPIO_OUT_W1TC 0x0cu
#define GPIO_OUT1_W1TS 0x14u
#define GPIO_OUT1_W1TC 0x18u
#define GPIO_ENABLE_W1TS 0x24u
#define GPIO_ENABLE_W1TC 0x28u
#define GPIO_ENABLE1_W1TS 0x30u
#define GPIO_ENABLE1_W1TC 0x34u
#define GPIO_IN 0x3cu
#define GPIO_IN1 0x40u
#define GPIO_FUNC0_OUT_SEL 0x554u
#define FUN_WPD (1u << 7)
#define FUN_WPU (1u << 8)
#define FUN_IE (1u << 9)
#define MCU_SEL_SHIFT 12u
#define PIN_FUNC_GPIO 1u
#define SIG_GPIO_OUT 128u
#define MAX_CLAIMS 28u
static volatile uint32_t *reg(uint32_t offset) {
    return (volatile uint32_t *)(GPIO_BASE + offset);
}
static uint32_t mux_offset(uint8_t pin) {
    if (pin <= 21u) return 0x04u + (uint32_t)pin * 4u;
    if (pin >= 26u && pin <= 48u) return 0x04u + (uint32_t)pin * 4u;
    return 0;
}
typedef struct { uint64_t token; uint8_t pin; uint32_t flags; } claim_t;
static claim_t claims[MAX_CLAIMS];
static uint64_t next_token = 1;
static bool started;
static void write_level(uint8_t pin, bool level) {
    const uint32_t bit = 1u << (pin & 31u);
    *reg(level ? (pin < 32u ? GPIO_OUT_W1TS : GPIO_OUT1_W1TS)
               : (pin < 32u ? GPIO_OUT_W1TC : GPIO_OUT1_W1TC)) = bit;
}
static void set_output_enable(uint8_t pin, bool enable) {
    const uint32_t bit = 1u << (pin & 31u);
    *reg(enable ? (pin < 32u ? GPIO_ENABLE_W1TS : GPIO_ENABLE1_W1TS)
                : (pin < 32u ? GPIO_ENABLE_W1TC : GPIO_ENABLE1_W1TC)) = bit;
}
static bool read_level(uint8_t pin) {
    const uint32_t in = pin < 32u ? *reg(GPIO_IN) : *reg(GPIO_IN1);
    return (in & (1u << (pin & 31u))) != 0;
}
static bool configure(uint8_t pin, uint32_t flags) {
    const uint32_t mux = mux_offset(pin);
    if (!mux || ((flags & RISC_GPIO_PULLUP) && (flags & RISC_GPIO_PULLDOWN))) return false;
    uint32_t value = FUN_IE | (PIN_FUNC_GPIO << MCU_SEL_SHIFT);
    if (flags & RISC_GPIO_PULLUP) value |= FUN_WPU;
    if (flags & RISC_GPIO_PULLDOWN) value |= FUN_WPD;
    *(volatile uint32_t *)(IOMUX_BASE + mux) = value;
    *reg(GPIO_FUNC0_OUT_SEL + (uint32_t)pin * 4u) = SIG_GPIO_OUT | (1u << 10);
    if (flags & RISC_GPIO_OUTPUT) {
        write_level(pin, false);
        set_output_enable(pin, true);
    } else {
        set_output_enable(pin, false);
    }
    return true;
}
static claim_t *find(uint64_t token) {
    if (!token) return NULL;
    for (size_t i = 0; i < MAX_CLAIMS; ++i)
        if (claims[i].token == token) return &claims[i];
    return NULL;
}
static bool claim_pin(void *context, uint8_t pin, uint32_t flags, uint64_t *out) {
    (void)context;
    if (out) *out = 0;
    if (!started || !out || pin > 48u || next_token == UINT64_MAX) return false;
    if (!(flags & (RISC_GPIO_INPUT | RISC_GPIO_OUTPUT))) return false;
    for (size_t i = 0; i < MAX_CLAIMS; ++i)
        if (claims[i].token && claims[i].pin == pin) return false;
    claim_t *slot = NULL;
    for (size_t i = 0; i < MAX_CLAIMS; ++i)
        if (!claims[i].token) { slot = &claims[i]; break; }
    if (!slot || !configure(pin, flags)) return false;
    slot->pin = pin;
    slot->flags = flags;
    slot->token = next_token++;
    *out = slot->token;
    return true;
}
static bool write_pin(void *context, uint64_t token, bool level) {
    (void)context;
    claim_t *slot = find(token);
    if (!started || !slot || !(slot->flags & RISC_GPIO_OUTPUT)) return false;
    write_level(slot->pin, level);
    return true;
}
static bool read_pin(void *context, uint64_t token, bool *level) {
    (void)context;
    claim_t *slot = find(token);
    if (!started || !slot || !level) return false;
    *level = read_level(slot->pin);
    return true;
}
static bool release_pin(void *context, uint64_t token) {
    (void)context;
    claim_t *slot = find(token);
    if (!started || !slot) return false;
    set_output_enable(slot->pin, false);
    *slot = (claim_t){0};
    return true;
}
static bool quiesce(void) {
    for (size_t i = 0; i < MAX_CLAIMS; ++i)
        if (claims[i].token) return false;
    started = false;
    return true;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    (void)deps;
    if (started || count) return false;
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const risc_gpio_bank_api_v1 api = {
    RISC_GPIO_BANK_API_V1, sizeof(api), NULL, claim_pin, write_pin, read_pin, release_pin
};
static const risc_driver_v2 driver = {
    RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver),
    "twatch-gpio", RISC_GPIO_BANK_CAPABILITY, RISC_GPIO_BANK_API_V1,
    &api, start, stop, quiesce
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

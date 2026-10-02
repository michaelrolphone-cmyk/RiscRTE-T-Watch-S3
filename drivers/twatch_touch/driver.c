/* FT6336U on the touch I2C pair. No reset pin is wired. This driver never
 * writes the sleep register: LilyGO documents that a slept controller cannot
 * be restored without a power cycle. */
#include "RiscGpioBankV1.h"
#include "RiscI2cBusV1.h"
#include "RiscPlatformClockV1.h"
#include "RiscTouchV1.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
#define FT_TD_STATUS 0x02u
#define FT_P1 0x03u
typedef struct { uint64_t id; uint32_t read_seq; } sub_t;
static const risc_i2c_bus_api_v1 *bus;
static const risc_gpio_bank_api_v1 *gpio_api;
static const risc_platform_clock_api_v1 *clock_api;
static uint64_t claim, irq;
static bool started;
static sub_t subs[RISC_TOUCH_MAX_SUBSCRIBERS];
static risc_touch_event_v1 queues[RISC_TOUCH_MAX_SUBSCRIBERS][RISC_TOUCH_QUEUE_LENGTH];
static uint8_t qh[RISC_TOUCH_MAX_SUBSCRIBERS], qt[RISC_TOUCH_MAX_SUBSCRIBERS];
static bool gap[RISC_TOUCH_MAX_SUBSCRIBERS];
static uint64_t next_sub = 1, sequence = 1;
static risc_touch_contact_v1 contacts[2];
static uint8_t contact_count;
static char error[64];
static uint64_t now(void) {
    return clock_api && clock_api->monotonic_ms ? clock_api->monotonic_ms(clock_api->context) : 0;
}
static bool read_reg(uint8_t reg, uint8_t *out, size_t n) {
    return bus->transact(bus->context, claim, &reg, 1, out, n, 30);
}
static void push(uint8_t kind, uint8_t id, uint16_t x, uint16_t y) {
    risc_touch_event_v1 ev = {sequence++, now(), kind, id, x, y};
    for (size_t s = 0; s < RISC_TOUCH_MAX_SUBSCRIBERS; ++s) {
        if (!subs[s].id) continue;
        uint8_t next = (uint8_t)((qh[s] + 1u) % RISC_TOUCH_QUEUE_LENGTH);
        if (next == qt[s]) { gap[s] = true; continue; }
        queues[s][qh[s]] = ev;
        qh[s] = next;
    }
}
static bool poll(void *context, size_t max_reports) {
    (void)context;
    if (!started) return false;
    if (!max_reports) max_reports = 1;
    for (size_t n = 0; n < max_reports; ++n) {
        bool pending = true;
        if (irq && !gpio_api->read(gpio_api->context, irq, &pending)) return false;
        if (pending) return true; /* FT6336 INT is active low; high means idle. */
        uint8_t raw[7] = {0};
        if (!read_reg(FT_TD_STATUS, raw, 7)) {
            twatch_copy_error(error, sizeof error, "FT6336 read failed");
            return false;
        }
        uint8_t count = raw[0] & 0x0fu;
        if (count > 2u) count = 2u;
        risc_touch_contact_v1 next_c[2] = {0};
        for (uint8_t i = 0; i < count; ++i) {
            const uint8_t *p = raw + 1 + i * 0; /* first point only in this 6-byte window */
            if (i == 0) {
                next_c[0].id = 0;
                next_c[0].x = (uint16_t)(((p[0] & 0x0fu) << 8) | p[1]);
                next_c[0].y = (uint16_t)(((p[2] & 0x0fu) << 8) | p[3]);
            }
        }
        if (count > 1u) {
            uint8_t p2[4] = {0};
            if (read_reg(0x09u, p2, 4)) {
                next_c[1].id = 1;
                next_c[1].x = (uint16_t)(((p2[0] & 0x0fu) << 8) | p2[1]);
                next_c[1].y = (uint16_t)(((p2[2] & 0x0fu) << 8) | p2[3]);
            } else count = 1;
        }
        for (uint8_t i = 0; i < count; ++i) {
            if (next_c[i].x >= TWATCH_LCD_W) next_c[i].x = TWATCH_LCD_W - 1u;
            if (next_c[i].y >= TWATCH_LCD_H) next_c[i].y = TWATCH_LCD_H - 1u;
            bool seen = false;
            for (uint8_t j = 0; j < contact_count; ++j)
                if (contacts[j].id == next_c[i].id) seen = true;
            push(seen ? RISC_TOUCH_EVENT_MOVE : RISC_TOUCH_EVENT_DOWN,
                 next_c[i].id, next_c[i].x, next_c[i].y);
        }
        for (uint8_t j = 0; j < contact_count; ++j) {
            bool still = false;
            for (uint8_t i = 0; i < count; ++i)
                if (next_c[i].id == contacts[j].id) still = true;
            if (!still) push(RISC_TOUCH_EVENT_UP, contacts[j].id, contacts[j].x, contacts[j].y);
        }
        contact_count = count;
        for (uint8_t i = 0; i < count; ++i) contacts[i] = next_c[i];
    }
    return true;
}
static uint64_t subscribe(void *context) {
    (void)context;
    if (!started) return 0;
    for (size_t i = 0; i < RISC_TOUCH_MAX_SUBSCRIBERS; ++i)
        if (!subs[i].id) {
            subs[i].id = next_sub++;
            subs[i].read_seq = 0;
            qh[i] = qt[i] = 0;
            gap[i] = false;
            return subs[i].id;
        }
    return 0;
}
static bool unsubscribe(void *context, uint64_t id) {
    (void)context;
    for (size_t i = 0; i < RISC_TOUCH_MAX_SUBSCRIBERS; ++i)
        if (subs[i].id == id) { subs[i] = (sub_t){0}; return true; }
    return false;
}
static int32_t next_ev(void *context, uint64_t id, risc_touch_event_v1 *out) {
    (void)context;
    if (!out) return -2;
    for (size_t i = 0; i < RISC_TOUCH_MAX_SUBSCRIBERS; ++i) {
        if (subs[i].id != id) continue;
        if (gap[i]) { gap[i] = false; qh[i] = qt[i] = 0; return -1; }
        if (qh[i] == qt[i]) return 0;
        *out = queues[i][qt[i]];
        qt[i] = (uint8_t)((qt[i] + 1u) % RISC_TOUCH_QUEUE_LENGTH);
        return 1;
    }
    return -1;
}
static bool snapshot(void *context, risc_touch_snapshot_v1 *out) {
    (void)context;
    if (!started || !out) return false;
    *out = (risc_touch_snapshot_v1){0};
    out->sequence = sequence;
    out->timestamp_ms = now();
    out->width = TWATCH_LCD_W;
    out->height = TWATCH_LCD_H;
    out->contact_count = contact_count;
    for (uint8_t i = 0; i < contact_count && i < RISC_TOUCH_MAX_CONTACTS; ++i)
        out->contacts[i] = contacts[i];
    return true;
}
static bool quiesce(void) {
    bool ok = true;
    if (claim && bus && !bus->release_device(bus->context, claim)) ok = false;
    if (irq && gpio_api && !gpio_api->release(gpio_api->context, irq)) ok = false;
    claim = irq = 0;
    bus = NULL; gpio_api = NULL; clock_api = NULL;
    started = false;
    contact_count = 0;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 3u) return false;
    for (size_t i = 0; i < count; ++i) {
        if (twatch_equal(deps[i].capability_id, "i2c.bus.touch")) bus = deps[i].api;
        else if (twatch_equal(deps[i].capability_id, RISC_GPIO_BANK_CAPABILITY)) gpio_api = deps[i].api;
        else if (twatch_equal(deps[i].capability_id, RISC_PLATFORM_CLOCK_CAPABILITY)) clock_api = deps[i].api;
    }
    if (!bus || !gpio_api || !clock_api) return false;
    if (!bus->claim_device(bus->context, TWATCH_I2C_FT6336, &claim) ||
        !gpio_api->claim(gpio_api->context, TWATCH_PIN_TOUCH_INT, RISC_GPIO_INPUT | RISC_GPIO_PULLUP, &irq)) {
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const risc_touch_api_v1 api = {
    RISC_TOUCH_API_V1, sizeof(api), NULL, subscribe, unsubscribe, poll, next_ev, snapshot
};
static const risc_driver_v2 driver = {
    RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-touch",
    RISC_TOUCH_CAPABILITY, RISC_TOUCH_API_V1, &api, start, stop, quiesce
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

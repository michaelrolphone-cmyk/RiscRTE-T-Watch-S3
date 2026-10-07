/* FT6336U on the touch I2C pair. No reset pin is wired. This driver never
 * writes the sleep register: LilyGO documents that a slept controller cannot
 * be restored without a power cycle. */
#include "RiscGpioBankV1.h"
#include "RiscI2cBusV1.h"
#include "RiscPlatformClockV1.h"
#include "RiscTouchV1.h"
#include "twatch_support.h"
#include <stdatomic.h>
#include "twatch_util.h"
#include <stddef.h>
#define FT_TD_STATUS 0x02u
#define FT_P1 0x03u
typedef struct {
    uint64_t id;
    uint32_t read_seq;
} sub_t;
static const risc_i2c_bus_api_v1 *bus;
static const risc_gpio_bank_api_v1 *gpio_api;
static const risc_platform_clock_api_v1 *clock_api;
static uint64_t claim, irq;
static bool started;
static const risc_hw_i2c_touch_v1 *config;
static atomic_flag guard = ATOMIC_FLAG_INIT;
static sub_t subs[RISC_TOUCH_MAX_SUBSCRIBERS];
static risc_touch_event_v1 queues[RISC_TOUCH_MAX_SUBSCRIBERS][RISC_TOUCH_QUEUE_LENGTH];
static uint8_t qh[RISC_TOUCH_MAX_SUBSCRIBERS], qt[RISC_TOUCH_MAX_SUBSCRIBERS];
static bool gap[RISC_TOUCH_MAX_SUBSCRIBERS];
static uint64_t next_sub = 1, sequence = 1;
static risc_touch_contact_v1 contacts[2];
static uint8_t contact_count;
static uint64_t now(void) {
    return clock_api && clock_api->monotonic_ms ? clock_api->monotonic_ms(clock_api->context) : 0;
}
static bool read_reg(uint8_t reg, uint8_t *out, size_t n) {
    return bus->transact(bus->context, claim, &reg, 1, out, n, 30);
}
static void push(uint8_t kind, uint8_t id, uint16_t x, uint16_t y) {
    /* snapshot.sequence is the last emitted event, matching raw touch consumers. */
    risc_touch_event_v1 ev = {++sequence, now(), kind, id, x, y};
    for (size_t s = 0; s < RISC_TOUCH_MAX_SUBSCRIBERS; ++s) {
        if (!subs[s].id)
            continue;
        uint8_t next = (uint8_t)((qh[s] + 1u) % RISC_TOUCH_QUEUE_LENGTH);
        if (next == qt[s]) {
            gap[s] = true;
            continue;
        }
        queues[s][qh[s]] = ev;
        qh[s] = next;
    }
}
static bool poll_impl(void *context, size_t max_reports) {
    (void)context;
    if (!started)
        return false;
    (void)max_reports;
    for (size_t n = 0; n < 1; ++n) {
        /* Read a complete coherent report even when the edge IRQ has deasserted;
         * a missed pulse must not leave a finger permanently down. */
        uint8_t raw[13] = {0};
        if (!read_reg(FT_TD_STATUS, raw, sizeof(raw)))
            return false;
        uint8_t count = raw[0] & 15;
        if (count > 2) {
            for (size_t i = 0; i < RISC_TOUCH_MAX_SUBSCRIBERS; i++)
                if (subs[i].id)
                    gap[i] = true;
            return false;
        }
        risc_touch_contact_v1 next_c[2] = {0};
        for (uint8_t i = 0; i < count; i++) {
            const uint8_t *p = raw + 1 + 6 * i;
            next_c[i].id = p[2] >> 4;
            next_c[i].x = (uint16_t)(((p[0] & 15) << 8) | p[1]);
            next_c[i].y = (uint16_t)(((p[2] & 15) << 8) | p[3]);
            if ((p[0] >> 6) == 3 || (i && next_c[0].id == next_c[i].id)) {
                for (size_t j = 0; j < RISC_TOUCH_MAX_SUBSCRIBERS; j++)
                    if (subs[j].id)
                        gap[j] = true;
                return false;
            }
        }
        for (uint8_t i = 0; i < count; ++i) {
            if (next_c[i].x >= config->width)
                next_c[i].x = config->width - 1u;
            if (next_c[i].y >= config->height)
                next_c[i].y = config->height - 1u;
            bool seen = false;
            for (uint8_t j = 0; j < contact_count; ++j)
                if (contacts[j].id == next_c[i].id)
                    seen = true;
            push(seen ? RISC_TOUCH_EVENT_MOVE : RISC_TOUCH_EVENT_DOWN, next_c[i].id, next_c[i].x,
                 next_c[i].y);
        }
        for (uint8_t j = 0; j < contact_count; ++j) {
            bool still = false;
            for (uint8_t i = 0; i < count; ++i)
                if (next_c[i].id == contacts[j].id)
                    still = true;
            if (!still)
                push(RISC_TOUCH_EVENT_UP, contacts[j].id, contacts[j].x, contacts[j].y);
        }
        contact_count = count;
        for (uint8_t i = 0; i < count; ++i)
            contacts[i] = next_c[i];
    }
    return true;
}
static uint64_t subscribe_impl(void *context) {
    (void)context;
    if (!started || next_sub == UINT64_MAX)
        return 0;
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
static bool unsubscribe_impl(void *context, uint64_t id) {
    (void)context;
    if (!started || !id)
        return false;
    for (size_t i = 0; i < RISC_TOUCH_MAX_SUBSCRIBERS; ++i)
        if (subs[i].id == id) {
            subs[i] = (sub_t){0};
            return true;
        }
    return false;
}
static int32_t next_ev_impl(void *context, uint64_t id, risc_touch_event_v1 *out) {
    (void)context;
    if (!started || !out || !id)
        return -2;
    for (size_t i = 0; i < RISC_TOUCH_MAX_SUBSCRIBERS; ++i) {
        if (subs[i].id != id)
            continue;
        if (gap[i]) {
            gap[i] = false;
            qh[i] = qt[i] = 0;
            return -1;
        }
        if (qh[i] == qt[i])
            return 0;
        *out = queues[i][qt[i]];
        qt[i] = (uint8_t)((qt[i] + 1u) % RISC_TOUCH_QUEUE_LENGTH);
        return 1;
    }
    return -1;
}
static bool snapshot_impl(void *context, risc_touch_snapshot_v1 *out) {
    (void)context;
    if (!started || !out)
        return false;
    *out = (risc_touch_snapshot_v1){0};
    out->sequence = sequence;
    out->timestamp_ms = now();
    out->width = config->width;
    out->height = config->height;
    out->contact_count = contact_count;
    for (uint8_t i = 0; i < contact_count && i < RISC_TOUCH_MAX_CONTACTS; ++i)
        out->contacts[i] = contacts[i];
    return true;
}
static bool quiesce_impl(void) {
    for (size_t i = 0; i < RISC_TOUCH_MAX_SUBSCRIBERS; i++)
        if (subs[i].id)
            return false;
    bool ok = true;
    if (claim) {
        if (!bus->release_device(bus->context, claim))
            return false;
        claim = 0;
    }
    if (irq) {
        if (!gpio_api->release(gpio_api->context, irq))
            return false;
        irq = 0;
    }
    claim = irq = 0;
    bus = NULL;
    gpio_api = NULL;
    clock_api = NULL;
    started = false;
    contact_count = 0;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || claim || irq)
        return false;
    config = tw_config(deps, count, "focaltech,ft6336u", "touch.i2c", sizeof(*config));
    if (!config || !tw_bus(&config->bus, 2) || config->address < 8 || config->address > 0x77 ||
        !config->width || !config->height || config->width > 4096 || config->height > 4096 ||
        config->reset != -1 || !tw_pin(config->irq) || config->irq == config->bus.sda ||
        config->irq == config->bus.scl || config->irq_pull_up > 1 || config->irq_active_high > 1)
        return false;
    bus = tw_dep(deps, count, "i2c.bus", sizeof(*bus));
    gpio_api = tw_dep(deps, count, "gpio.bank", offsetof(risc_gpio_bank_api_v1,light_sleep));
    clock_api = tw_dep(deps, count, "platform.clock", sizeof(*clock_api));
    if (!tw_i2c_valid(bus) || !tw_gpio_valid(gpio_api) || !tw_clock_valid(clock_api))
        return false;
    if (!bus || !gpio_api || !clock_api)
        return false;
    if (!bus->claim_device(bus->context, config->address, &claim) ||
        !gpio_api->claim(gpio_api->context, config->irq,
                         RISC_GPIO_INPUT | (config->irq_pull_up ? RISC_GPIO_PULLUP : 0), &irq)) {
        (void)quiesce_impl();
        return false;
    }
    started = true;
    return true;
}
static bool poll(void *c, size_t n) {
    if (atomic_flag_test_and_set(&guard))
        return false;
    bool r = poll_impl(c, n);
    atomic_flag_clear(&guard);
    return r;
}
static uint64_t subscribe(void *c) {
    if (atomic_flag_test_and_set(&guard))
        return 0;
    uint64_t r = subscribe_impl(c);
    atomic_flag_clear(&guard);
    return r;
}
static bool unsubscribe(void *c, uint64_t t) {
    if (atomic_flag_test_and_set(&guard))
        return false;
    bool r = unsubscribe_impl(c, t);
    atomic_flag_clear(&guard);
    return r;
}
static int32_t next_ev(void *c, uint64_t t, risc_touch_event_v1 *o) {
    if (atomic_flag_test_and_set(&guard))
        return -2;
    int32_t r = next_ev_impl(c, t, o);
    atomic_flag_clear(&guard);
    return r;
}
static bool snapshot(void *c, risc_touch_snapshot_v1 *o) {
    if (atomic_flag_test_and_set(&guard))
        return false;
    bool r = snapshot_impl(c, o);
    atomic_flag_clear(&guard);
    return r;
}
static bool quiesce(void) {
    if (atomic_flag_test_and_set(&guard))
        return false;
    bool r = quiesce_impl();
    atomic_flag_clear(&guard);
    return r;
}
static void stop(void) {
    (void)quiesce();
}
static const risc_touch_api_v1 api = {RISC_TOUCH_API_V1, sizeof(api), NULL,    subscribe,
                                      unsubscribe,       poll,        next_ev, snapshot};
static const risc_driver_v2 driver = {RISC_PROVIDER_DRIVER_ABI_V2,
                                      sizeof(driver),
                                      "twatch-touch",
                                      RISC_TOUCH_CAPABILITY,
                                      RISC_TOUCH_API_V1,
                                      &api,
                                      start,
                                      stop,
                                      quiesce};
__attribute__((visibility("default"))) const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver : NULL;
}

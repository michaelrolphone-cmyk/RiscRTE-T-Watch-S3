/* The app and driver SDKs intentionally have separate physical headers.
 * Compile this file once for each side, sharing only C ABI scalars/pointers. */
#ifdef POINTS_PMU_FIXTURE
#include <assert.h>
#include "twatch_support.h"
#include "fixture_config.h"
extern uint64_t monotonic_ms;
extern unsigned key_reads;
extern int32_t points_test_hardware_sleep(void);
static uint8_t regs[256];
static bool bus_owned, irq_owned;
static const risc_driver_v2 *driver;
/* Actual PMU owns these hardware dependencies and its private release latch. */
static bool bus_claim(void *context, uint8_t address, uint64_t *token) {
    (void)context; assert(address == m_config.device.address && !bus_owned);
    bus_owned = true; *token = 1; return true;
}
static bool bus_release(void *context, uint64_t token) {
    (void)context; assert(token == 1 && bus_owned); bus_owned = false; return true;
}
static bool bus_transfer(void *context, uint64_t token, const uint8_t *tx, size_t tx_size,
                         uint8_t *rx, size_t rx_size, uint32_t timeout) {
    (void)context; assert(token == 1 && bus_owned && timeout && tx_size);
    uint8_t reg = tx[0];
    for (size_t i = 1; i < tx_size; ++i) {
        unsigned index = (uint8_t)(reg + i - 1);
        if (index >= 0x48 && index <= 0x4a) regs[index] &= (uint8_t)~tx[i];
        else regs[index] = tx[i];
    }
    for (size_t i = 0; i < rx_size; ++i) {
        unsigned index = (uint8_t)(reg + i);
        if (index == 0x49) { assert(!regs[index]); ++key_reads; }
        rx[i] = regs[index];
    }
    return true;
}
static bool gpio_claim(void *context, uint8_t pin, uint32_t flags, uint64_t *token) {
    (void)context; assert(pin == m_config.device.irq && (flags & RISC_GPIO_INPUT) && !irq_owned);
    irq_owned = true; *token = 2; return true;
}
static bool gpio_release(void *context, uint64_t token) {
    (void)context; assert(token == 2 && irq_owned); irq_owned = false; return true;
}
static bool gpio_read(void *context, uint64_t token, bool *high) {
    (void)context; assert(token == 2 && irq_owned); *high = true; return true;
}
static bool gpio_write(void *context, uint64_t token, bool high) {
    (void)context; (void)token; (void)high; assert(!"PMU IRQ is input-only"); return false;
}
static int32_t gpio_sleep(void *context, uint64_t token, bool high,
                          risc_light_sleep_result_v1 *out) {
    (void)context;
    assert(token == 2 && irq_owned && !high && out->struct_size == sizeof(*out));
    out->wake_cause = RISC_LIGHT_SLEEP_WAKE_GPIO;
    return points_test_hardware_sleep();
}
static uint64_t clock_now(void *context) { (void)context; return monotonic_ms; }
static void clock_sleep(void *context, uint32_t ms) { (void)context; monotonic_ms += ms; }
static risc_i2c_bus_api_v1 bus = {1,sizeof(bus),NULL,bus_claim,bus_transfer,bus_release};
static risc_gpio_bank_api_v1 gpio = {
    .api_version=1,.struct_size=sizeof(gpio),.claim=gpio_claim,.write=gpio_write,
    .read=gpio_read,.release=gpio_release,.light_sleep=gpio_sleep
};
static risc_platform_clock_api_v1 platform_clock = {1,sizeof(platform_clock),NULL,clock_now,clock_sleep};

const void *points_test_start_pmu(void) {
    regs[3] = 0x4a;
    const risc_provider_dependency_v1 dependencies[] = {
        {"hardware.device",1,&m_device},{"i2c.bus",1,&bus},
        {"gpio.bank",1,&gpio},{"platform.clock",1,&platform_clock}
    };
    driver = t5_driver_get(2);
    assert(driver && driver->start(dependencies,sizeof(dependencies)/sizeof(*dependencies)));
    return driver->capability;
}
bool points_test_stop_pmu(void) {
    return driver->quiesce() && !bus_owned && !irq_owned;
}
#else
/* Host integration regression: real crown, Points projection/rendering and PMU.
 * Only the runtime, display transport, RTC, storage, alarm service and physical
 * I2C/GPIO boundary are fixtures. No crown edge or touch contact is injected. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "RiscRuntimeV1.h"
#include "RiscTouchV1.h"
#include "twatch_power.h"
#include "twatch_caps.h"
#include "apps/clock/nova/nova.h"
#include "apps/clock/faces/picker.h"
#include "apps/clock/points_projection.h"
#include "PortableSleepPolicy.h"
#include "PortableTimeFormat.h"
#include "AlarmServiceV1.h"

#ifndef POINTS_DEFAULTS_AVAILABLE
#error This regression requires the current shared Points morning defaults
#endif
void app_main(void);
const void *points_test_start_pmu(void);
bool points_test_stop_pmu(void);
static const twatch_pmu_api_v1 *pmu;
static uint16_t pixels[240 * 240];
uint64_t monotonic_ms;
static uint32_t began_at, ready_at, frame_cost, present_at, first_countdown;
static uint32_t last_countdown, last_render_at, last_hash, last_second;
unsigned key_reads;
static unsigned frames, countdown_frames, changed_seconds;
static unsigned grants, releases, subscriptions, unsubscribes, touch_polls;
static unsigned panel_attempts, sleep_calls, alarm_prepares, points_reads;
static uint32_t attempt_at, slept_at;
static bool ready, frame_owned, frame_pending, panel_asleep;

static uint32_t now(void) { return (uint32_t)monotonic_ms; }
static bool health(risc_runtime_health_v1 *out) {
    out->uptime_ms = now();
    return !sleep_calls && (uint32_t)(now() - began_at) < 70000u;
}
static void yield_ms(uint32_t ms) { assert(ms && ms <= 50); monotonic_ms += ms; }
static bool diagnostic(const char *line) {
    if (!strcmp(line, "WATCH_CLOCK ready crown=enabled")) {
        assert(!ready && points_reads == 2);
        ready = true;
        ready_at = now();
    }
    return true;
}
static bool launch(const char *name) {
    (void)name; assert(!"Idle watch must not request a launcher"); return false;
}

/* Wrap only the renderer entry point called by crown. Every frame still runs
 * the unmodified production Points RGB565 renderer. */
bool test_points_face_render(risc_display_surface_v1 *surface,
                            const nova_watch_state *state, unsigned id) {
    assert(id == 24 && state->time_valid && state->points);
    const nova_points_state *view = state->points;
    assert(view->status == NOVA_POINTS_READY && view->next_count > 0);
    assert(view->next[0].kind == NOVA_POINT_CUSTOM_1);
    assert(!strcmp(view->next[0].label, "Drive to Work"));
    assert(view->next[0].hour == 5 && view->next[0].minute == 30);
    assert(state->time.year == 2026 && state->time.month == 10 && state->time.day == 5);
    assert(state->time.hour == 4 && state->time.minute >= 45 && state->time.minute <= 46);
    uint32_t remaining = view->next[0].at_rtc - view->now_rtc;
    assert(remaining > 0 && remaining <= 2700);
    bool result = nova_watch_face_render(surface, state, id);
    assert(result);
    if (ready && !panel_attempts) {
        uint32_t hash = 2166136261u;
        for (unsigned i = 0; i < 240 * 240; ++i)
            hash = (hash ^ ((const uint16_t *)surface->pixels)[i]) * 16777619u;
        if (!countdown_frames) first_countdown = remaining;
        else {
            assert(remaining <= last_countdown);
            if (view->now_rtc != last_second) {
                assert(hash != last_hash);
                ++changed_seconds;
            }
        }
        last_hash = hash;
        last_second = view->now_rtc;
        last_countdown = remaining;
        last_render_at = now();
        ++countdown_frames;
    }
    return result;
}

static bool display_info(void *context, risc_display_info_v1 *out) {
    (void)context; out->width = out->height = 240; return true;
}
static bool frame_acquire(void *context, uint32_t format, risc_display_surface_v1 *out) {
    (void)context;
    assert(!frame_owned && !frame_pending && !panel_asleep);
    assert(format == RISC_DISPLAY_FORMAT_RGB565);
    frame_owned = true;
    *out = (risc_display_surface_v1){1,pixels,240,240,480,sizeof(pixels),5};
    return true;
}
static void frame_release(void *context, uint64_t frame) {
    (void)context; assert(frame == 1 && frame_owned); frame_owned = false;
}
static bool frame_submit(void *context, uint64_t frame, const risc_display_rect_v1 *dirty,
                         size_t count, const risc_display_present_options_v1 *options,
                         uint64_t *token) {
    (void)context; (void)options;
    assert(frame == 1 && frame_owned && !frame_pending && !dirty && !count);
    frame_owned = false; frame_pending = true; present_at = now(); *token = ++frames;
    return true;
}
static bool frame_status(void *context, uint64_t token, risc_display_present_status_v1 *out) {
    (void)context; assert(token == frames && frame_pending);
    if ((uint32_t)(now() - present_at) < frame_cost) out->state = RISC_DISPLAY_PRESENT_ACTIVE;
    else { frame_pending = false; out->state = RISC_DISPLAY_PRESENT_COMPLETE; }
    return true;
}
static bool brightness(void *context, uint16_t value, uint16_t maximum) {
    (void)context; assert((value == 0 || value == 40) && maximum == 100); return true;
}
static bool panel_prepare(void *context) {
    (void)context;
    assert(ready && !frame_owned && !frame_pending && subscriptions == unsubscribes);
    assert(!panel_attempts && !sleep_calls);
    for (unsigned i = 0; i < 240 * 240; ++i) assert(!pixels[i]);
    attempt_at = now(); ++panel_attempts; panel_asleep = true; return true;
}
static bool panel_resume(void *context) {
    (void)context; assert(panel_asleep); panel_asleep = false; return true;
}
static twatch_panel_power_v1 display = {
    .base = {1,sizeof(display),NULL,display_info,frame_acquire,frame_release,
             frame_submit,frame_status,NULL,brightness},
    .prepare_sleep = panel_prepare, .resume = panel_resume
};

static bool rtc_read(void *context, twatch_rtc_time_v1 *out) {
    (void)context;
    unsigned seconds = (uint32_t)(now() - began_at) / 1000;
    /* Hardware RTC convention is UTC+8; October Denver display is 14h earlier. */
    *out = (twatch_rtc_time_v1){2026,10,5,1,18,(uint8_t)(45 + seconds / 60),
                              (uint8_t)(seconds % 60)};
    return true;
}
static twatch_rtc_api_v1 rtc = {2,sizeof(rtc),NULL,rtc_read,NULL,NULL,NULL};
static uint64_t touch_subscribe(void *context) { (void)context; return ++subscriptions; }
static bool touch_unsubscribe(void *context, uint64_t token) {
    (void)context; assert(token && subscriptions > unsubscribes); ++unsubscribes; return true;
}
static bool touch_poll(void *context, size_t count) {
    (void)context; assert(count == 1); ++touch_polls; return true;
}
static int32_t touch_next(void *context, uint64_t token, risc_touch_event_v1 *event) {
    (void)context; (void)event; assert(token); return 0;
}
static bool touch_snapshot(void *context, risc_touch_snapshot_v1 *out) {
    (void)context; *out = (risc_touch_snapshot_v1){.width=240,.height=240}; return true;
}
static risc_touch_api_v1 touch = {1,sizeof(touch),NULL,touch_subscribe,touch_unsubscribe,
                                touch_poll,touch_next,touch_snapshot};
static int32_t kv_get(void *context, const char *key, void *out, uint32_t capacity,
                      uint32_t *size) {
    (void)context; assert(!frame_owned && !frame_pending); *size = 0;
    if (!strcmp(key, POINTS_CONFIG_KEY) || !strcmp(key, POINTS_META_KEY)) {
        ++points_reads; return RISC_KEY_VALUE_NOT_FOUND; /* Real shared defaults. */
    }
    if (!strcmp(key, PORTABLE_TIME_FORMAT_KEY)) return RISC_KEY_VALUE_NOT_FOUND;
    assert(capacity == 4); *size = 4;
    if (!strcmp(key, WATCH_FACE_KEY)) {
        memcpy(out, (uint8_t[]){0x46,1,24,24 ^ 0xa5},4); return RISC_KEY_VALUE_OK;
    }
    assert(!strcmp(key, PORTABLE_SLEEP_KEY));
    memcpy(out, (uint8_t[]){0x53,1,PORTABLE_SLEEP_LIGHT,0xa5},4); return RISC_KEY_VALUE_OK;
}
static int32_t kv_put(void *context, const char *key, const void *bytes, uint32_t size) {
    (void)context; (void)key; (void)bytes; (void)size;
    assert(!"Countdown and idle sleep must not write settings"); return RISC_KEY_VALUE_IO;
}
static risc_key_value_v1 kv = {1,sizeof(kv),NULL,kv_get,kv_put};
static int32_t alarm_status(void *context, alarm_status_v1 *out) {
    (void)context;
    *out = (alarm_status_v1){.api_version=1,.struct_size=sizeof(*out),.state=ALARM_STATE_READY};
    return ALARM_OK;
}
static int32_t alarm_noop(void *context) { (void)context; return ALARM_OK; }
static int32_t alarm_ack(void *context, const alarm_token_v1 *token) {
    (void)context; (void)token; assert(!"No alert was raised"); return ALARM_INVALID;
}
static int32_t alarm_prepare(void *context, alarm_sleep_v1 *out) {
    (void)context; ++alarm_prepares;
    *out = (alarm_sleep_v1){.struct_size=sizeof(*out)}; return ALARM_OK;
}
static alarm_service_v1 alarm = {1,sizeof(alarm),NULL,alarm_status,alarm_noop,alarm_noop,
                               alarm_ack,alarm_prepare,alarm_noop};
static bool acquire(const char *name, uint32_t version, uint64_t instance,
                    risc_runtime_capability_v1 *grant) {
    assert(grant->struct_size == sizeof(*grant));
    if (!strcmp(name,RISC_KEY_VALUE_CAPABILITY)) {
        assert(version == 1 && (instance == 1 || instance == 5)); grant->api = &kv;
    } else {
        assert(!instance);
        if (!strcmp(name,"display.output")) grant->api = &display;
        else if (!strcmp(name,"board.battery")) grant->api = pmu;
        else if (!strcmp(name,"rtc.clock")) { assert(version == 2); grant->api = &rtc; }
        else if (!strcmp(name,"input.touch.raw")) grant->api = &touch;
        else { assert(!strcmp(name,ALARM_SERVICE_CAPABILITY)); grant->api = &alarm; }
    }
    ++grants; return true;
}
static bool release(risc_runtime_capability_v1 *grant) {
    assert(grant->api && !frame_owned && !frame_pending);
    grant->api = NULL; ++releases; return true;
}
static risc_runtime_api_v1 runtime = {1,sizeof(runtime),health,yield_ms,diagnostic,
                                    launch,acquire,release};
const risc_runtime_api_v1 *risc_runtime_get_api(uint32_t version) {
    assert(version == 1); return &runtime;
}

int32_t points_test_hardware_sleep(void) {
    assert(panel_asleep && panel_attempts == 1 && alarm_prepares == 1);
    assert(!frame_owned && !frame_pending && subscriptions == unsubscribes);
    ++sleep_calls; slept_at = now();
    return RISC_LIGHT_SLEEP_ACTIVE_WAKE;
}

int main(int argc, char **argv) {
    assert(argc == 3);
    frame_cost = (uint32_t)strtoul(argv[1],NULL,10);
    monotonic_ms = atoi(argv[2]) ? UINT32_MAX - 5000u : 0;
    pmu = points_test_start_pmu();
    assert(pmu);
    began_at = now();
    app_main();
    assert(ready && points_reads == 2 && panel_attempts == 1);
    uint32_t idle_ms = attempt_at - ready_at;
    assert(idle_ms >= 60000u && idle_ms <= 60020u + 2u * frame_cost);
    uint32_t cadence = frame_cost > 20 ? frame_cost : 20;
    assert(countdown_frames >= 60000u / cadence);
    assert(changed_seconds >= 59 && first_countdown - last_countdown >= 59);
    assert((uint32_t)(last_render_at - ready_at) < 60000u);
    assert((uint32_t)(last_render_at - ready_at) >= 60000u - cadence);
    assert(key_reads > countdown_frames && touch_polls >= countdown_frames);
    fprintf(stderr,"Points NEXT: %u rendered frames, %u changed seconds, idle attempt at +%ums, hardware sleep calls=%u\n",
            countdown_frames,changed_seconds,idle_ms,sleep_calls);
    assert(sleep_calls == 1); /* Fails with cold-boot key_released=false baseline. */
    assert((uint32_t)(slept_at - attempt_at) <= 150u);
    assert(grants == releases && subscriptions == unsubscribes);
    assert(!frame_owned && !frame_pending && !panel_asleep);
    assert(points_test_stop_pmu());
    puts("Points cold boot: live morning countdown does not reset 60s idle; real PMU reaches sleep without a key/touch event");
    return 0;
}
#endif

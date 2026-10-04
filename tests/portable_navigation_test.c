/* Exercise the app-local bridge against exactly the legacy key API prefix. */
#include "PortableNavigation.h"
#include "twatch_caps.h"
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

static unsigned grants, acquisitions, releases, reads, diagnostics;
static uint32_t pending;
static bool fail_acquire, fail_read, fail_release;
static int context_marker;
static bool key_events(void *context, uint32_t *events) {
    assert(context == &context_marker && events);
    ++reads;
    if (fail_read)
        return false;
    *events = pending;
    pending = 0;
    return true;
}
/* Intentionally excludes every sleep/power extension after key_events. */
static struct {
    risc_battery_gauge_api_v1 base;
    bool (*key_events)(void *, uint32_t *);
} legacy = {{1, sizeof(legacy), &context_marker, NULL}, key_events};
static bool acquire(const char *name, uint32_t version, uint64_t instance,
                    risc_runtime_capability_v1 *out) {
    assert(!strcmp(name, "board.battery") && version == 1 && !instance);
    assert(out && out->struct_size == sizeof(*out));
    ++acquisitions;
    if (fail_acquire)
        return false;
    assert(!grants);
    ++grants;
    out->api = &legacy;
    return true;
}
static bool release(risc_runtime_capability_v1 *out) {
    assert(grants == 1 && out->api == &legacy);
    ++releases;
    if (fail_release)
        return false;
    --grants;
    out->api = NULL;
    return true;
}
static bool diagnostic(const char *message) {
    assert(!strcmp(message, "PORTABLE_APP error=local-navigation-release"));
    ++diagnostics;
    return true;
}
static const risc_runtime_api_v1 runtime = {
    .api_version = 1, .struct_size = sizeof(runtime), .diagnostic = diagnostic,
    .acquire = acquire, .release = release
};
static const risc_input_navigation_api_v1 *nav;
static void sample(uint32_t events, bool back) {
    risc_input_navigation_frame_v1 frame = {99, 99, 99};
    pending = events;
    assert(nav->poll(nav->context, &frame));
    assert(!frame.buttons);
    assert(frame.pressed == (back ? RISC_NAV_BACK : 0));
    assert(frame.released == frame.pressed);
}
int main(void) {
    assert(!portable_input_navigation_open(NULL));
    portable_input_navigation_close(NULL);
    fail_acquire = true;
    assert(!portable_input_navigation_open(&runtime));
    portable_input_navigation_close(&runtime);
    assert(!grants);
    fail_acquire = false;
    for (unsigned invalid = 0; invalid < 3; ++invalid) {
        legacy.base.api_version = invalid == 0 ? 2 : 1;
        legacy.base.struct_size = invalid == 1 ? sizeof(legacy.base) : sizeof(legacy);
        legacy.key_events = invalid == 2 ? NULL : key_events;
        assert(!portable_input_navigation_open(&runtime));
        portable_input_navigation_close(&runtime);
        assert(!grants);
    }
    legacy.base.api_version = 1;
    legacy.base.struct_size = sizeof(legacy);
    legacy.key_events = key_events;
    nav = portable_input_navigation_open(&runtime);
    assert(nav && nav->api_version == 1 && nav->struct_size == sizeof(*nav));
    assert(!portable_input_navigation_open(&runtime));
    assert(!nav->poll(nav->context, NULL));
    const risc_input_foreground_v1 touch[] = {{"input.touch.raw", 1}};
    pending = 2; /* A stale app-launch event is drained. */
    assert(nav->foreground(nav->context, touch, 1));
    assert(!pending);
    assert(nav->reset(nav->context));
    sample(2, false); /* A clean sample is required after every boundary. */
    sample(0, false);
    sample(2, true);
    sample(2, false); /* No repeat without an event-free sample. */
    sample(0, false);
    sample(1, false); /* Long press never exits or sleeps. */
    sample(2, false);
    sample(0, false);
    sample(3, false); /* Coalesced long+short is ambiguous. */
    sample(0, false);
    sample(2, true);
    sample(0, false);
    pending = 2;
    assert(nav->reset(nav->context) && !pending);
    sample(0, false);
    fail_read = true;
    risc_input_navigation_frame_v1 frame = {99, 99, 99};
    assert(!nav->poll(nav->context, &frame));
    assert(!frame.buttons && !frame.pressed && !frame.released);
    fail_read = false;
    sample(2, false);
    sample(0, false);
    sample(2, true);
    const risc_input_foreground_v1 own[] = {{"input.navigation", 1}};
    assert(nav->foreground(nav->context, own, 1));
    unsigned before = reads;
    sample(2, false);
    assert(reads == before && pending == 2); /* Do not consume foreground-owned input. */
    assert(nav->foreground(nav->context, touch, 1));
    assert(!pending);
    assert(!nav->foreground(nav->context, NULL, 1));
    before = reads;
    sample(2, false);
    assert(reads == before);
    assert(!nav->foreground(nav->context, touch, 5));
    const risc_input_foreground_v1 invalid[] = {{NULL, 1}};
    assert(!nav->foreground(nav->context, invalid, 1));
    fail_read = true;
    assert(!nav->foreground(nav->context, touch, 1));
    fail_read = false;
    assert(nav->foreground(nav->context, touch, 1));
    sample(0, false);
    sample(2, true);
    fail_release = true;
    portable_input_navigation_close(&runtime);
    assert(grants == 1 && diagnostics == 1);
    assert(!nav->poll(nav->context, &frame));
    fail_release = false;
    portable_input_navigation_close(&runtime);
    assert(!grants);
    portable_input_navigation_close(&runtime);
    /* A fresh app can acquire and Back after the prior app is closed. */
    nav = portable_input_navigation_open(&runtime);
    assert(nav && nav->foreground(nav->context, touch, 1));
    sample(0, false);
    sample(2, true);
    portable_input_navigation_close(&runtime);
    assert(!grants && acquisitions == 6 && releases == 6);
    puts("Legacy PMU app-local navigation: ABI, boundary, Back, failure and cleanup checks passed");
    return 0;
}

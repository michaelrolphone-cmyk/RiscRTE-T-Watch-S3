/* App-local projection of the physically verified PMU's original key API.
 * The existing PMU remains the sole register/IRQ/power owner. This bridge
 * acquires its declared board.battery grant and never asks it to sleep. */
#include "PortableNavigation.h"
#include "twatch_caps.h"
#include <stddef.h>
#include <string.h>

static risc_runtime_capability_v1 grant;
static const twatch_pmu_api_v1 *pmu;
static bool suppressed, neutral;

enum { LEGACY_KEY_LONG = 1u, LEGACY_KEY_SHORT = 2u };

static bool reset(void *context) {
    (void)context;
    neutral = false;
    uint32_t discarded = 0;
    return pmu && pmu->key_events(pmu->base.context, &discarded);
}

static bool poll(void *context, risc_input_navigation_frame_v1 *out) {
    (void)context;
    if (!pmu || !out)
        return false;
    *out = (risc_input_navigation_frame_v1){0};
    if (suppressed)
        return true;
    uint32_t events = 0;
    if (!pmu->key_events(pmu->base.context, &events)) {
        neutral = false;
        return false;
    }
    /* The baseline provides latched, completed short/long events, not physical
     * down state. Drain pending boundary events, wait for an event-free sample,
     * and never interpret a long or ambiguous combined event as Back. */
    if (!events) {
        neutral = true;
    } else if (neutral && events == LEGACY_KEY_SHORT) {
        out->pressed = out->released = RISC_NAV_BACK;
        neutral = false;
    } else {
        neutral = false;
    }
    return true;
}

static bool foreground(void *context, const risc_input_foreground_v1 *claims,
                       size_t count) {
    (void)context;
    suppressed = true;
    neutral = false;
    if (!pmu || count > RISC_INPUT_NAVIGATION_MAX_FOREGROUND || (count && !claims))
        return false;
    for (size_t i = 0; i < count; ++i)
        if (!claims[i].capability || !claims[i].api_version)
            return false;
    bool overlap = false;
    for (size_t i = 0; i < count; ++i)
        if (!strcmp(claims[i].capability, "input.navigation"))
            overlap = true;
    if (!reset(NULL))
        return false;
    suppressed = overlap;
    return true;
}

static const risc_input_navigation_api_v1 api = {
    1, sizeof(api), NULL, poll, foreground, reset
};

const risc_input_navigation_api_v1 *portable_input_navigation_open(
    const risc_runtime_api_v1 *runtime) {
    if (!runtime || runtime->api_version != 1 ||
        runtime->struct_size < RISC_RUNTIME_CAPABILITIES_V1_SIZE ||
        !runtime->acquire || !runtime->release || !runtime->diagnostic || grant.api)
        return NULL;
    grant = (risc_runtime_capability_v1){.struct_size = sizeof(grant)};
    suppressed = true;
    neutral = false;
    if (!runtime->acquire("board.battery", 1, 0, &grant))
        return NULL;
    pmu = grant.api;
    const size_t key_api_size = offsetof(twatch_pmu_api_v1, key_events) +
                                sizeof(pmu->key_events);
    if (!pmu || pmu->base.api_version != 1 ||
        pmu->base.struct_size < key_api_size || !pmu->key_events) {
        pmu = NULL;
        return NULL;
    }
    return &api;
}

void portable_input_navigation_close(const risc_runtime_api_v1 *runtime) {
    pmu = NULL;
    suppressed = true;
    neutral = false;
    if (grant.api && runtime && runtime->release) {
        if (runtime->release(&grant))
            grant = (risc_runtime_capability_v1){0};
        else if (runtime->diagnostic)
            runtime->diagnostic("PORTABLE_APP error=local-navigation-release");
    }
}

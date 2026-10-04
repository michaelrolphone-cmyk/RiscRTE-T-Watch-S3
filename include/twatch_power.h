#pragma once
#include "RiscDisplayOutputV1.h"
#include "RiscDeepSleepV1.h"
/* Watch-local append-only display extension. Base remains display.output@1.
 * Caller must check base.struct_size >= sizeof(twatch_panel_power_v1).
 * Serialized owner only. prepare refuses held/pending frames; partial failure
 * still requires resume. resume is idempotent; failure retains dependencies. */
typedef struct {
    risc_display_output_api_v1 base;
    bool (*prepare_sleep)(void *context);
    bool (*resume)(void *context);
    /* 0 prepared; negative deep-sleep status on failure. RETAINED forbids
     * resume/normal I/O. Successful preparation holds the inactive backlight
     * through CPU reset. Ordinary refusal is undone by the existing resume. */
    int32_t (*prepare_deep_sleep)(void *context);
} twatch_panel_power_v1;
#define TWATCH_PANEL_LIGHT_SLEEP_SIZE offsetof(twatch_panel_power_v1, prepare_deep_sleep)
#define TWATCH_PANEL_DEEP_SLEEP_SIZE sizeof(twatch_panel_power_v1)

#pragma once
#include "RiscDisplayOutputV1.h"
/* Watch-local append-only display extension. Base remains display.output@1.
 * Caller must check base.struct_size >= sizeof(twatch_panel_power_v1).
 * Serialized owner only. prepare refuses held/pending frames; partial failure
 * still requires resume. resume is idempotent; failure retains dependencies. */
typedef struct {
    risc_display_output_api_v1 base;
    bool (*prepare_sleep)(void *context);
    bool (*resume)(void *context);
} twatch_panel_power_v1;

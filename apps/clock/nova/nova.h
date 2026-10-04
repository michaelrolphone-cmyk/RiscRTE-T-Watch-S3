#pragma once
#include "RiscDisplayOutputV1.h"
#include "twatch_calendar.h"
#ifdef __cplusplus
extern "C" {
#endif
/* RTC fields are already the selected wall time. No timezone, host clock,
 * capability lookup, or synchronization claim is made by this renderer. */
typedef struct {
    twatch_rtc_time_v1 time;
    bool time_valid;
    bool battery_valid;
    uint8_t battery_percent; /* 0 is a valid empty battery; >100 is unknown. */
    uint16_t subsecond_ms;   /* RTC-anchored phase; values >999 clamp to 999. */
    uint32_t animation_ms;   /* Monotonic elapsed animation time, not civil time. */
} nova_watch_state;
typedef struct {
    char hour_minute[6], meridiem[3], seconds[3], date[11], status[6], battery[5];
    bool time_valid, battery_valid;
} nova_watch_labels;
void nova_watch_format(const nova_watch_state *state, nova_watch_labels *labels);
/* Pure, bounded 240x240 little-endian RGB565 output. No allocation, I/O, mutable
 * globals, floating point, trig, framebuffer cache, or runtime SVG/font engine.
 * Writes only active pixels. Stride padding and caller guards are preserved. */
bool nova_watch_render(risc_display_surface_v1 *surface, const nova_watch_state *state);
const char *nova_watch_face_name(unsigned id);
bool nova_watch_face_render(risc_display_surface_v1 *surface, const nova_watch_state *state, unsigned face_id);
unsigned nova_watch_picker_pulse(uint32_t elapsed_ms);
bool nova_watch_picker_render(risc_display_surface_v1 *surface, const nova_watch_state *state,
    unsigned selected, int position_q8, const char *status, unsigned pulse_face, unsigned pulse_scale_q8, uint16_t *scratch);
#ifdef __cplusplus
}
#endif

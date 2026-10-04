#pragma once
#include "RiscDisplayOutputV1.h"
#include "twatch_calendar.h"
#include "../faces/catalog.h"
#include "../faces/points_state.h"
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
    bool hour_24;           /* false is the accepted Settings12-hour policy. */
    const nova_points_state *points; /* NULL is explicitly unavailable. */
} nova_watch_state;
typedef struct {
    char hour_minute[6], meridiem[3], seconds[3], date[11], status[6], battery[5];
    bool time_valid, battery_valid;
} nova_watch_labels;
void nova_watch_format(const nova_watch_state *state, nova_watch_labels *labels);
/* Pure, bounded 240x240 little-endian RGB565 face output. No allocation, I/O,
 * mutable globals, floating point, trig, or runtime SVG/font engine. The picker
 * alone uses its explicit caller-owned cache below.
 * Writes only active pixels. Stride padding and caller guards are preserved. */
bool nova_watch_render(risc_display_surface_v1 *surface, const nova_watch_state *state);
const char *nova_watch_face_name(unsigned id);
bool nova_watch_face_render(risc_display_surface_v1 *surface, const nova_watch_state *state, unsigned face_id);
unsigned nova_watch_picker_pulse(uint32_t elapsed_ms);
/* Caller-owned, picker-lifetime cache. Two translated rows need at most six
 * visible cards; exactly one focused face is live across both collections.
 * Only visible cards occupy these slots;
 * focused pixels are live, neighbors freeze between meaningful data changes. */
typedef struct {
    uint8_t valid_mask,face_ids[6];
    nova_watch_state stamp;
    uint32_t points_revision, points_next_rtc;
    uint8_t points_status, points_phase;
    uint16_t pixels[6][240*240];
} nova_watch_picker_cache;
bool nova_watch_picker_render(risc_display_surface_v1 *surface, const nova_watch_state *state,
    unsigned selected, int position_q8, const watch_face_page *page, const char *status, unsigned pulse_face, unsigned pulse_scale_q8, nova_watch_picker_cache *cache);
bool nova_watch_picker_collections_render(risc_display_surface_v1 *surface, const nova_watch_state *state,
    unsigned selected, int category_position_q8, const int positions_q8[WATCH_FACE_CATEGORY_COUNT],
    const char *status, unsigned pulse_face, unsigned pulse_scale_q8, nova_watch_picker_cache *cache);
/* Optional service-provided label, bounded to 23 characters; NULL preserves
 * the existing ALARM/COUNTDOWN title. No recurrence lookup occurs here. */
bool nova_watch_alarm_label_render(risc_display_surface_v1 *surface,const char *label,
    bool countdown,bool blocked,bool rtc_error,bool dismissing,bool uncertain,bool occurrence);
bool nova_watch_alarm_render(risc_display_surface_v1 *surface,bool countdown,bool blocked,
    bool rtc_error,bool dismissing,bool uncertain,bool occurrence);
#ifdef __cplusplus
}
#endif

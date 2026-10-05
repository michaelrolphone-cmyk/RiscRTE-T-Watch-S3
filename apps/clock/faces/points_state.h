#pragma once
#include <stdbool.h>
#include <stdint.h>
/* Read-only, precomputed rendering projection. The app owns this snapshot and
 * its lifetime. Build it outside the renderer from persisted daily points and
 * the shared recurrence/timezone policy; never put illustrative events here.
 * All *_rtc values use one absolute RTC-second axis (seconds since 2000-01-01), NOT displayed local wall
 * seconds. Display hour/minute/day_offset are supplied after conversion, so a
 * repeated or skipped local hour never changes countdown/progress arithmetic.
 * Durations, including BACK events, are already resolved by the scheduler. */
#define NOVA_POINTS_NEXT_MAX 4u
#define NOVA_POINTS_TODAY_MAX 16u
/* Historical custody builds retain their exact presentation ABI. The current
 * Points lane supports the owner-requested 13-character default label. */
#ifdef WATCH_POINTS_LEGACY_PRESENTATION
#define NOVA_POINT_LABEL_MAX 12u
#else
#define NOVA_POINT_LABEL_MAX 13u
#endif
typedef enum {
    NOVA_POINTS_UNAVAILABLE=0, NOVA_POINTS_READY=1,
    NOVA_POINTS_EMPTY=2, NOVA_POINTS_ERROR=3
} nova_points_status;
typedef enum {
    NOVA_POINT_WORK_START=1, NOVA_POINT_WORK_END=2, NOVA_POINT_LUNCH=3,
    NOVA_POINT_BREAK=4, NOVA_POINT_BEDTIME=5, NOVA_POINT_CUSTOM_1=6,
    NOVA_POINT_CUSTOM_2=7
} nova_point_kind;
typedef enum {
    NOVA_PHASE_UNKNOWN=0, NOVA_PHASE_WORKING=1, NOVA_PHASE_OFF_WORK=2,
    NOVA_PHASE_LUNCH=3, NOVA_PHASE_BREAK=4, NOVA_PHASE_WIND_DOWN=5
} nova_points_phase;
typedef struct {
    uint32_t at_rtc;
    uint8_t hour, minute, kind;
    uint8_t source_slot;    /* Persisted record identity, 0..7. Required to
                            * match an interruption with its own BACK edge. */
    uint8_t color_index;    /* Custom-type palette index, 0..7. Built-ins ignore. */
    bool is_end;            /* Duration end; warning cues are never projected. */
    int16_t day_offset;     /* Local civil days from today; next events >=0. */
    char label[NOVA_POINT_LABEL_MAX+1]; /* Custom label or empty for built-ins. */
} nova_point_event;
typedef struct {
    uint32_t revision;     /* Change on edit/reload, timezone/selection change,
                            * phase/event advance or error/availability change.
                            * Do NOT change merely for each second/frame. */
    uint32_t now_rtc;
    nova_points_status status;
    nova_points_phase phase;
    uint8_t next_count, today_count;
    bool previous_valid, work_valid;
    nova_point_event previous;
    nova_point_event next[NOVA_POINTS_NEXT_MAX]; /* Ordered, next deadline >= now. */
    nova_point_event today[NOVA_POINTS_TODAY_MAX]; /* Actual today, including ends. */
    nova_point_event work_start, work_end; /* A real paired work interval, may
                                          * cross local midnight or a DST jump. */
} nova_points_state;

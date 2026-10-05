#pragma once
#include "PointsRecords.h"

/* The current Points model adds presentation metadata and custom kinds without
 * changing the Clock's storage grant. Historical Wi-Fi/update custody lanes
 * intentionally compile against older reviewed Utilities snapshots. Keep those
 * lanes source-buildable with a zero-metadata compatibility type; only a build
 * whose PointsRecords.h declares POINTS_META_KEY may read/render custom data. */
#ifdef POINTS_META_KEY
#define WATCH_POINTS_EXTENDED 1
#else
#define WATCH_POINTS_EXTENDED 0
#define POINTS_META_KEY "points_meta"
#define POINTS_CUSTOM_COUNT 2u
#define POINTS_CUSTOM_NAME_MAX 12u
#define POINTS_COLOR_COUNT 8u
typedef struct {
    uint8_t color;
    char name[POINTS_CUSTOM_NAME_MAX+1];
} points_custom_type;
typedef struct {
    uint32_t revision;
    points_custom_type custom[POINTS_CUSTOM_COUNT];
} points_meta;
#endif

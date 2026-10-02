#pragma once
#include "RiscProviderV2.h"
#ifdef __cplusplus
extern "C" {
#endif
#define RISC_TOUCH_API_V1 1u
#define RISC_TOUCH_CAPABILITY "input.touch.raw"
#define RISC_TOUCH_MAX_CONTACTS 5u
#define RISC_TOUCH_MAX_SUBSCRIBERS 4u
#define RISC_TOUCH_QUEUE_LENGTH 32u
enum { RISC_TOUCH_EVENT_DOWN = 1u, RISC_TOUCH_EVENT_MOVE = 2u, RISC_TOUCH_EVENT_UP = 3u };
typedef struct { uint8_t id, reserved; uint16_t x, y; } risc_touch_contact_v1;
typedef struct {
    uint64_t sequence, timestamp_ms;
    uint8_t kind, id;
    uint16_t x, y;
} risc_touch_event_v1;
typedef struct {
    uint64_t sequence, timestamp_ms;
    uint16_t width, height;
    uint8_t contact_count, reserved[3];
    uint32_t buttons;
    risc_touch_contact_v1 contacts[RISC_TOUCH_MAX_CONTACTS];
} risc_touch_snapshot_v1;
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    uint64_t (*subscribe)(void *context);
    bool (*unsubscribe)(void *context, uint64_t subscription);
    bool (*poll)(void *context, size_t max_reports);
    int32_t (*next)(void *context, uint64_t subscription, risc_touch_event_v1 *out);
    bool (*snapshot)(void *context, risc_touch_snapshot_v1 *out);
} risc_touch_api_v1;
#ifdef __cplusplus
}
#endif

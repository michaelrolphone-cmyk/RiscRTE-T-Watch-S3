#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define RISC_INPUT_NAVIGATION_API_V1 1u
#define RISC_INPUT_NAVIGATION_CAPABILITY "input.navigation"
#define RISC_INPUT_NAVIGATION_MAX_FOREGROUND 4u
enum {
    RISC_NAV_BACK = 1u << 0, RISC_NAV_CONFIRM = 1u << 1,
    RISC_NAV_LEFT = 1u << 2, RISC_NAV_RIGHT = 1u << 3,
    RISC_NAV_UP = 1u << 4, RISC_NAV_DOWN = 1u << 5,
    RISC_NAV_HOME = 1u << 8
};
typedef struct { const char *capability; uint32_t api_version; } risc_input_foreground_v1;
typedef struct { uint32_t buttons, pressed, released; } risc_input_navigation_frame_v1;
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*poll)(void *context, risc_input_navigation_frame_v1 *out);
    bool (*foreground)(void *context, const risc_input_foreground_v1 *claims, size_t count);
    bool (*reset)(void *context);
} risc_input_navigation_api_v1;
#ifdef __cplusplus
}
#endif

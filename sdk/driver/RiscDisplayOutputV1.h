#pragma once
/* Vendored display.output v1 from RiscRTE-Drivers @ cb0bd49. RGB565 is the
 * T-Watch panel format. MONO1/GRAY consumers are not accepted by this board. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define RISC_DISPLAY_OUTPUT_API_V1 1u
#define RISC_DISPLAY_OUTPUT_CAPABILITY "display.output"
#define RISC_DISPLAY_MAX_DAMAGE_RECTS 8u
typedef uint64_t risc_display_frame_v1;
typedef uint64_t risc_display_present_token_v1;
#define RISC_DISPLAY_FRAME_INVALID 0u
#define RISC_DISPLAY_PRESENT_TOKEN_INVALID 0u
enum {
    RISC_DISPLAY_FORMAT_MONO1 = 1u,
    RISC_DISPLAY_FORMAT_GRAY2 = 2u,
    RISC_DISPLAY_FORMAT_GRAY4 = 3u,
    RISC_DISPLAY_FORMAT_GRAY8 = 4u,
    RISC_DISPLAY_FORMAT_RGB565 = 5u
};
#define RISC_DISPLAY_FORMAT_BIT(format) (1u << ((format) - 1u))
enum {
    RISC_DISPLAY_INFO_PARTIAL_DAMAGE = 1u << 0,
    RISC_DISPLAY_INFO_ASYNC_PRESENT = 1u << 1,
    RISC_DISPLAY_INFO_MAILBOX = 1u << 2,
    RISC_DISPLAY_INFO_RETAINS_IMAGE = 1u << 3,
    RISC_DISPLAY_INFO_CLEAN_PRESENT = 1u << 4,
    RISC_DISPLAY_INFO_BRIGHTNESS = 1u << 5
};
enum {
    RISC_DISPLAY_ROTATION_0 = 1u << 0,
    RISC_DISPLAY_ROTATION_90 = 1u << 1,
    RISC_DISPLAY_ROTATION_180 = 1u << 2,
    RISC_DISPLAY_ROTATION_270 = 1u << 3
};
enum { RISC_DISPLAY_PRESENT_DEFAULT = 0u, RISC_DISPLAY_PRESENT_LOW_LATENCY = 1u };
enum { RISC_DISPLAY_QUEUE_FIFO = 0u, RISC_DISPLAY_QUEUE_MAILBOX = 1u };
enum {
    RISC_DISPLAY_PRESENT_QUEUED = 1u,
    RISC_DISPLAY_PRESENT_ACTIVE = 2u,
    RISC_DISPLAY_PRESENT_COMPLETE = 3u,
    RISC_DISPLAY_PRESENT_FAILED = 5u
};
typedef struct { int32_t x, y; uint32_t width, height; } risc_display_rect_v1;
typedef struct { uint16_t top, right, bottom, left; } risc_display_insets_v1;
typedef struct {
    uint32_t api_version, struct_size, width, height;
    uint32_t physical_width_um, physical_height_um;
    uint32_t supported_formats, preferred_format, supported_rotations, flags;
    risc_display_insets_v1 safe_insets;
    uint16_t damage_x_alignment, damage_y_alignment, damage_width_alignment, damage_height_alignment;
    uint32_t nominal_refresh_millihz, typical_present_latency_us;
} risc_display_info_v1;
typedef struct {
    risc_display_frame_v1 frame;
    void *pixels;
    uint32_t width, height, stride_bytes, size_bytes, pixel_format;
} risc_display_surface_v1;
typedef struct { uint8_t intent, queue_policy; uint16_t reserved; } risc_display_present_options_v1;
typedef struct { uint8_t state; uint8_t reserved[3]; } risc_display_present_status_v1;
typedef struct {
    uint32_t api_version, struct_size;
    void *context;
    bool (*get_info)(void *context, risc_display_info_v1 *out);
    bool (*acquire)(void *context, uint32_t requested_format, risc_display_surface_v1 *out);
    void (*release)(void *context, risc_display_frame_v1 frame);
    bool (*submit)(void *context, risc_display_frame_v1 frame,
                   const risc_display_rect_v1 *damage, size_t damage_count,
                   const risc_display_present_options_v1 *options,
                   risc_display_present_token_v1 *token_out);
    bool (*present_status)(void *context, risc_display_present_token_v1 token,
                           risc_display_present_status_v1 *out);
    bool (*wait_present)(void *context, risc_display_present_token_v1 token,
                         uint32_t timeout_ms, risc_display_present_status_v1 *out);
    bool (*set_brightness)(void *context, uint16_t level, uint16_t maximum);
} risc_display_output_api_v1;
#ifdef __cplusplus
}
#endif

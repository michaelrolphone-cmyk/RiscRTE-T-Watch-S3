#pragma once

/* App-local bounded RGB565 transition. All buffers belong to the caller. No
 * runtime/provider ABI, allocator, floating point, libm or retained callback. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PORTABLE_TRANSITION_DURATION_MS 180u
#define PORTABLE_TRANSITION_MAX_RADIUS 6u
#define PORTABLE_TRANSITION_MAX_SIDE 320u

/* One shared elapsed-time endpoint for opacity and sharpness. */
static inline unsigned portable_transition_alpha(uint32_t elapsed_ms) {
    return elapsed_ms >= PORTABLE_TRANSITION_DURATION_MS ? 256u :
           elapsed_ms * 256u / PORTABLE_TRANSITION_DURATION_MS;
}

static inline uint16_t pt_pack(unsigned r, unsigned g, unsigned b) {
    return (uint16_t)((r << 11) | (g << 5) | b);
}

static inline uint16_t pt_mix(uint16_t old, uint16_t fresh, unsigned alpha) {
    unsigned inverse = 256u - alpha;
    return pt_pack(((old >> 11) * inverse + (fresh >> 11) * alpha + 128u) >> 8,
                   (((old >> 5) & 63u) * inverse +
                    ((fresh >> 5) & 63u) * alpha + 128u) >> 8,
                   ((old & 31u) * inverse + (fresh & 31u) * alpha + 128u) >> 8);
}

static inline unsigned pt_edge(int v, unsigned extent) {
    return v < 0 ? 0u : (unsigned)v >= extent ? extent - 1u : (unsigned)v;
}

static inline void pt_horizontal(const uint16_t *src, uint32_t stride,
                                 uint16_t *scratch, unsigned width,
                                 unsigned height, unsigned radius) {
    unsigned divisor = radius * 2u + 1u;
    for (unsigned y = 0; y < height; y++) {
        const uint16_t *row = (const uint16_t *)((const uint8_t *)src +
                                               (size_t)y * stride);
        unsigned r = 0, g = 0, b = 0;
        for (int k = -(int)radius; k <= (int)radius; k++) {
            uint16_t p = row[pt_edge(k, width)];
            r += p >> 11;
            g += (p >> 5) & 63u;
            b += p & 31u;
        }
        for (unsigned x = 0; x < width; x++) {
            scratch[(size_t)y * width + x] =
                pt_pack((r + divisor / 2u) / divisor,
                        (g + divisor / 2u) / divisor,
                        (b + divisor / 2u) / divisor);
            uint16_t drop = row[pt_edge((int)x - (int)radius, width)];
            uint16_t add = row[pt_edge((int)x + (int)radius + 1, width)];
            r = r - (drop >> 11) + (add >> 11);
            g = g - ((drop >> 5) & 63u) + ((add >> 5) & 63u);
            b = b - (drop & 31u) + (add & 31u);
        }
    }
}

static inline void pt_vertical(uint16_t *dst, uint32_t stride,
                               const uint16_t *scratch, unsigned width,
                               unsigned height, unsigned radius,
                               unsigned alpha, bool mix) {
    unsigned divisor = radius * 2u + 1u;
    for (unsigned x = 0; x < width; x++) {
        unsigned r = 0, g = 0, b = 0;
        for (int k = -(int)radius; k <= (int)radius; k++) {
            uint16_t p = scratch[(size_t)pt_edge(k, height) * width + x];
            r += p >> 11;
            g += (p >> 5) & 63u;
            b += p & 31u;
        }
        for (unsigned y = 0; y < height; y++) {
            uint16_t *pixel = (uint16_t *)((uint8_t *)dst + (size_t)y * stride) + x;
            uint16_t value = pt_pack((r + divisor / 2u) / divisor,
                                     (g + divisor / 2u) / divisor,
                                     (b + divisor / 2u) / divisor);
            *pixel = mix ? pt_mix(value, *pixel, alpha) : value;
            uint16_t drop = scratch[(size_t)pt_edge((int)y - (int)radius, height) *
                                    width + x];
            uint16_t add = scratch[(size_t)pt_edge((int)y + (int)radius + 1,
                                                  height) * width + x];
            r = r - (drop >> 11) + (add >> 11);
            g = g - ((drop >> 5) & 63u) + ((add >> 5) & 63u);
            b = b - (drop & 31u) + (add & 31u);
        }
    }
}

/* Include inter-row padding in each image's conservative byte envelope, but
 * not unused padding after the last row. Check before multiplying on 32-bit
 * targets, where even a bounded height can overflow with a large stride. */
static inline bool pt_image_span(uint32_t stride, size_t row_bytes,
                                 unsigned height, size_t *span) {
    size_t rows = height - 1u;
    if (rows && stride > (SIZE_MAX - row_bytes) / rows) {
        return false;
    }
    *span = rows * (size_t)stride + row_bytes;
    return true;
}

/* Integer address comparisons avoid relational comparisons between unrelated
 * C allocations. Reject unaligned buffers and ranges whose end would wrap. */
static inline bool pt_buffer_range(const void *buffer, size_t bytes,
                                   uintptr_t *begin, uintptr_t *end) {
    *begin = (uintptr_t)buffer;
    if (*begin % sizeof(uint16_t) || bytes > UINTPTR_MAX - *begin) {
        return false;
    }
    *end = *begin + (uintptr_t)bytes;
    return true;
}

static inline bool pt_ranges_overlap(uintptr_t a_begin, uintptr_t a_end,
                                     uintptr_t b_begin, uintptr_t b_end) {
    return a_begin < b_end && b_begin < a_end;
}

/* Render the fresh image into dst before entry. Strides and scratch_bytes are
 * in bytes. Each image must have at least (height - 1) * stride + width * 2
 * accessible bytes; this API cannot verify the caller's allocation sizes.
 * Scratch is packed and requires exactly width * height * 2 usable bytes, at
 * most 204800 bytes. No other frame-sized storage is used.
 *
 * All three buffers must be 2-byte aligned and their used byte envelopes must
 * be disjoint, including image padding between rows. Adjacent disjoint slices
 * of one allocation are supported. Only the required scratch prefix is used.
 *
 * For intermediate phases each channel uses separable, clamped-edge box blur,
 * rounding to RGB565 after EACH pass, followed by rounded alpha/256 mixing.
 * Alpha 0 copies the outgoing visible pixels exactly; alpha 256 leaves dst
 * byte-exact and sharp. Both endpoints leave scratch untouched. Row padding
 * is never modified. Invalid arguments return false without writing anything,
 * including at the endpoints. Internal pt_* helpers require validated inputs.
 */
static inline bool portable_transition_rgb565(uint16_t *dst, uint32_t stride,
                                              const uint16_t *old,
                                              uint32_t old_stride,
                                              uint16_t *scratch,
                                              size_t scratch_bytes,
                                              unsigned width, unsigned height,
                                              unsigned alpha) {
    if (!dst || !old || !scratch || !width || !height ||
        width > PORTABLE_TRANSITION_MAX_SIDE ||
        height > PORTABLE_TRANSITION_MAX_SIDE || alpha > 256u) {
        return false;
    }
    size_t row_bytes = (size_t)width * sizeof(uint16_t);
    size_t required = row_bytes * height;
    if (stride < row_bytes || old_stride < row_bytes ||
        stride % sizeof(uint16_t) || old_stride % sizeof(uint16_t) ||
        scratch_bytes < required) {
        return false;
    }
    size_t dst_span, old_span;
    uintptr_t dst_begin, dst_end, old_begin, old_end, scratch_begin, scratch_end;
    if (!pt_image_span(stride, row_bytes, height, &dst_span) ||
        !pt_image_span(old_stride, row_bytes, height, &old_span) ||
        !pt_buffer_range(dst, dst_span, &dst_begin, &dst_end) ||
        !pt_buffer_range(old, old_span, &old_begin, &old_end) ||
        !pt_buffer_range(scratch, required, &scratch_begin, &scratch_end) ||
        pt_ranges_overlap(dst_begin, dst_end, old_begin, old_end) ||
        pt_ranges_overlap(dst_begin, dst_end, scratch_begin, scratch_end) ||
        pt_ranges_overlap(old_begin, old_end, scratch_begin, scratch_end)) {
        return false;
    }
    if (alpha == 256u) {
        return true;
    }
    if (!alpha) {
        for (unsigned y = 0; y < height; y++) {
            uint16_t *row = (uint16_t *)((uint8_t *)dst + (size_t)y * stride);
            const uint16_t *old_row = (const uint16_t *)((const uint8_t *)old +
                                                       (size_t)y * old_stride);
            for (unsigned x = 0; x < width; x++) {
                row[x] = old_row[x];
            }
        }
        return true;
    }
    /* Keep the incoming image blurred until the very same sharp/opaque
     * endpoint. Rounding down would make it sharp up to 30 ms too early. */
    unsigned incoming = (PORTABLE_TRANSITION_MAX_RADIUS * (256u - alpha) + 255u) / 256u;
    unsigned outgoing = (PORTABLE_TRANSITION_MAX_RADIUS * alpha + 255u) / 256u;
    if (incoming) {
        pt_horizontal(dst, stride, scratch, width, height, incoming);
        pt_vertical(dst, stride, scratch, width, height, incoming, 0, false);
    }
    pt_horizontal(old, old_stride, scratch, width, height, outgoing);
    pt_vertical(dst, stride, scratch, width, height, outgoing, alpha, true);
    return true;
}

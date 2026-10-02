/* ST7789 240x240 SPI panel. Bit-banged; no DMA. Backlight is GPIO45 and is
 * owned here so a second frontlight ELF cannot fight the pad. Display reset
 * is not connected. MADCTL 0x00 is the LilyGO default and may need a board
 * tweak after the first on-device frame. */
#include "RiscDisplayOutputV1.h"
#include "RiscGpioBankV1.h"
#include "RiscPlatformClockV1.h"
#include "twatch_pins.h"
#include "twatch_util.h"
#include <stddef.h>
#define FRAME_BYTES (TWATCH_LCD_W * TWATCH_LCD_H * 2u)
static const risc_gpio_bank_api_v1 *gpio_api;
static const risc_platform_clock_api_v1 *clock_api;
static uint64_t cs, mosi, sck, dc, bl;
static bool started, held, lit;
static uint64_t token = 1;
static uint8_t frame[FRAME_BYTES];
static char error[64];
static void set_error(const char *msg) { twatch_copy_error(error, sizeof error, msg); }
static void sleep_ms(uint32_t ms) {
    if (clock_api && clock_api->sleep_ms) clock_api->sleep_ms(clock_api->context, ms);
}
static bool pin(uint64_t claim, bool level) {
    return gpio_api->write(gpio_api->context, claim, level);
}
static void spi_byte(uint8_t value) {
    for (int i = 7; i >= 0; --i) {
        (void)pin(sck, false);
        (void)pin(mosi, (value >> i) & 1);
        (void)pin(sck, true);
    }
    (void)pin(sck, false);
}
static void cmd(uint8_t c) {
    (void)pin(dc, false);
    (void)pin(cs, false);
    spi_byte(c);
    (void)pin(cs, true);
}
static void data(uint8_t c) {
    (void)pin(dc, true);
    (void)pin(cs, false);
    spi_byte(c);
    (void)pin(cs, true);
}
static void window(uint16_t x, uint16_t y, uint16_t w, uint16_t h) {
    uint16_t x1 = (uint16_t)(x + w - 1u), y1 = (uint16_t)(y + h - 1u);
    cmd(0x2A);
    data(x >> 8); data(x & 0xff); data(x1 >> 8); data(x1 & 0xff);
    cmd(0x2B);
    data(y >> 8); data(y & 0xff); data(y1 >> 8); data(y1 & 0xff);
    cmd(0x2C);
}
static bool panel_init(void) {
    (void)pin(cs, true);
    (void)pin(bl, false);
    cmd(0x01);
    sleep_ms(20);
    cmd(0x11);
    sleep_ms(20);
    cmd(0x3A); data(0x55);
    cmd(0x36); data(0x00);
    cmd(0x21);
    cmd(0x13);
    cmd(0x29);
    lit = true;
    return pin(bl, true);
}
static bool get_info(void *context, risc_display_info_v1 *out) {
    (void)context;
    if (!started || !out) return false;
    *out = (risc_display_info_v1){0};
    out->api_version = RISC_DISPLAY_OUTPUT_API_V1;
    out->struct_size = sizeof *out;
    out->width = TWATCH_LCD_W;
    out->height = TWATCH_LCD_H;
    out->physical_width_um = 27640;
    out->physical_height_um = 27640;
    out->supported_formats = RISC_DISPLAY_FORMAT_BIT(RISC_DISPLAY_FORMAT_RGB565);
    out->preferred_format = RISC_DISPLAY_FORMAT_RGB565;
    out->supported_rotations = RISC_DISPLAY_ROTATION_0;
    out->flags = RISC_DISPLAY_INFO_PARTIAL_DAMAGE | RISC_DISPLAY_INFO_RETAINS_IMAGE |
                 RISC_DISPLAY_INFO_BRIGHTNESS;
    out->damage_x_alignment = out->damage_y_alignment = 1;
    out->damage_width_alignment = out->damage_height_alignment = 1;
    return true;
}
static bool acquire(void *context, uint32_t format, risc_display_surface_v1 *out) {
    (void)context;
    if (!started || held || !out || format != RISC_DISPLAY_FORMAT_RGB565) return false;
    held = true;
    *out = (risc_display_surface_v1){
        1, frame, TWATCH_LCD_W, TWATCH_LCD_H, TWATCH_LCD_W * 2u, FRAME_BYTES, format
    };
    return true;
}
static void release_frame(void *context, risc_display_frame_v1 id) {
    (void)context;
    if (id == 1) held = false;
}
static bool submit(void *context, risc_display_frame_v1 id, const risc_display_rect_v1 *damage,
                   size_t damage_count, const risc_display_present_options_v1 *options,
                   risc_display_present_token_v1 *token_out) {
    (void)context;
    (void)options;
    if (!started || id != 1 || !token_out) return false;
    if (!damage_count) {
        window(0, 0, TWATCH_LCD_W, TWATCH_LCD_H);
        (void)pin(dc, true);
        (void)pin(cs, false);
        for (size_t i = 0; i < FRAME_BYTES; ++i) spi_byte(frame[i]);
        (void)pin(cs, true);
    } else {
        for (size_t r = 0; r < damage_count && r < RISC_DISPLAY_MAX_DAMAGE_RECTS; ++r) {
            if (damage[r].x < 0 || damage[r].y < 0) return false;
            uint16_t x = (uint16_t)damage[r].x, y = (uint16_t)damage[r].y;
            uint16_t w = (uint16_t)damage[r].width, h = (uint16_t)damage[r].height;
            if (!w || !h || x + w > TWATCH_LCD_W || y + h > TWATCH_LCD_H) return false;
            window(x, y, w, h);
            (void)pin(dc, true);
            (void)pin(cs, false);
            for (uint16_t row = 0; row < h; ++row) {
                const uint8_t *src = frame + ((size_t)(y + row) * TWATCH_LCD_W + x) * 2u;
                for (uint16_t col = 0; col < w * 2u; ++col) spi_byte(src[col]);
            }
            (void)pin(cs, true);
        }
    }
    *token_out = token++;
    if (!*token_out) *token_out = token++;
    return true;
}
static bool present_status(void *context, risc_display_present_token_v1 id,
                           risc_display_present_status_v1 *out) {
    (void)context;
    if (!started || !id || !out) return false;
    out->state = RISC_DISPLAY_PRESENT_COMPLETE;
    return true;
}
static bool wait_present(void *context, risc_display_present_token_v1 id, uint32_t timeout,
                         risc_display_present_status_v1 *out) {
    (void)timeout;
    return present_status(context, id, out);
}
static bool set_brightness(void *context, uint16_t level, uint16_t maximum) {
    (void)context;
    if (!started || !maximum || level > maximum) return false;
    lit = level != 0;
    return pin(bl, lit);
}
static bool last_error(char *dst, size_t cap) {
    if (!error[0]) return false;
    twatch_copy_error(dst, cap, error);
    return true;
}
static bool claim_out(uint8_t pin_no, uint64_t *out) {
    return gpio_api->claim(gpio_api->context, pin_no, RISC_GPIO_OUTPUT, out);
}
static bool quiesce(void) {
    bool ok = true;
    uint64_t *all[] = {&cs, &mosi, &sck, &dc, &bl};
    for (size_t i = 0; i < 5; ++i) {
        if (*all[i] && gpio_api && !gpio_api->release(gpio_api->context, *all[i])) ok = false;
        *all[i] = 0;
    }
    gpio_api = NULL;
    clock_api = NULL;
    started = false;
    held = false;
    return ok;
}
static bool start(const risc_provider_dependency_v1 *deps, size_t count) {
    if (started || !deps || count != 2u) return false;
    for (size_t i = 0; i < count; ++i) {
        if (twatch_equal(deps[i].capability_id, RISC_GPIO_BANK_CAPABILITY)) gpio_api = deps[i].api;
        else if (twatch_equal(deps[i].capability_id, RISC_PLATFORM_CLOCK_CAPABILITY)) clock_api = deps[i].api;
    }
    if (!gpio_api || !clock_api) return false;
    if (!claim_out(TWATCH_PIN_LCD_CS, &cs) || !claim_out(TWATCH_PIN_LCD_MOSI, &mosi) ||
        !claim_out(TWATCH_PIN_LCD_SCK, &sck) || !claim_out(TWATCH_PIN_LCD_DC, &dc) ||
        !claim_out(TWATCH_PIN_LCD_BL, &bl) || !panel_init()) {
        set_error("ST7789 claim or init failed");
        (void)quiesce();
        return false;
    }
    started = true;
    return true;
}
static void stop(void) { (void)quiesce(); }
static const risc_display_output_api_v1 api = {
    RISC_DISPLAY_OUTPUT_API_V1, sizeof(api), NULL,
    get_info, acquire, release_frame, submit, present_status, wait_present, set_brightness
};
static const risc_driver_diagnostics_v2 driver = {
    { RISC_PROVIDER_DRIVER_ABI_V2, sizeof(driver), "twatch-panel",
      RISC_DISPLAY_OUTPUT_CAPABILITY, RISC_DISPLAY_OUTPUT_API_V1,
      &api, start, stop, quiesce },
    last_error
};
__attribute__((visibility("default")))
const risc_driver_v2 *t5_driver_get(uint32_t abi) {
    return abi == RISC_PROVIDER_DRIVER_ABI_V2 ? &driver.base : NULL;
}

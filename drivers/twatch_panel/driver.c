#include "twatch_support.h"
#include "twatch_power.h"
#define TWATCH_PANEL_POWER 1
static bool asleep, sleep_prepared, unblank_pending;
static bool deep_held, deep_retained;
static uint16_t brightness_level, brightness_maximum=100;
#include "common/spi.h"
#define WIDTH 240u
#define HEIGHT 240u
#define STRIDE 480u
#define FORMAT RISC_DISPLAY_FORMAT_RGB565
#define DISPLAY_FLAGS (RISC_DISPLAY_INFO_ASYNC_PRESENT | RISC_DISPLAY_INFO_BRIGHTNESS)
#define DISPLAY_ID "twatch-panel"
static const risc_hw_spi_display_v1 *config;
static bool hw_start(const risc_provider_dependency_v1 *d, size_t n) {
    if (spi_claim || !gpio_clean())
        return false;
    config = tw_config(d, n, "sitronix,st7789v3", "display.spi", sizeof(*config));
    if (!config || config->width != 240 || config->height != 240 || !tw_bus_limit(&config->bus, RISC_HW_BUS_SPI, 40000000) ||
        !tw_pin(config->cs) || !tw_pin(config->dc) || !tw_pin(config->backlight) ||
        config->busy != -1 || config->power_count || config->offset_x || config->offset_y ||
        (config->rotation != 0 && config->rotation != 2) || config->reserved[0] || config->reserved[1] || config->reserved[2] ||
        config->reset != -1 || config->backlight_active_high > 1)
        return false;
    int16_t p[] = {config->bus.sclk, config->bus.mosi, config->bus.miso,
                   config->cs,       config->dc,       config->backlight};
    if (!tw_unique(p, 6) || !spi_dependencies(d, n))
        return false;
    if (!gpio_claim(config->backlight, true, !config->backlight_active_high) ||
        !gpio_output(config->dc))
        return false;
    if (!spi->claim(spi->context, config->bus.sclk, config->bus.mosi, config->bus.miso, config->cs,
                    &spi_claim) ||
        !spi_claim)
        return false;
    if (!display_command(config->bus.frequency_hz, config->dc, 0x01, NULL, 0))
        return false;
    timer->sleep_ms(timer->context, 150);
    if (!display_command(config->bus.frequency_hz, config->dc, 0x11, NULL, 0))
        return false;
    timer->sleep_ms(timer->context, 120);
    uint8_t format = 0x55, madctl = config->rotation == 2 ? 0xc0 : 0;
    asleep = sleep_prepared = false; unblank_pending = true; brightness_level = 0; brightness_maximum = 100;
    if (!display_command(config->bus.frequency_hz, config->dc, 0x3a, &format, 1) ||
        !display_command(config->bus.frequency_hz, config->dc, 0x36, &madctl, 1) ||
        !display_command(config->bus.frequency_hz, config->dc, 0x21, NULL, 0) ||
        !display_command(config->bus.frequency_hz, config->dc, 0x13, NULL, 0) || !display_command(config->bus.frequency_hz, config->dc, 0x29, NULL, 0))
        return false;
    return true;
}
static void hw_submit(void) {}
/* Worst-case first row: window commands + 8 address bytes + RGB565 row.
 * Never start a row whose wire time alone exceeds the remaining deadline. */
static uint32_t hw_row_min_budget_ms(void) {
    const uint32_t wire_bits_ms = (3u + 8u + STRIDE) * 8u * 1000u;
    return (wire_bits_ms + config->bus.frequency_hz - 1u) / config->bus.frequency_hz;
}
static bool hw_row(uint32_t y, const uint8_t *pixels) {
    uint8_t wire[STRIDE];
    for (size_t i = 0; i < STRIDE; i += 2) {
        uint16_t v;
        memcpy(&v, pixels + i, 2);
        wire[i] = v >> 8;
        wire[i + 1] = v;
    }
    if (!spi_begin(config->bus.frequency_hz))
        return false;
    bool ok = true;
    if (y == 0) {
        /* The glass occupies 240 rows of 320-row RAM. MX|MY moves the visible
         * range to 80..319; preserve both address bytes across row 255. Every
         * new frame resets the full window and RAM write pointer explicitly. */
        const uint16_t first = config->rotation == 2 ? 80u : 0u;
        const uint16_t last = first + HEIGHT - 1u;
        const uint8_t x[] = {0, 0, 0, WIDTH - 1u};
        const uint8_t rows[] = {(uint8_t)(first >> 8), (uint8_t)first,
                               (uint8_t)(last >> 8), (uint8_t)last};
        const uint8_t cmds[] = {0x2a, 0x2b, 0x2c};
        const uint8_t *data[] = {x, rows};
        for (size_t i = 0; i < 3 && ok; i++) {
            gpio_write(config->dc, false);
            ok = !io_fault && spi->exchange(spi->context, spi_claim, &cmds[i], NULL, 1);
            if (i < 2 && ok) {
                gpio_write(config->dc, true);
                ok = !io_fault && spi->exchange(spi->context, spi_claim, data[i], NULL, 4);
            }
        }
    }
    /* ST7789V3 v0.1 section 8.5 permits byte-aligned frame-data pauses with
     * CS high. The RAM pointer survives each drained/released row transaction.
     * No bus ownership or DMA survives a successful poll. Never retry a partial
     * failed row: the common provider fails the frame and blocks reacquisition. */
    if (ok) {
        gpio_write(config->dc, true);
        ok = !io_fault && spi->exchange(spi->context, spi_claim, wire, NULL, sizeof(wire));
    }
    bool ended = spi_end();
    return ok && ended;
}
static int hw_finish(void) {
    /* Cold activation and wake retain unknown/old panel RAM. Make it visible
     * only after all rows of a new frame have drained successfully. A failed
     * row or PWM operation leaves the provider fail-closed and the gate armed. */
    if (unblank_pending) {
        if (!gpio->pwm(gpio->context, pins[config->backlight], 1000,
                       config->backlight_active_high ? brightness_level : brightness_maximum-brightness_level,
                       brightness_maximum)) return -1;
        unblank_pending=false;
    }
    return 1;
}
static bool hw_brightness(uint16_t v, uint16_t max) {
    if (asleep) return false;
    if (!unblank_pending && !gpio->pwm(gpio->context, pins[config->backlight], 1000,
                     config->backlight_active_high ? v : max - v, max)) return false;
    brightness_level=v; brightness_maximum=max;
    return true;
}
static bool hw_stop(void) {
    if (deep_held || deep_retained) return false;
    io_fault = false;
    if (config && tw_pin(config->backlight) && pins[config->backlight])
        gpio_write(config->backlight, !config->backlight_active_high);
    if (io_fault || !spi_release())
        return false;
    for (uint8_t i = 0; i < 49; i++)
        gpio_release(i);
    return gpio_clean();
}
#include "common/display.h"

/* No rail removal: ALDO3 also powers touch and must stay supplied in sleep. */
static bool panel_prepare_sleep(void *context) {
    (void)context;
    if (!enter()) return false;
    bool ok = running && !held && !active && !failed;
    if (ok && asleep) ok = sleep_prepared;
    else if (ok) {
        closing = true; /* Blocks new frames even if a command fails. */
        asleep = true; /* resume must undo a partially completed sequence. */
        unblank_pending = true;
        ok = gpio->pwm(gpio->context,pins[config->backlight],1000,
                       config->backlight_active_high ? 0 : 100,100) &&
             display_command(config->bus.frequency_hz,config->dc,0x28,NULL,0) &&
             display_command(config->bus.frequency_hz,config->dc,0x10,NULL,0);
        if (ok) {timer->sleep_ms(timer->context,120);sleep_prepared=true;}
    }
    leave(); return ok;
}
static bool panel_resume(void *context) {
    (void)context;
    if (!enter()) return false;
    bool ok = running && !deep_retained;
    if (ok && deep_held) {
        int32_t rc=gpio->deep_sleep_hold(gpio->context,pins[config->backlight],false);
        if (rc==RISC_DEEP_SLEEP_RETAINED) deep_retained=true;
        ok=rc==0;
        if (ok) deep_held=false;
    }
    if (ok && asleep) {
        ok = display_command(config->bus.frequency_hz,config->dc,0x11,NULL,0);
        if (ok) {
            timer->sleep_ms(timer->context,120);
            /* Resume the controller while keeping the backlight off. hw_finish
             * restores the saved brightness after the first complete new frame. */
            ok = gpio->pwm(gpio->context,pins[config->backlight],1000,
                          config->backlight_active_high ? 0 : 100,100) &&
                 display_command(config->bus.frequency_hz,config->dc,0x29,NULL,0);
        }
        if (ok) {asleep=sleep_prepared=false;closing=false;}
    }
    leave(); return ok;
}

/* Deep-only suffix. Keep the accepted light-sleep and rendering path intact.
 * PWM duty zero is still an active PWM resource; stop it with a successful
 * static write before requesting pad retention across deep sleep/reset. */
static int32_t panel_prepare_deep_sleep(void *context) {
    if (deep_retained) return RISC_DEEP_SLEEP_RETAINED;
    if (!gpio || gpio->struct_size<GARDEN_GPIO_DEEP_SLEEP_HOLD_V1_SIZE ||
        !gpio->deep_sleep_hold) return RISC_DEEP_SLEEP_UNSUPPORTED;
    if (deep_held) return 0;
    if (!panel_prepare_sleep(context)) return RISC_DEEP_SLEEP_PLATFORM;
    if (!enter()) return RISC_DEEP_SLEEP_BUSY;
    int32_t rc=RISC_DEEP_SLEEP_PLATFORM;
    if (running && asleep && sleep_prepared && !held && !active && !failed &&
        gpio->write(gpio->context,pins[config->backlight],!config->backlight_active_high)) {
        rc=gpio->deep_sleep_hold(gpio->context,pins[config->backlight],true);
        if (rc==0) deep_held=true;
        else if (rc==RISC_DEEP_SLEEP_RETAINED) deep_retained=true;
    }
    leave();return rc;
}

static int32_t panel_resume_status(void *context) {
    if(deep_retained)return RISC_DEEP_SLEEP_RETAINED;
    if(panel_resume(context))return RISC_LIGHT_SLEEP_OK;
    return deep_retained?RISC_DEEP_SLEEP_RETAINED:RISC_LIGHT_SLEEP_PLATFORM;
}

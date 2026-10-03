#include "twatch_support.h"
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
    if (!config || config->width != 240 || config->height != 240 || !tw_bus(&config->bus, 1) ||
        !tw_pin(config->cs) || !tw_pin(config->dc) || !tw_pin(config->backlight) ||
        config->busy != -1 || config->power_count || config->offset_x || config->offset_y ||
        config->rotation || config->reserved[0] || config->reserved[1] || config->reserved[2] ||
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
    if (!display_command(config->dc, 0x01, NULL, 0))
        return false;
    timer->sleep_ms(timer->context, 150);
    if (!display_command(config->dc, 0x11, NULL, 0))
        return false;
    timer->sleep_ms(timer->context, 120);
    uint8_t format = 0x55, madctl = 0;
    if (!display_command(config->dc, 0x3a, &format, 1) ||
        !display_command(config->dc, 0x36, &madctl, 1) ||
        !display_command(config->dc, 0x21, NULL, 0) ||
        !display_command(config->dc, 0x13, NULL, 0) || !display_command(config->dc, 0x29, NULL, 0))
        return false;
    return true;
}
static void hw_submit(void) {}
static bool hw_row(uint32_t y, const uint8_t *pixels) {
    uint8_t x[] = {0, 0, 0, 239}, row[] = {0, (uint8_t)y, 0, (uint8_t)y}, wire[480];
    for (size_t i = 0; i < 480; i += 2) {
        uint16_t v;
        memcpy(&v, pixels + i, 2);
        wire[i] = v >> 8;
        wire[i + 1] = v;
    }
    if (!spi_begin(config->bus.frequency_hz))
        return false;
    uint8_t cmds[] = {0x2a, 0x2b, 0x2c};
    const uint8_t *data[] = {x, row, wire};
    size_t sizes[] = {4, 4, 480};
    bool ok = true;
    for (size_t i = 0; i < 3 && ok; i++) {
        gpio_write(config->dc, false);
        ok = !io_fault && spi->exchange(spi->context, spi_claim, &cmds[i], NULL, 1);
        if (ok) {
            gpio_write(config->dc, true);
            ok = !io_fault && spi->exchange(spi->context, spi_claim, data[i], NULL, sizes[i]);
        }
    }
    bool ended = spi_end();
    return ok && ended;
}
static int hw_finish(void) {
    return 1;
}
static bool hw_brightness(uint16_t v, uint16_t max) {
    return gpio->pwm(gpio->context, pins[config->backlight], 1000,
                     config->backlight_active_high ? v : max - v, max);
}
static bool hw_stop(void) {
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

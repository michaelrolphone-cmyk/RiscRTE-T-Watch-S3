/* SX1262 / SX1280 LoRa packet engine. No board pins and no implicit RF model. */
#include "twatch_support.h"
#include "twatch_caps.h"
#include "common/spi.h"
static const tw_hw_lora_v1 *config;
static bool started, configured, is1280;
static twatch_lora_config_v2 settings;
static twatch_lora_status_v2 state;
static uint64_t began;
static uint32_t timeout;
static uint8_t received[255];
static bool ready(void) {
    uint64_t begin = timer->monotonic_ms(timer->context);
    for (unsigned i = 0; i < 21; i++) {
        bool v = gpio_read(config->busy);
        if (io_fault)
            return false;
        if (v != (config->busy_active_high != 0))
            return true;
        if (timer->monotonic_ms(timer->context) - begin >= 20)
            return false;
        timer->sleep_ms(timer->context, 1);
    }
    return false;
}
static bool command(uint8_t op, const uint8_t *tx, size_t tn, uint8_t *rx, size_t rn) {
    if (spi_held || !ready() || !spi_begin(config->bus.frequency_hz))
        return false;
    bool ok = spi->exchange(spi->context, spi_claim, &op, NULL, 1);
    if (ok && tn)
        ok = spi->exchange(spi->context, spi_claim, tx, NULL, tn);
    if (ok && rn) {
        uint8_t dummy = 0, status = 0;
        ok = spi->exchange(spi->context, spi_claim, &dummy, &status, 1);
        if (ok)
            ok = spi->exchange(spi->context, spi_claim, NULL, rx, rn);
    }
    bool ended = spi_end();
    return ok && ended && ready();
}
static bool put(uint8_t op, uint8_t value) {
    return command(op, &value, 1, NULL, 0);
}
static bool register_read(uint16_t address, uint8_t *out) {
    uint8_t a[] = {address >> 8, address};
    return command(is1280 ? 0x19 : 0x1d, a, 2, out, 1);
}
static bool register_write(uint16_t address, uint8_t value) {
    uint8_t a[] = {address >> 8, address, value};
    return command(is1280 ? 0x18 : 0x0d, a, 3, NULL, 0);
}
static bool clear_irq(void) {
    uint8_t mask[] = {0xff, 0xff};
    return command(is1280 ? 0x97 : 0x02, mask, 2, NULL, 0);
}
static bool idle(void) {
    return put(0x80, 0) && clear_irq();
}
static bool packet_params(uint8_t length) {
    if (is1280) {
        uint8_t e = 1, m = 1;
        while (e < 15 && (uint32_t)15 * (1u << e) < settings.preamble)
            e++;
        while (m < 15 && (uint32_t)m * (1u << e) < settings.preamble)
            m++;
        uint8_t a[] = {(uint8_t)((e << 4) | m), 0, length, 0x20, 0x40, 0, 0};
        return command(0x8c, a, 7, NULL, 0);
    }
    uint8_t a[] = {settings.preamble >> 8, settings.preamble, 0, length, 1, 0};
    return command(0x8c, a, 6, NULL, 0);
}
static bool configure(void *c, const twatch_lora_config_v2 *v) {
    (void)c;
    if (!started || !v || state.state == TW_LORA_TX || state.state == TW_LORA_RX ||
        v->reserved[0] || v->reserved[1] || v->reserved[2] ||
        v->frequency_hz < config->minimum_hz || v->frequency_hz > config->maximum_hz || v->sf < 5 ||
        v->sf > 12 || v->coding_rate < 5 || v->coding_rate > 8 || v->preamble < 8 ||
        v->preamble > 4096)
        return false;
    uint8_t bw = 0xff;
    if (is1280) {
        if (v->power_dbm < -18 || v->power_dbm > 13)
            return false;
        if (v->bandwidth_hz == 203125)
            bw = 0x34;
        if (v->bandwidth_hz == 406250)
            bw = 0x26;
        if (v->bandwidth_hz == 812500)
            bw = 0x18;
        if (v->bandwidth_hz == 1625000)
            bw = 0x0a;
    } else {
        if (v->power_dbm < -9 || v->power_dbm > 22)
            return false;
        if (v->bandwidth_hz == 125000)
            bw = 4;
        if (v->bandwidth_hz == 250000)
            bw = 5;
        if (v->bandwidth_hz == 500000)
            bw = 6;
    }
    if (bw == 0xff)
        return false;
    configured = false;
    if (!idle())
        return false;
    settings = *v;
    uint8_t modulation[] = {is1280 ? (uint8_t)(v->sf << 4) : v->sf, bw,
                            (uint8_t)(v->coding_rate - 4),
                            (uint8_t)(((1u << v->sf) * 1000u / v->bandwidth_hz) >= 16)};
    uint32_t divisor = is1280 ? 812500u : 15625u, multiplier = is1280 ? 4096u : 16384u;
    uint32_t word = (v->frequency_hz / divisor) * multiplier +
                    ((v->frequency_hz % divisor) * multiplier) / divisor;
    uint8_t frequency[] = {word >> 24, word >> 16, word >> 8, word};
    uint8_t power[] = {is1280 ? (uint8_t)(v->power_dbm + 18) : (uint8_t)v->power_dbm,
                       is1280 ? 0xe0 : 4};
    if (!is1280) {
        uint8_t calibration[2];
        uint32_t f = v->frequency_hz;
        if (f >= 902000000 && f <= 928000000) {
            calibration[0] = 0xe1;
            calibration[1] = 0xe9;
        } else if (f >= 863000000 && f <= 870000000) {
            calibration[0] = 0xd7;
            calibration[1] = 0xdb;
        } else if (f >= 430000000 && f <= 440000000) {
            calibration[0] = 0x6b;
            calibration[1] = 0x6f;
        } else
            return false;
        uint8_t pa[] = {4, 7, 0, 1};
        if (!command(0x98, calibration, 2, NULL, 0) || !command(0x95, pa, 4, NULL, 0))
            return false;
    }
    if (!command(0x86, frequency + (is1280 ? 1 : 0), is1280 ? 3 : 4, NULL, 0) ||
        !command(0x8b, modulation, is1280 ? 3 : 4, NULL, 0) || !command(0x8e, power, 2, NULL, 0) ||
        !packet_params(255))
        return false;
    if (is1280) {
        uint8_t value;
        if (!register_write(0x0925, v->sf <= 6   ? 0x1e
                                    : v->sf <= 8 ? 0x37
                                                 : 0x32) ||
            !register_read(0x093c, &value) || !register_write(0x093c, value | 1))
            return false;
    } else {
        uint8_t value;
        if (!register_read(0x08d8, &value) || !register_write(0x08d8, value | 0x1e) ||
            !register_write(0x0740, 0x14) || !register_write(0x0741, 0x24))
            return false;
        if (!register_read(0x0736, &value) || !register_write(0x0736, value | 4))
            return false;
        if (!register_read(0x0889, &value) ||
            !register_write(0x0889, v->bandwidth_hz == 500000 ? (value & ~4) : (value | 4)))
            return false;
    }
    configured = true;
    state = (twatch_lora_status_v2){.state = TW_LORA_IDLE};
    return true;
}
static bool arm(bool tx, uint32_t ms) {
    if (!ms || ms > 60000 || !configured || state.state == TW_LORA_TX || state.state == TW_LORA_RX)
        return false;
    uint16_t mask = (uint16_t)(is1280 ? 0x4063 : 0x0263);
    uint8_t irq[] = {mask >> 8, mask, mask >> 8, mask, 0, 0, 0, 0};
    if (!clear_irq() || !command(is1280 ? 0x8d : 0x08, irq, 8, NULL, 0))
        return false;
    uint32_t ticks = is1280 ? ms : ms * 64u;
    uint8_t arg[] = {is1280 ? 2 : (uint8_t)(ticks >> 16), (uint8_t)(ticks >> 8), (uint8_t)ticks};
    if (!command(tx ? 0x83 : 0x82, arg, 3, NULL, 0)) {
        state.state = TW_LORA_IO_ERROR;
        configured = false; /* Command may have reached the radio: cancel/reconfigure. */
        return false;
    }
    began = timer->monotonic_ms(timer->context);
    timeout = ms;
    state = (twatch_lora_status_v2){.state = tx ? TW_LORA_TX : TW_LORA_RX};
    return true;
}
static bool send(void *c, const uint8_t *data, size_t n, uint32_t ms) {
    (void)c;
    if (!started || !configured || !data || !n || n > 255 || !ms || ms > 60000 ||
        state.state == TW_LORA_TX || state.state == TW_LORA_RX)
        return false;
    uint8_t buf[256];
    buf[0] = 0;
    memcpy(buf + 1, data, n);
    return idle() && packet_params(n) && command(is1280 ? 0x1a : 0x0e, buf, n + 1, NULL, 0) &&
           arm(true, ms);
}
static bool receive(void *c, uint32_t ms) {
    (void)c;
    if (!started || !configured || !ms || ms > 60000 || state.state == TW_LORA_TX ||
        state.state == TW_LORA_RX)
        return false;
    return idle() && packet_params(255) && arm(false, ms);
}
static bool cancel(void *c) {
    (void)c;
    if (!started || !spi_end())
        return false;
    io_fault = false;
    if (!idle())
        return false;
    state = (twatch_lora_status_v2){.state = TW_LORA_IDLE};
    return true;
}
static bool poll(void *c, twatch_lora_status_v2 *out) {
    (void)c;
    if (!started || !out)
        return false;
    if (state.state == TW_LORA_TX || state.state == TW_LORA_RX) {
        uint8_t flags[2];
        if (!command(is1280 ? 0x15 : 0x12, NULL, 0, flags, 2))
            return false;
        uint16_t irq = ((uint16_t)flags[0] << 8) | flags[1];
        uint8_t next = state.state;
        if (irq & 0x60)
            next = TW_LORA_CRC_ERROR;
        else if (irq & (is1280 ? 0x4000 : 0x0200))
            next = TW_LORA_TIMEOUT;
        else if (state.state == TW_LORA_TX && (irq & 1))
            next = TW_LORA_SENT;
        else if (state.state == TW_LORA_RX && (irq & 2)) {
            uint8_t buf[2], metrics[5];
            if (!command(is1280 ? 0x17 : 0x13, NULL, 0, buf, 2) ||
                !command(is1280 ? 0x1d : 0x14, NULL, 0, metrics, is1280 ? 5 : 3))
                return false;
            if (!buf[0] || !command(is1280 ? 0x1b : 0x1e, &buf[1], 1, received, buf[0]))
                return false;
            state.length = buf[0];
            state.rssi_dbm = -(int16_t)metrics[0] / 2;
            state.snr_quarter_db = (int8_t)metrics[1];
            next = TW_LORA_RECEIVED;
        } else if (timer->monotonic_ms(timer->context) - began >= timeout)
            next = TW_LORA_TIMEOUT;
        if (next != state.state) {
            if (!idle())
                return false;
            state.state = next;
        }
    }
    *out = state;
    return true;
}
static bool read_packet(void *c, uint8_t *out, size_t capacity, size_t *got) {
    (void)c;
    if (got)
        *got = 0;
    if (!started || !out || !got || state.state != TW_LORA_RECEIVED || capacity < state.length)
        return false;
    memcpy(out, received, state.length);
    *got = state.length;
    state.length = 0;
    state.state = TW_LORA_IDLE;
    return true;
}
static bool quiesce(void) {
    if (config && tw_pin(config->reset) && pins[config->reset]) {
        io_fault = false;
        gpio_write(config->reset, config->reset_active_high);
        if (io_fault)
            return false;
    }
    if (!spi_release())
        return false;
    for (uint8_t i = 0; i < 49; i++)
        gpio_release(i);
    if (!gpio_clean())
        return false;
    started = configured = false;
    return true;
}
static bool start(const risc_provider_dependency_v1 *d, size_t n) {
    if (started || spi_claim || !gpio_clean())
        return false;
    config = tw_config(d, n, "semtech,sx1262", "radio.lora", sizeof(*config));
    is1280 = false;
    if (!config) {
        config = tw_config(d, n, "semtech,sx1280", "radio.lora", sizeof(*config));
        is1280 = true;
    }
    if (!config || !tw_bus(&config->bus, 1) || config->bus.miso < 0 ||
        config->minimum_hz > config->maximum_hz || config->tcxo_voltage > 7 ||
        config->reset_active_high > 1 || config->busy_active_high > 1 ||
        config->irq_active_high > 1)
        return false;
    if (is1280 ? (config->minimum_hz < 2400000000u || config->maximum_hz > 2500000000u)
               : (config->minimum_hz < 430000000u || config->maximum_hz > 928000000u))
        return false;
    int16_t p[] = {config->bus.sclk, config->bus.mosi, config->bus.miso, config->cs,
                   config->reset,    config->busy,     config->irq};
    for (size_t i = 0; i < 7; i++)
        if (!tw_pin(p[i]))
            return false;
    if (!tw_unique(p, 7) || !spi_dependencies(d, n))
        return false;
    if (!gpio_claim(config->reset, true, config->reset_active_high) || !gpio_input(config->busy) ||
        !gpio_input(config->irq) ||
        !spi->claim(spi->context, config->bus.sclk, config->bus.mosi, config->bus.miso, config->cs,
                    &spi_claim) ||
        !spi_claim)
        return false;
    timer->sleep_ms(timer->context, 5);
    gpio_write(config->reset, !config->reset_active_high);
    timer->sleep_ms(timer->context, 10);
    if (io_fault || !ready() || !put(0x80, 0) || !put(0x96, 0))
        return false;
    if (!is1280) {
        uint8_t tcxo[] = {config->tcxo_voltage, 0, 1, 0};
        if (!command(0x97, tcxo, 4, NULL, 0) || !put(0x89, 0x7f) || !put(0x9d, 1))
            return false;
    }
    if (!put(0x8a, 1))
        return false;
    uint8_t type = 0;
    if (!command(is1280 ? 0x03 : 0x11, NULL, 0, &type, 1) || type != 1)
        return false;
    uint8_t base[] = {0, 0};
    if (!command(0x8f, base, 2, NULL, 0) || !clear_irq())
        return false;
    state = (twatch_lora_status_v2){0};
    started = true;
    return true;
}
static const twatch_radio_api_v2 api = {2,       sizeof(api), NULL,        configure, send,
                                        receive, poll,        read_packet, cancel};
TW_DRIVER("twatch-lora", "radio.lora", 2, api)

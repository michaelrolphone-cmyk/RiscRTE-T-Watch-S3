#pragma once
#include "twatch_support.h"
#include "twatch_caps.h"
#include "RiscDisplayOutputV1.h"
#include "RiscTouchV1.h"
#include <assert.h>
#include <stdio.h>
static uint64_t m_now, m_serial;
static unsigned m_live, m_claims, m_writes, m_attempts, m_fail_at, m_transfers, m_fail_transfer_at;
static bool m_admit(void) {
    return !m_fail_at || ++m_attempts != m_fail_at;
}
static bool m_fail_io, m_fail_release;
static bool m_tokens[512], m_levels[512];
static uint8_t m_madctl;
static uint8_t m_pin[512], m_regs[256], m_op, m_phase;
static uint16_t m_irq;
static int m_busy = -1;
static size_t m_bytes, m_frames, m_nec_count;
static int16_t m_pcm[512];
static uint16_t m_nec[128];
static uint32_t m_hz;
static uint64_t m_alloc(void) {
    assert(++m_serial < 512);
    m_tokens[m_serial] = true;
    m_live++;
    m_claims++;
    return m_serial;
}
static bool m_free(void *c, uint64_t t) {
    (void)c;
    assert(t && m_tokens[t]);
    if (m_fail_release)
        return false;
    m_tokens[t] = false;
    m_live--;
    return true;
}
static bool m_gclaim(void *c, uint8_t p, bool output, bool initial, bool pull, uint64_t *t) {
    (void)c;
    (void)pull;
    if (m_fail_io || !m_admit())
        return false;
    *t = m_alloc();
    m_pin[*t] = p;
    m_levels[*t] = output ? initial : (p == m_busy ? false : true);
    return true;
}
static bool m_gwrite(void *c, uint64_t t, bool v) {
    (void)c;
    assert(m_tokens[t]);
    if (m_fail_io)
        return false;
    m_levels[t] = v;
    m_writes++;
    return true;
}
static bool m_gread(void *c, uint64_t t, bool *v) {
    (void)c;
    assert(m_tokens[t]);
    if (m_fail_io)
        return false;
    *v = m_levels[t];
    return true;
}
static bool m_pwm(void *c, uint64_t t, uint32_t hz, uint16_t v, uint16_t max) {
    (void)hz;
    return v <= max && m_gwrite(c, t, v != 0);
}
static bool m_wave(void *c, uint64_t t, const uint32_t *p, size_t n) {
    (void)p;
    (void)n;
    return m_gwrite(c, t, false);
}
static uint64_t m_sleep_token;
static int32_t m_light_sleep(void *c,uint64_t t,bool high,risc_light_sleep_result_v1 *out) {
    (void)c; assert(t && m_tokens[t] && !high && out->struct_size==sizeof(*out));
    m_sleep_token=t;out->wake_cause=RISC_LIGHT_SLEEP_WAKE_GPIO;return RISC_LIGHT_SLEEP_OK;
}
static garden_gpio_v1 m_gpio = {1,       sizeof(m_gpio), NULL,   m_gclaim, m_gwrite,
                                m_gread, m_pwm,          m_free, m_wave, m_light_sleep};
static bool m_bank_claim(void *c, uint8_t pin, uint32_t flags, uint64_t *t) {
    return m_gclaim(c, pin, flags & RISC_GPIO_OUTPUT, false, flags & RISC_GPIO_PULLUP, t);
}
static risc_gpio_bank_api_v1 m_bank = {1,        sizeof(m_bank), NULL,  m_bank_claim,
                                       m_gwrite, m_gread,        m_free, m_light_sleep};
static uint64_t m_time(void *c) {
    (void)c;
    return m_now;
}
static void m_sleep(void *c, uint32_t n) {
    (void)c;
    m_now += n;
}
static risc_platform_clock_api_v1 m_clock = {1, sizeof(m_clock), NULL, m_time, m_sleep};
static bool m_iclaim(void *c, uint8_t a, uint64_t *t) {
    (void)c;
    assert(a >= 8 && a <= 0x77);
    if (m_fail_io || !m_admit())
        return false;
    *t = m_alloc();
    return true;
}
static bool m_transfer(void *c, uint64_t t, const uint8_t *tx, size_t tn, uint8_t *rx, size_t rn,
                       uint32_t ms) {
    (void)c;
    assert(t && m_tokens[t] && ms);
    if (m_fail_io || (m_fail_transfer_at && ++m_transfers == m_fail_transfer_at))
        return false;
    uint8_t reg = tn ? tx[0] : 0;
    for (size_t i = 1; i < tn; i++) {
#if TEST_KIND == 4
        if (reg+i-1 >= 0x48 && reg+i-1 <= 0x4a) m_regs[(uint8_t)(reg+i-1)] &= (uint8_t)~tx[i];
        else
#endif
        m_regs[(uint8_t)(reg + i - 1)] = tx[i];
        m_writes++;
    }
    for (size_t i = 0; i < rn; i++)
        rx[i] = m_regs[(uint8_t)(reg + i)];
    return true;
}
static risc_i2c_bus_api_v1 m_bus = {1, sizeof(m_bus), NULL, m_iclaim, m_transfer, m_free};
static bool m_iopen(void *c, uint8_t unit, uint8_t sda, uint8_t scl, uint32_t hz, uint64_t *t) {
    (void)c;
    assert(unit <= 1 && sda != scl && hz <= 400000);
    if (m_fail_io || !m_admit())
        return false;
    *t = m_alloc();
    m_pin[*t] = sda;
    return true;
}
static bool m_itransfer(void *c, uint64_t t, uint8_t a, const uint8_t *tx, size_t tn, uint8_t *rx,
                        size_t rn, uint32_t ms) {
    assert(a >= 8);
    return m_transfer(c, t, tx, tn, rx, rn, ms);
}
static twatch_i2c_controller_v1 m_i2c = {1, sizeof(m_i2c), NULL, m_iopen, m_itransfer, m_free};
static bool m_sclaim(void *c, uint8_t clk, uint8_t mosi, int8_t miso, uint8_t cs, uint64_t *t) {
    (void)c;
    (void)miso;
    assert(clk != mosi && clk != cs && mosi != cs);
    if (m_fail_io || !m_admit())
        return false;
    *t = m_alloc();
    m_pin[*t] = cs;
    return true;
}
static uint32_t m_expected_spi_hz;
static bool m_begin(void *c, uint64_t t, uint32_t hz, uint8_t mode, uint32_t ms) {
    (void)c;
    assert(m_tokens[t] && hz && mode == 0 && ms);
    if (m_expected_spi_hz) assert(hz == m_expected_spi_hz);
    m_phase = 0;
    return !m_fail_io;
}
static bool m_exchange(void *c, uint64_t t, const uint8_t *tx, uint8_t *rx, size_t n) {
    (void)c;
    assert(m_tokens[t] && n <= 512);
    if (m_fail_io)
        return false;
    if (m_phase == 0 && tx) {
        m_op = tx[0];
        m_phase = 1;
        return true;
    }
    if (tx && n==1 && m_op==0x36) m_madctl=*tx;
    if (tx && n == 1 && (*tx == 0x2a || *tx == 0x2b || *tx == 0x2c))
        m_op = *tx;
    if (rx) {
        memset(rx, 0, n);
        if (m_phase >= 2) {
            if (m_op == 0x11 || m_op == 0x03)
                rx[0] = 1;
            if ((m_op == 0x12 || m_op == 0x15) && n == 2) {
                rx[0] = m_irq >> 8;
                rx[1] = m_irq;
            }
            if ((m_op == 0x13 || m_op == 0x17) && n == 2) {
                rx[0] = 3;
                rx[1] = 0;
            }
            if (m_op == 0x1e || m_op == 0x1b)
                for (size_t i = 0; i < n; i++)
                    rx[i] = (uint8_t)(i + 1);
        }
    }
    if (tx && m_op == 0x2c && n == 480) {
        m_bytes += n;
        assert(tx[0] == 0x12 && tx[1] == 0x34);
    }
    m_phase++;
    return true;
}
static bool m_end(void *c, uint64_t t) {
    (void)c;
    assert(m_tokens[t]);
    return !m_fail_release;
}
static bool m_clocks(void *c, uint64_t t, uint32_t hz, uint16_t n) {
    (void)hz;
    (void)n;
    return m_end(c, t);
}
static garden_spi_v1 m_spi = {1,          sizeof(m_spi), NULL,     m_sclaim, m_begin,
                              m_exchange, m_end,         m_clocks, m_free};
static bool m_aopen(void *c, uint8_t unit, bool rx, uint8_t clk, int8_t ws, uint8_t data,
                    uint32_t rate, uint8_t channels, uint64_t *t) {
    (void)c;
    assert(unit <= 1 && clk != data && rate && channels);
    assert(rx ? ws == -1 : ws >= 0);
    if (m_fail_io || !m_admit())
        return false;
    *t = m_alloc();
    m_pin[*t] = clk;
    return true;
}
static bool m_awrite(void *c, uint64_t t, const int16_t *p, size_t n, size_t *done, uint32_t ms) {
    (void)c;
    assert(m_tokens[t] && n <= 256 && ms <= 40);
    *done = 0;
    if (m_fail_io)
        return false;
    memcpy(m_pcm, p, n * 2 * sizeof(int16_t));
    m_frames = n;
    *done = n;
    return true;
}
static bool m_aread(void *c, uint64_t t, int16_t *p, size_t n, size_t *done, uint32_t ms) {
    (void)c;
    assert(m_tokens[t] && n <= 256 && ms <= 40);
    *done = 0;
    if (m_fail_io)
        return false;
    for (size_t i = 0; i < n; i++)
        p[i] = i % 2 ? -1000 : 1000;
    *done = n;
    return true;
}
static twatch_i2s_controller_v1 m_i2s = {1,        sizeof(m_i2s), NULL,  m_aopen,
                                         m_awrite, m_aread,       m_free};
static bool m_carrier_claim(void *c, uint8_t p, uint64_t *t) {
    return m_gclaim(c, p, true, false, false, t);
}
static bool m_carrier_send(void *c, uint64_t t, uint32_t hz, const uint16_t *us, size_t n) {
    (void)c;
    assert(m_tokens[t] && n <= 128);
    if (m_fail_io)
        return false;
    memcpy(m_nec, us, n * 2);
    m_nec_count = n;
    m_hz = hz;
    return true;
}
static bool m_carrier_idle(void *c, uint64_t t) {
    return m_gwrite(c, t, false);
}
static twatch_carrier_v1 m_carrier = {
    1, sizeof(m_carrier), NULL, m_carrier_claim, m_carrier_send, m_carrier_idle, m_free};
static uint8_t m_wifi_state;
static bool m_rclaim(void *c, uint64_t *t) {
    (void)c;
    if (!m_admit())
        return false;
    *t = m_alloc();
    return true;
}
static bool m_join(void *c, uint64_t t, const char *s, const char *p) {
    (void)c;
    (void)s;
    (void)p;
    assert(m_tokens[t]);
    m_wifi_state = 1;
    return !m_fail_io;
}
static bool m_state(void *c, uint64_t t, uint8_t *s, int8_t *r) {
    (void)c;
    assert(m_tokens[t]);
    *s = m_wifi_state;
    *r = -40;
    return !m_fail_io;
}
static bool m_leave(void *c, uint64_t t) {
    (void)c;
    assert(m_tokens[t]);
    m_wifi_state = 0;
    return !m_fail_release;
}
static bool m_ap(void *c, uint64_t t, const char *s, const char *p, const uint8_t *a,
                 const uint8_t *g, const uint8_t *mask) {
    (void)s;
    (void)p;
    (void)a;
    (void)g;
    (void)mask;
    return m_leave(c, t);
}
static bool m_addresses(void *c, uint64_t t, uint8_t *s, uint8_t *a) {
    (void)c;
    assert(m_tokens[t]);
    memset(s, 0, 12);
    memset(a, 0, 12);
    return true;
}
static garden_radio_v1 m_radio = {1,       sizeof(m_radio), NULL, m_rclaim, m_join,     m_state,
                                  m_leave, m_free,          m_ap, m_leave,  m_addresses};
static bool m_hopen(void *c, uint32_t unit, uint64_t *t) {
    assert(!unit);
    return m_rclaim(c, t);
}
static bool m_hsend(void *c, uint64_t t, uint8_t type, const uint8_t *p, size_t n, uint32_t ms) {
    (void)c;
    (void)p;
    assert(m_tokens[t] && type && n && ms == 20);
    return !m_fail_io;
}
static bool m_hreceive(void *c, uint64_t t, uint8_t *type, uint8_t *p, size_t cap, size_t *n,
                       uint32_t ms) {
    (void)c;
    assert(m_tokens[t] && cap == 1028 && !ms);
    if (m_fail_io)
        return false;
    *type = 4;
    p[0] = 0x0e;
    p[1] = 1;
    p[2] = 0;
    *n = 3;
    return true;
}
static twatch_hci_controller_v1 m_hci = {1,       sizeof(m_hci), NULL,  m_hopen,
                                         m_hsend, m_hreceive,    m_free};

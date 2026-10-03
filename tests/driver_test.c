#include "twatch_power.h"
#include "tests/mock.h"
#include "fixture_config.h"
#include DRIVER_SOURCE
static risc_provider_dependency_v1 m_deps[] = {{"hardware.device", 1, &m_device},
                                               {"platform.gpio", 1, &m_gpio},
                                               {"gpio.bank", 1, &m_bank},
                                               {"platform.clock", 1, &m_clock},
                                               {"i2c.bus", 1, &m_bus},
                                               {"platform.i2c.controller", 1, &m_i2c},
                                               {"spi.bus", 1, &m_spi},
                                               {"platform.i2s.controller", 1, &m_i2s},
                                               {"platform.carrier", 1, &m_carrier},
                                               {"platform.radio", 1, &m_radio},
                                               {"platform.hci.controller", 1, &m_hci}};
int main(void) {
    const risc_driver_v2 *d = t5_driver_get(2);
    size_t n = sizeof(m_deps) / sizeof(m_deps[0]);
#if TEST_KIND == 5
    m_panel_dc_pin=m_config.dc;
#endif
    assert(d && d->quiesce && !t5_driver_get(1));
    assert(!d->start(NULL, 0));
    assert(m_live == 0);
    const char *saved = m_device.compatible;
    m_device.compatible = "wrong,chip";
    assert(!d->start(m_deps, n));
    assert(m_live == 0);
    m_device.compatible = saved;
    uint32_t size = m_device.config_size;
    m_device.config_size = 1;
    assert(!d->start(m_deps, n));
    assert(m_live == 0);
    m_device.config_size = size;
    m_device.config_version = 2;
    assert(!d->start(m_deps, n));
    m_device.config_version = 1;
    m_deps[0].api_version = 2;
    assert(!d->start(m_deps, n));
    m_deps[0].api_version = 1;
    risc_provider_dependency_v1 duplicates[12];
    memcpy(duplicates, m_deps, sizeof(m_deps));
    duplicates[11] = m_deps[0];
    assert(!d->start(duplicates, 12));
#if TEST_KIND == 4
    m_regs[3] = 0x4a;
    m_regs[0x34] = 0x0e;
    m_regs[0x35] = 0x74;
#elif TEST_KIND == 7
    m_regs[0] = m_config.chip_id;
#elif TEST_KIND == 9
    m_regs[0] = 0x60;
#elif TEST_KIND == 11
    m_busy = m_config.busy;
#endif
#if TEST_KIND == 5
    /* 10MHz, alternate2MHz and deployment40MHz verify every SPI begin. */
    m_expected_spi_hz = m_config.bus.frequency_hz;
    const uint32_t original_hz = m_config.bus.frequency_hz;
    m_config.bus.frequency_hz = 40000001;
    assert(!d->start(m_deps,n) && !m_live);
    m_config.bus.frequency_hz = 0;
    assert(!d->start(m_deps,n) && !m_live);
    m_config.bus.frequency_hz = original_hz;
    assert(tw_bus_limit(&m_config.bus,RISC_HW_BUS_SPI,40000000));
    if (original_hz>10000000) assert(!tw_bus(&m_config.bus,RISC_HW_BUS_SPI));
    assert(!tw_bus_limit(&m_config.bus,99,40000000));
    int16_t original_pin = m_config.backlight;
    m_config.backlight = -1;
    assert(!d->start(m_deps, n));
    assert(d->quiesce());
    m_config.backlight = original_pin;
#elif TEST_KIND == 11
    int16_t original_pin = m_config.reset;
    m_config.reset = -1;
    assert(!d->start(m_deps, n));
    assert(d->quiesce());
    m_config.reset = original_pin;
#endif
    assert(d->start(m_deps, n));
    assert(!d->start(m_deps, n));
#if TEST_KIND == 1
    const risc_gpio_bank_api_v1 *a = d->capability;
    uint64_t t = 0;
    assert(a->claim(NULL, 6, RISC_GPIO_OUTPUT, &t));
    assert(t);
    assert(a->write(NULL, t, true));
    assert(!d->quiesce());
    assert(!a->release(NULL, 0));
    assert(a->release(NULL, t));
    assert(!a->write(NULL, t, false));
    m_serial+=3; /* Public bank token must differ from raw CPU token. */
    assert(a->claim(NULL,21,RISC_GPIO_INPUT,&t));
    risc_light_sleep_result_v1 sr={sizeof(sr),0};
    assert(a->light_sleep(NULL,t,false,&sr)==RISC_LIGHT_SLEEP_OK);
    assert(m_sleep_token==m_serial && m_sleep_token!=t && sr.wake_cause==RISC_LIGHT_SLEEP_WAKE_GPIO);
    assert(a->light_sleep(NULL,999,false,&sr)==RISC_LIGHT_SLEEP_INVALID);
    assert(a->release(NULL,t));
    assert(a->claim(NULL,6,RISC_GPIO_OUTPUT,&t));
    assert(a->light_sleep(NULL,t,false,&sr)==RISC_LIGHT_SLEEP_INVALID);
    assert(a->release(NULL,t));
#elif TEST_KIND == 2 || TEST_KIND == 3
    const risc_i2c_bus_api_v1 *a = d->capability;
    uint64_t t = 0, u = 0;
    assert(!a->release_device(NULL, 0));
    assert(a->claim_device(NULL, 0x34, &t));
    assert(!a->claim_device(NULL, 0x34, &u) && !u);
    uint8_t tx[] = {4, 0x91}, rx = 0;
    assert(a->transact(NULL, t, tx, 2, NULL, 0, 20));
    assert(a->transact(NULL, t, tx, 1, &rx, 1, 20) && rx == 0x91);
    assert(!a->transact(NULL, t, tx, 1, &rx, 1, 0));
    assert(!d->quiesce());
    assert(a->release_device(NULL, t));
    assert(!a->transact(NULL, t, tx, 1, &rx, 1, 20));
#elif TEST_KIND == 4
    const twatch_pmu_api_v1 *a = d->capability;
    risc_battery_sample_v1 battery;
    m_regs[1] = 0x20;
    assert(a->base.read(NULL, &battery) && battery.millivolts == 3700 &&
           (battery.flags & RISC_BATTERY_CHARGING));
    m_regs[0x49] = 0x0c;
    uint32_t events = 0;
    assert(a->key_events(NULL, &events) && events == 3);
    assert(m_regs[0x62] == 4);
    uint8_t irq0=m_regs[0x40],irq1=m_regs[0x41],irq2=m_regs[0x42];
    for(unsigned cycle=0;cycle<3;cycle++) {
        m_regs[0x49]=0x08;assert(a->key_events(NULL,&events)&&events==2);
        assert(a->prepare_sleep(NULL));
        assert(m_regs[0x40]==0&&m_regs[0x41]==8&&m_regs[0x42]==0);
        risc_light_sleep_result_v1 sr={sizeof(sr),0};
        assert(a->light_sleep(NULL,&sr)==RISC_LIGHT_SLEEP_OK && m_pin[m_sleep_token]==m_config.device.irq);
        assert(a->resume(NULL));assert(a->resume(NULL));
        assert(m_regs[0x40]==irq0&&m_regs[0x41]==irq1&&m_regs[0x42]==irq2);
    }
    m_regs[0x49]=0x02;assert(a->key_events(NULL,&events)&&!events);
    assert(!a->prepare_sleep(NULL)); /* Held key never arms wake. */
    m_regs[0x49]=0x09;assert(a->key_events(NULL,&events)&&events==2);
    m_fail_io=true;assert(!a->prepare_sleep(NULL));m_fail_io=false;
    assert(a->resume(NULL));
#elif TEST_KIND == 5
    assert(m_madctl==(m_config.rotation==2?0xc0:0));
    const risc_display_output_api_v1 *a = d->capability;
    risc_display_surface_v1 surface;
    assert(a->acquire(NULL, 5, &surface));
    const twatch_panel_power_v1 *power_api=d->capability;
    assert(a->struct_size>=sizeof(*power_api));
    assert(!power_api->prepare_sleep(NULL));
    assert(!d->quiesce());
    a->release(NULL, surface.frame);
    assert(d->quiesce());
    assert(d->start(m_deps, n));
    assert(a->acquire(NULL, 5, &surface));
    uint16_t *p = surface.pixels;
    for (size_t i = 0; i < 240 * 240; i++)
        p[i] = 0x1234;
    risc_display_present_token_v1 t;
    assert(!a->submit(NULL, surface.frame, NULL, 1, NULL, &t));
    assert(a->submit(NULL, surface.frame, NULL, 0, NULL, &t));
    assert(!a->acquire(NULL, 5, &surface));
    risc_display_present_status_v1 status;
    assert(!a->present_status(NULL, t + 1, &status));
    const risc_driver_poll_v2 *extended = (const void *)d;
    const unsigned before_zero = m_spi_begins;
    const unsigned before_exchanges = m_panel_exchanges;
    extended->poll(0);
    assert(m_spi_begins == before_zero && m_panel_row_count == 0);
    /* A frozen monotonic mock must still be bounded by the row ceiling. */
    extended->poll(20);
    assert(m_panel_row_count == 32 && !m_spi_active);
    assert(a->present_status(NULL, t, &status) && status.state == RISC_DISPLAY_PRESENT_ACTIVE);
    for (size_t i = 1; i < 8; i++)
        extended->poll(20);
    assert(a->present_status(NULL, t, &status) && status.state == RISC_DISPLAY_PRESENT_COMPLETE);
    assert(m_bytes == 115200);
    /* Decode the actual CASET/RASET/RAMWR stream, including addresses >255. */
    assert(m_panel_row_count == 240);
    const unsigned first_row = m_config.rotation == 2 ? 80 : 0;
    for (unsigned row = 0; row < 320; row++)
        assert(m_panel_rows[row] == (row >= first_row && row < first_row + 240));
    assert(m_panel_first == first_row && m_panel_last == first_row + 239);
    assert(m_panel_row == first_row + 240);
    assert(m_panel_columns==1 && m_panel_windows==1 && m_panel_ramwrites==1);
    assert(!m_spi_active);
    /* One window (five transfers), then exactly 240 data transfers, although
     * CS is released between every pair of rows and between provider polls. */
    assert(m_panel_data_attempts==240 && m_panel_exchanges-before_exchanges==245);
    assert(m_spi_begins==m_spi_ends);

    /* Nonzero bus cost consumes the supplied budget, reducing timeout per row. */
    assert(a->acquire(NULL, 5, &surface));
    assert(a->submit(NULL, surface.frame, NULL, 0, NULL, &t));
    m_panel_row_count = m_spi_begins = 0;
    m_panel_row_cost_ms = 1;
    const uint64_t poll_start = m_now;
    extended->poll(2);
    assert(m_now - poll_start == 1 && m_panel_row_count == 1);
    assert(m_spi_timeouts[0] == 2);
    assert(m_panel_columns==2 && m_panel_windows==2 && m_panel_ramwrites==2);
    assert(m_panel_row==first_row+1 && !m_spi_active);
    /* Never restart with a 1ms budget: the backend truncates deadlines to ms. */
    assert(m_spi_begins == 1);
    for (unsigned i = 1; i < 240; i++) extended->poll(2);
    assert(m_panel_row_count == 240);
    assert(a->present_status(NULL, t, &status) && status.state == RISC_DISPLAY_PRESENT_COMPLETE);
    assert(a->acquire(NULL, 5, &surface));
    assert(a->submit(NULL, surface.frame, NULL, 0, NULL, &t));
    m_panel_row_count = m_spi_begins = 0;
    extended->poll(3);
    assert(m_panel_row_count == 2 && m_spi_timeouts[0] == 3 && m_spi_timeouts[1] == 2);
    for (unsigned i = 1; i < 120; i++) extended->poll(3);
    assert(a->present_status(NULL, t, &status) && status.state == RISC_DISPLAY_PRESENT_COMPLETE);
    m_panel_row_cost_ms = 0;
    /* A failed row stops the batch and never completes or accepts another frame. */
    assert(a->acquire(NULL, 5, &surface));
    assert(a->submit(NULL, surface.frame, NULL, 0, NULL, &t));
    m_panel_row_count = m_spi_begins = 0;
    m_panel_fail_row = 3;
    extended->poll(20);
    assert(m_panel_row_count == 2 && m_spi_begins == 3 && !m_spi_active);
    assert(a->present_status(NULL, t, &status) && status.state == RISC_DISPLAY_PRESENT_FAILED);
    assert(!a->acquire(NULL, 5, &surface));
    extended->poll(20);
    assert(m_panel_row_count == 2 && m_spi_begins == 3 && !m_spi_active);
    m_panel_fail_row = 0;
    assert(d->quiesce());
    assert(d->start(m_deps, n));
    /* A failed CS/end leaves the bus retained, not falsely released. No frame
     * retry occurs; quiescence must retry the failed drain/end before unload. */
    assert(a->acquire(NULL, 5, &surface));
    for (unsigned i=0; i<240*240; i++) ((uint16_t *)surface.pixels)[i]=0x1234;
    assert(a->submit(NULL, surface.frame, NULL, 0, NULL, &t));
    m_panel_row_count=m_spi_begins=0;
    m_fail_release=true;
    extended->poll(20);
    assert(m_panel_row_count==1 && m_spi_begins==1 && m_spi_active);
    assert(a->present_status(NULL,t,&status) && status.state==RISC_DISPLAY_PRESENT_FAILED);
    assert(!a->acquire(NULL,5,&surface) && !d->quiesce() && m_live && m_spi_active);
    extended->poll(20);
    assert(m_panel_row_count==1 && m_spi_begins==1 && m_spi_active);
    m_fail_release=false;
    assert(d->quiesce() && !m_spi_active && !m_live);
    assert(d->start(m_deps,n));
    assert(a->set_brightness(NULL, 1, 2));
    for(unsigned cycle=0;cycle<3;cycle++) {
        assert(power_api->prepare_sleep(NULL));
        assert(m_op==0x10);
        assert(power_api->prepare_sleep(NULL));
        assert(!a->acquire(NULL,5,&surface));
        assert(power_api->resume(NULL));
        assert(m_op==0x29);
        assert(power_api->resume(NULL));
        const unsigned windows_before=m_panel_windows;
        assert(a->acquire(NULL,5,&surface));
        for (unsigned i=0; i<240*240; i++) ((uint16_t *)surface.pixels)[i]=0x1234;
        assert(a->submit(NULL,surface.frame,NULL,0,NULL,&t));
        for(unsigned i=0;i<8;i++) extended->poll(20);
        assert(a->present_status(NULL,t,&status) && status.state==RISC_DISPLAY_PRESENT_COMPLETE);
        assert(m_panel_windows==windows_before+1 && m_panel_row==first_row+240 && !m_spi_active);
    }
    m_fail_io=true;
    assert(!power_api->prepare_sleep(NULL));
    assert(!power_api->prepare_sleep(NULL));
    assert(!power_api->resume(NULL));
    assert(!a->acquire(NULL,5,&surface));
    m_fail_io=false;
    assert(power_api->resume(NULL));
#elif TEST_KIND == 6
    const risc_touch_api_v1 *a = d->capability;
    uint64_t sub = a->subscribe(NULL);
    assert(sub && !a->unsubscribe(NULL, 0));
    m_regs[2] = 1;
    m_regs[3] = 0;
    m_regs[4] = 12;
    m_regs[5] = 0x30;
    m_regs[6] = 24;
    assert(a->poll(NULL, 1));
    risc_touch_event_v1 ev;
    assert(a->next(NULL, sub, &ev) == 1 && ev.id == 3 && ev.x == 12 && ev.kind == 1);
    m_regs[2] = 0;
    assert(a->poll(NULL, 1));
    assert(a->next(NULL, sub, &ev) == 1 && ev.kind == 3);
    assert(!d->quiesce());
    assert(a->unsubscribe(NULL, sub));
    assert(a->next(NULL, sub, &ev) == -1);
#elif TEST_KIND == 7
    const twatch_motion_api_v1 *a = d->capability;
    uint8_t chip;
    assert(a->chip_id(NULL, &chip) && chip == m_config.chip_id);
    m_regs[0x12] = 0;
    m_regs[0x13] = 0x80;
    twatch_accel_sample_v1 xyz;
    assert(a->read(NULL, &xyz) && xyz.x == -32768);
#elif TEST_KIND == 8
    const twatch_rtc_api_v1 *a = d->capability;
    twatch_rtc_time_v1 date = {2024, 2, 29, 4, 23, 59, 58}, out;
    assert(a->write(NULL, &date));
    assert(a->read(NULL, &out) && out.year == 2024 && out.day == 29);
    date.year = 2023;
    assert(!a->write(NULL, &date));
    m_regs[2] = 0x6a;
    assert(!a->read(NULL, &out));
    assert(a->alarm(NULL, 30, 12, 255, 255, true));
    assert(m_regs[9] == 0x30 && m_regs[11] == 0x80);
    m_regs[1] |= 8;
    bool pending;
    assert(a->alarm_pending(NULL, &pending, true) && pending);
#elif TEST_KIND == 9
    const twatch_haptic_api_v1 *a = d->capability;
    assert(a->effect(NULL, 123));
    assert(m_regs[4] == 123 && m_regs[5] == 0 && m_regs[12] == 1);
    assert(!a->effect(NULL, 124));
    assert(a->stop(NULL) && m_regs[12] == 0);
#elif TEST_KIND == 10
    const risc_input_navigation_api_v1 *a = d->capability;
    risc_input_navigation_frame_v1 frame;
    assert(a->poll(NULL, &frame));
    m_now += 40;
    assert(a->poll(NULL, &frame));
    m_levels[key] = false;
    assert(a->poll(NULL, &frame));
    m_now += 40;
    assert(a->poll(NULL, &frame) && frame.pressed == RISC_NAV_BACK);
    assert(a->reset(NULL));
#elif TEST_KIND == 11
    const twatch_radio_api_v2 *a = d->capability;
    twatch_lora_config_v2 v = {.frequency_hz = m_config.minimum_hz,
                               .bandwidth_hz = is1280 ? 812500 : 125000,
                               .preamble = 16,
                               .sf = 7,
                               .coding_rate = 5,
                               .power_dbm = 10};
    assert(a->configure(NULL, &v));
    uint8_t bytes[] = {1, 2, 3};
    assert(a->send(NULL, bytes, 3, 100));
    assert(!a->send(NULL, bytes, 3, 100));
    m_irq = 1;
    twatch_lora_status_v2 status;
    assert(a->poll(NULL, &status) && status.state == TW_LORA_SENT);
    m_irq = 0;
    assert(a->receive(NULL, 100));
    m_irq = 2;
    assert(a->poll(NULL, &status) && status.state == TW_LORA_RECEIVED);
    uint8_t packet[3];
    size_t got;
    assert(a->read(NULL, packet, 3, &got) && got == 3 && !memcmp(packet, bytes, 3));
    m_irq = 0;
    assert(a->receive(NULL, 100));
    m_now += 101;
    assert(a->poll(NULL, &status) && status.state == TW_LORA_TIMEOUT);
#elif TEST_KIND == 12
    const twatch_audio_out_api_v1 *a = d->capability;
    assert(a->open(NULL, 16000, 1));
    assert(!a->open(NULL, 16000, 1));
    assert(a->set_gain(NULL, 1, 2));
    int16_t pcm[] = {1000, -1000};
    assert(a->write(NULL, pcm, 2));
    assert(m_pcm[0] == 500 && m_pcm[1] == 500 && m_pcm[2] == -500 && m_pcm[3] == -500);
    m_fail_io = true;
    assert(!a->write(NULL, pcm, 2));
    m_fail_io = false;
#elif TEST_KIND == 13
    const twatch_audio_in_api_v1 *a = d->capability;
    assert(a->open(NULL, 16000));
    int16_t pcm[8];
    size_t got;
    assert(a->read(NULL, pcm, 8, &got) && got == 8);
    uint16_t level;
    assert(a->level(NULL, &level) && level == 1000);
#elif TEST_KIND == 14
    const twatch_ir_api_v1 *a = d->capability;
    assert(a->send_nec(NULL, 0x12, 0x34));
    assert(m_nec_count == 67 && m_hz == 38000 && m_nec[0] == 9000 && m_nec[1] == 4500 &&
           m_nec[3] == 560 && m_nec[5] == 1690);
    uint16_t bad[] = {65535, 65535, 65535};
    assert(!a->send_raw(NULL, bad, 3, 38000));
#elif TEST_KIND == 15
    const wifi_api_v1 *a = d->capability;
    assert(a->connect(NULL, "network", "password"));
    assert(a->status(NULL) == WIFI_LINK_JOINING);
    m_wifi_state = 2;
    assert(a->status(NULL) == WIFI_LINK_UP && a->rssi(NULL) == -40);
    a->disconnect(NULL);
    assert(a->status(NULL) == WIFI_LINK_DOWN);
#elif TEST_KIND == 16
    const risc_bluetooth_hci_v1 *a = d->capability;
    uint8_t reset[] = {3, 12, 0};
    assert(a->send(NULL, 1, reset, 3));
    assert(!a->send(NULL, 1, reset, 2));
    uint8_t packet[1028], type;
    size_t count;
    assert(a->next(NULL, &type, packet, sizeof(packet), &count) == 1 && type == 4 && count == 3);
#endif
    unsigned live = m_live;
    m_fail_release = true;
    if (live) {
        assert(!d->quiesce());
        assert(m_live > 0);
    }
    m_fail_release = false;
    assert(d->quiesce());
    assert(m_live == 0);
    d->stop();
    assert(d->quiesce());
    assert(d->start(m_deps, n));
    assert(d->quiesce());
    assert(m_live == 0);
    for (unsigned fail = 1; fail <= 4; fail++) {
        m_attempts = 0;
        m_fail_at = fail;
        (void)d->start(m_deps, n);
        m_fail_at = 0;
        m_fail_release = true;
        if (m_live)
            assert(!d->quiesce());
        m_fail_release = false;
        assert(d->quiesce());
        assert(m_live == 0);
    }
#if TEST_KIND == 4 || TEST_KIND == 7 || TEST_KIND == 8 || TEST_KIND == 9
    for (unsigned fail = 1; fail <= 12; fail++) {
        m_transfers = 0;
        m_fail_transfer_at = fail;
        (void)d->start(m_deps, n);
        m_fail_transfer_at = 0;
        assert(d->quiesce());
        assert(m_live == 0);
    }
#endif
    puts(d->driver_id);
    return 0;
}

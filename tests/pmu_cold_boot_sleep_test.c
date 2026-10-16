/* Exercise the production PMU from a real start, without seeding a crown press. */
#include "twatch_power.h"
#include "tests/mock.h"
#include "fixture_config.h"
#include DRIVER_SOURCE

static unsigned transfers, fail_transfer, gpio_reads, fail_gpio_read;
static unsigned guard_waits, edge_wait;
static uint8_t edge_bits;
static bool forced_irq_low, edge_during_clear, edge_during_mask;
static unsigned light_calls, deep_calls;
static const uint8_t saved_masks[3] = {0xa5, 0xc0, 0x5a};

/* Model the datasheet's enabled-event latch and write-one-to-clear status. */
static void key_edge(uint8_t bits) { m_regs[0x49] |= bits & m_regs[0x41]; }
static bool transfer(void *c,uint64_t token,const uint8_t *tx,size_t tn,
                     uint8_t *rx,size_t rn,uint32_t ms) {
    ++transfers;
    if (fail_transfer && transfers == fail_transfer) return false;
    if (tn == 2 && tx[0] == 0x49 && tx[1] == 0xf0 && edge_during_clear) {
        key_edge(2);edge_during_clear=false;
    }
    if (tn == 2 && tx[0] == 0x41 && tx[1] == 8 && edge_during_mask) {
        key_edge(2);edge_during_mask=false;
    }
    return m_transfer(c,token,tx,tn,rx,rn,ms);
}
static bool irq_read(void *c,uint64_t token,bool *high) {
    ++gpio_reads;
    if (fail_gpio_read && gpio_reads == fail_gpio_read) return false;
    if (!m_gread(c,token,high)) return false;
    if (forced_irq_low) *high=false;
    for (unsigned i=0;i<3;++i)
        if (m_regs[0x48+i] & m_regs[0x40+i]) *high=false;
    return true;
}
static void delay(void *c,uint32_t ms) {
    m_sleep(c,ms);
    if (ms == 10 && ++guard_waits == edge_wait) key_edge(edge_bits);
}
static int32_t light(void *c,uint64_t token,bool high,risc_light_sleep_result_v1 *r) {
    ++light_calls;return m_light_sleep(c,token,high,r);
}
static int32_t deep(void *c,uint64_t token,bool high) {
    (void)c;assert(token && m_tokens[token] && !high);++deep_calls;
    return RISC_DEEP_SLEEP_ACTIVE_WAKE;
}
static risc_provider_dependency_v1 deps[] = {
    {"hardware.device",1,&m_device},{"platform.clock",1,&m_clock},
    {"gpio.bank",1,&m_bank},{"i2c.bus",1,&m_bus}
};
static const risc_driver_v2 *driver_api;
static const twatch_pmu_api_v1 *pmu_api;
static void masks_restored(void) {
    assert(m_regs[0x40]==saved_masks[0]);
    assert(m_regs[0x41]==(saved_masks[1]|15));
    assert(m_regs[0x42]==saved_masks[2]);
}
static void begin(uint8_t boot_events) {
    assert(!m_live);
    memset(m_regs,0,sizeof(m_regs));m_regs[3]=0x4a;
    memcpy(m_regs+0x40,saved_masks,3);m_regs[0x49]=boot_events;
    transfers=fail_transfer=gpio_reads=fail_gpio_read=guard_waits=edge_wait=0;
    edge_bits=0;forced_irq_low=edge_during_clear=edge_during_mask=false;
    m_bus.transact=transfer;m_bank.read=irq_read;m_clock.sleep_ms=delay;
    m_bank.light_sleep=light;m_bank.deep_sleep=deep;
    assert(driver_api->start(deps,sizeof(deps)/sizeof(deps[0])));
    assert(key_state==KEY_UNKNOWN);masks_restored();
    transfers=gpio_reads=guard_waits=0;
}
static void end(void) {
    assert(driver_api->quiesce() && !m_live);
    assert(m_regs[0x41]==saved_masks[1]);
}
static void poll(uint32_t expected) {
    uint32_t events=99;assert(pmu_api->key_events(NULL,&events));assert(events==expected);
}
static void prepared(void) {
    uint64_t before=m_now;
    assert(pmu_api->prepare_sleep(NULL));
    assert(m_now-before==50 && guard_waits>=5);
    assert(m_regs[0x40]==0 && m_regs[0x41]==8 && m_regs[0x42]==0);
    risc_light_sleep_result_v1 result={sizeof(result),0};
    assert(pmu_api->light_sleep(NULL,&result)==RISC_LIGHT_SLEEP_OK);
    assert(pmu_api->deep_sleep(NULL)==RISC_DEEP_SLEEP_ACTIVE_WAKE);
    assert(pmu_api->resume(NULL));assert(pmu_api->resume(NULL));masks_restored();
}
static void refused(void) {
    assert(!pmu_api->prepare_sleep(NULL));
    risc_light_sleep_result_v1 result={sizeof(result),0};
    assert(pmu_api->light_sleep(NULL,&result)==RISC_LIGHT_SLEEP_INVALID);
    assert(pmu_api->deep_sleep(NULL)==RISC_DEEP_SLEEP_INVALID);
    assert(pmu_api->resume(NULL));assert(pmu_api->resume(NULL));masks_restored();
}
int main(void) {
    driver_api=t5_driver_get(2);assert(driver_api);pmu_api=driver_api->capability;
    /* Untouched cold boot, repeated timer attempts, teardown and reactivation.
     * No synthetic short/release IRQ is supplied anywhere in this scenario. */
    for(unsigned boot=0;boot<3;++boot) {
        begin(0);
        for(unsigned minute=0;minute<3;++minute) {
            for(unsigned second=0;second<60;++second){poll(0);m_now+=1000;}
            assert(key_state==KEY_UNKNOWN);prepared();assert(key_state==KEY_UNKNOWN);
        }
        end();
    }
    /* A latched startup falling edge or long-only press is held, including a
     * prepare call made without a prior app poll. Clearing its IRQ does not
     * clear the held observation. Non-key IRQ status remains unacknowledged. */
    const uint8_t holds[]={2,4,6};
    for(unsigned h=0;h<sizeof(holds);++h)for(unsigned pre_poll=0;pre_poll<2;++pre_poll) {
        begin(0x90|holds[h]);
        if(pre_poll)poll((holds[h]>>2)&3);
        for(unsigned retry=0;retry<3;++retry){refused();assert(key_state==KEY_HELD);}
        assert(m_regs[0x49]==0x90);
        key_edge(1);prepared();assert(key_state==KEY_RELEASED);end();
    }
    /* A later hold remains blocked across resume. A fresh release read by
     * prepare itself unblocks it, without an extra poll or fabricated event. */
    begin(0);prepared();key_edge(2);poll(0);
    for(unsigned retry=0;retry<3;++retry){refused();assert(key_state==KEY_HELD);}
    key_edge(1);prepared();end();
    /* Every key-event kind during every 10ms quiet interval refuses entry.
     * Edge IRQs must remain enabled throughout that interval to observe this. */
    for(unsigned wait=1;wait<=5;++wait)for(uint8_t bits=1;bits<=8;bits<<=1) {
        begin(0);edge_wait=wait;edge_bits=bits;refused();
        assert(m_regs[0x49]==bits);poll((bits>>2)&3);
        if(bits&6){refused();assert(key_state==KEY_HELD);key_edge(1);}
        prepared();end();
    }
    /* A new falling edge between key observation and non-key status clearing
     * must not be erased. Nor may final short-only masking conceal an edge. */
    begin(0);edge_during_clear=true;refused();assert(m_regs[0x49]&2);
    poll(0);refused();key_edge(1);prepared();end();
    begin(0);edge_during_mask=true;refused();assert(m_regs[0x49]&2);
    poll(0);refused();key_edge(1);prepared();end();
    /* Refused IRQ level and GPIO errors keep unknown unknown and permit a
     * clean retry after the fault, with original masks restored each time. */
    begin(0);forced_irq_low=true;
    for(unsigned i=0;i<3;++i){refused();assert(key_state==KEY_UNKNOWN);}
    forced_irq_low=false;prepared();end();
    for(unsigned failure=1;failure<=6;++failure) {
        begin(0);fail_gpio_read=failure;refused();fail_gpio_read=0;
        prepared();end();
    }
    /* Fail every I2C operation in a complete preparation. This includes the
     * initial status/ACK and snapshot before any mask mutation. */
    begin(0);assert(pmu_api->prepare_sleep(NULL));unsigned count=transfers;
    assert(pmu_api->resume(NULL));end();
    for(unsigned failure=1;failure<=count;++failure) {
        begin(0);fail_transfer=failure;refused();fail_transfer=0;
        assert(key_state==KEY_UNKNOWN);prepared();end();
    }
    /* Incomplete restoration remains retryable and cannot arm sleep. */
    for(unsigned failure=1;failure<=3;++failure) {
        begin(0);forced_irq_low=true;assert(!pmu_api->prepare_sleep(NULL));
        assert(sleep_changed && !sleep_prepared);
        transfers=0;fail_transfer=failure;assert(!pmu_api->resume(NULL));
        assert(!pmu_api->prepare_sleep(NULL));fail_transfer=0;
        assert(pmu_api->resume(NULL));masks_restored();forced_irq_low=false;
        prepared();end();
    }
    /* A completed preparation is no longer armed once restoration starts.
     * A single failed awake-mask write must not admit any native sleep entry,
     * even after the bus fault disappears. Only verified rollback clears it. */
    for(unsigned failure=1;failure<=3;++failure) {
        begin(0);assert(pmu_api->prepare_sleep(NULL));
        const uint8_t charger=m_regs[0x18],current=m_regs[0x62],thermal=m_regs[0x50];
        transfers=0;fail_transfer=failure;assert(!pmu_api->resume(NULL));
        assert(sleep_changed && !sleep_prepared);fail_transfer=0;
        for(unsigned retry=0;retry<3;++retry) {
            unsigned calls=light_calls+deep_calls;
            assert(!pmu_api->prepare_sleep(NULL));
            risc_light_sleep_result_v1 result={sizeof(result),0};
            assert(pmu_api->light_sleep(NULL,&result)==RISC_LIGHT_SLEEP_INVALID);
            assert(pmu_api->light_sleep_for(NULL,1000,&result)==RISC_LIGHT_SLEEP_INVALID);
            assert(pmu_api->light_sleep_set(NULL,1000,&result)==RISC_LIGHT_SLEEP_INVALID);
            assert(pmu_api->deep_sleep(NULL)==RISC_DEEP_SLEEP_INVALID);
            assert(pmu_api->deep_sleep_for(NULL,1000)==RISC_DEEP_SLEEP_INVALID);
            assert(pmu_api->deep_sleep_set(NULL,1000)==RISC_DEEP_SLEEP_INVALID);
            bool pending=false;assert(!pmu_api->sleep_wake_pending(NULL,&pending));
            assert(calls==light_calls+deep_calls);
            assert(m_regs[0x18]==charger && m_regs[0x62]==current && m_regs[0x50]==thermal);
        }
        assert(pmu_api->resume(NULL));masks_restored();
        prepared();assert(m_regs[0x18]==charger && m_regs[0x62]==current && m_regs[0x50]==thermal);
        end();
    }
    assert(light_calls && deep_calls==light_calls);
    puts("PMU cold boot: no-crown autosleep, held startup/later, release, edge races, all preparation I/O faults, repeated refusal/restore PASS");
    return 0;
}

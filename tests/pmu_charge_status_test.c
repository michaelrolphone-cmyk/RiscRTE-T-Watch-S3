/* Actual PMU initialization, transport faults, retry and no-write status. */
#include "twatch_power.h"
#include "tests/mock.h"
#include "fixture_config.h"
#include DRIVER_SOURCE
static unsigned transfers, writes_enable, writes_ts, fail_at, corrupt_reg;
static bool fail_after_apply, fail_cleanup;
static bool transaction(void *c,uint64_t token,const uint8_t *tx,size_t tn,uint8_t *rx,size_t rn,uint32_t ms) {
    ++transfers;
    if (fail_cleanup && charge_enable_pending && transfers>fail_at) return false;
    if (transfers==fail_at && !fail_after_apply) return false;
    if(tn>1) {
        uint8_t r=tx[0];
        assert(r!=0x13 && !(r>=0x50&&r<=0x5d) && r!=0x61 &&
               !(r>=0x63&&r<=0x68) && r!=0xa1 && r!=0xa2);
    }
    if(tn>1 && tx[0]==0x18)writes_enable++;
    if(tn>1 && tx[0]==0x50)writes_ts++;
    bool ok=m_transfer(c,token,tx,tn,rx,rn,ms);
    if(corrupt_reg && tn>1 && tx[0]==corrupt_reg)m_regs[corrupt_reg]^=2;
    if(transfers==fail_at)return false;
    return ok;
}
static risc_provider_dependency_v1 deps[]={
    {"hardware.device",1,&m_device},{"platform.clock",1,&m_clock},
    {"gpio.bank",1,&m_bank},{"i2c.bus",1,&m_bus}
};
static const risc_driver_v2 *d;
static const twatch_pmu_api_v1 *pmu;
static void reset(uint8_t control,uint8_t policy) {
    assert(!m_live);memset(m_regs,0,sizeof(m_regs));m_regs[3]=0x4a;
    m_regs[0x18]=control;m_regs[0x50]=policy;m_regs[0x62]=0xe9;
    m_regs[0x68]=1;m_regs[0x34]=14;m_regs[0x35]=116;m_regs[0xa4]=42;
    transfers=writes_enable=writes_ts=fail_at=corrupt_reg=0;fail_after_apply=fail_cleanup=false;
    m_bus.transact=transaction;
}
static bool begin(void) {return d->start(deps,sizeof(deps)/sizeof(deps[0]));}
int main(void) {
    d=t5_driver_get(2);pmu=d->capability;
    for(unsigned mode=0;mode<32;mode++)for(unsigned enabled=0;enabled<2;enabled++) {
        reset((uint8_t)(0x0d|(enabled?2:0)),(uint8_t)mode);
        assert(begin());assert(m_regs[0x62]==0xe4 && m_regs[0x18]==0x0f && m_regs[0x50]==mode);
        assert(writes_enable==!enabled && !writes_ts && !charge_enable_pending);
        assert(d->quiesce() && !m_live);assert(m_regs[0x18]==0x0f && m_regs[0x62]==0xe4);
        assert(begin());assert(writes_enable==!enabled);assert(d->quiesce());
    }
    reset(0x0d,0x0e);assert(begin());unsigned setup_count=transfers;assert(d->quiesce());
    /* Every startup I2C boundary fails both before and after device mutation.
     * A later clean startup works. A failed enable never remains unowned. */
    for(unsigned after=0;after<2;after++)for(unsigned n=1;n<=setup_count;n++) {
        reset(0x0d,0x0e);fail_at=n;fail_after_apply=after;
        assert(!begin());fail_at=0;assert(d->quiesce() && !m_live);
        assert(!(m_regs[0x18]&2));assert(m_regs[0x50]==0x0e && !writes_ts);
        assert(begin());assert(m_regs[0x18]==0x0f && (m_regs[0x62]&31)==4);
        assert(d->quiesce());
    }
    for(unsigned reg=0x18;reg<=0x62;reg+=0x4a) {
        reset(0x0d,0x0e);corrupt_reg=reg;assert(!begin());corrupt_reg=0;
        assert(d->quiesce() && !m_live);assert(!(m_regs[0x18]&2));
    }
    /* Ambiguous enable write plus failed cleanup retains the token and pending
     * state. Re-entry is blocked until explicit cleanup succeeds. */
    reset(0x0d,0x0e);assert(begin());unsigned enable_at=setup_count-2;assert(d->quiesce());
    reset(0x0d,0x0e);fail_at=enable_at;fail_after_apply=true;fail_cleanup=true;
    assert(!begin());assert(charge_enable_pending && claim && m_live);
    assert(!begin());assert(!d->quiesce());fail_cleanup=false;fail_at=0;
    assert(d->quiesce() && !m_live && !(m_regs[0x18]&2));assert(begin());
    /* Status uses exactly the existing six read-only transactions. Exercise
     * every direction/state and all input/presence/thermal combinations. */
    for(unsigned s0=0;s0<64;s0++)for(unsigned s1=0;s1<128;s1++) {
        m_regs[0]=(uint8_t)s0;m_regs[1]=(uint8_t)s1;
        unsigned before=m_writes;risc_battery_sample_v1 s={0};
        assert(pmu->base.read(NULL,&s));assert(m_writes==before);
        assert(s.flags&PORTABLE_POWER_STATUS_VALID);
        assert(!!(s.flags&PORTABLE_POWER_INPUT_READY)==!!(s0&0x20));
        assert(!!(s.flags&PORTABLE_POWER_BATTERY_PRESENT)==!!(s0&8));
        assert(!!(s.flags&PORTABLE_POWER_THERMAL_LIMIT)==!!(s0&2));
        assert(s.flags&PORTABLE_POWER_CHARGER_ENABLED);
        assert(!!(s.flags&PORTABLE_POWER_CHARGE_DONE)==((s0&0x28)==0x28 && (s1&7)==4));
        assert(!!(s.flags&RISC_BATTERY_CHARGING)==((s1&0x60)==0x20));
    }
    m_regs[0]=0x28;m_regs[1]=0x24;m_regs[0xa4]=100;
    m_regs[0x68]=0;risc_battery_sample_v1 no_detect;
    assert(pmu->base.read(NULL,&no_detect) && !(no_detect.flags&PORTABLE_POWER_STATUS_VALID) && no_detect.percent==255);
    m_regs[0x68]=1;
    for(unsigned n=1;n<=6;n++) {
        risc_battery_sample_v1 s={4200,100,255};transfers=0;fail_at=n;
        assert(!pmu->base.read(NULL,&s));assert(s.millivolts==0 && s.percent==255 && s.flags==2);
        fail_at=0;assert(pmu->base.read(NULL,&s) && s.percent==100);
        char error_text[80];assert(!((const risc_driver_diagnostics_v2*)d)->last_error(error_text,sizeof(error_text)));
    }
    assert(d->quiesce() && !m_live && m_regs[0x18]==0x0f && m_regs[0x50]==0x0e);
    puts("PMU charging: explicit enable/readback, all startup faults, ambiguous-write cleanup retry, 8192 status states, sampling recovery PASS");
}

#include "twatch_power.h"
#include "tests/mock.h"
#include "fixture_config.h"
#include DRIVER_SOURCE
static bool held_output[512], active_pwm[512], outputs[512];
static unsigned hold_calls, unhold_calls, deep_calls, order, hold_at, unhold_at, pwm_at;
static int32_t hold_result, unhold_result, deep_result=RISC_DEEP_SLEEP_ACTIVE_WAKE;
static bool static_failure;
static bool tracked_claim(void *c,uint8_t p,bool output,bool initial,bool pull,uint64_t *t) {
    bool ok=m_gclaim(c,p,output,initial,pull,t);
    if(ok)outputs[*t]=output;
    return ok;
}
static bool tracked_write(void *c,uint64_t t,bool value) {
    if(held_output[t] || (static_failure && m_pin[t]==45))return false;
    if(!m_gwrite(c,t,value))return false;
    active_pwm[t]=false;++order;return true;
}
static bool tracked_pwm(void *c,uint64_t t,uint32_t hz,uint16_t duty,uint16_t max) {
    assert(!held_output[t]);
    if(!m_pwm(c,t,hz,duty,max))return false;
    active_pwm[t]=true;pwm_at=++order;return true;
}
static bool tracked_free(void *c,uint64_t t) {
    if(held_output[t])return false;
    return m_free(c,t);
}
static int32_t tracked_hold(void *c,uint64_t t,bool enable) {
    (void)c;assert(m_tokens[t] && outputs[t] && !active_pwm[t]);
    if(enable) {
        ++hold_calls;hold_at=++order;
        if(!hold_result || hold_result==RISC_DEEP_SLEEP_RETAINED)held_output[t]=true;
        return hold_result;
    }
    ++unhold_calls;unhold_at=++order;
    if(!unhold_result)held_output[t]=false;
    return unhold_result;
}
static int32_t tracked_deep(void *c,uint64_t t,bool high) {
    (void)c;assert(t && m_tokens[t] && !high && !outputs[t]);
    for(unsigned i=0;i<512;++i)assert(!active_pwm[i]);
    m_sleep_token=t;++deep_calls;return deep_result;
}
static unsigned timer_calls,deep_timer_calls;
static int32_t tracked_deep_timed(void *c,uint64_t t,bool high,uint32_t ms) {
 assert(ms==300000);deep_timer_calls++;return tracked_deep(c,t,high);
}
static int32_t tracked_timed(void *c,uint64_t t,bool high,uint32_t ms,risc_light_sleep_result_v1*out) {
    assert(ms==300000);timer_calls++;return m_light_sleep(c,t,high,out);
}
static risc_provider_dependency_v1 dependencies[]={
    {"hardware.device",1,&m_device},{"platform.gpio",1,&m_gpio},
    {"gpio.bank",1,&m_bank},{"platform.clock",1,&m_clock},
    {"i2c.bus",1,&m_bus},{"spi.bus",1,&m_spi}};
int main(int argc,char **argv) {
    const char *mode=argc>1?argv[1]:"normal";
    m_gpio.claim=tracked_claim;m_gpio.write=tracked_write;m_gpio.pwm=tracked_pwm;
    m_gpio.release=tracked_free;m_gpio.deep_sleep=tracked_deep;m_gpio.deep_sleep_hold=tracked_hold;
    m_bank.deep_sleep=tracked_deep;m_bank.light_sleep_for=tracked_timed;m_gpio.light_sleep_for=tracked_timed;
    m_bank.deep_sleep_for=tracked_deep_timed;m_gpio.deep_sleep_for=tracked_deep_timed;
#if TEST_KIND==4
    m_regs[3]=0x4a;
#elif TEST_KIND==5
    m_panel_dc_pin=m_config.dc;m_expected_spi_hz=m_config.bus.frequency_hz;
#endif
    const risc_driver_v2 *d=t5_driver_get(2);
    assert(d && d->start(dependencies,sizeof(dependencies)/sizeof(dependencies[0])));
#if TEST_KIND==1
    const risc_gpio_bank_api_v1 *a=d->capability;
    uint64_t token; m_serial+=4;
    assert(a->claim(NULL,21,RISC_GPIO_INPUT|RISC_GPIO_PULLUP,&token));
    assert(a->deep_sleep(NULL,token,false)==RISC_DEEP_SLEEP_ACTIVE_WAKE);
    assert(m_sleep_token!=token && deep_calls==1);
    risc_light_sleep_result_v1 timed_result={sizeof(timed_result),99};
    for(unsigned n=0;n<3;n++)assert(a->light_sleep_for(NULL,token,false,300000,&timed_result)==0 && m_sleep_token!=token);
    assert(timer_calls==3);
    for(int32_t rc=RISC_DEEP_SLEEP_RETAINED;rc<0;rc++) {
        deep_result=rc;assert(a->deep_sleep_for(NULL,token,false,300000)==rc);
    }
    deep_result=RISC_DEEP_SLEEP_ACTIVE_WAKE;
    assert(a->deep_sleep_for(NULL,token,false,0)==RISC_DEEP_SLEEP_INVALID);
    assert(a->deep_sleep_for(NULL,token,false,86400001)==RISC_DEEP_SLEEP_INVALID);
    m_gpio.struct_size=GARDEN_GPIO_DEEP_SLEEP_FOR_V1_SIZE-1;
    assert(a->deep_sleep_for(NULL,token,false,300000)==RISC_DEEP_SLEEP_UNSUPPORTED);
    m_gpio.struct_size=sizeof(m_gpio);m_gpio.deep_sleep_for=NULL;
    assert(a->deep_sleep_for(NULL,token,false,300000)==RISC_DEEP_SLEEP_UNSUPPORTED);
    m_gpio.deep_sleep_for=tracked_deep_timed;
    assert(a->light_sleep_for(NULL,token,false,0,&timed_result)==RISC_LIGHT_SLEEP_INVALID);
    assert(a->light_sleep_for(NULL,token,false,86400001,&timed_result)==RISC_LIGHT_SLEEP_INVALID);
    m_gpio.struct_size=GARDEN_GPIO_DEEP_SLEEP_HOLD_V1_SIZE;
    assert(a->light_sleep_for(NULL,token,false,300000,&timed_result)==RISC_LIGHT_SLEEP_UNSUPPORTED);
    m_gpio.struct_size=GARDEN_GPIO_LIGHT_SLEEP_FOR_V1_SIZE-1;
    assert(a->light_sleep_for(NULL,token,false,300000,&timed_result)==RISC_LIGHT_SLEEP_UNSUPPORTED);
    m_gpio.struct_size=GARDEN_GPIO_LIGHT_SLEEP_V1_SIZE;
    assert(a->deep_sleep(NULL,token,false)==RISC_DEEP_SLEEP_UNSUPPORTED);
    risc_light_sleep_result_v1 light={sizeof(light),0};
    assert(a->light_sleep(NULL,token,false,&light)==0);
    m_gpio.struct_size=sizeof(m_gpio);
    assert(a->release(NULL,token));
    assert(a->deep_sleep(NULL,token,false)==RISC_DEEP_SLEEP_INVALID);
    assert(a->deep_sleep_for(NULL,token,false,300000)==RISC_DEEP_SLEEP_INVALID);
    assert(a->light_sleep_for(NULL,token,false,300000,&timed_result)==RISC_LIGHT_SLEEP_INVALID);
    assert(a->claim(NULL,6,RISC_GPIO_OUTPUT,&token));
    assert(a->deep_sleep(NULL,token,false)==RISC_DEEP_SLEEP_INVALID);
    assert(a->deep_sleep_for(NULL,token,false,300000)==RISC_DEEP_SLEEP_INVALID);
    assert(a->light_sleep_for(NULL,token,false,300000,&timed_result)==RISC_LIGHT_SLEEP_INVALID);
    assert(a->release(NULL,token));
    assert(a->claim(NULL,6,RISC_GPIO_INPUT|RISC_GPIO_OUTPUT,&token));
    assert(a->deep_sleep(NULL,token,false)==RISC_DEEP_SLEEP_INVALID);
    assert(a->deep_sleep_for(NULL,token,false,300000)==RISC_DEEP_SLEEP_INVALID);
    assert(a->light_sleep_for(NULL,token,false,300000,&timed_result)==RISC_LIGHT_SLEEP_INVALID);
    assert(a->release(NULL,token));
#elif TEST_KIND==4
    const twatch_pmu_api_v1 *a=d->capability;
    assert(a->deep_sleep(NULL)==RISC_DEEP_SLEEP_INVALID);
    assert(a->deep_sleep_for(NULL,300000)==RISC_DEEP_SLEEP_INVALID);
    uint8_t rails_before=m_regs[0x90];
    for(unsigned cycle=0;cycle<3;++cycle) {
        m_regs[0x49]=8;uint32_t events;assert(a->key_events(NULL,&events) && events==2);
        assert(a->prepare_sleep(NULL));
        m_bank.struct_size=RISC_GPIO_BANK_LIGHT_SLEEP_V1_SIZE;
        assert(a->deep_sleep(NULL)==RISC_DEEP_SLEEP_UNSUPPORTED);
        m_bank.struct_size=sizeof(m_bank);
        assert(a->deep_sleep(NULL)==RISC_DEEP_SLEEP_ACTIVE_WAKE);
        assert(a->deep_sleep_for(NULL,0)==RISC_DEEP_SLEEP_INVALID);
        assert(a->deep_sleep_for(NULL,86400001)==RISC_DEEP_SLEEP_INVALID);
        for(int32_t rc=RISC_DEEP_SLEEP_RETAINED;rc<0;rc++) {
            deep_result=rc;assert(a->deep_sleep_for(NULL,300000)==rc);
        }
        deep_result=RISC_DEEP_SLEEP_ACTIVE_WAKE;
        m_bank.struct_size=RISC_GPIO_BANK_DEEP_SLEEP_FOR_V1_SIZE-1;
        assert(a->deep_sleep_for(NULL,300000)==RISC_DEEP_SLEEP_UNSUPPORTED);
        m_bank.struct_size=sizeof(m_bank);m_bank.deep_sleep_for=NULL;
        assert(a->deep_sleep_for(NULL,300000)==RISC_DEEP_SLEEP_UNSUPPORTED);
        m_bank.deep_sleep_for=tracked_deep_timed;
        risc_light_sleep_result_v1 timed_result={sizeof(timed_result),99};
        m_bank.struct_size=RISC_GPIO_BANK_DEEP_SLEEP_V1_SIZE;
        assert(a->light_sleep_for(NULL,300000,&timed_result)==RISC_LIGHT_SLEEP_UNSUPPORTED);
        m_bank.struct_size=sizeof(m_bank);
        assert(a->light_sleep_for(NULL,0,&timed_result)==RISC_LIGHT_SLEEP_INVALID);
        assert(a->light_sleep_for(NULL,300000,&timed_result)==0);
        bool pending=true;
        assert(a->sleep_wake_pending(NULL,&pending)&&!pending);
        for(unsigned bit=1;bit<=8;bit<<=1) {
            m_regs[0x49]=bit;
            assert(a->sleep_wake_pending(NULL,&pending)&&pending&&m_regs[0x49]==bit);
        }
        m_regs[0x49]=0;m_levels[irq_claim]=false;
        assert(a->sleep_wake_pending(NULL,&pending)&&pending);
        m_levels[irq_claim]=true;
        assert(a->resume(NULL));assert(m_regs[0x90]==rails_before);
        assert(a->prepare_sleep(NULL)); /* no synthetic key between retries */
        assert(a->resume(NULL));
        m_regs[0x49]=2;assert(a->key_events(NULL,&events)&&events==0);
        assert(!a->prepare_sleep(NULL)); /* known held still refuses */
        m_regs[0x49]=1;assert(a->key_events(NULL,&events)&&events==0);
        assert(a->prepare_sleep(NULL));assert(a->resume(NULL));
    }
    assert(deep_calls==3+deep_timer_calls);
#elif TEST_KIND==5
    const twatch_panel_power_v1 *a=d->capability;
    /* Missing suffix cleanly refuses without a single sleep command. */
    m_gpio.struct_size=GARDEN_GPIO_LIGHT_SLEEP_V1_SIZE;
    assert(a->prepare_deep_sleep(NULL)==RISC_DEEP_SLEEP_UNSUPPORTED && !asleep);
    m_gpio.struct_size=sizeof(m_gpio);
    risc_display_surface_v1 frame={0};assert(a->base.acquire(NULL,RISC_DISPLAY_FORMAT_RGB565,&frame));
    assert(a->prepare_deep_sleep(NULL)==RISC_DEEP_SLEEP_PLATFORM);
    a->base.release(NULL,frame.frame);display_poll(1);assert(!held);
    if(!strcmp(mode,"retained-hold"))hold_result=RISC_DEEP_SLEEP_RETAINED;
    if(!strcmp(mode,"retained-unhold"))unhold_result=RISC_DEEP_SLEEP_RETAINED;
    if(!strcmp(mode,"hold-error"))hold_result=RISC_DEEP_SLEEP_PLATFORM;
    if(!strcmp(mode,"static-error"))static_failure=true;
    int32_t rc=a->prepare_deep_sleep(NULL);
    if(!strcmp(mode,"retained-hold")) {
        assert(rc==RISC_DEEP_SLEEP_RETAINED && deep_retained);
        assert(a->resume_status(NULL)==RISC_DEEP_SLEEP_RETAINED);
        assert(!a->resume(NULL) && !d->quiesce());
        assert(a->prepare_deep_sleep(NULL)==RISC_DEEP_SLEEP_RETAINED);
        puts("deep panel retained hold blocks I/O and teardown");return 0;
    }
    if(!strcmp(mode,"hold-error") || !strcmp(mode,"static-error")) {
        assert(rc==RISC_DEEP_SLEEP_PLATFORM);
        hold_result=0;static_failure=false;assert(a->resume(NULL));
    } else {
        assert(rc==0 && deep_held && hold_calls==1 && hold_at>pwm_at);
        assert(!d->quiesce());
        assert(a->prepare_deep_sleep(NULL)==0 && hold_calls==1);
        if(!strcmp(mode,"retained-unhold")) {
            assert(a->resume_status(NULL)==RISC_DEEP_SLEEP_RETAINED);
            assert(!a->resume(NULL) && deep_retained && !d->quiesce());
            puts("deep panel retained unhold blocks I/O and teardown");return 0;
        }
        if(!strcmp(mode,"resume-spi-error")) {
            m_fail_io=true;
            assert(a->resume_status(NULL)==RISC_LIGHT_SLEEP_PLATFORM && !deep_held && !deep_retained);
            m_fail_io=false; /* Ordinary restore error can be retried safely. */
        }
        assert(a->resume_status(NULL)==0 && !deep_held && unhold_at>hold_at && pwm_at>unhold_at);
    }
    for(unsigned i=0;i<3;++i) {
        assert(a->prepare_deep_sleep(NULL)==0 && deep_held);
        assert(!m_levels[pins[m_config.backlight]] && !active_pwm[pins[m_config.backlight]]);
        assert(a->resume(NULL));
    }
#endif
    (void)mode;assert(d->quiesce() && !m_live);
    puts("deep production driver: old suffix/refusal/rollback/repeated entry passed");return 0;
}

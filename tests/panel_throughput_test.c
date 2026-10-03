#include "twatch_power.h"
#include "tests/mock.h"
#include "fixture_config.h"
#include "drivers/twatch_panel/driver.c"

static risc_provider_dependency_v1 deps[] = {
    {"hardware.device",1,&m_device}, {"platform.gpio",1,&m_gpio},
    {"platform.clock",1,&m_clock}, {"spi.bus",1,&m_spi}, {"board.battery",1,&m_pmu}
};

static uint64_t frame_time(uint32_t hz, uint32_t quantum, uint32_t scheduler_ms,
                           uint32_t overhead_us, unsigned *polls) {
    const risc_driver_v2 *d=t5_driver_get(2);
    const risc_driver_poll_v2 *polled=(const void *)d;
    m_panel_model=false;
    m_config.bus.frequency_hz=hz;
    m_expected_spi_hz=hz;
    m_panel_dc_pin=m_config.dc;
    assert(d->start(deps,sizeof(deps)/sizeof(deps[0])));
    const risc_display_output_api_v1 *a=d->capability;
    risc_display_surface_v1 s;
    assert(a->acquire(NULL,RISC_DISPLAY_FORMAT_RGB565,&s));
    for(unsigned i=0;i<240*240;i++)((uint16_t *)s.pixels)[i]=0x1234;
    risc_display_present_token_v1 token;
    assert(a->submit(NULL,s.frame,NULL,0,NULL,&token));
    m_panel_model=true;m_panel_model_us=0;m_panel_model_overhead_us=overhead_us;
    const unsigned transfers=m_panel_exchanges;
    *polls=0;
    for(;;) {
        assert(++*polls<=300);
        polled->poll(quantum);
        assert(!m_spi_active); /* No bus held during either scheduler policy. */
        m_panel_model_us+=(uint64_t)scheduler_ms*1000u;
        risc_display_present_status_v1 status;
        assert(a->present_status(NULL,token,&status));
        assert(status.state!=RISC_DISPLAY_PRESENT_FAILED);
        if(status.state==RISC_DISPLAY_PRESENT_COMPLETE)break;
    }
    assert(m_panel_exchanges-transfers==245);
    uint64_t result=m_panel_model_us;
    m_panel_model=false;
    assert(d->quiesce()&&!m_live);
    return result;
}

static void full_rows_only(void) {
 const risc_driver_v2*d=t5_driver_get(2);const risc_driver_poll_v2*p=(const void*)d;
 m_config.bus.frequency_hz=m_expected_spi_hz=40000000;m_panel_dc_pin=m_config.dc;
 assert(d->start(deps,sizeof(deps)/sizeof(deps[0])));
 const risc_display_output_api_v1*a=d->capability;const twatch_panel_power_v1*power=d->capability;
 assert(a->set_brightness(NULL,40,100));
 for(unsigned cycle=0;cycle<3;cycle++) {
  risc_display_surface_v1 s;risc_display_present_token_v1 t;risc_display_present_status_v1 status;
  assert(a->acquire(NULL,5,&s));for(unsigned i=0;i<240*240;i++)((uint16_t*)s.pixels)[i]=0x1234;
  const risc_display_rect_v1 damage={0,100,240,10};unsigned rows=m_panel_row_count;
  assert(a->submit(NULL,s.frame,&damage,1,NULL,&t));
  for(unsigned i=0;i<8;i++)p->poll(20);
  assert(a->present_status(NULL,t,&status)&&status.state==RISC_DISPLAY_PRESENT_COMPLETE);
  assert(m_panel_row_count-rows==240u);
  if(cycle==1){assert(m_panel_first==80&&m_panel_last==319);assert(power->prepare_sleep(NULL)&&power->resume(NULL));}
 }
 assert(d->quiesce());puts("Full 240-row transfer for every damage hint, including wake, passed");
}
int main(void) {
    /* Real panel/provider code, modeled wire cost and explicit per-exchange
     * overhead. Old policy:10MHz,2ms quantum,two2tick waits. New:40MHz,8ms,
     * one1tick wait. Runtime tests independently enforce its scheduling policy.
     * A full extra tick is conservatively charged per wait. These are regression
     * scenarios, not physical-watch frame-rate measurements. */
    const unsigned overheads[]={0,100,250};
    for(unsigned i=0;i<sizeof(overheads)/sizeof(overheads[0]);i++) {
        unsigned old_polls,new_polls;
        uint64_t before=frame_time(10000000,2,4,overheads[i],&old_polls);
        uint64_t after=frame_time(40000000,8,1,overheads[i],&new_polls);
        assert(new_polls<=16 && after<=120000 && after*3<before);
        printf("Panel transport model overhead=%uus: %llu us/%u polls -> %llu us/%u polls\n",
               overheads[i],(unsigned long long)before,old_polls,
               (unsigned long long)after,new_polls);
    }
    full_rows_only();
    return 0;
}

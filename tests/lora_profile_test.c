#include "twatch_power.h"
#define TEST_KIND 11
#include "tests/mock.h"
#include "drivers/twatch_lora/driver.c"
static tw_hw_lora_v2 fixture={.base={.struct_size=sizeof(fixture),.bus={.struct_size=sizeof(risc_hw_bus_v1),.kind=RISC_HW_BUS_SPI,.instance_id=10,.controller=1,.frequency_hz=2000000,.sclk=3,.mosi=1,.miso=4,.sda=-1,.scl=-1},.cs=5,.reset=8,.busy=7,.irq=9,.minimum_hz=430000000,.maximum_hz=2500000000u,.tcxo_voltage=0,.busy_active_high=1,.irq_active_high=1},.allowed_profiles=15};
static risc_hardware_device_v1 device={1,sizeof(device),11,"semtech,sx1262-sx1280-selectable","unspecified","radio.lora",2,sizeof(fixture),&fixture};
static risc_provider_dependency_v1 deps[]={{"hardware.device",1,&device},{"platform.gpio",1,&m_gpio},{"platform.clock",1,&m_clock},{"spi.bus",1,&m_spi}};
static twatch_lora_config_v2 settings_for(unsigned choice){
 const uint32_t hz[]={0,433000000,868000000,915000000,2440000000u};
 return (twatch_lora_config_v2){.frequency_hz=hz[choice],.bandwidth_hz=choice==4?812500:125000,.preamble=16,.sf=7,.coding_rate=5,.power_dbm=10};
}
static unsigned exchanges, fail_exchange;
static bool exchange_fault(void*c,uint64_t token,const uint8_t*tx,uint8_t*rx,size_t n){
 if(fail_exchange && ++exchanges==fail_exchange)return false;
 return m_exchange(c,token,tx,rx,n);
}
int main(void){
 const risc_driver_v2*d=t5_driver_get(2);const twatch_radio_api_v2*a=d->capability;m_busy=fixture.base.busy;
 for(unsigned mask=0;mask<=16;++mask){fixture.allowed_profiles=mask;assert(d->start(deps,4)==(mask>0 && mask<16));assert(!m_live && !m_claims && !m_writes && !m_now);assert(d->quiesce());}
 fixture.allowed_profiles=15;device.config_size=sizeof(tw_hw_lora_v1);assert(!d->start(deps,4));device.config_size=sizeof(fixture);
 fixture.base.struct_size=sizeof(tw_hw_lora_v1);assert(!d->start(deps,4));fixture.base.struct_size=sizeof(fixture);
 device.config_version=1;assert(!d->start(deps,4));device.config_version=2;
 assert(d->start(deps,4));twatch_lora_profile_info_v1 info={sizeof(info),0,0,0};assert(a->profile_info(NULL,&info) && info.supported_profiles==15 && !info.selected_profile && !info.reserved);
 info.struct_size=sizeof(info)-1;assert(!a->profile_info(NULL,&info));info.struct_size=sizeof(info);
 twatch_lora_config_v2 v=settings_for(1);assert(!a->configure(NULL,&v));assert(!a->select_profile(NULL,5));assert(!m_live && !m_claims && !m_writes && !m_now);
 for(unsigned choice=1;choice<=4;++choice){
  unsigned claims=m_claims,writes=m_writes;uint64_t before=m_now;assert(a->select_profile(NULL,choice));assert(!m_live && m_claims==claims && m_writes==writes && m_now==before);
  assert(a->profile_info(NULL,&info) && info.selected_profile==choice);
  v=settings_for(choice);twatch_lora_config_v2 wrong=v;wrong.frequency_hz=1;assert(!a->configure(NULL,&wrong) && !m_live && m_claims==claims);
  assert(a->configure(NULL,&v) && m_live==4);assert(a->receive(NULL,100));
  if(choice==1){
   m_fail_release=true;assert(!a->select_profile(NULL,4));assert(a->profile_info(NULL,&info) && info.selected_profile==1 && m_live==4);
   writes=m_writes;assert(!a->configure(NULL,&v) && m_writes==writes);assert(!d->quiesce());m_fail_release=false;
  }
  assert(a->cancel(NULL) && !m_live);assert(a->profile_info(NULL,&info) && info.selected_profile==choice);
 }
 assert(a->select_profile(NULL,0));assert(a->profile_info(NULL,&info) && !info.selected_profile);assert(!a->configure(NULL,&v));assert(d->quiesce());
 for(unsigned fault=1;fault<=4;++fault){
  assert(d->start(deps,4));assert(a->select_profile(NULL,3));v=settings_for(3);m_attempts=0;m_fail_at=fault;
  assert(!a->configure(NULL,&v));m_fail_at=0;assert(a->cancel(NULL) && !m_live);assert(a->configure(NULL,&v));assert(d->quiesce() && !m_live);
 }
 assert(d->start(deps,4));assert(a->select_profile(NULL,2));v=settings_for(2);m_fail_io=true;assert(!a->configure(NULL,&v));m_fail_io=false;assert(a->cancel(NULL) && !m_live);assert(a->configure(NULL,&v));assert(d->quiesce());
 m_spi.exchange=exchange_fault;
 for(unsigned choice=3;choice<=4;++choice)for(unsigned fault=1;fault<=6;++fault){
  assert(d->start(deps,4));assert(a->select_profile(NULL,choice));v=settings_for(choice);exchanges=0;fail_exchange=fault;
  assert(!a->configure(NULL,&v));fail_exchange=0;assert(a->cancel(NULL) && !m_live);assert(a->configure(NULL,&v));assert(d->quiesce());
 }
 fixture.allowed_profiles=1;assert(d->start(deps,4));assert(!a->select_profile(NULL,2));assert(a->select_profile(NULL,1));assert(d->quiesce());
 puts("Selectable LoRa: inert admission/selection, four profiles, exact ABI/mask/band bounds, failed-switch retention and initialization cleanup retry PASS");
}

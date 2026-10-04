#include "tests/mock.h"
#include "fixture_config.h"
#include DRIVER_SOURCE
static risc_provider_dependency_v1 deps[]={
 {"hardware.device",1,&m_device},{"i2c.bus",1,&m_bus},{"gpio.bank",1,&m_bank},
 {"platform.i2s.controller",1,&m_i2s}};
#if TEST_KIND == 12
static bool partial_open(void*c,uint8_t unit,bool rx,uint8_t clk,int8_t ws,uint8_t data,uint32_t rate,uint8_t channels,uint64_t*t){
 assert(m_aopen(c,unit,rx,clk,ws,data,rate,channels,t));return false;
}
static unsigned raw_writes;
static bool partial_write(void*c,uint64_t t,const int16_t*p,size_t n,size_t*done,uint32_t ms){
 (void)c;(void)p;assert(m_tokens[t] && n==256 && ms==40);++raw_writes;*done=32;return true;
}
#endif
int main(void){
 const risc_driver_v2*d=t5_driver_get(2);const size_t n=sizeof(deps)/sizeof(deps[0]);
#if TEST_KIND == 12
 const twatch_audio_out_api_v1*a=d->capability;
 assert(d->start(deps,n));assert(a->close(NULL));
 m_i2s.open=partial_open;assert(!a->open(NULL,8000,1) && stream && m_live==1);
 int16_t pcm[256]={1};assert(!a->write(NULL,pcm,256));
 m_fail_release=true;assert(!a->close(NULL) && stream);assert(!a->write(NULL,pcm,256));assert(!d->quiesce());
 m_fail_release=false;assert(a->close(NULL) && !stream && !m_live);
 m_i2s.open=m_aopen;assert(a->open(NULL,8000,1));
 m_i2s.write=partial_write;assert(!a->write(NULL,pcm,256) && raw_writes==1);
 assert(!a->write(NULL,pcm,256) && raw_writes==1); // Never replay partial PCM.
 m_i2s.write=m_awrite;m_fail_io=true;assert(!a->silence(NULL));
 assert(a->close(NULL) && !stream && !m_live); // close does not depend on silence.
 m_fail_io=false;assert(a->open(NULL,8000,1));assert(a->write(NULL,pcm,256));
 assert(m_pcm[0]==1 && m_pcm[1]==1 && m_frames==256);assert(d->quiesce() && !m_live);
 puts("MAX98357A: failed-open token, partial-write no replay, silence-independent close and retries PASS");
#else
 const twatch_haptic_api_v1*a=d->capability;
 m_regs[0]=0x60;m_regs[12]=1;assert(d->start(deps,n));assert(m_regs[12]==0); // Fresh boot must stop inherited GO.
 assert(a->effect(NULL,47) && m_regs[12]==1);m_fail_io=true;
 assert(!a->stop(NULL) && !d->quiesce() && claim && m_live);m_fail_io=false;
 assert(a->stop(NULL) && m_regs[12]==0 && d->quiesce() && !m_live);
 // Failure of every startup write still attempts GO=0 and preserves claims
 // when that cleanup itself cannot prove idle.
 for(unsigned fail=2;fail<=5;++fail){
  m_transfers=0;m_fail_transfer_at=fail;m_regs[12]=1;
  assert(!d->start(deps,n));assert(m_regs[12]==0 && !m_live);m_fail_transfer_at=0;
 }
 m_regs[12]=1;m_fail_io=false;assert(d->start(deps,n));
 for(unsigned fail=1;fail<=6;++fail){
  m_transfers=0;m_fail_transfer_at=fail;assert(!a->effect(NULL,47));m_fail_transfer_at=0;
  assert(a->stop(NULL) && m_regs[12]==0);
 }
 assert(d->quiesce() && !m_live);
 m_regs[0]=0;unsigned before=m_writes;assert(!d->start(deps,n) && m_writes==before && !m_live);
 puts("DRV2605: fresh GO clear, bounded partial-start/effect rollback, retained failed-stop, no unidentified writes PASS");
#endif
}

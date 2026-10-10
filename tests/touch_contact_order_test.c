/* Actual candidate provider, original transport mocks and unchanged reducer. */
#include "twatch_support.h"
#include "tests/mock.h"
#include "fixture_config.h"
#include DRIVER_SOURCE
#include "PortableTouch.h"
static const risc_touch_api_v1 *touch_api;
static const risc_driver_v2 *touch_driver;
static portable_touch reducer;
static portable_touch_sample sample;
static const risc_provider_dependency_v1 dependencies[]={{"hardware.device",1,&m_device},{"gpio.bank",1,&m_bank},{"platform.clock",1,&m_clock},{"i2c.bus",1,&m_bus}};
static void point(unsigned slot,unsigned id,unsigned x,unsigned y){
 uint8_t *p=&m_regs[3+6*slot];p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;p[2]=(uint8_t)((id<<4)|(y>>8));p[3]=(uint8_t)y;
}
static void report(unsigned count,unsigned x,bool second){
 ++m_now;m_regs[2]=(uint8_t)count;point(0,3,x,100);if(second)point(1,9,200,120);
 assert(touch_api->poll(NULL,1));
}
static bool step(void){return portable_touch_next(&reducer,&sample);}
static bool tap(void){return sample.valid&&sample.released&&sample.tap_eligible&&!sample.moved&&!sample.cancelled;}
static void drain(void){for(unsigned i=0;i<80;++i)if(!step())return;assert(!"undrained stream");}
static void start_case(void){
 touch_driver=t5_driver_get(2);assert(touch_driver&&touch_driver->start(dependencies,4));touch_api=touch_driver->capability;
 reducer=(portable_touch){.api=touch_api,.subscription=touch_api->subscribe(NULL)};assert(reducer.subscription&&!step());
}
static void finish_case(void){assert(touch_api->unsubscribe(NULL,reducer.subscription));assert(touch_driver->quiesce()&&!m_live);}
static void fresh_tap(void){report(1,20,false);assert(step()&&sample.began);report(0,0,false);assert(step()&&tap());assert(!step());}
int main(int argc,char **argv){
 assert(argc==2);start_case();const char *mode=argv[1];
 if(!strcmp(mode,"same-report")||!strcmp(mode,"unchanged-report")||!strcmp(mode,"all-released")){
  report(1,20,false);assert(step()&&sample.began);report(2,140,true);
  if(!strcmp(mode,"unchanged-report"))report(2,140,true);
  if(!strcmp(mode,"all-released"))report(0,0,false);
  ++m_now;assert(step());
  fprintf(stderr,"first same-report edge: seq=%llu event_ms=%llu dispatch_ms=%llu cancelled=%u down=%u\n",(unsigned long long)reducer.sequence,(unsigned long long)reducer.timestamp_ms,(unsigned long long)m_now,sample.cancelled,sample.down);
  assert(sample.cancelled&&!sample.down);assert(step()&&!sample.down&&!sample.released);
  drain();report(0,0,false);drain();fresh_tap();
 }else if(!strcmp(mode,"earlier-move")){
  report(1,20,false);assert(step()&&sample.began);report(1,140,false);report(2,150,true);++m_now;
  assert(step()&&sample.down&&sample.moved&&!sample.cancelled&&sample.x==140);
  assert(step()&&sample.cancelled);assert(step()&&!sample.down);report(0,0,false);drain();fresh_tap();
 }else if(!strcmp(mode,"replacement")){
  report(1,20,false);assert(step()&&sample.began);++m_now;m_regs[2]=1;point(0,9,180,120);assert(touch_api->poll(NULL,1));
  assert(step()&&tap()&&sample.contact_id==3);assert(step()&&sample.began&&sample.contact_id==9);
  report(0,0,false);assert(step()&&tap()&&sample.contact_id==9);assert(!step());fresh_tap();
 }else if(!strcmp(mode,"rapid-same-tick")){
  uint64_t stamp=m_now+1;for(unsigned i=0;i<15;++i){m_now=stamp-1;report(1,20,false);m_now=stamp-1;report(0,0,false);}
  unsigned taps=0,begins=0;while(step()){assert(!sample.cancelled);taps+=tap();begins+=sample.began;}assert(taps==15&&begins==15);
 }else if(!strcmp(mode,"unchanged-moves")){
  report(1,20,false);assert(step()&&sample.began);report(1,20,false);assert(step()&&sample.valid&&sample.down&&!sample.moved);assert(!step());report(0,0,false);assert(step()&&tap());
 }else if(!strcmp(mode,"two-subscribers")){
  uint64_t other=touch_api->subscribe(NULL);assert(other);report(1,20,false);report(2,140,true);
  const uint8_t kinds[]={RISC_TOUCH_EVENT_DOWN,RISC_TOUCH_EVENT_DOWN,RISC_TOUCH_EVENT_MOVE};
  for(unsigned i=0;i<3;++i){risc_touch_event_v1 a={0},b={0};assert(touch_api->next(NULL,reducer.subscription,&a)==1&&touch_api->next(NULL,other,&b)==1);assert(a.kind==kinds[i]&&!memcmp(&a,&b,sizeof(a)));}
  assert(touch_api->unsubscribe(NULL,other));
 }else if(!strcmp(mode,"overflow")){
  report(1,20,false);assert(step()&&sample.began);for(unsigned i=0;i<32;++i)report(1,20,false);
  assert(step()&&sample.cancelled);drain();report(0,0,false);drain();fresh_tap();
 }else if(!strcmp(mode,"read-failure")){
  report(1,20,false);assert(step()&&sample.began);m_fail_io=true;assert(!portable_touch_collect(&reducer));assert(step()&&sample.cancelled);m_fail_io=false;
  report(0,0,false);assert(portable_touch_collect(&reducer));drain();fresh_tap();
 }else assert(!"unknown case");
 finish_case();printf("Watch contact order PASS: %s\n",mode);return 0;
}

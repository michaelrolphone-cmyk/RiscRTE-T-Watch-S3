// The production runtime, seven independently mapped physical driver instances,
// NOVA clock and all three shared apps. Only low-level hardware is modeled.
#include "ports/esp32s3/CpuPort.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
namespace {
struct Model {
 bool pins[49]{},levels[49]{},bus[2]{},spi=false,held=false;
 bool sleep_test=false,pad_held=false;unsigned sleep_fault=0,sleep_attempts=0,sleep_unloads=0;uint64_t sleep_attempt_at=0;
 uint8_t registers[2][256]{},frame[240*240*2]{},retained_clock[240*240*2]{};uint64_t time=0,app_start=0,clock_ready_at=0;
 unsigned retained_checks=0,returnLoads=0,terminalLoads=0;std::string previous_app;bool clock_ready=false;
 unsigned frames_in_app=0,calls=0,rows=0,pwm=0,dateWrites=0,clockReady=0,clockLoads=0,springLoads=0,batteryLoads=0,settingsLoads=0,touchReads=0;
 unsigned row=0,command=0,frame_rows=0,crown_events=0,keys_in_app=0,touch_failures=0;std::string app;bool edit=false,crown=false,crown_spring=false;
} m;
RiscCpu::Port* cpu;
bool owner(){return true;}
uint64_t now(){return m.time;}
void delay(uint32_t ms){m.time+=ms;assert(m.time<(m.sleep_test?80000u:30000u));}
bool live(risc_runtime_health_v1*h){assert(++m.calls<100000);h->uptime_ms=(uint32_t)m.time;if(m.sleep_test)return !m.sleep_attempts || m.time-m.sleep_attempt_at<700;return m.clockReady<(m.crown_spring?3u:2u);}
bool log(const char*s){puts(s);assert(!strstr(s,"error="));if(!strncmp(s,"WATCH_CLOCK ready",17)){m.clockReady++;if(m.app=="clock.elf")assert(m.time-m.app_start<300);else assert(m.time-m.app_start>=2000);m.clock_ready_at=m.time;m.clock_ready=true;}return true;}
bool gpioOpen(uint8_t p,bool out,bool initial,bool){assert(p<49&&!m.pins[p]);m.pins[p]=true;m.levels[p]=out?initial:true;return true;}
bool gpioWrite(uint8_t p,bool value){assert(m.pins[p]);m.levels[p]=value;return true;}
bool gpioRead(uint8_t p,bool*v){assert(m.pins[p]);*v=m.levels[p];return true;}
bool gpioPwm(uint8_t p,uint32_t hz,uint16_t duty,uint16_t maximum){assert(p==45&&hz==1000&&maximum&&duty<=maximum);if(duty){assert(m.frame_rows==240);if(m.app=="default.elf")assert(m.frames_in_app>0);m.pwm++;}m.levels[p]=duty!=0;return true;}
bool gpioClose(uint8_t p){assert(m.pins[p]);m.pins[p]=false;return true;}
bool i2cOpen(uint8_t p,uint8_t sda,uint8_t scl,uint32_t hz){assert(p<2&&!m.bus[p]&&hz==100000);assert(sda==(p?39:10)&&scl==(p?40:11));m.bus[p]=true;return true;}
bool i2cClose(uint8_t p){assert(p<2&&m.bus[p]);m.bus[p]=false;return true;}
void contact(uint8_t*rx,unsigned x,unsigned y){ // logical → physical, independent expected transform
 rx[0]=1;rx[1]=(x>>8)&15;rx[2]=(uint8_t)x;rx[3]=(y>>8)&15;rx[4]=(uint8_t)y;
}
bool i2cTransfer(uint8_t p,uint8_t a,const uint8_t*tx,size_t tn,uint8_t*rx,size_t rn,uint32_t ms){
 assert(p<2&&m.bus[p]&&tn&&ms&&ms<=1000);
 if(p){
  assert(a==0x38&&tn==1&&tx[0]==2&&rn==13);memset(rx,0,rn);m.touchReads++;
  unsigned age=(unsigned)(m.time-m.app_start);
  if(m.sleep_test)return true;
  if(m.crown&&m.app=="battery.elf"&&age>=50){m.touch_failures++;return false;}
  if(m.app=="default.elf"||m.app=="clock.elf"){
   // First poll is neutral, then a held movement begins after startup.
   if(m.clock_ready&&m.time-m.clock_ready_at>=20)contact(rx,m.time-m.clock_ready_at<60?120:160,120);
  }else if(m.app=="springboard.elf"){
   // Preserve the held swipe through entry, continue dragging, release, then
   // wait for spring settling before a fresh deliberate app-icon tap.
   if(age<120&&(m.previous_app=="default.elf"||m.previous_app=="clock.elf"))contact(rx,160+age/12,120);
   if(age>=1500&&age<1600&&!(m.crown_spring&&m.springLoads==1)&&!m.settingsLoads)contact(rx,93,!m.batteryLoads?166:74);
   if(m.settingsLoads&&!m.crown&&age>=200&&age<260)contact(rx,20,18);
   assert(age<5000);
  }else if(m.app=="battery.elf"){
   if(!m.crown&&age>=100&&age<160)contact(rx,20,18);
   assert(age<2000);
  }else if(m.app=="settings.elf"){
   if(m.edit){
    if(age>=100&&age<160)contact(rx,120,144); // Set Time
    if(!m.crown&&age>=400&&age<460)contact(rx,170,212); // Save displayed time through inverse policy
    if(!m.crown&&age>=1000&&age<1060)contact(rx,120,205); // Root Back
   }else if(!m.crown&&age>=100&&age<160)contact(rx,120,205);
   assert(age<3000);
  }
  return true;
 }
 assert(a==0x34||a==0x51);auto*r=m.registers[a==0x51];unsigned reg=tx[0];assert(reg+rn<=256&&reg+tn-1<=256);
 if(tn>1){assert(!rn);for(size_t i=1;i<tn;i++){
  if(a==0x51&&reg>=2&&reg<=8)m.dateWrites++;
  // PMU IRQ status is write-one-to-clear, not ordinary RAM.
  if(a==0x34&&reg>=0x48&&reg<=0x4a)r[reg]&=(uint8_t)~tx[i];else r[reg]=tx[i];reg++;
 }}
 if(m.sleep_test&&a==0x34&&reg==0x49&&rn==1&&m.clock_ready&&!m.keys_in_app&&m.time-m.clock_ready_at>=300){r[0x49]|=8;m.keys_in_app++;}
 if(a==0x34&&reg==0x49&&rn==1&&m.crown){
  unsigned age=(unsigned)(m.time-m.app_start);
  bool back=(m.app=="battery.elf"&&age>=220&&!m.keys_in_app) ||
      (m.app=="settings.elf"&&age>=(m.edit?(m.keys_in_app?850u:400u):220u)&&m.keys_in_app<(m.edit?2u:1u)) ||
      (m.app=="springboard.elf"&&((m.crown_spring&&m.springLoads==1)||m.settingsLoads)&&age>=300&&!m.keys_in_app);
  if(back){r[0x49]|=0x08;m.keys_in_app++;m.crown_events++;}
 }
 if(rn)memcpy(rx,r+reg,rn);
 return true;
}
bool spiOpen(uint8_t p,int16_t clk,int16_t mosi,int16_t miso){assert(p==2&&clk==18&&mosi==13&&miso==-1&&!m.spi);m.spi=true;return true;}
bool spiBegin(uint8_t p,uint8_t cs,uint32_t hz,uint8_t mode,uint32_t ms){assert(p==2&&cs==12&&hz==40000000&&!mode&&ms&&m.spi&&!m.held);m.held=true;m.levels[cs]=false;return true;}
bool spiTransfer(uint8_t p,const uint8_t*tx,uint8_t*,size_t n,uint32_t ms){
 assert(p==2&&m.held&&tx&&n&&ms);
 if(!m.levels[38]){assert(n==1);m.command=tx[0];if(m.command==0x2c)m.frame_rows=0;}
 else if(m.command==0x2a)assert(n==4&&tx[0]==0&&tx[1]==0&&tx[2]==0&&tx[3]==239);
 else if(m.command==0x2b){assert(n==4&&tx[0]==0&&tx[1]==80&&tx[2]==1&&tx[3]==63);m.row=80;}
 else if(m.command==0x2c){assert(n==480&&m.row>=80&&m.row<320);memcpy(m.frame+(m.row-80)*480,tx,480);m.row++;m.frame_rows++;m.rows++;
  if(m.frame_rows==240){m.frames_in_app++;if(m.app=="springboard.elf"&&m.frames_in_app==1){assert(memcmp(m.frame,m.retained_clock,sizeof(m.frame)));m.retained_checks++;}}}
 return true;
}
bool spiEnd(uint8_t p,uint8_t cs,uint32_t){assert(p==2&&cs==12&&m.held);m.held=false;m.levels[cs]=true;return true;}
bool spiClose(uint8_t p){assert(p==2&&!m.held);m.spi=false;return true;}
int32_t kvGet(void*,uint32_t ns,const char*key,void*data,uint32_t capacity,uint32_t*size){assert(ns==1&&!strcmp(key,"sleep_mode"));*size=0;if(m.sleep_test){assert(capacity>=4);memcpy(data,"\x53\x01\x01\xa4",4);*size=4;return 0;}return RISC_KEY_VALUE_NOT_FOUND;}
int32_t kvPut(void*,uint32_t,const char*,const void*,uint32_t){assert(!"Existing GUI flows never save sleep mode");return RISC_KEY_VALUE_IO;}
const RiscBoot::KeyValueBackend kv={nullptr,kvGet,kvPut};
bool bind(RiscBoot::Runtime&r){return cpu->bind(r);}
}
extern "C" void watch_test_unloading(){if(m.sleep_test)++m.sleep_unloads;}
extern "C" void watch_test_loading(const char*path){
 const char*name=strrchr(path,'/');name=name?name+1:path;if(!strcmp(name,"driver.elf"))return;
 if(!strcmp(name,"springboard.elf")){assert((m.app=="default.elf"||m.app=="clock.elf"||m.app=="battery.elf"||m.app=="settings.elf")&&m.frame_rows==240);memcpy(m.retained_clock,m.frame,sizeof(m.frame));}
 m.previous_app=m.app;m.app=name;m.app_start=m.time;m.frames_in_app=0;m.clock_ready=false;m.keys_in_app=0;
 if(m.app=="default.elf"){if(m.clockReady>=(m.crown_spring?3u:2u))m.terminalLoads++;else m.clockLoads++;}
 else if(m.app=="clock.elf")m.returnLoads++;
 else if(m.app=="springboard.elf")m.springLoads++;
 else if(m.app=="battery.elf")m.batteryLoads++;
 else if(m.app=="settings.elf")m.settingsLoads++;
 else assert(!"Unexpected app path");
 fprintf(stderr,"Load %s at %llu ms\n",name,(unsigned long long)m.time);
}
int main(int argc,char**argv){
 assert(argc==2);for(unsigned scenario=0;scenario<5;scenario++){
 m=Model{};m.edit=scenario==1||scenario>=3;m.crown=scenario>=2;m.crown_spring=scenario==4;m.registers[0][3]=0x4a;
 m.registers[0][0x34]=0x0f;m.registers[0][0x35]=0xa0;
 const uint8_t raw[]={0,0x40,0,4,0,0x10,0x26};memcpy(m.registers[1]+2,raw,7);
 RiscCpu::Port port({owner,now,delay,gpioOpen,gpioWrite,gpioRead,gpioPwm,gpioClose,i2cOpen,i2cTransfer,i2cClose,spiOpen,spiBegin,spiTransfer,spiEnd,spiClose});cpu=&port;
 RiscBoot::Runtime runtime({owner,live,delay,log,bind,&kv,[](){return cpu->appExitSafe();}});
 if(!runtime.prepare(argv[1])||!runtime.run()){fprintf(stderr,"Runtime failure: %s\n",runtime.error());return 1;}
 unsigned extra=m.crown_spring?1u:0u;
 assert(m.clockLoads==1&&m.returnLoads==1+extra&&m.terminalLoads==1&&m.clockReady==2+extra&&m.springLoads==3+extra&&m.batteryLoads==1&&m.settingsLoads==1);
 assert(m.touchReads>40&&m.rows>240&&m.pwm>=1&&m.retained_checks==3+extra);
 assert(m.edit&&!m.crown?m.dateWrites==7:m.dateWrites==0);
 if(m.crown){assert(m.touch_failures>0&&m.crown_events==(m.edit?4u:3u)+extra);}assert(!memcmp(m.registers[1]+2,raw,7));
 assert(!m.bus[0]&&!m.bus[1]&&!m.spi&&!m.held&&port.quiescent());for(bool pin:m.pins)assert(!pin);
 fprintf(stderr,"Real modules PASS scenario=%u frames=%u touch=%u crown=%u retained=%u RTCwrites=%u; all resources quiescent\n",scenario,m.rows/240,m.touchReads,m.crown_events,m.retained_checks,m.dateWrites);
 }
 return 0;
}

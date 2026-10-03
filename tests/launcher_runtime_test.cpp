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
 uint8_t registers[2][256]{};uint64_t time=0,app_start=0;
 unsigned railWrites=0,calls=0,rows=0,pwm=0,dateWrites=0,clockReady=0,clockLoads=0,springLoads=0,batteryLoads=0,settingsLoads=0,touchReads=0;
 unsigned row=0,last_row=319,command=0,frame_rows=0,mode=0,key_stage=0,partial_frames=0,max_touch_gap=0,sleep_attempts=0;uint64_t sub_us=0,touch_at=0;std::string app;bool edit=false;
} m;
RiscCpu::Port* cpu;
void advance_us(uint64_t us){m.sub_us+=us;m.time+=m.sub_us/1000;m.sub_us%=1000;}
bool owner(){return true;}
uint64_t now(){return m.time;}
void delay(uint32_t ms){m.time+=ms;assert(m.time<30000);}
bool live(risc_runtime_health_v1*h){assert(++m.calls<100000);h->uptime_ms=(uint32_t)m.time;return m.clockReady<3 || m.time-m.app_start<3000;}
bool log(const char*s){puts(s);assert(!strstr(s,"error="));if(!strncmp(s,"WATCH_CLOCK ready",17))m.clockReady++;return true;}
bool gpioOpen(uint8_t p,bool out,bool initial,bool){assert(p<49&&!m.pins[p]);m.pins[p]=true;m.levels[p]=out?initial:true;return true;}
bool gpioWrite(uint8_t p,bool value){assert(m.pins[p]);m.levels[p]=value;return true;}
bool gpioRead(uint8_t p,bool*v){assert(m.pins[p]);*v=m.levels[p];return true;}
bool gpioPwm(uint8_t p,uint32_t hz,uint16_t duty,uint16_t maximum){assert(p==45&&hz==1000&&maximum&&duty<=maximum);if(duty){assert(m.frame_rows==240 && (m.registers[0][0x90]&2u));m.pwm++;}m.levels[p]=duty!=0;return true;}
bool gpioClose(uint8_t p){assert(m.pins[p]);m.pins[p]=false;return true;}
bool i2cOpen(uint8_t p,uint8_t sda,uint8_t scl,uint32_t hz){assert(p<2&&!m.bus[p]&&hz==100000);assert(sda==(p?39:10)&&scl==(p?40:11));m.bus[p]=true;return true;}
bool i2cClose(uint8_t p){assert(p<2&&m.bus[p]);m.bus[p]=false;return true;}
void contact(uint8_t*rx,unsigned x,unsigned y){ // logical → physical, independent expected transform
 /* native FT6336 axes */ rx[0]=1;rx[1]=(x>>8)&15;rx[2]=(uint8_t)x;rx[3]=(y>>8)&15;rx[4]=(uint8_t)y;
}
bool i2cTransfer(uint8_t p,uint8_t a,const uint8_t*tx,size_t tn,uint8_t*rx,size_t rn,uint32_t ms){
 assert(p<2&&m.bus[p]&&tn&&ms&&ms<=1000);
 if(p){
  assert(a==0x38&&tn==1&&tx[0]==2&&rn==13);memset(rx,0,rn);m.touchReads++;
  if(m.touch_at && m.time-m.touch_at>m.max_touch_gap)m.max_touch_gap=(unsigned)(m.time-m.touch_at);
  m.touch_at=m.time;
  unsigned age=(unsigned)(m.time-m.app_start);
  if(m.mode)advance_us(1500);
  if(m.mode>=2&&m.app=="battery.elf")return false; /* crown escape with failed touch */
  if(m.app=="default.elf"){
   // First poll is neutral, then a held movement begins after startup.
   if(m.clockLoads<3 && age>2200)contact(rx,age<2240?120:160,120);
  }else if(m.app=="springboard.elf"){
   // Preserve the held swipe through entry, continue dragging, release, then
   // wait for spring settling before a fresh deliberate app-icon tap.
   if(age<120)contact(rx,160+age/12,120);
   if(age>=1500&&age<1600)contact(rx,93,m.springLoads==1?166:74);
   assert(age<5000);
  }else if(m.app=="battery.elf"){
   if(age>=100&&age<160)contact(rx,20,18);
   assert(age<2000);
  }else if(m.app=="settings.elf"){
   if(m.mode==3){if(age>=100&&age<160)contact(rx,120,144);}
   else if(m.mode==2){/* Crown owns exit; no touch. */}
   else if(m.edit){
    if(age>=100&&age<160)contact(rx,120,144); // Set Time
    if(age>=400&&age<460)contact(rx,170,212); // Save displayed time through inverse policy
    if(age>=1000&&age<1060)contact(rx,120,205); // Root Back
   }else if(age>=100&&age<160)contact(rx,120,205);
   assert(age<3000);
  }
  return true;
 }
 if(a==0x34 && tn>1 && tx[0]==0x90){
  // A bounded delayed PMU completion: old 1ms rail writes cannot succeed.
  // Startup/teardown use 40ms; no application presentation may change rails.
  if(ms<2)return false;
  advance_us(1500);m.railWrites++;
 }
 if(m.mode)advance_us(500);
 if(a==0x34 && tx[0]==0x49 && m.mode>=2 && (m.app=="battery.elf" || m.app=="settings.elf")) {
  unsigned age=(unsigned)(m.time-m.app_start);
  const unsigned basic[]={100,160},nested[]={500,560,900,960};
  const unsigned*times=m.mode==3&&m.app=="settings.elf"?nested:basic;
  unsigned count=m.mode==3&&m.app=="settings.elf"?4:2;
  if(m.key_stage<count && age>=times[m.key_stage]){m.registers[0][0x49]|=(m.key_stage%2?8:2);m.key_stage++;}
 }
 assert(a==0x34||a==0x51);auto*r=m.registers[a==0x51];unsigned reg=tx[0];assert(reg+rn<=256&&reg+tn-1<=256);
 if(tn>1){assert(!rn);for(size_t i=1;i<tn;i++){
  if(a==0x51&&reg>=2&&reg<=8)m.dateWrites++;
  if(a==0x34&&reg==0x41&&tx[i]==8)m.sleep_attempts++;
  // PMU IRQ status is write-one-to-clear, not ordinary RAM.
  if(a==0x34&&reg>=0x48&&reg<=0x4a)r[reg]&=(uint8_t)~tx[i];else r[reg]=tx[i];reg++;
 }}
 if(rn)memcpy(rx,r+reg,rn);
 return true;
}
bool spiOpen(uint8_t p,int16_t clk,int16_t mosi,int16_t miso){assert(p==2&&clk==18&&mosi==13&&miso==-1&&!m.spi);m.spi=true;return true;}
bool spiBegin(uint8_t p,uint8_t cs,uint32_t hz,uint8_t mode,uint32_t ms){assert(p==2&&cs==12&&hz==40000000&&!mode&&ms&&m.spi&&!m.held);m.held=true;m.levels[cs]=false;return true;}
bool spiTransfer(uint8_t p,const uint8_t*tx,uint8_t*,size_t n,uint32_t ms){
 assert(p==2&&m.held&&tx&&n&&ms);
 if(m.mode)advance_us((n*8+39)/40+(m.mode==1?100:250));
 if(!m.levels[38]){assert(n==1);m.command=tx[0];if(m.command==0x2c)m.frame_rows=0;}
 else if(m.command==0x2a)assert(n==4&&tx[0]==0&&tx[1]==0&&tx[2]==0&&tx[3]==239);
 else if(m.command==0x2b){assert(n==4);m.row=unsigned(tx[0])*256+tx[1];m.last_row=unsigned(tx[2])*256+tx[3];assert(m.row>=80&&m.last_row<320&&m.row<=m.last_row);}
 else if(m.command==0x2c){assert(n==480&&m.row>=80&&m.row<320);m.row++;m.frame_rows++;m.rows++;if(m.row>m.last_row&&m.frame_rows<240)m.partial_frames++;}
 return true;
}
bool spiEnd(uint8_t p,uint8_t cs,uint32_t){assert(p==2&&cs==12&&m.held);m.held=false;m.levels[cs]=true;return true;}
bool spiClose(uint8_t p){assert(p==2&&!m.held);m.spi=false;return true;}
bool bind(RiscBoot::Runtime&r){return cpu->bind(r);}
}
extern "C" void watch_test_loading(const char*path){
 const char*name=strrchr(path,'/');name=name?name+1:path;if(!strcmp(name,"driver.elf"))return;
 if(m.app=="settings.elf"&&m.mode==3)assert(m.key_stage==4);
 m.app=name;m.app_start=m.time;m.key_stage=0;m.touch_at=0;
 if(m.app=="default.elf")m.clockLoads++;
 else if(m.app=="springboard.elf")m.springLoads++;
 else if(m.app=="battery.elf")m.batteryLoads++;
 else if(m.app=="settings.elf")m.settingsLoads++;
 else assert(!"Unexpected app path");
 fprintf(stderr,"Load %s at %llu ms\n",name,(unsigned long long)m.time);
}
int main(int argc,char**argv){
 assert(argc==2);for(unsigned mode=0;mode<4;mode++){
 m=Model{};m.mode=mode;m.edit=mode==1;m.registers[0][3]=0x4a;
 m.registers[0][0x34]=0x0f;m.registers[0][0x35]=0xa0;
 const uint8_t raw[]={0,0x40,0,4,0,0x10,0x26};memcpy(m.registers[1]+2,raw,7);
 RiscCpu::Port port({owner,now,delay,gpioOpen,gpioWrite,gpioRead,gpioPwm,gpioClose,i2cOpen,i2cTransfer,i2cClose,spiOpen,spiBegin,spiTransfer,spiEnd,spiClose});cpu=&port;
 RiscBoot::Runtime runtime({owner,live,delay,log,bind});
 if(!runtime.prepare(argv[1])||!runtime.run()){fprintf(stderr,"Runtime failure: %s\n",runtime.error());return 1;}
 assert(m.clockLoads==3&&m.clockReady==3&&m.springLoads==2&&m.batteryLoads==1&&m.settingsLoads==1);
 assert(m.touchReads>40&&m.rows>240&&m.pwm>=1);
 assert(m.railWrites==2); /* one startup, one restored teardown; none per frame */
 assert(m.edit?m.dateWrites==7:m.dateWrites==0);assert(!memcmp(m.registers[1]+2,raw,7));
 assert(!m.bus[0]&&!m.bus[1]&&!m.spi&&!m.held&&port.quiescent());for(bool pin:m.pins)assert(!pin);
 assert(m.partial_frames>0 && m.max_touch_gap<=65 && !m.sleep_attempts);
 fprintf(stderr,"Real modules PASS mode=%u rows=%u partial=%u touch=%u maxInputGap=%u RTCwrites=%u; all resources quiescent\n",mode,m.rows,m.partial_frames,m.touchReads,m.max_touch_gap,m.dateWrites);
 }
}

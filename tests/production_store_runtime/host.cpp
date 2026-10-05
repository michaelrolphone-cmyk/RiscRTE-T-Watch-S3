// Production boot policy, Runtime/CpuPort, all selected production providers,
// and the actual default Clock. Only the lowest native hardware is modeled.
#include "ports/esp32s3/CpuPort.h"
#include "backend.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>
#ifdef PRODUCTION_POINTS_DEFAULTS
extern "C" bool production_points_expiration_valid(const void*,uint32_t);
#endif
namespace {
struct Model {
  bool pins[49]{},levels[49]{},buses[2]{},spi=false,held=false,ready=false;
  bool appLoaded=false,firstAppDelay=false;
  uint8_t registers[3][256]{},frame[240*240*2]{};
  uint64_t milliseconds=0;
  unsigned healthCalls=0,moduleLoads=0,moduleUnloads=0,appLoads=0,appUnloads=0;
  unsigned rows=0,frameRows=0,frames=0,brightness=0,touchReads=0,rtcWrites=0;
  unsigned appSettingsReads=0,appPointsReads=0,quickSettingsReads=0,radioActivity=0,storageWrites=0;
  uint8_t pointsLedger[64]{};bool pointsLedgerPresent=false;unsigned pointsLedgerReads=0;
  unsigned command=0,row=0;
  void* application=nullptr;
} m;
RiscCpu::Port* cpu=nullptr;
bool owner(){return true;}
uint64_t now(){return m.milliseconds;}
void delay(uint32_t ms){
  m.milliseconds+=ms;assert(m.milliseconds<30000);
  if(m.appLoaded)m.firstAppDelay=true;
}
bool health(risc_runtime_health_v1* h){
  assert(++m.healthCalls<100000);h->uptime_ms=(uint32_t)m.milliseconds;
  return !m.ready;
}
bool log(const char* line){
  puts(line);assert(!strstr(line,"error=")&&!strstr(line,"unavailable")&&!strstr(line,"unreadable"));
  if(!strncmp(line,"WATCH_CLOCK ready",17))m.ready=true;
  return true;
}
bool gpioOpen(uint8_t p,bool output,bool initial,bool){
  assert(p<49&&!m.pins[p]);m.pins[p]=true;m.levels[p]=output?initial:true;return true;
}
bool gpioWrite(uint8_t p,bool level){assert(p<49&&m.pins[p]);m.levels[p]=level;return true;}
bool gpioRead(uint8_t p,bool* level){assert(p<49&&m.pins[p]);*level=m.levels[p];return true;}
bool gpioPwm(uint8_t p,uint32_t hz,uint16_t duty,uint16_t maximum){
  assert(p==45&&hz==1000&&maximum&&duty<=maximum);
  if(duty){assert(m.frameRows==240&&m.frames>0);++m.brightness;}
  m.levels[p]=duty!=0;return true;
}
bool gpioClose(uint8_t p){assert(p<49&&m.pins[p]);m.pins[p]=false;return true;}
bool i2cOpen(uint8_t p,uint8_t sda,uint8_t scl,uint32_t hz){
  assert(p<2&&!m.buses[p]&&hz==100000);
  assert(sda==(p?39:10)&&scl==(p?40:11));m.buses[p]=true;return true;
}
bool i2cTransfer(uint8_t p,uint8_t address,const uint8_t* tx,size_t tn,uint8_t* rx,size_t rn,uint32_t ms){
  assert(p<2&&m.buses[p]&&tn&&ms&&ms<=1000);
  if(p){assert(address==0x38&&tn==1&&tx[0]==2&&rn==13);memset(rx,0,rn);++m.touchReads;return true;}
  assert(address==0x34||address==0x51||address==0x5a);
  uint8_t* registers=m.registers[address==0x34?0:address==0x51?1:2];
  unsigned reg=tx[0];assert(reg+rn<=256&&reg+tn-1<=256);
  if(tn>1){assert(!rn);for(size_t i=1;i<tn;++i){
    if(address==0x51&&reg>=2&&reg<=8)++m.rtcWrites;
    if(address==0x5a&&reg==12)assert(tx[i]==0); // No haptic GO during empty startup.
    if(address==0x34&&reg>=0x48&&reg<=0x4a)registers[reg]&=(uint8_t)~tx[i];
    else registers[reg]=tx[i];++reg;
  }}
  if(rn)memcpy(rx,registers+reg,rn);return true;
}
bool i2cClose(uint8_t p){assert(p<2&&m.buses[p]);m.buses[p]=false;return true;}
bool spiOpen(uint8_t p,int16_t clk,int16_t mosi,int16_t miso){
  assert(p==2&&clk==18&&mosi==13&&miso==-1&&!m.spi);m.spi=true;return true;
}
bool spiBegin(uint8_t p,uint8_t cs,uint32_t hz,uint8_t mode,uint32_t ms){
  assert(p==2&&cs==12&&hz==40000000&&!mode&&ms&&m.spi&&!m.held);
  m.held=true;m.levels[cs]=false;return true;
}
bool spiTransfer(uint8_t p,const uint8_t* tx,uint8_t*,size_t n,uint32_t ms){
  assert(p==2&&m.held&&tx&&n&&ms);
  if(!m.levels[38]){assert(n==1);m.command=tx[0];if(m.command==0x2c)m.frameRows=0;}
  else if(m.command==0x2a)assert(n==4&&tx[0]==0&&tx[1]==0&&tx[2]==0&&tx[3]==239);
  else if(m.command==0x2b){assert(n==4&&tx[0]==0&&tx[1]==80&&tx[2]==1&&tx[3]==63);m.row=80;}
  else if(m.command==0x2c){
    assert(n==480&&m.row>=80&&m.row<320);
    memcpy(m.frame+(m.row-80)*480,tx,480);++m.row;++m.frameRows;++m.rows;
    if(m.frameRows==240)++m.frames;
  }
  return true;
}
bool spiEnd(uint8_t p,uint8_t cs,uint32_t){assert(p==2&&cs==12&&m.held);m.held=false;m.levels[cs]=true;return true;}
bool spiClose(uint8_t p){assert(p==2&&!m.held&&m.spi);m.spi=false;return true;}
int32_t kvGet(void*,uint32_t ns,const char* key,void* bytes,uint32_t cap,uint32_t* size){
  assert(ns>=1&&ns<=5&&key&&size);*size=0;
  // Before Clock's first yield no provider poll has run. These are direct
  // namespace reads by production crown.c, after all providers started.
  if(m.appLoaded&&!m.firstAppDelay){
    if(ns==1&&(!strcmp(key,"watch_face")||!strcmp(key,"time_format")))++m.appSettingsReads;
    if(ns==5&&!strcmp(key,"points_cfg"))++m.appPointsReads;
    if(ns==1&&(!strcmp(key,"brightness")||!strcmp(key,"alarm_volume")||!strcmp(key,"quick_volume")))++m.quickSettingsReads;
  }
#ifdef PRODUCTION_POINTS_DEFAULTS
  if(ns==4&&!strcmp(key,"points_occ")&&m.pointsLedgerPresent){
    *size=sizeof(m.pointsLedger);if(cap<*size)return RISC_KEY_VALUE_BUFFER_SMALL;
    assert(bytes);memcpy(bytes,m.pointsLedger,*size);++m.pointsLedgerReads;
    return RISC_KEY_VALUE_OK;
  }
#else
  (void)bytes;(void)cap;
#endif
  return RISC_KEY_VALUE_NOT_FOUND;
}
int32_t kvPut(void*,uint32_t ns,const char* key,const void* bytes,uint32_t size){
#ifdef PRODUCTION_POINTS_DEFAULTS
  // Defaults are virtual. Only the ordinary provider's expired-edge highwater
  // may be committed; app settings/config/meta and active cue records fail.
  assert(ns==4&&key&&!strcmp(key,"points_occ")&&bytes&&size==sizeof(m.pointsLedger));
  assert(!m.pointsLedgerPresent&&production_points_expiration_valid(bytes,size));
  memcpy(m.pointsLedger,bytes,size);m.pointsLedgerPresent=true;++m.storageWrites;
  return RISC_KEY_VALUE_OK;
#else
  (void)ns;(void)key;(void)bytes;(void)size;
  ++m.storageWrites;assert(!"Empty startup must not write persistent records");return RISC_KEY_VALUE_IO;
#endif
}
[[maybe_unused]] bool startupStorageOk(){
#ifdef PRODUCTION_POINTS_DEFAULTS
  return m.storageWrites==1&&m.pointsLedgerPresent&&m.pointsLedgerReads>=1;
#else
  return m.storageWrites==0;
#endif
}
bool bind(RiscBoot::Runtime& runtime){return cpu->bind(runtime);}
}
extern "C" void production_test_loading(const char* path){
  ++m.moduleLoads;const char* name=strrchr(path,'/');name=name?name+1:path;
  if(strcmp(name,"driver.elf")){assert(!strcmp(name,"default.elf"));++m.appLoads;m.appLoaded=true;}
}
extern "C" void production_test_loaded(void* module){
  assert(module);if(m.appLoaded&&!m.application)m.application=module;
}
extern "C" void production_test_unloading(void* module){
  ++m.moduleUnloads;if(module==m.application){++m.appUnloads;m.appLoaded=false;}
}
extern "C" void risc_test_native_loading(const char* path){production_test_loading(path);}
extern "C" void risc_test_native_loaded(const char*,void* module){production_test_loaded(module);}
extern "C" void risc_test_native_unloading(const char*,void* module){production_test_unloading(module);}
int main(int argc,char** argv){
  assert(argc==2||argc==4);
  setvbuf(stdout,nullptr,_IONBF,0);
  m.registers[0][3]=0x4a;m.registers[0][0x34]=0x0f;m.registers[0][0x35]=0xa0;
  m.registers[2][0]=0x60; // DRV2605 chip identity.
  const uint8_t date[]={0,0x40,0,4,0,0x10,0x26};memcpy(m.registers[1]+2,date,sizeof(date));
  RiscCpu::Hardware hardware{owner,now,delay,gpioOpen,gpioWrite,gpioRead,gpioPwm,gpioClose,
    i2cOpen,i2cTransfer,i2cClose,spiOpen,spiBegin,spiTransfer,spiEnd,spiClose};
  hardware.i2sOpen=[](uint8_t,uint8_t,uint8_t,uint8_t,uint32_t){assert(!"No alarm audio expected");return false;};
  hardware.i2sWrite=[](uint8_t,const int16_t*,size_t,size_t*,uint32_t){assert(!"No alarm audio expected");return false;};
  hardware.i2sClose=[](uint8_t){assert(!"No alarm audio expected");return false;};
#ifdef PRODUCTION_HAS_RADIO
  hardware.radioJoin=[](const char*,const char*){++m.radioActivity;assert(!"No RF activity expected");return false;};
  hardware.radioState=[](uint8_t* state,int8_t* rssi){*state=0;*rssi=-127;return true;};
  hardware.radioLeave=[](){return true;};
  hardware.radioAddresses=[](uint8_t*,uint8_t*){assert(!"No radio address request expected");return false;};
  hardware.radioScanStart=[](){++m.radioActivity;assert(!"No RF activity expected");return false;};
  hardware.radioScanPoll=[](garden_radio_scan_result_v1*){assert(!"No RF activity expected");return false;};
  hardware.radioScanCancel=[](){return true;};hardware.radioIdle=[](){return true;};
#endif
  RiscCpu::Port port(hardware);cpu=&port;
  const RiscBoot::KeyValueBackend kv={nullptr,kvGet,kvPut};
  RiscBoot::Runtime runtime({owner,health,delay,log,bind,&kv,
    [](){return cpu->appExitSafe();}
#ifdef PRODUCTION_STORAGE_SAFE
    ,[](){return cpu->providerStorageSafe();}
#endif
  });
  const bool prepared=runtime.prepare(argv[1]);
  if(argc==4&&!strcmp(argv[2],"prepare")){
    if(prepared||strcmp(runtime.error(),argv[3])){
      fprintf(stderr,"Expected prepare rejection '%s'; got prepared=%d error='%s'\n",argv[3],prepared,runtime.error());return 2;
    }
    assert(m.moduleLoads==0&&m.milliseconds==0&&port.quiescent());
    printf("Expected admission rejection before module load: %s\n",runtime.error());return 0;
  }
  if(!prepared){fprintf(stderr,"prepare: %s\n",runtime.error());return 2;}
  const bool ran=runtime.run();
  if(argc==4&&!strcmp(argv[2],"runtime")){
    if(ran||strcmp(runtime.error(),argv[3])){
      fprintf(stderr,"Expected runtime rejection '%s'; got ran=%d error='%s'\n",argv[3],ran,runtime.error());return 3;
    }
    assert(!m.appLoads&&!m.appUnloads&&!m.frames&&m.moduleLoads==m.moduleUnloads);
    assert(!m.radioActivity&&!m.storageWrites&&!m.buses[0]&&!m.buses[1]&&!m.spi&&!m.held&&port.quiescent());
    assert(!risc_test_native_mapping_count());
    for(bool pin:m.pins)assert(!pin);
    printf("Expected native registry startup rejection before Clock: %s; modules=%u/%u; all resources quiescent\n",runtime.error(),m.moduleLoads,m.moduleUnloads);
    return 0;
  }
  if(!ran){fprintf(stderr,"run: %s\n",runtime.error());return 3;}
  printf("Lifecycle observed: ready=%u apps=%u/%u modules=%u/%u frames=%u namespace1=%u namespace5=%u touch=%u elapsed=%llu\n",
    m.ready,m.appLoads,m.appUnloads,m.moduleLoads,m.moduleUnloads,m.frames,m.appSettingsReads,m.appPointsReads,m.touchReads,
    (unsigned long long)m.milliseconds);
  assert(m.ready&&m.appLoads==1&&m.appUnloads==1&&m.moduleLoads==m.moduleUnloads);
  assert(m.appSettingsReads==2&&m.appPointsReads==PRODUCTION_POINTS_READS&&m.frames>0&&m.frameRows==240&&m.brightness>0);
  bool nonzero=false;for(uint8_t pixel:m.frame)nonzero|=pixel!=0;assert(nonzero);
  assert(m.touchReads>0&&!m.rtcWrites&&startupStorageOk()&&!m.radioActivity);
  assert(!memcmp(m.registers[1]+2,date,sizeof(date)));
  assert(!m.buses[0]&&!m.buses[1]&&!m.spi&&!m.held&&port.quiescent());for(bool pin:m.pins)assert(!pin);
  assert(!risc_test_native_mapping_count());
  printf("Startup storage: writes=%u namespace4_points_occ=%u verified_readbacks=%u namespace5_writes=0\n",m.storageWrites,m.pointsLedgerPresent,m.pointsLedgerReads);
  printf("Production default Clock PASS: target registry, frames=%u, settings_reads=%u, points_reads=%u, modules=%u/%u, all resources quiescent, no RF\n",
    m.frames,m.appSettingsReads,m.appPointsReads,m.moduleLoads,m.moduleUnloads);
  return 0;
}

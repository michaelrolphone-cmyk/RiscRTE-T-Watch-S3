// Full production JSON remains unchanged. Reuse the lowest-hardware model,
// injecting only raw input, I2S outcomes, RTC registers and in-memory KV.
#define main original_clock_test_main
#define production_test_loading original_clock_loading
#define production_test_loaded original_clock_loaded
#define production_test_unloading original_clock_unloading
#include "host.cpp"
#undef main
#undef production_test_loading
#undef production_test_loaded
#undef production_test_unloading
#include "AlarmRecords.h"
#include <cstdlib>
namespace {
struct AudioModel {
 std::string mode,current;std::map<void*,std::string> modules;
 uint64_t loadedAt=0;unsigned clocks=0,audioLoads=0,springboards=0;
 unsigned opens=0,closes=0,writes=0,toneCloses=0,alarmOpens=0,liveKv=0,kv=0,acks=0;
 unsigned backs=0,sleeps=0,retainedYields=0,io=0,retainedIo=0,retainedKv=0,retainedCloses=0;
 unsigned rate=0;bool live=false,ready=false,retained=false,fault=false,started=false;
 uint8_t config[ALARM_RECORD_SIZE]{};std::map<std::string,std::vector<uint8_t>> values;
} a;
RiscBoot::Runtime* running=nullptr;
bool mode(const char* value){return a.mode==value;}
bool audio(){return a.current=="frequency_generator.elf";}
uint64_t elapsed(){return m.milliseconds-a.loadedAt;}
void audioDelay(uint32_t ms){
 m.milliseconds+=ms;
 if(m.milliseconds>=400000)fprintf(stderr,"TIMEBOUND current=%s opens=%u closes=%u writes=%u live=%u mode=%s\n",a.current.c_str(),a.opens,a.closes,a.writes,a.live,a.mode.c_str());
 assert(m.milliseconds<400000);
 if(m.appLoaded)m.firstAppDelay=true;
 if(a.retained){
  assert(a.io==a.retainedIo&&a.kv==a.retainedKv&&a.closes==a.retainedCloses);
  assert(!cpu->appExitSafe()&&!cpu->providerStorageSafe());assert(a.live&&a.audioLoads==1&&!a.springboards);
  if(++a.retainedYields==8){printf("Production audio %s PASS: retained invocation, no late I/O/storage/unload\n",a.mode.c_str());fflush(stdout);std::_Exit(0);}
 }
}
bool audioHealth(risc_runtime_health_v1* h){
 assert(++m.healthCalls<3000000);h->uptime_ms=(uint32_t)m.milliseconds;
 if(mode("health-failure")&&audio()&&a.writes>=4)return false;
 return !((a.current=="default.elf"||a.current=="clock.elf")&&a.ready);
}
bool audioLog(const char* line){
 puts(line);
 if(!strncmp(line,"WATCH_CLOCK ready",17)){a.ready=true;if(a.clocks==1)assert(running->launch("frequency_generator.elf"));}
 if(strstr(line,"cleanup-unconfirmed")){
  assert(mode("close-retained")||mode("open-retained")||mode("write-retained"));
  a.retained=true;a.retainedIo=a.io;a.retainedKv=a.kv;a.retainedCloses=a.closes;
 }
 return true;
}
bool tap(unsigned start,unsigned end,uint16_t& x,uint16_t& y){if(elapsed()>=start&&elapsed()<end){x=120;y=219;return true;}return false;}
bool audioGpioOpen(uint8_t p,bool o,bool v,bool pull){++a.io;return gpioOpen(p,o,v,pull);}
bool audioGpioWrite(uint8_t p,bool v){++a.io;return gpioWrite(p,v);}
bool audioGpioRead(uint8_t p,bool* v){++a.io;return gpioRead(p,v);}
bool audioGpioPwm(uint8_t p,uint32_t hz,uint16_t duty,uint16_t maximum){++a.io;return gpioPwm(p,hz,duty,maximum);}
bool audioGpioClose(uint8_t p){++a.io;return gpioClose(p);}
bool audioI2c(uint8_t p,uint8_t address,const uint8_t* tx,size_t tn,uint8_t* rx,size_t rn,uint32_t ms){
 ++a.io;
 if(p==1&&audio()){
  if(mode("touch-failure")&&a.writes>=4){a.fault=true;return false;}
  assert(address==0x38&&tn==1&&tx[0]==2&&rn==13);memset(rx,0,rn);++m.touchReads;
  uint16_t x=0,y=0;bool down=tap(100,170,x,y);
  if(mode("restart"))down=down||tap(650,720,x,y)||tap(1000,1070,x,y);
  if(mode("display-failure")&&elapsed()>=650&&elapsed()<720){down=true;x=60;y=110;}
  if(mode("touch-back")&&elapsed()>=1600&&elapsed()<1670){down=true;x=24;y=18;}
  if(down){rx[0]=1;rx[1]=(uint8_t)(x>>8);rx[2]=(uint8_t)x;rx[3]=(uint8_t)(y>>8);rx[4]=(uint8_t)y;}return true;
 }
 if(p==0&&address==0x34&&tn==1&&tx[0]==0x49&&rn==1){
  bool back=a.current=="springboard.elf"&&elapsed()>250&&!a.backs;
  if(audio()&&!mode("touch-back")&&!mode("display-failure")){
   if(mode("idle-sleep"))back=a.sleeps&&elapsed()>62000&&!a.backs;
   else if(mode("alarm-preempt"))back=(a.alarmOpens&&elapsed()>4000&&!a.backs)||(a.acks&&elapsed()>5500&&a.backs==1);
   else back=elapsed()>1800&&!a.backs;
  }
  if(back){m.registers[0][0x49]|=8;++a.backs;}
 }
 if(p==0&&address==0x51&&tn==1&&tx[0]==2&&rn==7){unsigned seconds=(unsigned)(m.milliseconds/1000);m.registers[1][2]=(uint8_t)(((seconds%60)/10)*16+seconds%10);unsigned minutes=40+seconds/60;m.registers[1][3]=(uint8_t)((minutes/10)*16+minutes%10);}
 return i2cTransfer(p,address,tx,tn,rx,rn,ms);
}
bool audioSpi(uint8_t p,const uint8_t* tx,uint8_t* rx,size_t n,uint32_t ms){++a.io;if(mode("display-failure")&&audio()&&a.writes>=4&&!a.fault){a.fault=true;return false;}return spiTransfer(p,tx,rx,n,ms);}
bool audioOpen(uint8_t unit,uint8_t clk,uint8_t ws,uint8_t data,uint32_t rate){
 ++a.io;assert(unit==1&&clk==48&&ws==15&&data==46&&!a.live);assert(rate==16000||rate==8000);a.live=true;a.rate=rate;++a.opens;a.started=true;
 if(rate==8000){assert(mode("alarm-preempt")&&a.toneCloses==1);++a.alarmOpens;}
 if(mode("open-failure")||mode("open-retained")){a.fault=true;return false;}return true;
}
bool audioWrite(uint8_t unit,const int16_t* pcm,size_t frames,size_t* done,uint32_t ms){
 ++a.io;assert(unit==1&&a.live&&pcm&&frames<=256&&ms<=40);++a.writes;*done=frames;
 for(size_t i=0;i<frames;++i)assert(pcm[2*i]==pcm[2*i+1]);
 if((mode("partial-write")||mode("write-failure")||mode("write-retained"))&&a.writes==4){a.fault=true;*done=mode("partial-write")?frames/2:0;return mode("partial-write");}
 m.milliseconds+=frames*1000/a.rate;return true;
}
bool audioClose(uint8_t unit){++a.io;assert(unit==1&&a.live);++a.closes;if(mode("close-retained")||mode("open-retained")||mode("write-retained"))return false;if(a.rate==16000)++a.toneCloses;a.live=false;return true;}
int32_t audioGet(void*,uint32_t ns,const char* key,void* bytes,uint32_t cap,uint32_t* size){
 assert(!a.retained&&ns>=1&&ns<=5);++a.kv;if(a.live){assert(cpu->providerStorageSafe());++a.liveKv;}
 auto found=a.values.find(std::to_string(ns)+":"+key);*size=0;if(found==a.values.end())return RISC_KEY_VALUE_NOT_FOUND;
 assert(found->second.size()<=cap);memcpy(bytes,found->second.data(),found->second.size());*size=(uint32_t)found->second.size();return RISC_KEY_VALUE_OK;
}
int32_t audioPut(void*,uint32_t ns,const char* key,const void* bytes,uint32_t n){
 assert(mode("alarm-preempt")&&!a.retained&&ns==4&&n==ALARM_RECORD_SIZE);++a.kv;++m.storageWrites;
 a.values[std::to_string(ns)+":"+key]=std::vector<uint8_t>((const uint8_t*)bytes,(const uint8_t*)bytes+n);
 alarm_occurrence occurrence{};assert(alarm_occurrence_decode(&occurrence,(const uint8_t*)bytes,n,ALARM_KIND_ALARM));if(occurrence.state==ALARM_OCC_ACKED)++a.acks;return RISC_KEY_VALUE_OK;
}
}
extern "C" void production_test_loading(const char* path){
 ++m.moduleLoads;const char* name=strrchr(path,'/');name=name?name+1:path;
 if(strcmp(name,"driver.elf")){
  assert(!a.live);a.current=name;a.loadedAt=m.milliseconds;a.backs=0;a.ready=false;++m.appLoads;m.appLoaded=true;
  if(a.current=="default.elf"||a.current=="clock.elf")++a.clocks;
  else if(a.current=="springboard.elf")++a.springboards;
  else {assert(audio());++a.audioLoads;if(mode("alarm-preempt")){
   uint32_t current=0;assert(alarm_calendar_seconds(2026,10,4,0,40,0,&current));current+=(uint32_t)(m.milliseconds/1000);
   alarm_config config{1,current+2,current,0,ALARM_KIND_ALARM,1};alarm_config_encode(&config,a.config);
   a.values["3:alarm_cfg"]=std::vector<uint8_t>(a.config,a.config+sizeof(a.config));a.values["1:alert_mode"]={ALARM_MODE_SOUND};
  }}
 }
}
extern "C" void production_test_loaded(void* module){assert(module);a.modules[module]=m.appLoaded?a.current:"driver";}
extern "C" void production_test_unloading(void* module){assert(!a.retained&&!a.live);++m.moduleUnloads;if(a.modules[module]!="driver"){++m.appUnloads;m.appLoaded=false;}a.modules.erase(module);}
int main(int argc,char** argv){
 assert(argc==3);setvbuf(stdout,nullptr,_IONBF,0);a.mode=argv[2];
 m.registers[0][0x49]=1; // A completed crown release precedes this scenario.
 m.registers[0][3]=0x4a;m.registers[0][0x34]=0x0f;m.registers[0][0x35]=0xa0;m.registers[2][0]=0x60;
 const uint8_t date[]={0,0x40,0,4,0,0x10,0x26};memcpy(m.registers[1]+2,date,sizeof(date));
 RiscCpu::Hardware hardware{owner,now,audioDelay,audioGpioOpen,audioGpioWrite,audioGpioRead,audioGpioPwm,audioGpioClose,i2cOpen,audioI2c,i2cClose,spiOpen,spiBegin,audioSpi,spiEnd,spiClose};
 hardware.i2sOpen=audioOpen;hardware.i2sWrite=audioWrite;hardware.i2sClose=audioClose;
 hardware.wakeValid=[](uint8_t p){assert(p==21);return true;};hardware.wakeArm=[](uint8_t p,bool level){assert(p==21&&!level&&!a.live);return true;};hardware.wakeClear=[](uint8_t p){assert(p==21);return true;};
 hardware.timerArm=[](uint32_t duration){assert(duration==300000&&!a.live);return true;};hardware.timerClear=[](){return true;};
 hardware.lightSleep=[](uint32_t* cause){assert(!a.live);++a.sleeps;m.milliseconds+=1000;*cause=RISC_LIGHT_SLEEP_WAKE_GPIO;return true;};
 hardware.radioJoin=[](const char*,const char*){assert(!"No RF activity permitted");return false;};hardware.radioState=[](uint8_t* s,int8_t* r){*s=0;*r=-127;return true;};hardware.radioLeave=[](){return true;};
 hardware.radioAddresses=[](uint8_t*,uint8_t*){assert(false);return false;};hardware.radioScanStart=[](){assert(false);return false;};hardware.radioScanPoll=[](garden_radio_scan_result_v1*){assert(false);return false;};hardware.radioScanCancel=[](){return true;};hardware.radioIdle=[](){return true;};
 RiscCpu::Port port(hardware);cpu=&port;const RiscBoot::KeyValueBackend kv={nullptr,audioGet,audioPut};
 RiscBoot::Runtime runtime({owner,audioHealth,audioDelay,audioLog,bind,&kv,[](){return cpu->appExitSafe();},[](){return cpu->providerStorageSafe();}});running=&runtime;
 if(!runtime.prepare(argv[1])){fprintf(stderr,"prepare: %s\n",runtime.error());return 2;}if(!runtime.run()){fprintf(stderr,"run: %s\n",runtime.error());return 3;}
 printf("Observed audio=%u clocks=%u springboards=%u opens=%u closes=%u writes=%u\n",a.audioLoads,a.clocks,a.springboards,a.opens,a.closes,a.writes);
 assert(a.audioLoads==1&&a.clocks==(a.springboards?3u:2u)&&!a.live&&a.opens>=1&&a.closes>=a.opens&&a.toneCloses>=1);
 assert(m.moduleLoads==m.moduleUnloads&&m.appLoads==m.appUnloads&&a.modules.empty()&&port.quiescent());assert(!m.radioActivity&&!m.rtcWrites);for(bool pin:m.pins)assert(!pin);
 if(mode("restart"))assert(a.opens==2&&a.toneCloses==2);if(mode("idle-sleep"))assert(a.sleeps==1&&a.opens==1);
 if(mode("alarm-preempt"))assert(a.alarmOpens&&a.acks&&a.toneCloses==1&&a.liveKv);if(mode("open-failure"))assert(!a.writes);
 if(mode("partial-write")||mode("write-failure")||mode("health-failure"))assert(a.writes==4);
 if(mode("crown-back")||mode("touch-back")||mode("restart"))assert(a.springboards==1);
 printf("Production audio %s PASS: opens=%u closes=%u writes=%u liveKV=%u alarms=%u ack=%u sleep=%u modules=%u/%u; full-store policy unchanged, no hardware I/O\n",a.mode.c_str(),a.opens,a.closes,a.writes,a.liveKv,a.alarmOpens,a.acks,a.sleeps,m.moduleLoads,m.moduleUnloads);return 0;
}

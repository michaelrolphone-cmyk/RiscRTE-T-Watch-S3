#include "ports/esp32s3/CpuPort.h"
#include "fixture.h"
#include "AlarmRecords.h"
#ifdef POINTS_CROSS_LAYER
#include "PointsRecords.h"
#endif
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <unistd.h>
static std::string mode;
static RiscCpu::Port*cpu;
static uint64_t ticks;
static unsigned reads,rtcReads,steps,holds,unholds,lightCalls,deepCalls,finiCalls,quiesces,serviceWhileHeld;
static uint32_t timer;
static bool held,nativeRetained,restored,postRestore,revoked;
static int result=999;
static std::vector<std::string>events;
extern "C" const char*probe_mode(){return mode.c_str();}
extern "C" void probe_event(const char*s){events.push_back(s);if(!strcmp(s,"app-fini"))finiCalls++;if(!strcmp(s,"sleep-quiesce"))quiesces++;if(!strcmp(s,"post-restore-kv-live"))postRestore=true;if(!strcmp(s,"permanent-revocation-proved"))revoked=true;}
extern "C" void probe_delay(unsigned ms){assert(!nativeRetained);ticks+=ms;}
extern "C" void probe_service(const char*s){if(held||nativeRetained)serviceWhileHeld++;assert(!held&&!nativeRetained);if(!strcmp(s,"step"))steps++;probe_event(s);}
extern "C" void probe_result(int rc){result=rc;}
static uint32_t rtcSeconds(){uint32_t s=0;assert(alarm_calendar_seconds(2026,10,4,0,0,0,&s));return s;}
extern "C" uint32_t probe_expected_deadline(){
#ifdef POINTS_CROSS_LAYER
 return rtcSeconds()+600;
#else
 return rtcSeconds()+1000;
#endif
}
extern "C" bool probe_rtc(twatch_rtc_time_v1*t){assert(!held&&!nativeRetained);rtcReads++;uint32_t s=ticks/1000;*t={2026,10,4,0,uint8_t(s/3600),uint8_t(s/60%60),uint8_t(s%60)};return true;}
static bool owner(){return true;}
static bool health(risc_runtime_health_v1*h){h->uptime_ms=ticks;return true;}
static bool logLine(const char*s){probe_event(s);return true;}
static uint64_t now(){return ticks;}
static void delay(uint32_t ms){probe_delay(ms);}
static bool gpioOpen(uint8_t,bool,bool,bool){return true;}
static bool gpioWrite(uint8_t,bool){assert(!nativeRetained);return true;}
static bool gpioRead(uint8_t,bool*value){assert(!nativeRetained);*value=true;return true;}
static bool gpioPwm(uint8_t,uint32_t,uint16_t,uint16_t){return true;}
static bool gpioClose(uint8_t){assert(!held&&!nativeRetained);return true;}
static bool busClose(uint8_t){return true;}
static bool i2cOpen(uint8_t,uint8_t,uint8_t,uint32_t){return true;}
static bool i2cTransfer(uint8_t,uint8_t,const uint8_t*,size_t,uint8_t*,size_t,uint32_t){assert(!nativeRetained);return true;}
static bool spiOpen(uint8_t,int16_t,int16_t,int16_t){return true;}
static bool spiBegin(uint8_t,uint8_t,uint32_t,uint8_t,uint32_t){return true;}
static bool spiTransfer(uint8_t,const uint8_t*,uint8_t*,size_t,uint32_t){return true;}
static bool spiEnd(uint8_t,uint8_t,uint32_t){return true;}
static bool valid(uint8_t pin){return pin==7;}
static bool ready(){return true;}
static bool deepArm(uint8_t pin,bool high,bool pullup){assert(pin==7&&!high&&pullup);deepCalls++;return mode=="native-return";}
static bool deepClear(uint8_t pin,bool pullup){assert(pin==7&&pullup);return true;}
static bool deepHold(uint8_t pin,bool enable){assert(pin==6);if(enable){assert(!held);held=true;holds++;if(mode!="old-order")assert(reads>=5&&rtcReads&&steps);}else{unholds++;if(mode=="unhold-retained"){nativeRetained=true;return false;}held=false;restored=true;}return true;}
static void deepSleep(){assert(mode=="native-return");nativeRetained=true;}
static bool lightArm(uint8_t pin,bool high){assert(pin==7&&!high);return true;}
static bool lightClear(uint8_t pin){assert(pin==7);return true;}
static bool timerArm(uint32_t ms){timer=ms;return true;}
static bool timerClear(){return true;}
static bool lightSleep(uint32_t*cause){lightCalls++;assert(!held&&timer==300000);ticks+=timer;*cause=RISC_LIGHT_SLEEP_WAKE_TIMER;return true;}
static bool bind(RiscBoot::Runtime&r){return cpu->bind(r);}
static bool exitSafe(){return cpu->appExitSafe();}
static int32_t get(void*,uint32_t ns,const char*key,void*data,uint32_t cap,uint32_t*size){assert(!held&&!nativeRetained);reads++;*size=0;
#ifdef POINTS_CROSS_LAYER
 if(ns==5&&!strcmp(key,"points_cfg")){
  points_config c{};c.revision=1;c.created=rtcSeconds();
  for(unsigned i=0;i<POINTS_MAX;i++)c.points[i].kind=POINTS_BREAK;
  c.points[0]={POINTS_LUNCH,1,0,127,10,10,30};uint8_t b[64];points_config_encode(&c,b);
  assert(cap>=64);memcpy(data,b,64);*size=64;return RISC_KEY_VALUE_OK;
 }
#endif
 if(ns==3&&!strcmp(key,"alarm_cfg")){alarm_config config={1,rtcSeconds()+1000,rtcSeconds(),0,ALARM_KIND_ALARM,1};uint8_t b[32];alarm_config_encode(&config,b);assert(cap>=32);memcpy(data,b,32);*size=32;return RISC_KEY_VALUE_OK;}return RISC_KEY_VALUE_NOT_FOUND;}
static int32_t put(void*,uint32_t,const char*,const void*,uint32_t){assert(!"Future alarm writes no occurrence");return RISC_KEY_VALUE_IO;}
static const RiscBoot::KeyValueBackend kv={nullptr,get,put};
int main(int argc,char**argv){assert(argc==3);mode=argv[2];RiscCpu::Hardware h{};h.owner=owner;h.now=now;h.sleep=delay;h.gpioOpen=gpioOpen;h.gpioWrite=gpioWrite;h.gpioRead=gpioRead;h.gpioPwm=gpioPwm;h.gpioClose=gpioClose;h.i2cOpen=i2cOpen;h.i2cTransfer=i2cTransfer;h.i2cClose=busClose;h.spiOpen=spiOpen;h.spiBegin=spiBegin;h.spiTransfer=spiTransfer;h.spiEnd=spiEnd;h.spiClose=busClose;h.deepWakeValid=valid;h.deepReady=ready;h.deepWakeArm=deepArm;h.deepWakeClear=deepClear;h.deepSleep=deepSleep;h.deepHold=deepHold;h.wakeValid=valid;h.wakeArm=lightArm;h.wakeClear=lightClear;h.lightSleep=lightSleep;h.timerArm=timerArm;h.timerClear=timerClear;
 cpu=new RiscCpu::Port(h);auto*r=new RiscBoot::Runtime({owner,health,delay,logLine,bind,&kv,exitSafe});if(!r->prepare(argv[1])){fprintf(stderr,"prepare: %s\n",r->error());return 2;}bool ok=r->run();
 bool retained=mode=="native-return"||mode=="unhold-retained";
 if(retained){if(ok||result!=-2||finiCalls||quiesces||!nativeRetained||cpu->appExitSafe()){fprintf(stderr,"retention failure ok=%d result=%d fini=%u quiesce=%u error=%s\n",ok,result,finiCalls,quiesces,r->error());return 3;}assert(strstr(r->error(),"native retention barrier"));}
 else{if(!ok){fprintf(stderr,"run: %s\n",r->error());return 4;}assert(finiCalls==1&&quiesces==1&&!held&&cpu->appExitSafe());if(mode=="old-order")assert(revoked&&reads==0);else{assert(postRestore&&restored&&reads>=10);assert(result==(mode=="resume-spi-error"?-1:0));}}
 assert(holds==1&&!serviceWhileHeld);if(mode=="hybrid-refusal")assert(lightCalls==1&&deepCalls==1&&rtcReads>=3);else assert(!lightCalls);if(mode=="crown-after-hold")assert(!deepCalls);
 printf("Actual Runtime + CpuPort + alarm service + Watch helper: %s PASS (reads=%u, RTC=%u, steps=%u, holds=%u, unholds=%u, fini=%u)\n",mode.c_str(),reads,rtcReads,steps,holds,unholds,finiCalls);fflush(stdout);_exit(0);
}

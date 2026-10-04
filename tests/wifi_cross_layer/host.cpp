#include "ports/esp32s3/CpuPort.h"
#include "fixture.h"
#include "twatch_caps.h"
#include "PortableWifiCredentials.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <map>
#include <vector>
#include <unistd.h>
static std::string mode;static RiscCpu::Port*cpu;static bool idle=true,recovered=false,joined=false;
static unsigned healthyProviderReads,uiPolls,uiOpens,uiFrames,addressesCalls;
static unsigned calls,invocations,finis,observations,consumers,lightCalls,joinCalls;static uint64_t ticks;static std::map<std::string,std::vector<uint8_t>> saved;
extern "C" void wifi_ui_event(const char*e){if(!strcmp(e,"display-open"))uiOpens++;if(!strcmp(e,"frame"))uiFrames++;if(!strcmp(e,"poll")){uiPolls++;assert(uiPolls<800);}}
extern "C" bool wifi_ui_fail_frame(){return mode=="real-ui-display-failure"&&joined&&addressesCalls>0;}
extern "C" uint32_t wifi_ui_buttons(){
 if(uiOpens>1)return 0;
 switch(uiPolls){case 20:case 40:case 60:case 180:case 200:case 220:case 240:return 32;case 80:case 260:return 2;case 160:case 320:return 1;default:return 0;}
}
extern "C" void probe_event(const char*){}
extern "C" bool probe_rtc(twatch_rtc_time_v1*t){*t={2026,10,4,0,0,0,0};return true;}
extern "C" const char*wifi_test_mode(){return mode.c_str();}
extern "C" void wifi_test_event(const char*s){if(!strcmp(s,"fini"))finis++;if(!strcmp(s,"observer-denied-radio-and-credentials"))observations++;if(!strcmp(s,"consumer-reused-saved-profile"))consumers++;}
extern "C" unsigned wifi_test_invocation(){return ++invocations;}
extern "C" void wifi_test_recover(){recovered=true;}
static bool owner(){return true;}
static bool bind(RiscBoot::Runtime&r){return cpu->bind(r);}
static bool exitSafe(){return cpu->appExitSafe();}
int main(int argc,char**argv){assert(argc==3);mode=argv[2];
 RiscCpu::Hardware h{};h.owner=owner;h.now=[]()->uint64_t{return ticks;};h.sleep=[](uint32_t ms){ticks+=ms;assert(++calls<1000);};
 h.gpioOpen=[](uint8_t,bool,bool,bool){return true;};h.gpioWrite=[](uint8_t,bool){return true;};h.gpioRead=[](uint8_t,bool*v){*v=true;return true;};h.gpioPwm=[](uint8_t,uint32_t,uint16_t,uint16_t){return true;};h.gpioClose=[](uint8_t){return true;};
 h.i2cOpen=[](uint8_t,uint8_t,uint8_t,uint32_t){return true;};h.i2cTransfer=[](uint8_t,uint8_t,const uint8_t*,size_t,uint8_t*,size_t,uint32_t){return true;};h.i2cClose=[](uint8_t){return true;};
 h.spiOpen=[](uint8_t,int16_t,int16_t,int16_t){return true;};h.spiBegin=[](uint8_t,uint8_t,uint32_t,uint8_t,uint32_t){return true;};h.spiTransfer=[](uint8_t,const uint8_t*,uint8_t*,size_t,uint32_t){return true;};h.spiEnd=[](uint8_t,uint8_t,uint32_t){return true;};h.spiClose=[](uint8_t){return true;};
 h.wakeValid=[](uint8_t p){return p==7;};h.wakeArm=[](uint8_t,bool){assert(idle);return true;};h.wakeClear=[](uint8_t){return true;};h.lightSleep=[](uint32_t*c){assert(idle);lightCalls++;ticks+=500;*c=RISC_LIGHT_SLEEP_WAKE_TIMER;return true;};h.timerArm=[](uint32_t ms){return ms==500;};h.timerClear=[](){return true;};
 h.radioJoin=[](const char*s,const char*p){assert(idle&&!strcmp(s,"FixtureOnly")&&!strcmp(p,"fixture-password"));idle=false;joined=true;joinCalls++;return mode!="join-retry"||recovered;};
 h.radioState=[](uint8_t*s,int8_t*r){assert(!idle&&joined);*s=2;*r=-43;return true;};
 h.radioLeave=[](){if(joined&&!recovered&&(mode=="cleanup-retained"||mode=="cleanup-retry"))return false;idle=true;joined=false;return true;};
 h.radioAddresses=[](uint8_t*s,uint8_t*a){addressesCalls++;memset(s,0,12);memset(a,0,12);s[0]=192;s[1]=0;s[2]=2;s[3]=10;return true;};
 h.radioScanStart=[](){assert(idle);idle=false;return true;};h.radioScanPoll=[](garden_radio_scan_result_v1*r){assert(!idle);*r={};r->struct_size=sizeof(*r);r->state=GARDEN_RADIO_SCAN_DONE;r->count=1;strcpy(r->entries[0].ssid,"FixtureOnly");r->entries[0].rssi=-43;r->entries[0].channel=1;return true;};h.radioScanCancel=[](){idle=true;return true;};h.radioIdle=[](){return idle;};
 static const RiscBoot::KeyValueBackend kv={nullptr,
 [](void*,uint32_t ns,const char*k,void*buf,uint32_t cap,uint32_t*n)->int32_t{
  if(ns!=6){assert(ns>=1&&ns<=5);if(!idle)healthyProviderReads++;*n=0;return RISC_KEY_VALUE_NOT_FOUND;}*n=0;auto it=saved.find(k);if(it==saved.end())return RISC_KEY_VALUE_NOT_FOUND;
  *n=it->second.size();if(cap<*n)return RISC_KEY_VALUE_BUFFER_SMALL;memcpy(buf,it->second.data(),*n);return 0;},
 [](void*,uint32_t ns,const char*k,const void*data,uint32_t n)->int32_t{
  assert(ns==6&&n<=64&&strlen(k)<=15&&saved.size()<=5);const auto*p=static_cast<const uint8_t*>(data);saved[k]=std::vector<uint8_t>(p,p+n);return 0;}};
 if(mode.rfind("real-ui",0)==0){
  const risc_key_value_v1 direct={1,sizeof(direct),nullptr,
   [](void*,const char*k,void*b,uint32_t c,uint32_t*n)->int32_t{return kv.get(nullptr,6,k,b,c,n);},
   [](void*,const char*k,const void*b,uint32_t n)->int32_t{return kv.put(nullptr,6,k,b,n);}};
  const portable_wifi_credentials profile={"FixtureOnly","fixture-password"};
  assert(portable_wifi_credentials_save(&direct,&profile)==PORTABLE_WIFI_CREDENTIALS_SAVED);
 }
 cpu=new RiscCpu::Port(h);auto*r=new RiscBoot::Runtime({owner,[](risc_runtime_health_v1*h){h->uptime_ms=ticks;return mode!="real-ui"||uiOpens<2;},h.sleep,[](const char*s){assert(!strstr(s,"fixture-password")&&!strstr(s,"FixtureOnly"));return true;},bind,&kv,exitSafe,[](){return cpu->providerStorageSafe();}});
 if(!r->prepare(argv[1])){fprintf(stderr,"prepare: %s\n",r->error());return 2;}
 bool ok=r->run();if(mode=="real-ui-display-failure"){
  if(!ok){fprintf(stderr,"actual UI display failure: %s\n",r->error());return 5;}
  assert(uiOpens==1&&joinCalls==1&&addressesCalls&&!observations&&!consumers&&idle&&cpu->quiescent());
  puts("Actual Wi-Fi app ordinary display failure: radio cleaned before Runtime pre-fini barrier PASS");delete r;delete cpu;return 0;
 }if(mode=="real-ui"){if(!ok){fprintf(stderr,"real UI: %s\n",r->error());return 4;}assert(uiOpens==2&&uiFrames>=5&&joinCalls==2&&addressesCalls&&observations==1&&consumers==1&&idle&&cpu->quiescent()&&healthyProviderReads);printf("Actual Wi-Fi Settings ELF + Runtime + CpuPort + production radio driver + real alarm service: saved-profile scan/connect/IP/Back/cross-app reuse PASS\n");delete r;delete cpu;return 0;}bool retained=mode=="live-return"||mode=="cleanup-retained";
 if(retained){assert(!ok&&!finis&&!observations&&!consumers&&!cpu->appExitSafe()&&strstr(r->error(),"retention barrier"));}
 else {if(!ok){fprintf(stderr,"run: %s\n",r->error());return 3;}assert(finis==2&&observations==1&&consumers==1&&invocations==2&&idle&&cpu->quiescent()&&lightCalls==2&&healthyProviderReads>=14);delete r;delete cpu;}
 assert(joinCalls==(retained?1u:mode=="join-retry"?3u:2u));
 printf("Actual Runtime + CpuPort + independently mapped Wi-Fi driver: %s PASS\n",mode.c_str());fflush(stdout);_exit(0);
}

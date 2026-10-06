#ifdef CURRENT_RADIO_IQ
#include <cstdint>
#include <cstdlib>
extern "C" {
volatile uint32_t *iq_test_register(uint32_t){std::abort();}
volatile uint32_t *iq_test_bank(void){std::abort();}
uint32_t iq_test_cycles(void){std::abort();}
uint8_t iq_test_analog_read(uint8_t,uint8_t,uint8_t){std::abort();}
void iq_test_analog_write(uint8_t,uint8_t,uint8_t,uint8_t){std::abort();}
unsigned iq_test_pbus_read(unsigned,unsigned){std::abort();}
void iq_test_delay(uint32_t){std::abort();}
}
#endif
// Reuse the unchanged delivered-Clock lowest-hardware fixture. Its original
// main remains compiled (and is never called); update-only hooks are separate.
#include "ports/esp32s3/CpuPort.h"
#define main delivered_clock_fixture_main
#define health delivered_health
#define log delivered_log
#include "../production_store_runtime/host.cpp"
#undef main
#undef health
#undef log
#include <RiscBankStoreV1.h>
#include <RiscHttpClientV1.h>
#ifdef STORE_ADMISSION_APP_DATA
#include "../app_data_admission_backend.h"
#endif
namespace {
std::string scenario;
unsigned confirms=0,rawCalls=0,hardwareCalls=0,storageCalls=0;
bool nativeSafe=true,confirmError=false;
RiscBoot::Runtime* current=nullptr;
uint64_t nativeNow(){++hardwareCalls;return now();}
void nativeDelay(uint32_t ms){++hardwareCalls;delay(ms);}
bool updateHealth(risc_runtime_health_v1* h) {
  if(scenario=="early-health"&&m.appLoaded)return false;
  if(scenario=="frame-health-loss"&&m.rows)return false;
  return delivered_health(h);
}
bool updateLog(const char* line) {
  if(!strcmp(line,"WATCH_CLOCK error=paired-boot-confirm")){
    assert(scenario=="confirm-refused"||scenario=="retained");confirmError=true;puts(line);return true;
  }
  if(!strncmp(line,"WATCH_CLOCK mode=",17)&&scenario=="retained")nativeSafe=false;
  return delivered_log(line);
}
bool safe(){return nativeSafe&&cpu->appExitSafe();}
bool storageSafe(){return nativeSafe&&cpu->providerStorageSafe();}
bool confirm(){
  // This is the native owner's acknowledgement boundary, reached only after
  // the real graph/providers and actual Clock have completed their startup.
  assert(current&&current->active()&&!current->retained()&&!m.ready);
  assert(m.appLoaded&&m.frames>0&&m.frameRows==240&&m.brightness>0&&m.touchReads>0);
#ifdef CURRENT_APPS_PROFILE
  assert(m.appSettingsReads==3&&m.quickSettingsReads==4&&m.appPointsReads==1&&nativeSafe);
#else
  assert(m.appSettingsReads==2&&m.appPointsReads==1&&nativeSafe);
#endif
  bool nonzero=false;for(auto pixel:m.frame)nonzero|=pixel!=0;assert(nonzero);
  risc_runtime_capability_v1 grant{};grant.struct_size=sizeof(grant);
  assert(!current->acquire("radio.iq",1,0,&grant));
  assert(!current->acquire(RISC_HTTP_CLIENT_CAPABILITY,1,0,&grant));
  assert(!current->acquire(RISC_BANK_STORE_CAPABILITY,1,0,&grant));
  ++confirms;return scenario!="confirm-refused";
}
// Complete provider-only native tables bind through the actual Runtime/CpuPort.
// No Clock startup path may use transport, mutate bank data, or restart.
int32_t raw(){++rawCalls;assert(!"Clock startup used native update I/O");return -1;}
const risc_http_client_v1 http={1,sizeof(http),nullptr,
  [](void*,const risc_http_request_v1*,uint64_t*){return raw();},
  [](void*,uint64_t,void*,uint32_t,uint32_t*){return raw();},
  [](void*,uint64_t,risc_http_response_v1*){return raw();},
  [](void*,uint64_t){return raw();}};
const risc_bank_store_v1 bank={1,sizeof(bank),nullptr,
  [](void*,risc_bank_status_v1*){raw();return false;},
  [](void*,const risc_bank_image_v1*,uint64_t*){return raw();},
  [](void*,const char*,const void*,uint32_t,const risc_bank_image_v1*,uint64_t*){return raw();},
  [](void*,uint64_t,risc_bank_status_v1*){return raw();},
  [](void*,uint64_t,const void*,uint32_t){return raw();},
  [](void*,uint64_t){return raw();},[](void*,uint64_t){return raw();},
  [](void*,uint64_t){return raw();},[](void*,uint64_t){raw();return false;},
  [](void*,uint32_t,void*,uint32_t,uint32_t*){return raw();}};
bool updateBind(RiscBoot::Runtime& r){
  if(!cpu->bind(r))return false;
  return scenario=="missing-bank"||r.registerPlatform(RISC_BANK_STORE_CAPABILITY,1,RiscBoot::Runtime::Scope::Global,0,&bank);
}
}
int main(int argc,char** argv){
  assert(argc==3);scenario=argv[2];setvbuf(stdout,nullptr,_IONBF,0);
  m.registers[0][3]=0x4a;m.registers[0][0x34]=0x0f;m.registers[0][0x35]=0xa0;
  m.registers[2][0]=0x60;
#ifdef CURRENT_APPS_PROFILE
  JsonDocument motionBoard;
  assert(RiscBoot::readJson((std::string(argv[1])+"/board.json").c_str(),motionBoard));
  for(auto d:motionBoard["devices"].as<ArduinoJson::JsonArrayConst>())
    if(d["instance_id"].as<unsigned>()==7)m.registers[3][0]=d["config"]["chip_id"].as<uint8_t>();
  assert(m.registers[3][0]==0x13 || m.registers[3][0]==0x16);
#endif
  const uint8_t date[]={0,0x40,0,4,0,0x10,0x26};memcpy(m.registers[1]+2,date,sizeof(date));
  RiscCpu::Hardware hardware{owner,nativeNow,nativeDelay,
    [](uint8_t p,bool o,bool i,bool u){++hardwareCalls;return gpioOpen(p,o,i,u);},
    [](uint8_t p,bool v){++hardwareCalls;return gpioWrite(p,v);},
    [](uint8_t p,bool* v){++hardwareCalls;return gpioRead(p,v);},
    [](uint8_t p,uint32_t h,uint16_t d,uint16_t x){++hardwareCalls;return gpioPwm(p,h,d,x);},
    [](uint8_t p){++hardwareCalls;return gpioClose(p);},
    [](uint8_t p,uint8_t a,uint8_t b,uint32_t h){++hardwareCalls;return i2cOpen(p,a,b,h);},
    [](uint8_t p,uint8_t a,const uint8_t* t,size_t n,uint8_t* r,size_t z,uint32_t ms){++hardwareCalls;return i2cTransfer(p,a,t,n,r,z,ms);},
    [](uint8_t p){++hardwareCalls;return i2cClose(p);},
    [](uint8_t p,int16_t c,int16_t o,int16_t i){++hardwareCalls;return spiOpen(p,c,o,i);},
    [](uint8_t p,uint8_t c,uint32_t h,uint8_t d,uint32_t ms){++hardwareCalls;return spiBegin(p,c,h,d,ms);},
    [](uint8_t p,const uint8_t* t,uint8_t* r,size_t n,uint32_t ms){++hardwareCalls;return spiTransfer(p,t,r,n,ms);},
    [](uint8_t p,uint8_t c,uint32_t ms){++hardwareCalls;return spiEnd(p,c,ms);},
    [](uint8_t p){++hardwareCalls;return spiClose(p);}};
  hardware.i2sOpen=[](uint8_t,uint8_t,uint8_t,uint8_t,uint32_t){raw();return false;};
  hardware.i2sWrite=[](uint8_t,const int16_t*,size_t,size_t*,uint32_t){raw();return false;};
  hardware.i2sClose=[](uint8_t){raw();return false;};
#ifdef CURRENT_APPS_PROFILE
  // Bluetooth defaults to Off. Startup may query the native controller but
  // must never initialize or send packets without an explicit saved choice.
  hardware.hciOpen=[](){raw();return false;};
  hardware.hciSend=[](uint8_t,const uint8_t*,size_t,uint32_t){raw();return false;};
  hardware.hciReceive=[](uint8_t*,uint8_t*,size_t,size_t*,uint32_t){raw();return false;};
  hardware.hciClose=[](){raw();return false;};
  hardware.hciIdle=[](){return true;};hardware.hciSafe=[](){return true;};
  hardware.i2sOpenRx=[](uint8_t,uint8_t,uint8_t,uint32_t){raw();return false;};
  hardware.i2sRead=[](uint8_t,int16_t*,size_t,size_t*,uint32_t){raw();return false;};
#endif
  hardware.radioJoin=[](const char*,const char*){++m.radioActivity;return false;};
  hardware.radioState=[](uint8_t* state,int8_t* rssi){*state=0;*rssi=-127;return true;};
  hardware.radioLeave=[](){return true;};
  hardware.radioAddresses=[](uint8_t*,uint8_t*){raw();return false;};
  hardware.radioScanStart=[](){++m.radioActivity;return false;};
  hardware.radioScanPoll=[](garden_radio_scan_result_v1*){raw();return false;};
  hardware.radioScanCancel=[](){return true;};hardware.radioIdle=[](){return true;};
#ifdef CURRENT_RADIO_IQ
  hardware.radioIqReady=[](){std::abort();return false;};
#endif
  hardware.httpClient=&http;hardware.httpIdle=[](){return true;};hardware.httpSafe=[](){return true;};
  RiscCpu::Port port(hardware);cpu=&port;
  const RiscBoot::KeyValueBackend kv={nullptr,
    [](void* c,uint32_t ns,const char* key,void* out,uint32_t cap,uint32_t* size){++storageCalls;return kvGet(c,ns,key,out,cap,size);},
    [](void* c,uint32_t ns,const char* key,const void* data,uint32_t size){++storageCalls;return kvPut(c,ns,key,data,size);}
#ifdef CURRENT_APPS_PROFILE
    ,RISC_KEY_VALUE_V2_BLOB_MAX
#endif
  };
#ifdef STORE_ADMISSION_APP_DATA
  const auto appData=admissionAppData(&storageCalls);
#endif
  RiscBoot::Runtime runtime({owner,updateHealth,nativeDelay,updateLog,updateBind,&kv,safe,storageSafe,confirm
#ifdef STORE_ADMISSION_APP_DATA
    ,&appData
#endif
  });current=&runtime;
  assert(!runtime.confirmBoot()&&!confirms);
  const bool prepared=runtime.prepare(argv[1]);
  if(scenario=="admit"||scenario=="missing-bank"){
    assert(!m.moduleLoads&&!m.milliseconds&&!rawCalls&&!hardwareCalls&&!storageCalls&&!m.storageWrites&&port.quiescent()&&!confirms);
    printf("{\"prepared\":%s,\"error\":\"%s\",\"hardware_calls\":%u,\"storage_calls\":%u,\"confirm_calls\":%u}\n",prepared?"true":"false",runtime.error(),hardwareCalls,storageCalls,confirms);
    return (prepared==(scenario=="admit"))?0:2;
  }
  if(!prepared){fprintf(stderr,"prepare: %s\n",runtime.error());return 2;}
  const bool ran=runtime.run();
  assert(!runtime.confirmBoot());
#ifdef CURRENT_APPS_PROFILE
  // Current virtual defaults may expire one inactive ledger; kvPut still
  // validates the exact namespace/key/size/content and rejects any config write.
  assert(m.storageWrites<=1&&(!m.storageWrites||startupStorageOk()));
  if(scenario=="healthy")assert(startupStorageOk()&&m.hidBondReads==4);
  assert(!m.rtcWrites&&!m.radioActivity&&!rawCalls);
#else
  assert(!m.rtcWrites&&!m.storageWrites&&!m.radioActivity&&!rawCalls);
#endif
  assert(!memcmp(m.registers[1]+2,date,sizeof(date)));
  if(scenario=="retained"){
    assert(!ran&&runtime.retained()&&!confirms&&!m.ready&&confirmError);
    assert(m.appLoads==1&&m.appUnloads==0&&m.moduleLoads>m.moduleUnloads);
  }else{
    if(!ran){fprintf(stderr,"run: %s\n",runtime.error());return 3;}
    assert(m.appLoads==1&&m.appUnloads==1&&m.moduleLoads==m.moduleUnloads);
    assert(!m.buses[0]&&!m.buses[1]&&!m.spi&&!m.held&&port.quiescent());for(bool pin:m.pins)assert(!pin);
    if(scenario=="healthy"){assert(m.ready&&confirms==1&&!confirmError);}
    else if(scenario=="confirm-refused"){assert(!m.ready&&confirms==1&&confirmError);}
    else if(scenario=="early-health"){assert(!m.ready&&!confirms&&!m.frames);}
    else {assert(scenario=="frame-health-loss"&&!m.ready&&!confirms&&m.rows&&m.frameRows==240);}
  }
  printf("UPDATE_CLOCK_RESULT {\"scenario\":\"%s\",\"ready\":%s,\"confirm_calls\":%u,\"frames\":%u,\"namespace1_reads\":%u,\"namespace5_reads\":%u,\"modules_loaded\":%u,\"modules_unloaded\":%u,\"retained\":%s,\"raw_update_calls\":%u,\"radio_calls\":%u}\n",
    scenario.c_str(),m.ready?"true":"false",confirms,m.frames,m.appSettingsReads,m.appPointsReads,m.moduleLoads,m.moduleUnloads,runtime.retained()?"true":"false",rawCalls,m.radioActivity);
  // Native retention deliberately keeps the active graph alive. Firmware never
  // destroys this owner while retained; GraphV2 correctly aborts if asked to do
  // so. End this isolated process after assertions instead of inventing cleanup.
  if(scenario=="retained")std::_Exit(0);
  return 0;
}

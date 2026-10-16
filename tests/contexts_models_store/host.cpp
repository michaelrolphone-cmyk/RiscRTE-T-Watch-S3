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
#define production_test_loading disabled_production_test_loading
#define production_test_loaded disabled_production_test_loaded
#define production_test_unloading disabled_production_test_unloading
#define risc_test_native_loading disabled_risc_test_native_loading
#define risc_test_native_loaded disabled_risc_test_native_loaded
#define risc_test_native_unloading disabled_risc_test_native_unloading
#define kvGet disabled_kvGet
#include "../production_store_runtime/host.cpp"
#undef production_test_loading
#undef production_test_loaded
#undef production_test_unloading
#undef risc_test_native_loading
#undef risc_test_native_loaded
#undef risc_test_native_unloading
#undef kvGet
#undef main
#undef health
#undef log

namespace {
std::string currentApp,pendingApp;
std::map<void*,std::string> apps;
unsigned audioModelReads=0,radioModelReads=0,micOpens=0,micReads=0,micCloses=0,sleepCalls=0,wakeClears=0,iqProbes=0,failedAtReads=0;
bool micLive=false,closeRefused=false;
int32_t kvGet(void*c,uint32_t ns,const char*key,void*bytes,uint32_t cap,uint32_t*size) {
  auto copy=[&](const uint8_t*value,uint32_t n){*size=n;if(cap<n)return int32_t(RISC_KEY_VALUE_BUFFER_SMALL);assert(bytes);memcpy(bytes,value,n);return int32_t(RISC_KEY_VALUE_OK);};
  if(ns==1&&!strcmp(key,"contexts_on")){const uint8_t b[]={'C',1,1,0xa4};return copy(b,4);}
  if(ns==1&&!strcmp(key,"sleep_idle")){const uint8_t b[]={0x54,1,5,0,0xa0};return copy(b,5);}
  if(ns==1&&!strcmp(key,"sleep_mode")){const uint8_t b[]={0x53,1,0,0xa5};return copy(b,4);}
  if(ns==1&&!strcmp(key,"tap_wake")){
    uint8_t b[]={0x57,1,0,3,12,0,0,0};uint16_t crc=0xffff;
    for(unsigned i=0;i<6;i++){crc^=uint16_t(b[i])<<8;for(unsigned j=0;j<8;j++)crc=uint16_t((crc<<1)^((crc&0x8000)?0x1021:0));}
    b[6]=uint8_t(crc);b[7]=uint8_t(crc>>8);return copy(b,8);
  }
  if(ns==7){assert(currentApp=="audio_spectrum.elf"&&!strncmp(key,"spectrum_",9));audioModelReads++;*size=0;return RISC_KEY_VALUE_NOT_FOUND;}
  if(ns==13){assert(currentApp=="waterfall.elf"&&!strncmp(key,"rf_",3));radioModelReads++;*size=0;return RISC_KEY_VALUE_NOT_FOUND;}
  return disabled_kvGet(c,ns,key,bytes,cap,size);
}
}
extern "C" void production_test_loading(const char*path) {
  ++m.moduleLoads;const char*name=strrchr(path,'/');name=name?name+1:path;
  if(strcmp(name,"driver.elf")) {
    assert(!strcmp(name,"default.elf")||!strcmp(name,"audio_spectrum.elf")||!strcmp(name,"waterfall.elf"));
    currentApp=pendingApp=name;++m.appLoads;m.appLoaded=true;if(currentApp=="default.elf")m.ready=false;
  }
}
extern "C" void production_test_loaded(void*module) {assert(module);if(!pendingApp.empty()){apps[module]=pendingApp;pendingApp.clear();m.application=module;}}
extern "C" void production_test_unloading(void*module) {
  ++m.moduleUnloads;auto found=apps.find(module);if(found!=apps.end()){++m.appUnloads;m.appLoaded=false;currentApp.clear();apps.erase(found);}
}
extern "C" void risc_test_native_loading(const char*p){production_test_loading(p);}
extern "C" void risc_test_native_loaded(const char*,void*m){production_test_loaded(m);}
extern "C" void risc_test_native_unloading(const char*,void*m){production_test_unloading(m);}

#include <RiscBankStoreV1.h>
#include <RiscHttpClientV1.h>
#ifdef STORE_ADMISSION_APP_DATA
#include "bootstrap/AppDataBackend.h"
#include "ContextsServiceV1.h"
#include "models.h"
#endif
namespace {
std::string scenario;
unsigned confirms=0,rawCalls=0,hardwareCalls=0,storageCalls=0;
int64_t realtimeEpoch=0;uint64_t realtimeAt=0;unsigned nativeSeeds=0,nativeReads=0;
unsigned fencedHardware=0,fencedStorage=0,fencedRows=0,fencedLoads=0,fencedUnloads=0;
bool nativeContextFenced=false;
bool captureFenced=false;
RiscRetainedWake::Image retainedImage{};RiscRetainedWake::Store retainedStore(retainedImage);
int32_t realtimeRead(risc_realtime_snapshot_v1*out) {
 ++nativeReads;
 if((scenario=="native-context-seed" && nativeReads==1) ||
    (scenario=="native-context-draw" && nativeReads==2)) {
  nativeContextFenced=true;fencedHardware=hardwareCalls;fencedStorage=storageCalls;
  fencedRows=m.rows;fencedLoads=m.moduleLoads;fencedUnloads=m.moduleUnloads;
  return RISC_REALTIME_CONTEXT;
 }
 *out={};out->struct_size=sizeof(*out);out->validity=realtimeEpoch?RISC_REALTIME_VALID:RISC_REALTIME_UNSET;
 if(realtimeEpoch){uint64_t elapsed=m.milliseconds-realtimeAt;out->epoch_seconds=realtimeEpoch+int64_t(elapsed/1000);out->nanoseconds=uint32_t(elapsed%1000)*1000000u;}
 out->monotonic_before_us=out->monotonic_after_us=m.milliseconds*1000;return RISC_REALTIME_OK;
}
int32_t realtimeSeed(int64_t value,uint32_t ns){assert(ns==0);realtimeEpoch=value;realtimeAt=m.milliseconds;++nativeSeeds;return RISC_REALTIME_OK;}
bool nativeSafe=true,confirmError=false;
RiscBoot::Runtime* current=nullptr;
uint64_t nativeNow(){++hardwareCalls;return now();}
void nativeDelay(uint32_t ms){++hardwareCalls;delay(ms);}
bool modelHealth();
bool updateHealth(risc_runtime_health_v1* h) {
  if(scenario.rfind("models-",0)==0){assert(++m.healthCalls<2000000);h->uptime_ms=(uint32_t)m.milliseconds;return modelHealth();}
  if(scenario=="early-health"&&m.appLoaded)return false;
  if(scenario=="frame-health-loss"&&m.rows)return false;
  assert(++m.healthCalls<2000000);h->uptime_ms=(uint32_t)m.milliseconds;
  if(scenario=="enabled-handoff")return !(audioModelReads==9&&radioModelReads==9&&micReads>=5);
  return !sleepCalls;
}
bool updateLog(const char* line) {
  if(!strcmp(line,"WATCH_CLOCK error=paired-boot-confirm")||!strcmp(line,"WATCH_CLOCK error=provider-promotion")){
    assert(scenario=="confirm-refused"||scenario=="retained");confirmError=true;puts(line);return true;
  }
  if(!strncmp(line,"WATCH_CLOCK mode=",17)&&scenario=="retained")nativeSafe=false;
  puts(line);
  if(!strncmp(line,"WATCH_CLOCK ready",17))m.ready=true;
  return true;
}
bool safe(){return nativeSafe&&cpu->appExitSafe();}
bool storageSafe(){return nativeSafe&&cpu->providerStorageSafe();}
bool confirm(){
  // This is the native owner's acknowledgement boundary, reached only after
  // the real graph/providers and actual Clock have completed their startup.
  assert(current&&current->active()&&!current->retained()&&!m.ready);
  assert(m.appLoaded&&m.frames>0&&m.frameRows==240&&m.brightness>0&&m.touchReads>0);
#ifdef CURRENT_APPS_PROFILE
  fprintf(stderr,"FEATURE_STARTUP reads settings=%u quick=%u points=%u\n",m.appSettingsReads,m.quickSettingsReads,m.appPointsReads);
  assert(m.appSettingsReads>=3&&m.quickSettingsReads>=4&&m.appPointsReads>=1&&nativeSafe);
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

unsigned modelStats[2]{}, modelReads[2]{}, readinessChecks[2]{};
bool modelRetained=false;
uint32_t retainedNamespace=0;
unsigned retainedHardware=0,retainedStorage=0,retainedLoads=0,retainedUnloads=0,retainedRows=0;
contexts_model_details_v1 modelViews[2]{};
void modelFence(uint32_t ns){
  assert(!modelRetained);modelRetained=true;retainedNamespace=ns;
  retainedHardware=hardwareCalls;retainedStorage=storageCalls;
  retainedLoads=m.moduleLoads;retainedUnloads=m.moduleUnloads;retainedRows=m.rows;
}
const uint8_t* modelRecord(uint32_t ns,const char*name,uint32_t*size){
  assert(!modelRetained&&name&&size&&(ns==2||ns==3));
  assert(currentApp==(ns==2?"audio_spectrum.elf":"waterfall.elf"));
  size_t length=0;const uint8_t* bytes=contexts_models_fixture_record(ns,name,&length);assert(bytes&&length&&length<=61252);*size=(uint32_t)length;
  return bytes;
}
RiscBoot::AppDataBackend modelBackend(){
 return {nullptr,
  [](void*,uint32_t ns,const char*name,uint32_t*size,uint64_t*revision)->int32_t{
    ++storageCalls;assert(!modelRetained);modelRecord(ns,name,size);++modelStats[ns-2];
    if(scenario==std::string("models-")+(ns==2?"audio":"radio")+"-stat-retained"){modelFence(ns);return RISC_APP_DATA_RETAINED;}
    *revision=100u+ns;return RISC_APP_DATA_OK;
  },
  [](void*,uint32_t ns,const char*name,uint64_t revision,void*buffer,uint32_t capacity,uint32_t*actual,uint64_t*currentRevision)->int32_t{
    ++storageCalls;assert(!modelRetained&&buffer&&actual&&currentRevision&&revision==100u+ns);
    uint32_t size=0;const uint8_t*bytes=modelRecord(ns,name,&size);assert(capacity>=size);++modelReads[ns-2];
    if(scenario==std::string("models-")+(ns==2?"audio":"radio")+"-read-retained"){modelFence(ns);return RISC_APP_DATA_RETAINED;}
    memcpy(buffer,bytes,size);*actual=size;*currentRevision=revision;return RISC_APP_DATA_OK;
  },
  [](void*,uint32_t,const char*,uint64_t,const void*,uint32_t)->int32_t{assert(!"model import wrote AppData");return RISC_APP_DATA_IO;},
  [](void*){return !modelRetained;}};
}
bool modelHealth(){
 assert(!modelRetained);
 if(currentApp=="default.elf"&&(modelReads[0]==3||modelReads[1]==3)){
   risc_runtime_capability_v1 grant{};grant.struct_size=sizeof(grant);
   // This observer runs in the native health callback, including checkpoints
   // inside provider loading. Newer Runtime rejects reentrant acquisitions
   // during that lifecycle interval. Inspect on the next permitted callback;
   // final assertions still require both complete model-readiness inspections.
   const unsigned beforeHardware=hardwareCalls,beforeStorage=storageCalls;
   const unsigned beforeLoads=m.moduleLoads,beforeUnloads=m.moduleUnloads;
   if(!current->acquire(CONTEXTS_SERVICE_CAPABILITY,1,0,&grant)){
     assert(!grant.slot&&!grant.generation&&!grant.api);
     assert(hardwareCalls==beforeHardware&&storageCalls==beforeStorage&&
            m.moduleLoads==beforeLoads&&m.moduleUnloads==beforeUnloads);
     return true;
   }
   const auto*service=static_cast<const contexts_service_v1*>(grant.api);
   assert(service&&service->struct_size>=CONTEXTS_MODEL_DETAILS_V1_SIZE&&service->model_details);
   contexts_status_v1 status{};status.struct_size=sizeof(status);assert(service->status(service->context,&status));
   for(unsigned i=0;i<2;++i)if(modelReads[i]==3){
     auto&view=modelViews[i];view={};view.struct_size=sizeof(view);
     assert(service->model_details(service->context,i?CONTEXTS_RADIO:CONTEXTS_AUDIO,&view));
     const auto&source=i?status.radio:status.audio;
     assert(source.signatures_ready&&source.temporal_ready&&source.neural_ready&&source.model_generation==1);
     assert(view.temporal_state==CONTEXTS_IMPORT_READY&&view.neural_state==CONTEXTS_IMPORT_READY&&view.temporal_generation==1);
     contexts_models_fixture_info expected{};assert(contexts_models_fixture_metadata(i+2,&expected));
     assert(view.positive_examples==expected.positive_examples&&view.negative_examples==expected.negative_examples&&!view.bank_error[0]&&!view.bank_error[1]&&!view.neural_error);
     assert(view.bank_size[0]==expected.bank_size[0]&&view.bank_size[1]==expected.bank_size[1]&&view.temporal_generation==expected.initial_temporal_generation);
     assert(!source.event_valid&&!source.room_valid);++readinessChecks[i];
   }
   assert(current->release(&grant));
 }
 return !(readinessChecks[0]&&readinessChecks[1]&&micReads>=5);
}
int modelResult(bool ran){
 assert(!rawCalls&&!m.rtcWrites&&!m.radioActivity);
 if(modelRetained){
   assert(!ran&&current->retained()&&currentApp==(retainedNamespace==2?"audio_spectrum.elf":"waterfall.elf"));
   assert(hardwareCalls==retainedHardware&&storageCalls==retainedStorage&&m.moduleLoads==retainedLoads&&m.moduleUnloads==retainedUnloads&&m.rows==retainedRows);
   assert(m.moduleLoads>m.moduleUnloads&&m.appLoads>m.appUnloads&&!micOpens&&!micReads&&!micCloses);
   unsigned index=retainedNamespace-2;assert(modelStats[index]==1&&modelReads[index]==unsigned(scenario.find("read-retained")!=std::string::npos));
   assert(m.appLoads==(index?4u:2u)&&confirms==(index?2u:1u));
   assert(modelStats[1-index]==(index?3u:0u)&&modelReads[1-index]==(index?3u:0u));
 }else{
   assert(ran&&!current->retained()&&m.appLoads==5&&m.appLoads==m.appUnloads&&m.moduleLoads==m.moduleUnloads&&cpu->quiescent());
   assert(confirms==3&&audioModelReads==9&&radioModelReads==9);
   assert(modelStats[0]==3&&modelStats[1]==3&&modelReads[0]==3&&modelReads[1]==3&&readinessChecks[0]&&readinessChecks[1]);
   assert(!micLive&&micOpens==1&&micCloses==1&&micReads>=5&&!sleepCalls);
 }
 printf("CONTEXTS_MODELS_RESULT {\"scenario\":\"%s\",\"apps\":%u,\"appdata_stats\":[%u,%u],\"appdata_reads\":[%u,%u],\"readiness_checks\":[%u,%u],\"temporal_generations\":[%u,%u],\"temporal_states\":[%u,%u],\"neural_states\":[%u,%u],\"positive_examples\":[%u,%u],\"negative_examples\":[%u,%u],\"retained\":%s,\"retained_namespace\":%u,\"post_retained_io\":0,\"modules_loaded\":%u,\"modules_unloaded\":%u}\n",
 scenario.c_str(),m.appLoads,modelStats[0],modelStats[1],modelReads[0],modelReads[1],readinessChecks[0],readinessChecks[1],modelViews[0].temporal_generation,modelViews[1].temporal_generation,modelViews[0].temporal_state,modelViews[1].temporal_state,modelViews[0].neural_state,modelViews[1].neural_state,modelViews[0].positive_examples,modelViews[1].positive_examples,modelViews[0].negative_examples,modelViews[1].negative_examples,modelRetained?"true":"false",retainedNamespace,m.moduleLoads,m.moduleUnloads);
 if(modelRetained)std::_Exit(0);return 0;
}
bool updateBind(RiscBoot::Runtime& r){
  if(!cpu->bind(r))return false;
  return scenario=="missing-bank"||r.registerPlatform(RISC_BANK_STORE_CAPABILITY,1,RiscBoot::Runtime::Scope::Global,0,&bank);
}
}
int main(int argc,char** argv){
  assert(argc==3);scenario=argv[2];setvbuf(stdout,nullptr,_IONBF,0);
  assert(scenario.rfind("models-",0)==0);assert(contexts_models_fixture_init());
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
    [](uint8_t p,bool o,bool i,bool u){++hardwareCalls;bool ok=gpioOpen(p,o,i,u);if(p==14&&!o)m.levels[p]=false;return ok;},
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
  hardware.realtimeRead=realtimeRead;hardware.realtimeSeed=realtimeSeed;
  hardware.i2sOpen=[](uint8_t,uint8_t,uint8_t,uint8_t,uint32_t){raw();return false;};
  hardware.i2sWrite=[](uint8_t,const int16_t*,size_t,size_t*,uint32_t){raw();return false;};
  hardware.i2sClose=[](uint8_t){
    ++micCloses;assert(micLive);
    if(scenario=="enabled-close-retained"||scenario=="enabled-capture-retained"){
      closeRefused=true;failedAtReads=micReads;
      if(scenario=="enabled-capture-retained"){
        captureFenced=true;fencedHardware=hardwareCalls;fencedStorage=storageCalls;
        fencedRows=m.rows;fencedLoads=m.moduleLoads;fencedUnloads=m.moduleUnloads;
      }
      return false;
    }
    micLive=false;return true;
  };
#ifdef CURRENT_APPS_PROFILE
  // Bluetooth defaults to Off. Startup may query the native controller but
  // must never initialize or send packets without an explicit saved choice.
  hardware.hciOpen=[](){raw();return false;};
  hardware.hciSend=[](uint8_t,const uint8_t*,size_t,uint32_t){raw();return false;};
  hardware.hciReceive=[](uint8_t*,uint8_t*,size_t,size_t*,uint32_t){raw();return false;};
  hardware.hciClose=[](){raw();return false;};
  hardware.hciIdle=[](){return true;};hardware.hciSafe=[](){return true;};
  hardware.i2sOpenRx=[](uint8_t,uint8_t,uint8_t,uint32_t){assert(!micLive);micLive=true;++micOpens;return true;};
  hardware.i2sRead=[](uint8_t,int16_t*,size_t count,size_t*got,uint32_t timeout){
    assert(micLive&&!closeRefused&&count==256&&timeout==40);++micReads;*got=0;
    return !(scenario=="enabled-capture-retained"&&micReads>=5);
  };
#endif
  hardware.radioJoin=[](const char*,const char*){++m.radioActivity;return false;};
  hardware.radioState=[](uint8_t* state,int8_t* rssi){*state=0;*rssi=-127;return true;};
  hardware.radioLeave=[](){return true;};
  hardware.radioAddresses=[](uint8_t*,uint8_t*){raw();return false;};
  hardware.radioScanStart=[](){++m.radioActivity;return false;};
  hardware.radioScanPoll=[](garden_radio_scan_result_v1*){raw();return false;};
  hardware.radioScanCancel=[](){return true;};hardware.radioIdle=[](){return true;};
#ifdef CURRENT_RADIO_IQ
  hardware.radioIqReady=[](){++iqProbes;return false;};
#ifdef CURRENT_IQ_LIFECYCLE
  hardware.radioIqPrepare=[](){std::abort();return false;};
  hardware.radioIqCleanup=[](){std::abort();return false;};
#endif
#endif
  hardware.wakeValid=[](uint8_t){return true;};hardware.wakeArm=[](uint8_t,bool){assert(!micLive);return true;};
  hardware.wakeClear=[](uint8_t){++wakeClears;assert(!micLive);return scenario!="enabled-sleep-retained";};
  hardware.lightSleep=[](uint32_t*cause){assert(!micLive&&micCloses>0);++sleepCalls;*cause=RISC_LIGHT_SLEEP_WAKE_GPIO;return scenario!="enabled-sleep-refused";};
  hardware.timerArm=[](uint32_t){assert(!micLive);return true;};hardware.timerClear=[](){return true;};
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
  const auto appData=modelBackend();
#endif
  RiscBoot::Port runtimePort{owner,updateHealth,nativeDelay,updateLog,updateBind,&kv,safe,storageSafe,confirm
#ifdef STORE_ADMISSION_APP_DATA
    ,&appData
#endif
  };
  retainedStore.boot(RISC_BOOT_POWER_ON);runtimePort.retainedWake=&retainedStore;
  RiscBoot::Runtime runtime(runtimePort);current=&runtime;
  assert(!runtime.confirmBoot()&&!confirms);
  const bool prepared=runtime.prepare(argv[1]);
  if(scenario=="admit"||scenario=="missing-bank"){
    assert(!m.moduleLoads&&!m.milliseconds&&!rawCalls&&!hardwareCalls&&!storageCalls&&!m.storageWrites&&port.quiescent()&&!confirms);
    printf("{\"prepared\":%s,\"error\":\"%s\",\"hardware_calls\":%u,\"storage_calls\":%u,\"confirm_calls\":%u}\n",prepared?"true":"false",runtime.error(),hardwareCalls,storageCalls,confirms);
    return (prepared==(scenario=="admit"))?0:2;
  }
  if(!prepared){fprintf(stderr,"prepare: %s\n",runtime.error());return 2;}
  const bool ran=runtime.run();
  return modelResult(ran);
}

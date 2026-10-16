/* Exact-byte Runtime-features cohort host proof. Production Runtime, native bank API,
 * graph/ELF validator and PairedBank run against the accepted IDF fixture.
 * VFS paths are immutable extracted views supplied by Python. The fixture
 * models an active app and IDF bank/state, never target instructions, physical
 * SPIFFS, bootloader selection or actual default-app health confirmation. */
#define private public
#include "bootstrap/Runtime.h"
#include "runtime/update/PairedBank.h"
#include "ports/esp32s3/CpuPort.h"
#undef private
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wreturn-type"
#define main unused_native_bank_fixture_main
#include "native_bank_test.cpp"
#undef main
#pragma GCC diagnostic pop
#include "../app_data_admission_backend.h"

namespace {
unsigned storageCalls=0,graphCalls=0;
bool graphAccepted=false,faultInjected=false,modeledActive=false;
std::string rfScenario;
const std::vector<uint8_t>* rfPayload=nullptr;
unsigned rfNative=0;
RiscCpu::Port* rfCpu=nullptr;

std::vector<uint8_t> readBytes(const char* name) {
  std::ifstream input(name,std::ios::binary);assert(input.good());
  return {std::istreambuf_iterator<char>(input),{}};
}
template<size_t N> void textField(JsonVariantConst value,char (&out)[N]) {
  assert(value.is<const char*>());const char* text=value.as<const char*>();
  assert(strlen(text)<N);strcpy(out,text);
}
void hashField(JsonVariantConst value,uint8_t (&out)[32]) {
  assert(value.is<const char*>());const char* text=value.as<const char*>();
  assert(strlen(text)==64);
  auto digit=[](char c){assert((c>='0'&&c<='9')||(c>='a'&&c<='f'));return c<='9'?c-'0':c-'a'+10;};
  for(unsigned i=0;i<32;++i)out[i]=uint8_t(digit(text[2*i])*16+digit(text[2*i+1]));
}
risc_bank_cohort_v1 readRequest(const char* path) {
  JsonDocument doc;assert(RiscBoot::readJson(path,doc));
  assert(doc["layout"].is<const char*>() && !strcmp(doc["layout"],RiscUpdate::Layout));
  risc_bank_cohort_v1 result{};result.struct_size=sizeof(result);
  result.store_abi=doc["store_abi"].as<uint32_t>();
  result.firmware_size=doc["firmware_size"].as<uint32_t>();
  result.store_size=doc["store_size"].as<uint32_t>();
  textField(doc["product"],result.product);textField(doc["version"],result.version);
  textField(doc["runtime_version"],result.runtime_version);textField(doc["source_repo"],result.source_repo);
  textField(doc["source_revision"],result.source_revision);
  hashField(doc["sha256"],result.sha256);hashField(doc["firmware_sha256"],result.firmware_sha256);
  hashField(doc["store_sha256"],result.store_sha256);hashField(doc["active_store_sha256"],result.active_store_sha256);
  assert(RiscUpdate::validCohortRequest(result));return result;
}
RiscCpu::Hardware rfHardware() {
  auto h=admissionHardware();
  // Register inert compiled-in capabilities required by the exact feature
  // manifests. Admission must never read or seed the clock backend.
  h.realtimeRead=[](risc_realtime_snapshot_v1*)->int32_t{++hardwareCalls;assert(false);return RISC_REALTIME_INVALID;};
  h.realtimeSeed=[](int64_t,uint32_t)->int32_t{++hardwareCalls;assert(false);return RISC_REALTIME_INVALID;};
  h.i2sOpen=[](uint8_t,uint8_t,uint8_t,uint8_t,uint32_t){++hardwareCalls;return false;};
  h.i2sWrite=[](uint8_t,const int16_t*,size_t,size_t*,uint32_t){++hardwareCalls;return false;};
  h.i2sClose=[](uint8_t){++hardwareCalls;return false;};
  h.i2sOpenRx=[](uint8_t,uint8_t,uint8_t,uint32_t){++hardwareCalls;return false;};
  h.i2sRead=[](uint8_t,int16_t*,size_t,size_t*,uint32_t){++hardwareCalls;return false;};
  h.radioJoin=[](const char*,const char*){++hardwareCalls;return false;};
  h.radioState=[](uint8_t*,int8_t*){++hardwareCalls;return false;};
  h.radioAddresses=[](uint8_t*,uint8_t*){++hardwareCalls;return false;};
  h.radioLeave=[](){++hardwareCalls;return false;};
  h.radioScanStart=[](){++hardwareCalls;return false;};
  h.radioScanPoll=[](garden_radio_scan_result_v1*){++hardwareCalls;return false;};
  h.radioScanCancel=[](){++hardwareCalls;return false;};
  h.radioIdle=[](){++hardwareCalls;return false;};
  h.hciOpen=[](){++hardwareCalls;return false;};
  h.hciSend=[](uint8_t,const uint8_t*,size_t,uint32_t){++hardwareCalls;return false;};
  h.hciReceive=[](uint8_t*,uint8_t*,size_t,size_t*,uint32_t){++hardwareCalls;return false;};
  h.hciClose=[](){++hardwareCalls;return false;};
  h.hciIdle=[](){++hardwareCalls;return false;};h.hciSafe=[](){++hardwareCalls;return false;};
  h.radioIqReady=[](){++hardwareCalls;return false;};
  h.radioIqPrepare=[](){++hardwareCalls;return false;};
  h.radioIqCleanup=[](){++hardwareCalls;return false;};
  // Only registration is exercised. No HTTP callback may run.
  h.httpClient=&bootstrapHttp;h.httpIdle=h.httpSafe=[](){++hardwareCalls;return false;};
  return h;
}
bool rfBind(RiscBoot::Runtime& instance) {
  return rfCpu->bind(instance) && RiscBankStore::bind(instance);
}
bool checkedGraph(void* context,unsigned bank) {
  ++graphCalls;
  assert(rfPayload && bank!=active);
  assert(!memcmp(flash.data()+RiscUpdate::StoreOffset[bank],rfPayload->data()+rfNative,RiscUpdate::StoreBytes));
  graphAccepted=RiscBankStore::validateStore(context,bank);
  if(graphAccepted && rfScenario=="post-admission-store-mutation")
    flash[RiscUpdate::StoreOffset[bank]+100]^=1;
  return graphAccepted;
}
bool checkedWrite(void* context,unsigned bank,unsigned region,uint32_t at,const void* data,uint32_t size) {
  const bool inject=!faultInjected && ((rfScenario=="write-native-failure" && region==0) ||
                                      (rfScenario=="write-store-failure" && region==1));
  writeFailure=inject;const bool okay=RiscBankStore::write(context,bank,region,at,data,size);
  writeFailure=false;faultInjected=faultInjected||inject;return okay;
}
bool checkedRecord(void* context,unsigned bank,const RiscUpdate::Record& value) {
  writeFailure=rfScenario=="journal-write-failure";
  const bool okay=RiscBankStore::record(context,bank,value);
  faultInjected=faultInjected||writeFailure;writeFailure=false;return okay;
}
}

int main(int argc,char** argv) {
  assert(argc==10);
  flash=readBytes(argv[1]);assert(flash.size()==0x1000000);const auto original=flash;
  auto payload=readBytes(argv[2]);rfNative=unsigned(std::stoul(argv[3]));
  active=unsigned(std::stoul(argv[4]));assert(active<2);rfScenario=argv[5];fsRoot=argv[8];
  auto request=readRequest(argv[9]);assert(request.firmware_size==rfNative);
  assert(payload.size()==rfNative+RiscUpdate::StoreBytes);rfPayload=&payload;
  uint8_t digest[32];SHA256(payload.data(),payload.size(),digest);assert(!memcmp(digest,request.sha256,32));
  SHA256(payload.data(),rfNative,digest);assert(!memcmp(digest,request.firmware_sha256,32));
  SHA256(payload.data()+rfNative,RiscUpdate::StoreBytes,digest);assert(!memcmp(digest,request.store_sha256,32));
  using namespace RiscBankStore;
  const auto old=*reinterpret_cast<const RiscUpdate::Record*>(flash.data()+RiscUpdate::JournalOffset+active*4096);
  assert(RiscUpdate::validRecord(old,active));imageSize=old.firmwareSize;
  RiscUpdate::CohortIdentity identity{};assert(RiscUpdate::readCohort("/bootfs",identity));
  const bool candidate=RiscUpdate::cohortMatches(identity,request);
  const bool reboot=rfScenario=="boot" || rfScenario=="boot-reject" || rfScenario=="boot-healthy";
  // IDF state is explicitly modeled: ordinary installed sources are confirmed;
  // the source-gate case and a new candidate remain pending. A candidate's
  // separate modeled healthy restart starts with the IDF VALID state.
  otaState=((candidate && rfScenario!="boot-healthy") || rfScenario=="unconfirmed-source")?
    ESP_OTA_IMG_PENDING_VERIFY:ESP_OTA_IMG_VALID;
  assert(prepareBoot(own,restartSafe,safe) && writes==0 && verifyRollbackLater());
  assert(identity.firmwareSize==old.firmwareSize && !memcmp(identity.firmwareSha,old.firmwareSha,32));
  assert(!strcmp(identity.runtimeVersion,RISC_BUILD_VERSION));
  const RiscBoot::KeyValueBackend kv{nullptr,
    [](void*,uint32_t,const char*,void*,uint32_t,uint32_t*)->int32_t{++storageCalls;return RISC_KEY_VALUE_IO;},
    [](void*,uint32_t,const char*,const void*,uint32_t)->int32_t{++storageCalls;return RISC_KEY_VALUE_IO;},
    RISC_KEY_VALUE_V2_BLOB_MAX};
  const auto appData=admissionAppData(&storageCalls);
  RiscCpu::Port cpu(rfHardware());rfCpu=&cpu;
  RiscBoot::Runtime instance({own,[](risc_runtime_health_v1*){return true;},[](uint32_t){},
    [](const char*){return true;},rfBind,&kv,exitSafe,safe,confirmBoot,&appData,RiscCpu::NativeRetainedWake::backend()});
  if(!instance.prepare("/bootfs"))std::cerr<<"Installed Runtime prepare failed: "<<instance.error()<<"\n";
  assert(instance.prepared_ && !hardwareCalls && !storageCalls);
  auto preserved=[&]() {
    for(auto region:{std::pair<unsigned,unsigned>{0,0x10000},{0x270000,0x80000},
        {RiscUpdate::FirmwareOffset[active],RiscUpdate::FirmwareBytes},
        {RiscUpdate::StoreOffset[active],RiscUpdate::StoreBytes},
        {RiscUpdate::JournalOffset+active*4096,4096}})
      assert(!memcmp(original.data()+region.first,flash.data()+region.first,region.second));
    assert(!hardwareCalls && !storageCalls && !bootNet.opens && !bootNet.joins);
  };
  int32_t lastError=0,beginResult=0;uint32_t failureState=RISC_BANK_IDLE;
  auto emit=[&](bool selected) {
    preserved();
    std::ofstream output(argv[6],std::ios::binary);
    output.write(reinterpret_cast<const char*>(flash.data()),flash.size());assert(output.good());
    JsonDocument proof;proof["scenario"]=rfScenario;proof["active_bank"]=active;proof["target_bank"]=1-active;
    proof["native_bytes"]=rfNative;proof["payload_bytes"]=payload.size();proof["writes"]=writes;
    proof["rollback_calls"]=rollbacks;proof["confirms"]=confirms;proof["selectors"]=selectorCalls;
    proof["selected"]=selected;proof["graph_callbacks"]=graphCalls;proof["graph_validated"]=graphAccepted;
    proof["production_graph_validator_used"]=graphCalls>0;proof["native_api_used"]=!reboot;
    proof["modeled_host_app_active"]=modeledActive;proof["modeled_idf_selection"]=true;
    proof["host_idf_valid_state"]=otaState==ESP_OTA_IMG_VALID;proof["active_is_candidate"]=candidate;
    proof["build_runtime_version"]=RISC_BUILD_VERSION;proof["error"]=lastError;
    proof["api_begin_result"]=beginResult;proof["failure_state"]=failureState;
    risc_bank_status_v1 finalStatus{};finalStatus.struct_size=sizeof(finalStatus);
    assert(transaction->status(&finalStatus));proof["transaction_state"]=finalStatus.state;
    proof["fault_injected"]=faultInjected;proof["nvs_appdata_preserved"]=true;proof["previous_pair_preserved"]=true;
    proof["hardware_calls"]=hardwareCalls;proof["storage_calls"]=storageCalls;proof["target_executed"]=false;
    std::string text;serializeJson(proof,text);std::ofstream out(argv[7]);out<<text<<"\n";assert(out.good());
  };
  if(reboot) {
    if(rfScenario=="boot-reject"){assert(candidate && pending && !confirmed);rejectBoot();assert(rollbacks==1);}
    if(rfScenario=="boot-healthy"){assert(candidate && confirmed && !pending);rejectBoot();assert(!rollbacks && !confirms);}
    emit(false);return 0;
  }
  assert(!candidate);
  // No target ELF is executed. Only the caller-active precondition is modeled;
  // all source policy preparation, request gates and transaction work is real.
  instance.active_=true;modeledActive=true;
  if(rfScenario=="unconfirmed-source") {
    assert(pending && !confirmed);
    uint64_t token=99;lastError=beginResult=api.begin_cohort(nullptr,&request,&token);
    assert(lastError==RISC_BANK_UNAVAILABLE && !token && !writes && !selectorCalls && !confirms);
    assert(!graphCalls && flash==original);emit(false);return 0;
  }
  assert(confirmed && !pending);
  transaction->io_.validateStore=checkedGraph;transaction->io_.write=checkedWrite;
  transaction->io_.record=checkedRecord;
  risc_bank_cohort_status_v1 installed{};installed.struct_size=sizeof(installed);
  assert(api.cohort_status(nullptr,&installed)==RISC_BANK_OK);
  assert(!strcmp(installed.version,identity.product.version) && !strcmp(installed.source_revision,identity.product.source_revision));
  if(rfScenario=="bad-source")request.source_revision[0]='Z';
  // Remains a syntactically valid target source, so the API accepts the request
  // and the production mounted cohort identity comparison must reject it.
  if(rfScenario=="wrong-source-request") {
    request.source_revision[0]=request.source_revision[0]=='0'?'1':'0';
    assert(RiscUpdate::validCohortRequest(request));
  }
  if(rfScenario=="bad-product")strcpy(request.product,"other-product");
  if(rfScenario=="bad-repo")strcpy(request.source_repo,"other/watch");
  if(rfScenario=="bad-version")strcpy(request.version,installed.version);
  if(rfScenario=="stale-store")request.active_store_sha256[0]^=1;
  if(rfScenario=="wrong-runtime-request")strcpy(request.runtime_version,"0.1.1");
  const bool badRequest=rfScenario=="bad-source" || rfScenario=="bad-product" || rfScenario=="bad-repo" ||
    rfScenario=="bad-version" || rfScenario=="stale-store" || rfScenario=="wrong-runtime-request";
  uint64_t token=99;lastError=beginResult=api.begin_cohort(nullptr,&request,&token);
  if(badRequest){assert(lastError==RISC_BANK_INVALID && !token && !writes && !selectorCalls);emit(false);return 0;}
  assert(lastError==RISC_BANK_OK && token);imageSize=rfNative;
  auto status=[&](){risc_bank_status_v1 s{};s.struct_size=sizeof(s);assert(api.status(nullptr,&s));return s;};
  auto reject=[&](int32_t expected) {
    assert(lastError==expected && !selectorCalls);
    failureState=status().state;assert(failureState==RISC_BANK_FAILED);
    assert(api.activate(nullptr,token)==RISC_BANK_STATE);
    if(rfScenario=="unmount-failure")assert(api.abort(nullptr,token)==RISC_BANK_RETAINED);
    mountFailure=unmountFailure=writeFailure=false;unavailableImport=nullptr;
    assert(api.abort(nullptr,token)==RISC_BANK_OK && !mounted);emit(false);
  };
  if(rfScenario=="power-begin"){emit(false);return 0;}
  if(rfScenario=="corrupt-native")payload[100]^=1;
  if(rfScenario=="corrupt-store")payload.back()^=1;
  for(size_t at=0;at<payload.size();) {
    const auto n=uint32_t(std::min(size_t(4081),payload.size()-at));
    lastError=api.write(nullptr,token,payload.data()+at,n);
    if(lastError){assert(faultInjected);reject(RISC_BANK_IO);return 0;}at+=n;
    if((at>=4096 && (rfScenario=="cancel" || rfScenario=="power-native")) ||
       (at>=rfNative+4096 && rfScenario=="power-store")) {
      if(rfScenario=="cancel")assert(api.abort(nullptr,token)==0 && status().state==RISC_BANK_IDLE);
      emit(false);return 0;
    }
  }
  lastError=api.finish(nullptr,token);
  if(rfScenario=="corrupt-native" || rfScenario=="corrupt-store"){reject(RISC_BANK_INTEGRITY);return 0;}
  assert(!lastError);
  if(rfScenario=="flash-corrupt-native")flash[RiscUpdate::FirmwareOffset[1-active]+100]^=1;
  if(rfScenario=="flash-corrupt-store")flash[RiscUpdate::StoreOffset[1-active]+100]^=1;
  mountFailure=rfScenario=="mount-failure";unmountFailure=rfScenario=="unmount-failure";
  if(rfScenario=="graph-rejection")unavailableImport="memcpy";
  for(unsigned i=0;i<12000;++i) {
    const auto s=status();
    if((rfScenario=="power-verify-native" && s.state==RISC_BANK_VERIFY_FIRMWARE) ||
       (rfScenario=="power-verify-store" && s.state==RISC_BANK_VERIFY_STORE) ||
       (rfScenario=="power-reverify-store" && s.state==RISC_BANK_REVERIFY_STORE)){emit(false);return 0;}
    if(s.state==RISC_BANK_READY)break;
    risc_bank_status_v1 next{};next.struct_size=sizeof(next);lastError=api.step(nullptr,token,&next);
    if(lastError){
      assert(rfScenario=="unmount-failure" || rfScenario=="journal-write-failure" ||
        rfScenario=="mount-failure" || rfScenario=="graph-rejection" ||
        rfScenario=="flash-corrupt-native" || rfScenario=="flash-corrupt-store" ||
        rfScenario=="post-admission-store-mutation" || rfScenario=="wrong-source-request");
      if(rfScenario=="wrong-source-request")assert(graphCalls==1 && !graphAccepted);
      const int32_t expected=rfScenario=="unmount-failure"?RISC_BANK_RETAINED:
        rfScenario=="journal-write-failure"?RISC_BANK_IO:RISC_BANK_INTEGRITY;
      reject(expected);return 0;
    }
  }
  assert(status().state==RISC_BANK_READY && graphCalls==1 && graphAccepted);
  const auto next=*reinterpret_cast<const RiscUpdate::Record*>(flash.data()+RiscUpdate::JournalOffset+(1-active)*4096);
  assert(RiscUpdate::validRecord(next,1-active) && next.firmwareSize==rfNative);
  assert(!memcmp(flash.data()+RiscUpdate::FirmwareOffset[1-active],payload.data(),rfNative));
  assert(!memcmp(flash.data()+RiscUpdate::StoreOffset[1-active],payload.data()+rfNative,RiscUpdate::StoreBytes));
  if(rfScenario=="power-ready"){emit(false);return 0;}
  selectFailure=rfScenario=="activation-unknown";lastError=api.activate(nullptr,token);
  assert(lastError==(selectFailure?RISC_BANK_RETAINED:RISC_BANK_OK) && selectorCalls==1);
  assert(api.abort(nullptr,token)==RISC_BANK_STATE);
  assert(rfScenario=="success" || rfScenario=="power-selected" || rfScenario=="rollback" || selectFailure);
  emit(true);
}

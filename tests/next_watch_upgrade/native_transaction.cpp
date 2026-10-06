/* Production PairedBank and native flash adapter, reusing Runtime's host IDF
 * boundary. Graph/ELF admission is run on exact bytes by the Python driver.
 * This does not execute target instructions, physical SPIFFS, TLS, or hardware. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wreturn-type"
#define main prior_native_fixture_main
#include "native_bank_test.cpp"
#undef main
#pragma GCC diagnostic pop

static std::vector<uint8_t> readBytes(const char* name) {
  std::ifstream file(name,std::ios::binary);assert(file.good());
  return std::vector<uint8_t>((std::istreambuf_iterator<char>(file)),{});
}
int main(int argc,char** argv) {
  assert(argc==9);
  flash=readBytes(argv[1]);assert(flash.size()==0x1000000);
  const auto original=flash;
  auto payload=readBytes(argv[2]);
  const unsigned nativeBytes=unsigned(std::stoul(argv[3]));
  active=unsigned(std::stoul(argv[4]));assert(active<2);
  const std::string scenario=argv[5];
  // The IDF boundary models a previously confirmed app for this restart only.
  // Actual target/default-app health confirmation is deliberately not claimed.
  if(scenario=="boot-healthy")otaState=ESP_OTA_IMG_VALID;
  using namespace RiscBankStore;
  const auto old=*reinterpret_cast<const RiscUpdate::Record*>(flash.data()+RiscUpdate::JournalOffset+active*4096);
  assert(RiscUpdate::validRecord(old,active));imageSize=old.firmwareSize;
  assert(prepareBoot(own,restartSafe,safe) && writes==0 && verifyRollbackLater());
  unsigned graphChecks=0;
  auto preserved=[&]() {
    for(auto region:{std::pair<unsigned,unsigned>{0,0x10000},{0x270000,0x80000},
         {RiscUpdate::FirmwareOffset[active],RiscUpdate::FirmwareBytes},
         {RiscUpdate::StoreOffset[active],RiscUpdate::StoreBytes},
         {RiscUpdate::JournalOffset+active*4096,4096}})
      assert(!memcmp(original.data()+region.first,flash.data()+region.first,region.second));
  };
  auto emit=[&](bool selected) {
    preserved();
    std::ofstream output(argv[6],std::ios::binary);
    output.write(reinterpret_cast<const char*>(flash.data()),flash.size());assert(output.good());
    std::ofstream proof(argv[7]);
    proof<<"{\"scenario\":\""<<scenario<<"\",\"active_bank\":"<<active
      <<",\"target_bank\":"<<(1-active)<<",\"native_bytes\":"<<nativeBytes
      <<",\"payload_bytes\":"<<payload.size()<<",\"writes\":"<<writes
      <<",\"graph_callbacks\":"<<graphChecks<<",\"rollback_calls\":"<<rollbacks
      <<",\"host_idf_valid_state\":"<<(otaState==ESP_OTA_IMG_VALID?"true":"false")
      <<",\"build_runtime_version\":\""<<RISC_BUILD_VERSION<<"\""
      <<",\"selected\":"<<(selected?"true":"false")
      <<",\"nvs_appdata_preserved\":true,\"previous_pair_preserved\":true,\"target_executed\":false}\n";
    assert(proof.good());
  };
  if(scenario=="boot" || scenario=="boot-reject" || scenario=="boot-healthy") {
    if(scenario=="boot-reject"){rejectBoot();assert(rollbacks==1);}
    if(scenario=="boot-healthy"){
      assert(confirmed && !pending);rejectBoot();assert(!rollbacks && !confirms);
    }
    emit(false);return 0;
  }
  assert(payload.size()==nativeBytes+RiscUpdate::StoreBytes);
  imageSize=nativeBytes;replacingFirmware=false;replacingCohort=true;
  assert(strlen(argv[8])<sizeof(scratch->cohort.runtime_version));
  strcpy(scratch->cohort.runtime_version,argv[8]);
  if(scenario=="wrong-runtime-request")strcpy(scratch->cohort.runtime_version,"0.1.1");
  struct Admission {const std::vector<uint8_t>* bytes;unsigned native;unsigned* calls;};
  Admission admission{&payload,nativeBytes,&graphChecks};
  RiscUpdate::Backend io{&admission,now,read,erase,write,invalidate,record,hashBegin,hashAdd,hashEnd,
    openApp,writeApp,finishApp,cleanup,validateFirmware,select,
    [](void* context,unsigned bank) {
      auto& witness=*static_cast<Admission*>(context);++*witness.calls;
      // The caller admitted these exact bytes using the installed production
      // Runtime graph/ELF validator. Bind that result to the actual written store.
      return operationSafe() && bank!=activeBank &&
        !memcmp(flash.data()+RiscUpdate::StoreOffset[bank],
                witness.bytes->data()+witness.native,RiscUpdate::StoreBytes);
    }};
  RiscUpdate::Transaction tx(io);assert(tx.initialize(active,old));uint64_t token=0;
  risc_bank_cohort_v1 request{};request.struct_size=sizeof(request);request.store_abi=2;
  request.firmware_size=nativeBytes;request.store_size=RiscUpdate::StoreBytes;
  memcpy(request.active_store_sha256,old.storeSha,32);
  SHA256(payload.data(),payload.size(),request.sha256);
  SHA256(payload.data(),nativeBytes,request.firmware_sha256);
  SHA256(payload.data()+nativeBytes,RiscUpdate::StoreBytes,request.store_sha256);
  assert(tx.beginCohort(request,&token)==0);
  auto status=[&]() {risc_bank_status_v1 out{};out.struct_size=sizeof(out);assert(tx.status(&out));return out;};
  auto stepTo=[&](uint32_t target) {
    risc_bank_status_v1 state{};state.struct_size=sizeof(state);
    for(unsigned i=0;i<12000;++i){if(status().state==target)return;assert(tx.step(token,&state)==0);}
    assert(false);
  };
  if(scenario=="power-begin"){emit(false);return 0;}
  if(scenario=="corrupt-native")payload[100]^=1;
  if(scenario=="corrupt-store")payload.back()^=1;
  for(size_t at=0;at<payload.size();) {
    const unsigned n=std::min(size_t(4081),payload.size()-at);
    assert(tx.write(token,payload.data()+at,n)==0);at+=n;
    if((at>=4096 && (scenario=="cancel" || scenario=="power-native")) ||
       (at>=nativeBytes+4096 && scenario=="power-store")) {
      if(scenario=="cancel")assert(tx.abort(token)==0 && status().state==RISC_BANK_IDLE);
      emit(false);return 0;
    }
  }
  const int result=tx.finish(token);
  if(scenario=="corrupt-native" || scenario=="corrupt-store") {
    assert(result==RISC_BANK_INTEGRITY);assert(tx.abort(token)==0);assert(graphChecks==0);emit(false);return 0;
  }
  assert(!result);
  if(scenario=="wrong-runtime-request") {
    risc_bank_status_v1 state{};state.struct_size=sizeof(state);int error=0;
    for(unsigned i=0;i<12000 && !error;++i)error=tx.step(token,&state);
    assert(error==RISC_BANK_INTEGRITY && !graphChecks);assert(tx.abort(token)==0);emit(false);return 0;
  }
  if(scenario=="power-verify-native"){assert(status().state==RISC_BANK_VERIFY_FIRMWARE);emit(false);return 0;}
  if(scenario=="power-verify-store"){stepTo(RISC_BANK_VERIFY_STORE);emit(false);return 0;}
  stepTo(RISC_BANK_READY);preserved();assert(graphChecks==1);
  const auto next=*reinterpret_cast<const RiscUpdate::Record*>(flash.data()+RiscUpdate::JournalOffset+(1-active)*4096);
  assert(RiscUpdate::validRecord(next,1-active) && next.firmwareSize==nativeBytes);
  assert(!memcmp(flash.data()+RiscUpdate::FirmwareOffset[1-active],payload.data(),nativeBytes));
  assert(!memcmp(flash.data()+RiscUpdate::StoreOffset[1-active],payload.data()+nativeBytes,RiscUpdate::StoreBytes));
  if(scenario=="power-ready"){emit(false);return 0;}
  selectFailure=scenario=="activation-unknown";
  assert(tx.activate(token)==(selectFailure?RISC_BANK_RETAINED:0));
  assert(tx.abort(token)==RISC_BANK_STATE);
  if(selectFailure){emit(true);return 0;}
  assert(scenario=="success" || scenario=="power-selected" || scenario=="rollback");
  emit(true);
}

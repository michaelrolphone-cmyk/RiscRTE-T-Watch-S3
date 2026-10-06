/* Production native adapter and paired transaction, with the existing flash/IDF
 * host boundary. Actual released image and candidate bytes are supplied by the
 * verifier. Full cohort graph/ELF admission is executed separately on those
 * exact store bytes before this transaction test. Target instructions, physical
 * SPIFFS, TLS and power-loss are not executed. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wreturn-type" /* renamed, uncalled fixture main */
#define main prior_native_fixture_main
#include "native_bank_test.cpp"
#undef main
#pragma GCC diagnostic pop
static std::vector<uint8_t> readBytes(const char* name){
 std::ifstream file(name,std::ios::binary);assert(file.good());
 return std::vector<uint8_t>((std::istreambuf_iterator<char>(file)),{});
}
int main(int argc,char** argv){
 assert(argc==8);flash=readBytes(argv[1]);assert(flash.size()==0x1000000);
 const auto original=flash;auto payload=readBytes(argv[2]);
 const unsigned nativeBytes=unsigned(std::stoul(argv[3]));const bool cohort=std::string(argv[4])=="cohort";
 const std::string scenario=argv[5];active=cohort?1:0;
 auto old=*reinterpret_cast<const RiscUpdate::Record*>(flash.data()+RiscUpdate::JournalOffset+active*4096);
 assert(RiscUpdate::validRecord(old,active));imageSize=old.firmwareSize;
 using namespace RiscBankStore;
 assert(prepareBoot(own,restartSafe,safe)&&writes==0);assert(verifyRollbackLater());
 auto preserved=[&](){
  for(auto region:{std::pair<unsigned,unsigned>{0,0x10000},{0x270000,0x80000},
      {RiscUpdate::FirmwareOffset[active],RiscUpdate::FirmwareBytes},
      {RiscUpdate::StoreOffset[active],RiscUpdate::StoreBytes},
      {RiscUpdate::JournalOffset+active*4096,4096}})
   assert(!memcmp(original.data()+region.first,flash.data()+region.first,region.second));
 };
 // Simulated previously saved NVS/app-data are deliberately non-empty. The
 // transport must preserve them exactly, not merely leave erased regions alone.
 assert(flash[0x9000]==0xa5 && flash[0x270000]==0x5a);
 imageSize=nativeBytes;replacingFirmware=!cohort;replacingCohort=cohort;
 strcpy(scratch->cohort.runtime_version,"0.1.34");
 RiscUpdate::Backend io{nullptr,now,read,erase,write,invalidate,record,hashBegin,hashAdd,hashEnd,
   openApp,writeApp,finishApp,cleanup,validateFirmware,select,
   [](void*,unsigned bank){
     // Caller already ran the production graph+ELF check for the exact store.
     return operationSafe()&&bank!=activeBank;
   }};
 RiscUpdate::Transaction tx(io);assert(tx.initialize(active,old));uint64_t token=0;
 if(cohort){
  assert(payload.size()==nativeBytes+RiscUpdate::StoreBytes);
  risc_bank_cohort_v1 request{};request.struct_size=sizeof(request);request.store_abi=2;
  request.firmware_size=nativeBytes;request.store_size=RiscUpdate::StoreBytes;
  memcpy(request.active_store_sha256,old.storeSha,32);
  SHA256(payload.data(),payload.size(),request.sha256);
  SHA256(payload.data(),nativeBytes,request.firmware_sha256);
  SHA256(payload.data()+nativeBytes,RiscUpdate::StoreBytes,request.store_sha256);
  assert(tx.beginCohort(request,&token)==0);
 }else{
  assert(payload.size()==nativeBytes);
  risc_bank_image_v1 request{};request.struct_size=sizeof(request);request.store_abi=2;request.size=payload.size();
  memcpy(request.active_store_sha256,old.storeSha,32);SHA256(payload.data(),payload.size(),request.sha256);
  assert(tx.begin(false,request,&token)==0);
 }
 auto status=[&](){risc_bank_status_v1 out{};out.struct_size=sizeof(out);assert(tx.status(&out));return out;};
 auto stepTo=[&](uint32_t targetState){
  risc_bank_status_v1 state{};state.struct_size=sizeof(state);
  for(unsigned i=0;i<12000;++i){if(status().state==targetState)return;assert(tx.step(token,&state)==0);}
  assert(false);
 };
 if(scenario=="power-begin"){preserved();return 0;}
 stepTo(RISC_BANK_RECEIVING);
 if(scenario=="power-copy"){preserved();return 0;}
 if(scenario=="corrupt")payload.back()^=1;
 for(size_t at=0;at<payload.size();){
  unsigned n=std::min(size_t(4081),payload.size()-at);assert(tx.write(token,payload.data()+at,n)==0);at+=n;
  if(at>=4096 && (scenario=="cancel" || scenario=="power-download")){
   if(scenario=="cancel")assert(tx.abort(token)==0&&status().state==RISC_BANK_IDLE);
   preserved();return 0;
  }
 }
 int result=tx.finish(token);
 if(scenario=="corrupt"){
  risc_bank_status_v1 state{};state.struct_size=sizeof(state);
  if(!result)for(unsigned i=0;i<12000 && !result;++i)result=tx.step(token,&state);
  assert(result!=0);assert(tx.abort(token)==0);preserved();return 0;
 }
 assert(!result);stepTo(RISC_BANK_READY);preserved();
 auto next=*reinterpret_cast<const RiscUpdate::Record*>(flash.data()+RiscUpdate::JournalOffset+(1-active)*4096);
 assert(RiscUpdate::validRecord(next,1-active));assert(next.firmwareSize==nativeBytes);
 assert(!memcmp(flash.data()+RiscUpdate::FirmwareOffset[1-active],payload.data(),nativeBytes));
 if(cohort)assert(!memcmp(flash.data()+RiscUpdate::StoreOffset[1-active],payload.data()+nativeBytes,RiscUpdate::StoreBytes));
 else assert(!memcmp(flash.data()+RiscUpdate::StoreOffset[1-active],original.data()+RiscUpdate::StoreOffset[active],RiscUpdate::StoreBytes));
 if(scenario=="power-ready")return 0;
 selectFailure=scenario=="activation-unknown";
 assert(tx.activate(token)==(selectFailure?RISC_BANK_RETAINED:0));preserved();
 assert(tx.abort(token)==RISC_BANK_STATE);
 // The previous native/store pair and its journal remain a byte-identical
 // rollback target even after selecting the candidate. Explicit rejection uses
 // the real native rollback hook; no synthetic confirmation of the candidate.
 if(scenario=="rollback" || scenario=="activation-unknown"){
  rejectBoot();assert(rollbacks==1);preserved();return 0;
 }
 assert(scenario=="success" || scenario=="power-selected");
 std::ofstream output(argv[6],std::ios::binary);output.write((const char*)flash.data(),flash.size());assert(output.good());
 std::ofstream proof(argv[7]);proof<<"{\"active_bank\":"<<active<<",\"target_bank\":"<<(1-active)<<",\"native_bytes\":"<<nativeBytes<<",\"payload_bytes\":"<<payload.size()<<",\"writes\":"<<writes<<",\"nvs_appdata_preserved\":true,\"previous_pair_preserved\":true,\"target_executed\":false}\n";
 std::cout<<(cohort?"cohort":"native-first")<<" "<<scenario<<" preserved NVS/app-data and rollback pair\n";
}

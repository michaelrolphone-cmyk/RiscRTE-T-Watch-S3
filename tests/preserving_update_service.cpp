/* Exact catalog and payload through the installed production updater.
 * HTTP, clock and native bank calls are explicit boundary doubles. The
 * separate transaction proof runs the real Runtime/bank implementation. */
#include <cassert>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#include <openssl/sha.h>
#define UPDATE_FIRMWARE 1
#include "service.cpp"
namespace {
std::string supplied_catalog,origin_json,target_json;
std::vector<uint8_t> supplied_payload,downloaded;
uint64_t ticks;
unsigned cursor,begin_calls,abort_calls,activate_calls,restart_calls,close_calls;
uint32_t bank_state=RISC_BANK_IDLE;
bool reading_payload,refuse_close;
const char *scenario;
char origin_product[32],origin_version[32],origin_repo[128],origin_revision[41];
char target_version[32],target_runtime[32],target_revision[41];
std::vector<uint8_t> bytes(const char *path){std::ifstream f(path,std::ios::binary);assert(f);return {std::istreambuf_iterator<char>(f),{}};}
std::string text(const char *path){auto b=bytes(path);return {b.begin(),b.end()};}
int32_t httpOpen(void*,const risc_http_request_v1 *request,uint64_t *handle){
 assert(!http_handle&&request->utc_seconds==1800000000ULL);cursor=0;
 reading_payload=strcmp(request->url,WatchUpdate::CatalogUrl)!=0;
 if(reading_payload){assert(!strcmp(request->url,catalog->rows[0].url));assert(request->max_bytes==supplied_payload.size());}
 *handle=1;return RISC_HTTP_OK;
}
int32_t httpRead(void*,uint64_t,void *out,uint32_t capacity,uint32_t *count){
 const auto size=reading_payload?supplied_payload.size():supplied_catalog.size();
 *count=0;if(cursor==size)return RISC_HTTP_EOF;
 *count=uint32_t(size-cursor);if(*count>capacity)*count=capacity;
 memcpy(out,reading_payload?(const void*)(supplied_payload.data()+cursor):(const void*)(supplied_catalog.data()+cursor),*count);
 cursor+=*count;return RISC_HTTP_OK;
}
int32_t httpInfo(void*,uint64_t,risc_http_response_v1 *out){out->status_code=200;return RISC_HTTP_OK;}
int32_t httpClose(void*,uint64_t){if(refuse_close)return RISC_HTTP_RETAINED;++close_calls;return RISC_HTTP_OK;}
bool bankStatus(void*,risc_bank_status_v1 *out){out->state=bank_state;out->firmware_capacity=0x260000;out->store_capacity=0x510000;out->store_abi=2;strcpy(out->layout,"riscrte-paired-appdata-v2");strcpy(out->runtime_version,"0.1.55");memset(out->active_store_sha256,42,32);return true;}
int32_t cohortStatus(void*,risc_bank_cohort_status_v1 *out){strcpy(out->product,origin_product);strcpy(out->version,origin_version);strcpy(out->source_repo,origin_repo);strcpy(out->source_revision,origin_revision);return RISC_BANK_OK;}
int32_t beginCohort(void*,const risc_bank_cohort_v1 *request,uint64_t *handle){
 assert(request->firmware_size+request->store_size==supplied_payload.size());
 assert(request->store_abi==2&&request->store_size==0x510000);
 uint8_t sha[32];SHA256(supplied_payload.data(),supplied_payload.size(),sha);assert(!memcmp(sha,request->sha256,32));
 SHA256(supplied_payload.data(),request->firmware_size,sha);assert(!memcmp(sha,request->firmware_sha256,32));
 SHA256(supplied_payload.data()+request->firmware_size,request->store_size,sha);assert(!memcmp(sha,request->store_sha256,32));
 for(auto value:request->active_store_sha256)assert(value==42);
 assert(!strcmp(request->product,origin_product)&&!strcmp(request->source_repo,origin_repo));
 assert(!strcmp(request->version,target_version)&&!strcmp(request->runtime_version,target_runtime)&&
        !strcmp(request->source_revision,target_revision));
 assert(t5_package_version_compare(request->version,origin_version)>0);
 ++begin_calls;*handle=2;bank_state=RISC_BANK_COPY_STORE;return RISC_BANK_OK;
}
int32_t noFirmware(void*,const risc_bank_image_v1*,uint64_t*){assert(false);return RISC_BANK_INVALID;}
int32_t noApp(void*,const char*,const void*,uint32_t,const risc_bank_image_v1*,uint64_t*){assert(false);return RISC_BANK_INVALID;}
int32_t noGet(void*,uint32_t,void*,uint32_t,uint32_t*){assert(false);return RISC_BANK_INVALID;}
int32_t bankStep(void*,uint64_t,risc_bank_status_v1 *out){
 if(bank_state==RISC_BANK_COPY_STORE)bank_state=RISC_BANK_RECEIVING;
 else if(bank_state==RISC_BANK_VERIFY_FIRMWARE)bank_state=RISC_BANK_VERIFY_STORE;
 else if(bank_state==RISC_BANK_VERIFY_STORE)bank_state=RISC_BANK_READY;
 out->state=bank_state;return RISC_BANK_OK;
}
int32_t bankWrite(void*,uint64_t,const void *data,uint32_t size){
 assert(downloaded.size()+size<=supplied_payload.size());
 assert(!memcmp(data,supplied_payload.data()+downloaded.size(),size));
 const auto *p=(const uint8_t*)data;downloaded.insert(downloaded.end(),p,p+size);return RISC_BANK_OK;
}
int32_t bankFinish(void*,uint64_t){assert(downloaded==supplied_payload);bank_state=RISC_BANK_VERIFY_FIRMWARE;return RISC_BANK_OK;}
int32_t bankActivate(void*,uint64_t){assert(!http_handle&&bank_state==RISC_BANK_READY);++activate_calls;bank_state=RISC_BANK_ACTIVATED;return RISC_BANK_OK;}
int32_t bankAbort(void*,uint64_t){++abort_calls;bank_state=RISC_BANK_IDLE;return RISC_BANK_OK;}
bool bankRestart(void*,uint64_t){++restart_calls;return true;}
uint64_t now(void*){return ticks;}
void wait(void*,uint32_t ms){ticks+=ms;}
void until(uint32_t wanted){for(unsigned i=0;i<40000&&view.state!=wanted&&view.state!=SOFTWARE_UPDATE_ERROR&&view.state!=SOFTWARE_UPDATE_RETAINED;++i)step(nullptr);assert(view.state==wanted);}
}
int main(int argc,char **argv){
 assert(argc==6);supplied_catalog=text(argv[1]);origin_json=text(argv[2]);supplied_payload=bytes(argv[3]);target_json=text(argv[4]);scenario=argv[5];
 WatchUpdate::WorkBudget budget(nullptr,nullptr);WatchUpdate::Slice origin{origin_json.data(),origin_json.size()};
 assert(WatchUpdate::str(origin,"product",origin_product,sizeof(origin_product),budget));
 assert(WatchUpdate::str(origin,"version",origin_version,sizeof(origin_version),budget));
 assert(WatchUpdate::str(origin,"source_repo",origin_repo,sizeof(origin_repo),budget));
 assert(WatchUpdate::str(origin,"source_revision",origin_revision,sizeof(origin_revision),budget));
 WatchUpdate::Slice target{target_json.data(),target_json.size()};
 assert(WatchUpdate::str(target,"version",target_version,sizeof(target_version),budget));
 assert(WatchUpdate::str(target,"runtime_version",target_runtime,sizeof(target_runtime),budget));
 assert(WatchUpdate::str(target,"source_revision",target_revision,sizeof(target_revision),budget));
 const risc_http_client_v1 http_api={1,sizeof(http_api),nullptr,httpOpen,httpRead,httpInfo,httpClose};
 const risc_bank_store_v1 bank_api={1,sizeof(bank_api),nullptr,bankStatus,noFirmware,noApp,bankStep,bankWrite,bankFinish,bankActivate,bankAbort,bankRestart,noGet,cohortStatus,beginCohort};
 const risc_platform_clock_api_v1 clock_api={1,sizeof(clock_api),nullptr,now,wait};
 const risc_provider_dependency_v1 deps[]={{RISC_HTTP_CLIENT_CAPABILITY,1,&http_api},{RISC_BANK_STORE_CAPABILITY,1,&bank_api},{"platform.clock",1,&clock_api}};
 auto *driver=t5_driver_get(2);assert(driver&&driver->start(deps,3));
 assert(refresh(nullptr,1800000000ULL));until(SOFTWARE_UPDATE_LIST);
 assert(catalog->count==1&&catalog->rows[0].pairedCohort);
 assert(catalog->rows[0].view.availability==SOFTWARE_UPDATE_AVAILABLE);
 if(!strcmp(scenario,"changed-origin")){
  strcpy(origin_version,catalog->rows[0].view.version);
  assert(!begin(nullptr,0,1800000000ULL)&&!begin_calls&&downloaded.empty());
 }else{
  assert(begin(nullptr,0,1800000000ULL)&&begin_calls==1);until(SOFTWARE_UPDATE_DOWNLOAD);
  if(!strcmp(scenario,"cancel")){
   assert(step(nullptr)&&!downloaded.empty());assert(cancel(nullptr)&&abort_calls==1&&!activate_calls);
  }else if(!strcmp(scenario,"close-retained")){
   refuse_close=true;assert(!cancel(nullptr)&&view.state==SOFTWARE_UPDATE_RETAINED&&!abort_calls);
   auto before=downloaded.size();assert(!driver->quiesce()&&downloaded.size()==before);
   refuse_close=false;assert(cancel(nullptr)&&abort_calls==1);
  }else{
   assert(!strcmp(scenario,"success"));until(SOFTWARE_UPDATE_READY);
   assert(downloaded==supplied_payload&&close_calls==2&&!activate_calls);
   assert(activate(nullptr)&&activate_calls==1);assert(!cancel(nullptr)&&!driver->quiesce());
   assert(restart(nullptr)&&restart_calls==1);
   view.state=SOFTWARE_UPDATE_READY; // Explicit model teardown after simulated restart.
  }
 }
 assert(driver->quiesce());driver->stop();
 printf("{\"scenario\":\"%s\",\"downloaded_bytes\":%zu,\"begin_calls\":%u,\"activations\":%u,\"actual_provider\":true,\"hardware\":false}\n",scenario,downloaded.size(),begin_calls,activate_calls);
}

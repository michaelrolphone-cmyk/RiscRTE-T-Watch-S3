#include <cassert>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#define UPDATE_FIRMWARE 0
#include "Services/update/service.cpp"
namespace {
std::vector<std::string> installed;
unsigned begin_calls=0, download_calls=0;
uint64_t now=0;
uint64_t time_ms(void*) { return now; }
void sleep_ms(void*, uint32_t n) { now+=n; }
bool bank_status(void*,risc_bank_status_v1* out) {
 out->store_abi=2;out->app_count=(uint32_t)installed.size();
 std::strcpy(out->runtime_version,"0.1.41");std::strcpy(out->layout,"riscrte-paired-appdata-v2");return true;
}
int32_t get_app(void*,uint32_t i,void* data,uint32_t cap,uint32_t* n) {
 assert(i<installed.size()&&installed[i].size()<=cap);
 *n=(uint32_t)installed[i].size();std::memcpy(data,installed[i].data(),*n);return RISC_BANK_OK;
}
int32_t begin_app(void*,const char*,const void*,uint32_t,const risc_bank_image_v1*,uint64_t*) {
 ++begin_calls;return RISC_BANK_UNAVAILABLE;
}
int32_t http_open(void*,const risc_http_request_v1*,uint64_t*) { ++download_calls;return RISC_HTTP_INVALID; }
std::string read(const char* name) {std::ifstream f(name);assert(f.good());return {std::istreambuf_iterator<char>(f),{}};}
}
int main(int argc,char** argv) {
 assert(argc==25);bool expected_available=!std::strcmp(argv[1],"positive");
 std::string index=read(argv[2]);for(int i=3;i<argc;++i)installed.push_back(read(argv[i]));
 risc_bank_store_v1 b{};b.api_version=1;b.struct_size=sizeof(b);b.status=bank_status;b.get_app=get_app;b.begin_app=begin_app;bank=&b;
 risc_http_client_v1 h{};h.api_version=1;h.struct_size=sizeof(h);h.open=http_open;http=&h;
 risc_platform_clock_api_v1 c{1,sizeof(c),nullptr,time_ms,sleep_ms};clock_api=&c;
 catalog=&catalog_storage;started=true;deadline=300000;
 assert(WatchUpdate::parse({index.data(),index.size()},false,*catalog,budget,nullptr));
 assert(catalog->count==22&&classify());
 for(uint32_t i=0;i<catalog->count;++i) {
  assert((catalog->rows[i].view.availability==SOFTWARE_UPDATE_AVAILABLE)==expected_available);
  if(!expected_available)assert(!std::strcmp(catalog->rows[i].view.reason,"Changed requirements are not authorized"));
  assert(!begin(nullptr,i,1800000000ULL));
 }
 assert(begin_calls==(expected_available?22u:0u));assert(download_calls==0&&bank_handle==0&&http_handle==0);
 std::printf("%s: 22 rows, %u bank transactions, %u payload downloads\n",expected_available?"positive":"old-cohort rejection",begin_calls,download_calls);
}

/* Source-wired host integration. Production Runtime, graph/module loader,
 * CpuPort, HTTP/parser, update provider, native bank and store audit are real.
 * TLS socket bytes, ESP image validity and SPIFFS/flash hardware are simulated.
 * No TLS handshake, target instruction execution, hardware or migration claim. */
#include "ports/esp32s3/NativeHttp.h"
#include "ports/esp32s3/NativeBankStore.cpp"
#include "ports/esp32s3/CpuPort.h"
#include "SoftwareUpdateV1.h"
#include "RiscKeyValueV1.h"
#include <cassert>
#include <dirent.h>
#include <sys/stat.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <vector>
namespace fs=std::filesystem;
using Bytes=std::vector<uint8_t>;
using Files=std::map<std::string,Bytes>;
static Bytes flash(0x1000000,0xff),originalFlash,payload;
static std::string root,modules,scenario,kind,activeRoot,stagedRoot,catalog;
static uint64_t ticks=1;
static unsigned activeBank=0,selectedBank=0,writeCount=0,confirms=0,restarts=0,finalized=0,networkOpens=0,networkCloses=0,kvNamespaces=0;
// Host adaptation of the target linker's compiled symbol availability. Only
// the import used by these synthetic ELFs is mapped to a real host symbol;
// production allowedImport() remains authoritative before this lookup.
extern "C" uintptr_t elf_find_sym_default(const char* name){return name&&!strcmp(name,"memcpy")&&scenario!="elf-unavailable"?reinterpret_cast<uintptr_t>(&memcpy):0;}
static bool owned=true,online=true,closeFailure=false,unmountFailure=false,selectFailure=false,freezeNetwork=false;
static uint32_t imageSize=8192;
static const uint64_t utc=1800000000ULL;
static RiscCpu::Port* cpu=nullptr;
static RiscBoot::Runtime* rt=nullptr;
static std::set<uint32_t> nativeStates;
static risc_key_value_v1 copiedKv{};
static void nativeAuthorityChecks();
static esp_ota_img_states_t otaState=ESP_OTA_IMG_PENDING_VERIFY;
static esp_partition_t table[]={
 {ESP_PARTITION_TYPE_APP,ESP_PARTITION_SUBTYPE_APP_OTA_0,0x10000,RiscUpdate::FirmwareBytes,"app0",false},
 {ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_SPIFFS,RiscUpdate::StoreOffset[0],RiscUpdate::StoreBytes,"bootfs0",false},
 {ESP_PARTITION_TYPE_APP,esp_partition_subtype_t(17),0x800000,RiscUpdate::FirmwareBytes,"app1",false},
 {ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_SPIFFS,RiscUpdate::StoreOffset[1],RiscUpdate::StoreBytes,"bootfs1",false},
 {ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_OTA,0xff0000,0x2000,"otadata",false},
 {ESP_PARTITION_TYPE_DATA,esp_partition_subtype_t(0x40),0xff2000,0x2000,"bank_state",false},
 {ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_NVS,0x9000,0x6000,"nvs",false}
#ifdef RISC_PAIRED_APP_DATA
 ,{ESP_PARTITION_TYPE_DATA,esp_partition_subtype_t(0x41),0x270000,0x80000,"appdata",false}
#endif
 };
static Bytes bytes(const std::string& s){return Bytes(s.begin(),s.end());}
static Bytes readFile(const fs::path& p){std::ifstream f(p,std::ios::binary);assert(f);return Bytes(std::istreambuf_iterator<char>(f),{});}
static void writeFile(const fs::path& p,const Bytes& b){std::ofstream f(p,std::ios::binary);assert(f);if(!b.empty())f.write((const char*)b.data(),b.size());assert(f);}
static void writeText(const fs::path& p,const std::string& s){writeFile(p,bytes(s));}
static std::string mapped(const char* p){std::string s=p;if(s=="/bootfs"||s.rfind("/bootfs/",0)==0)return activeRoot+s.substr(7);if(s=="/updatefs"||s.rfind("/updatefs/",0)==0)return stagedRoot+s.substr(9);return s;}
extern "C" FILE* __real_fopen(const char*,const char*);
extern "C" FILE* __wrap_fopen(const char* p,const char* m){return __real_fopen(mapped(p).c_str(),m);}
extern "C" DIR* __real_opendir(const char*);
extern "C" DIR* __wrap_opendir(const char* p){return __real_opendir(mapped(p).c_str());}
extern "C" int __real_stat(const char*,struct stat*);
extern "C" int __wrap_stat(const char* p,struct stat* s){return __real_stat(mapped(p).c_str(),s);}
// A bounded deterministic fake SPIFFS format. The production transaction still
// clones and independently hashes every byte of the selected store geometry.
static Files directory(const std::string& dir){Files files;for(auto& f:fs::directory_iterator(dir)){assert(f.is_regular_file());files[f.path().filename().string()]=readFile(f.path());}return files;}
static void pack(unsigned bank,const Files& files){
 auto* p=flash.data()+table[bank*2+1].address;size_t at=0;memset(p,0xff,RiscUpdate::StoreBytes);
 auto put=[&](const void* b,size_t n){assert(at+n<=RiscUpdate::StoreBytes);if(n)memcpy(p+at,b,n);at+=n;};
 uint32_t magic=0x48534653,count=files.size();put(&magic,4);put(&count,4);
 for(auto& f:files){uint32_t n=f.first.size(),s=f.second.size();assert(n&&n<193);put(&n,4);put(&s,4);put(f.first.data(),n);put(f.second.data(),s);}
}
static Files unpack(unsigned bank){
 const auto* p=flash.data()+table[bank*2+1].address;size_t at=0;
 auto get=[&](void* b,size_t n){assert(at+n<=RiscUpdate::StoreBytes);if(n)memcpy(b,p+at,n);at+=n;};
 uint32_t magic=0,count=0;get(&magic,4);get(&count,4);assert(magic==0x48534653&&count<=128);Files files;
 for(unsigned i=0;i<count;++i){uint32_t n=0,s=0;get(&n,4);get(&s,4);assert(n&&n<193&&s<=RiscUpdate::StoreBytes);std::string name(n,' ');get(name.data(),n);assert(name.find('/')==std::string::npos);Bytes b(s);get(b.data(),s);files[name]=std::move(b);}return files;
}
static void materialize(const std::string& dir,const Files& files){fs::remove_all(dir);fs::create_directories(dir);for(auto& f:files)writeFile(fs::path(dir)/f.first,f.second);}
static std::string digest(const Bytes& b){uint8_t hash[32];SHA256(b.data(),b.size(),hash);char out[65];for(unsigned i=0;i<32;++i)snprintf(out+i*2,3,"%02x",hash[i]);return out;}
FakeEsp ESP;esp_flash_t chip;esp_flash_t* esp_flash_default_chip=&chip;
uint32_t FakeEsp::getFlashChipSize()const{return flash.size();}
void FakeEsp::restart(){++restarts;}
uint32_t millis(){return ticks;}
void vTaskDelay(unsigned n){ticks+=n;}
esp_err_t esp_flash_read(esp_flash_t*,void* out,uint32_t off,uint32_t n){if(uint64_t(off)+n>flash.size())return -1;memcpy(out,flash.data()+off,n);return 0;}
const esp_partition_t* esp_partition_find_first(esp_partition_type_t t,esp_partition_subtype_t s,const char* label){for(auto& p:table)if(p.type==t&&p.subtype==s&&!strcmp(label,p.label))return &p;return nullptr;}
esp_err_t esp_partition_read(const esp_partition_t* p,size_t off,void* out,size_t n){if(!p||off+n>p->size)return -1;memcpy(out,flash.data()+p->address+off,n);return 0;}
static void permitted(const esp_partition_t* p,size_t off,size_t n){assert(p&&off+n<=p->size);assert(p==&table[(1-activeBank)*2]||p==&table[(1-activeBank)*2+1]||p==&table[5]);if(p==&table[5])assert(off/4096!=activeBank);++writeCount;}
esp_err_t esp_partition_write(const esp_partition_t* p,size_t off,const void* in,size_t n){permitted(p,off,n);memcpy(flash.data()+p->address+off,in,n);return 0;}
esp_err_t esp_partition_erase_range(const esp_partition_t* p,size_t off,size_t n){permitted(p,off,n);memset(flash.data()+p->address+off,0xff,n);return 0;}
const esp_partition_t* esp_ota_get_running_partition(){return &table[activeBank*2];}
esp_err_t esp_ota_get_state_partition(const esp_partition_t*,esp_ota_img_states_t* s){*s=otaState;return 0;}
const esp_app_desc_t* esp_ota_get_app_description(){static esp_app_desc_t d{};strcpy(d.project_name,"arduino-lib-builder");return &d;}
esp_err_t esp_ota_get_partition_description(const esp_partition_t*,esp_app_desc_t* out){*out=*esp_ota_get_app_description();return 0;}
esp_err_t esp_ota_set_boot_partition(const esp_partition_t* p){++writeCount;selectedBank=p==&table[2];return selectFailure?-1:0;}
esp_err_t esp_ota_mark_app_valid_cancel_rollback(){++confirms;otaState=ESP_OTA_IMG_VALID;return 0;}
esp_err_t esp_ota_mark_app_invalid_rollback_and_reboot(){assert(false);return 0;}
bool esp_ota_check_rollback_is_possible(){return true;}
esp_err_t esp_image_verify(int,const esp_partition_pos_t*,esp_image_metadata_t* out){out->image_len=imageSize;return 0;}
esp_err_t esp_vfs_spiffs_register(const esp_vfs_spiffs_conf_t* conf){assert(!conf->format_if_mount_failed&&!strcmp(conf->base_path,"/updatefs"));unsigned b=!strcmp(conf->partition_label,"bootfs1");assert(b!=activeBank);materialize(stagedRoot,unpack(b));return 0;}
esp_err_t esp_vfs_spiffs_unregister(const char* label){if(unmountFailure)return -1;unsigned b=!strcmp(label,"bootfs1");assert(b!=activeBank);pack(b,directory(stagedRoot));return 0;}
size_t heap_caps_get_free_size(unsigned){return 256*1024;}
size_t heap_caps_get_largest_free_block(unsigned){return 128*1024;}
void* heap_caps_malloc(size_t n,unsigned){return malloc(n);}
void heap_caps_free(void* p){free(p);}
int64_t esp_timer_get_time(){return ticks*1000;}
static std::vector<std::string> wires;
static std::vector<size_t> wireAt;
static std::vector<std::string> requests;
static mbedtls_ssl_config tlsConfig;
static int chain(void*,mbedtls_x509_crt*,int,uint32_t*){return 0;}
esp_err_t esp_crt_bundle_attach(void* p){static_cast<mbedtls_ssl_config*>(p)->f_vrfy=chain;return ESP_OK;}
esp_tls_t* esp_tls_init(){unsigned i=networkOpens++;requests.emplace_back();wireAt.push_back(0);wires.emplace_back();return new esp_tls_t{i};}
int esp_tls_conn_destroy(esp_tls_t* p){++networkCloses;delete p;return closeFailure?-1:0;}
extern "C" int __wrap_close(int fd){assert(fd==7);return closeFailure?-1:0;}
int esp_tls_conn_new_async(const char* host,int n,int port,const esp_tls_cfg_t* c,esp_tls_t* tls){tls->sockfd=7;tls->server_fd.fd=7;assert(n>0&&host[n]==0&&port==443&&c->non_block&&!c->skip_common_name);tlsConfig={};assert(c->crt_bundle_attach(&tlsConfig)==0&&tlsConfig.major==3&&tlsConfig.minor==3);return 1;}
ssize_t esp_tls_conn_write(esp_tls_t* p,const void* b,size_t n){requests[p->index].append(static_cast<const char*>(b),n);return n;}
ssize_t esp_tls_conn_read(esp_tls_t* p,void* out,size_t n){
 if(freezeNetwork)return ESP_TLS_ERR_SSL_WANT_READ;
 auto& s=wires[p->index];auto& at=wireAt[p->index];
 if(s.empty()){
  bool isCatalog=requests[p->index].find("/release-index/release-index.json")!=std::string::npos;
  std::string body=isCatalog?catalog:std::string((const char*)payload.data(),payload.size());size_t claimed=body.size();
  if(!isCatalog&&scenario=="short")body.resize(body.size()-13);
  if(!isCatalog&&scenario=="corrupt")body.back()^=1;
  s="HTTP/1.1 200 OK\r\nContent-Length: "+std::to_string(claimed)+"\r\n\r\n"+body;
 }
 size_t amount=std::min({n,size_t(127),s.size()-at});memcpy(out,s.data()+at,amount);at+=amount;return amount;
}
static bool owner(){return owned;}
static bool networkReady(){return online;}
static bool operationSafe(){return !cpu||cpu->providerStorageSafe();}
static bool restartSafe(){return cpu&&cpu->restartResourcesSafe();}
static bool exitSafe(){return cpu->appExitSafe()&&RiscBankStore::exitSafe();}
static bool storageSafe(){return cpu->providerStorageSafe();}
static bool bind(RiscBoot::Runtime& r){return cpu->bind(r)&&RiscBankStore::bind(r);}
static int32_t kvGet(void*,uint32_t ns,const char*,void*,uint32_t,uint32_t* size){assert(ns==1||ns==6||ns==5);kvNamespaces|=1u<<ns;*size=0;return RISC_KEY_VALUE_NOT_FOUND;}
static int32_t kvPut(void*,uint32_t ns,const char*,const void*,uint32_t){assert(ns==1||ns==6||ns==5);kvNamespaces|=1u<<ns;return RISC_KEY_VALUE_OK;}
static RiscBoot::KeyValueBackend kv{nullptr,kvGet,kvPut};
static void ensureActiveIntact(){for(unsigned r=0;r<2;++r){const auto& p=table[activeBank*2+r];assert(!memcmp(flash.data()+p.address,originalFlash.data()+p.address,p.size));}assert(!memcmp(flash.data()+RiscUpdate::JournalOffset+activeBank*4096,originalFlash.data()+RiscUpdate::JournalOffset+activeBank*4096,4096));
 assert(!memcmp(flash.data()+0x9000,originalFlash.data()+0x9000,0x6000));
#ifdef RISC_PAIRED_APP_DATA
 for(size_t i=0x270000;i<0x2f0000;++i)assert(flash[i]==0x5a);
#endif
}
static risc_bank_status_v1 nativeStatus(){risc_bank_status_v1 s{};s.struct_size=sizeof(s);assert(RiscBankStore::api.status(nullptr,&s));nativeStates.insert(s.state);return s;}
static software_update_status_v1 status(const software_update_v1* s){software_update_status_v1 out{};out.struct_size=sizeof(out);assert(s->status(s->context,&out));return out;}
static void advance(const software_update_v1* s,uint32_t desired){for(unsigned i=0;i<400000;++i){auto v=status(s);if(v.state==desired||v.state==SOFTWARE_UPDATE_ERROR||v.state==SOFTWARE_UPDATE_RETAINED)return;s->step(s->context);nativeStatus();++ticks;}assert(false);}
static void savePower(){ensureActiveIntact();writeFile(fs::path(root)/"power-flash.bin",flash);writeText(fs::path(root)/"selected",std::to_string(selectedBank));std::cout<<kind<<" "<<scenario<<" cut point saved, active pair intact\n";std::cout.flush();std::_Exit(0);}
extern "C" void integration_fini(){++finalized;}
extern "C" void integration_entry(const risc_runtime_api_v1* runtime){
 assert(runtime&&runtime->acquire&&runtime->confirm_boot);
 risc_runtime_capability_v1 denied{};denied.struct_size=sizeof(denied);
 for(const char* cap:{"platform.http-client","platform.bank-store",kind=="app"?SOFTWARE_UPDATE_FIRMWARE_CAPABILITY:SOFTWARE_UPDATE_APPS_CAPABILITY})assert(!runtime->acquire(cap,1,0,&denied));
 risc_runtime_capability_v1 one{},six{};one.struct_size=sizeof(one);six.struct_size=sizeof(six);
 assert(runtime->acquire(RISC_KEY_VALUE_CAPABILITY,1,1,&one));
 if(scenario=="namespace-missing"){assert(!runtime->acquire(RISC_KEY_VALUE_CAPABILITY,1,6,&six));assert(runtime->release(&one));assert(runtime->confirm_boot());assert(writeCount==0);return;}
 assert(runtime->acquire(RISC_KEY_VALUE_CAPABILITY,1,6,&six));
 assert(!runtime->acquire(RISC_KEY_VALUE_CAPABILITY,1,0,&denied));assert(!runtime->acquire(RISC_KEY_VALUE_CAPABILITY,1,5,&denied));
 auto* key=static_cast<const risc_key_value_v1*>(six.api);copiedKv=*key;char b=0;uint32_t size=0;
 assert(key->get(key->context,"utc",&b,1,&size)==RISC_KEY_VALUE_NOT_FOUND);
 assert(key->put(key->context,"utc",&b,1)==RISC_KEY_VALUE_OK);
 auto* keyOne=static_cast<const risc_key_value_v1*>(one.api);assert(keyOne->get(keyOne->context,"wifi",&b,1,&size)==RISC_KEY_VALUE_NOT_FOUND);
 assert(kvNamespaces==((1u<<1)|(1u<<6)));
 assert(runtime->release(&one)&&runtime->release(&six));assert(copiedKv.get(copiedKv.context,"utc",&b,1,&size)==RISC_KEY_VALUE_CONTEXT);
 if(scenario=="recover"){assert(runtime->confirm_boot()&&confirms==1);return;}
 risc_runtime_capability_v1 grant{};grant.struct_size=sizeof(grant);
 assert(runtime->acquire(kind=="app"?SOFTWARE_UPDATE_APPS_CAPABILITY:SOFTWARE_UPDATE_FIRMWARE_CAPABILITY,1,0,&grant));
 const auto* service=static_cast<const software_update_v1*>(grant.api);assert(service&&service->api_version==1);
 // No update may start before explicit default-entry health acknowledgement.
 if(scenario=="unconfirmed"){
  assert(service->refresh(service->context,utc));advance(service,SOFTWARE_UPDATE_LIST);
  assert(!service->begin(service->context,0,utc));assert(writeCount==0&&confirms==0);
  assert(service->cancel(service->context));assert(runtime->release(&grant));return;
 }
 assert(runtime->confirm_boot()&&confirms==1);
 nativeAuthorityChecks();
 assert(service->refresh(service->context,utc));advance(service,SOFTWARE_UPDATE_LIST);assert(status(service).state==SOFTWARE_UPDATE_LIST);
 software_update_row_v1 row{};row.struct_size=sizeof(row);assert(service->get(service->context,0,&row));
 if(scenario=="authority"){
  assert(row.availability!=SOFTWARE_UPDATE_AVAILABLE);assert(!service->begin(service->context,0,utc));assert(writeCount==0);assert(service->cancel(service->context));assert(runtime->release(&grant));return;
 }
 assert(row.availability==SOFTWARE_UPDATE_AVAILABLE);assert(service->begin(service->context,0,utc));assert(!service->activate(service->context));
 nativeStatus();
 if(scenario=="power-copy"){for(unsigned i=0;i<11;++i)service->step(service->context);savePower();}
 if(scenario=="cancel"||scenario=="retry"){
  for(unsigned i=0;i<17;++i)service->step(service->context);
  assert(service->cancel(service->context)&&nativeStatus().state==RISC_BANK_IDLE);ensureActiveIntact();
  assert(!RiscUpdate::validRecord(*reinterpret_cast<const RiscUpdate::Record*>(flash.data()+RiscUpdate::JournalOffset+4096),1));
  if(scenario=="cancel"){assert(runtime->release(&grant));return;}
  assert(service->begin(service->context,0,utc));
 }
 advance(service,SOFTWARE_UPDATE_DOWNLOAD);assert(status(service).state==SOFTWARE_UPDATE_DOWNLOAD);
 assert(!cpu->appExitSafe()&&cpu->providerStorageSafe());
 if(scenario=="power-download"){for(unsigned i=0;i<8;++i)service->step(service->context);savePower();}
 if(scenario=="network"||scenario=="network-retry")online=false;
 if(scenario=="timeout")freezeNetwork=true;
 if(scenario=="store-tamper")writeText(fs::path(stagedRoot)/"board.json","{}");
 if(scenario=="mount-retain")unmountFailure=true;
 if(scenario=="close-retain")closeFailure=true;
 advance(service,SOFTWARE_UPDATE_READY);
 auto view=status(service);
 bool rejected=scenario=="network"||scenario=="network-retry"||scenario=="timeout"||scenario=="short"||scenario=="corrupt"||scenario=="firmware-old"||scenario=="firmware-abi"||scenario=="elf-import"||scenario=="elf-unavailable"||scenario=="elf-structure"||scenario=="store-tamper";
 if(rejected){
  assert(view.state==SOFTWARE_UPDATE_ERROR);assert(nativeStatus().state==RISC_BANK_IDLE);assert(!selectedBank&&!restarts);ensureActiveIntact();
  online=true;freezeNetwork=false;assert(service->cancel(service->context));
  if(scenario!="network-retry"){assert(runtime->release(&grant));return;}
  assert(service->begin(service->context,0,utc));advance(service,SOFTWARE_UPDATE_READY);view=status(service);
 }
 if(scenario=="mount-retain"){
  assert(view.state==SOFTWARE_UPDATE_RETAINED&&!RiscBankStore::exitSafe());assert(!service->cancel(service->context));
  unmountFailure=false;assert(service->cancel(service->context));assert(RiscBankStore::exitSafe());assert(nativeStatus().state==RISC_BANK_IDLE);ensureActiveIntact();assert(runtime->release(&grant));return;
 }
 if(scenario=="close-retain"){
  assert(view.state==SOFTWARE_UPDATE_RETAINED&&!RiscCpu::NativeHttp::safe());assert(!service->cancel(service->context));assert(!cpu->providerStorageSafe());ensureActiveIntact();return;
 }
 assert(view.state==SOFTWARE_UPDATE_READY&&nativeStatus().state==RISC_BANK_READY);assert(networkOpens==networkCloses&&RiscCpu::NativeHttp::idle());
 ensureActiveIntact();
 assert(nativeStates.count(RISC_BANK_COPY_STORE)&&nativeStates.count(RISC_BANK_RECEIVING)&&nativeStates.count(RISC_BANK_VERIFY_FIRMWARE)&&nativeStates.count(RISC_BANK_VERIFY_STORE)&&nativeStates.count(RISC_BANK_READY));
 if(kind=="app"){
  assert(nativeStates.count(RISC_BANK_COPY_FIRMWARE)&&nativeStates.count(RISC_BANK_VERIFY_CLONE));
  auto before=unpack(0),after=unpack(1);assert(before.size()==after.size());
  for(auto& f:before)if(f.first!="clock.elf"&&f.first!="clock.json")assert(after[f.first]==f.second);
  assert(after["clock.elf"]==payload&&after["clock.elf"]!=before["clock.elf"]&&after["clock.json"]!=before["clock.json"]);
  assert(!memcmp(flash.data()+table[0].address,flash.data()+table[2].address,imageSize));
 }else assert(!memcmp(flash.data()+table[1].address,flash.data()+table[3].address,RiscUpdate::StoreBytes));
 auto& record=*reinterpret_cast<const RiscUpdate::Record*>(flash.data()+RiscUpdate::JournalOffset+4096);assert(RiscUpdate::validRecord(record,1));
 if(scenario=="power-ready")savePower();
 if(scenario=="activation-unknown")selectFailure=true;
 bool activated=service->activate(service->context);assert(activated==(scenario!="activation-unknown"));
 assert(status(service).state==(activated?SOFTWARE_UPDATE_ACTIVATED:SOFTWARE_UPDATE_ACTIVATION_UNKNOWN));
 assert(!service->cancel(service->context)); // Keep the app grant live through the restart handoff.
 if(scenario=="power-selected")savePower();
 owned=false;assert(!service->restart(service->context)&&restarts==0);owned=true;
 assert(!service->restart(service->context)&&restarts==1); // Fake restart returns; device restart never does.
 assert(runtime->release(&grant)); // Runtime still owns its independent provider lease.
 ensureActiveIntact();
}
static Bytes syntheticFirmware(const char* version,const char* abi=RiscUpdate::StoreAbi==2?"2":"1"){
 Bytes out(imageSize,0);std::string m=std::string("RISC_PAIRED_STORE_ABI:")+abi;memcpy(out.data()+100,m.c_str(),m.size()+1);m=std::string("RISC_RUNTIME_VERSION:")+version;memcpy(out.data()+4087,m.c_str(),m.size()+1);return out;
}
static std::vector<uint8_t> elf(const char* imported){
 std::vector<uint8_t> data(1024);auto* h=reinterpret_cast<elf32_hdr_t*>(data.data());
 memcpy(h->ident,"\177ELF\1\1\1",7);h->type=3;h->machine=94;h->version=1;
 h->ehsize=sizeof(*h);h->shentsize=sizeof(elf32_shdr_t);h->shoff=64;h->shnum=5;h->shstrndx=1;
 auto* s=reinterpret_cast<elf32_shdr_t*>(data.data()+64);
 const char names[]="\0.shstrtab\0.text\0.dynsym\0.dynstr\0";
 memcpy(data.data()+300,names,sizeof(names));
 s[1].name=1;s[1].type=SHT_STRTAB;s[1].offset=300;s[1].size=sizeof(names);
 s[2].name=11;s[2].type=SHT_PROGBITS;s[2].flags=SHF_ALLOC|SHF_EXECINSTR;s[2].addr=0x100;s[2].offset=400;s[2].size=4;
 s[3].name=17;s[3].type=SHT_SYNSYM;s[3].offset=416;s[3].size=3*sizeof(elf32_sym_t);s[3].link=4;
 s[4].name=25;s[4].type=SHT_STRTAB;s[4].offset=512;s[4].size=128;
 strcpy(reinterpret_cast<char*>(data.data()+513),"app_main");strcpy(reinterpret_cast<char*>(data.data()+522),imported);
 auto* sym=reinterpret_cast<elf32_sym_t*>(data.data()+416);
 sym[1].name=1;sym[1].value=0x100;sym[1].shndx=2;sym[1].info=(STB_GLOBAL<<4)|STT_FUNC;
 sym[2].name=10;sym[2].shndx=SHN_UNDEF;sym[2].info=(STB_GLOBAL<<4)|STT_FUNC;
 return data;
}
static std::string manifest(const char* id,const char* version,const char* file,const std::string& requirements){return std::string("{\"type\":\"application\",\"id\":\"")+id+"\",\"version\":\""+version+"\",\"architecture\":\"xtensa-esp32s3\",\"file_name\":\""+file+"\",\"entry\":\"app_main\",\"requires\":"+requirements+"}";}
static std::string requirement(const char* cap){return std::string("{\"capability\":\"")+cap+"\",\"api\":1}";}
static std::string grant(const char* cap,unsigned ns){return std::string("{\"capability\":\"")+cap+"\",\"api\":1,\"instance_id\":"+std::to_string(ns)+"}";}
static void nativeAuthorityChecks(){
 // Privileged harness assertions of the actual native admission authority.
 // These calls are never made through, or exported to, the host probe app API.
 auto installed=directory(activeRoot)["clock.json"];JsonDocument doc;
 assert(RiscBoot::parse(reinterpret_cast<const char*>(installed.data()),installed.size(),doc));doc["version"]="1.1.0";
 risc_bank_image_v1 image{};image.struct_size=sizeof(image);image.size=1024;image.store_abi=RiscUpdate::StoreAbi;auto current=nativeStatus();memcpy(image.active_store_sha256,current.active_store_sha256,32);
 auto refused=[&](const char* id){std::string text;serializeJson(doc,text);uint64_t token=99;assert(RiscBankStore::api.begin_app(nullptr,id,text.data(),text.size(),&image,&token)==RISC_BANK_INVALID&&token==0&&writeCount==0);};
 refused("unknown-app");
 for(const char* path:{"board.json","../clock.elf","other.elf","/clock.elf"}){doc["file_name"]=path;refused("clock");}doc["file_name"]="clock.elf";
 for(const char* version:{"1.0.0","0.9.9","1.0.01","1.1.0-rc"}){doc["version"]=version;refused("clock");}doc["version"]="1.1.0";
 doc["entry"]="driver_main";refused("clock");doc["entry"]="app_main";
 doc["grants"].to<JsonArray>();refused("clock");doc.remove("grants");
 auto req=doc["requires"].as<JsonArray>();req[0]["capability"]="platform.bank-store";refused("clock");
 req.clear();refused("clock");
 ensureActiveIntact();
}
static Files initialFiles(){
 Files files;const char* cap=kind=="app"?SOFTWARE_UPDATE_APPS_CAPABILITY:SOFTWARE_UPDATE_FIRMWARE_CAPABILITY;
 auto kvReq=requirement(RISC_KEY_VALUE_CAPABILITY);
 files["board.json"]=bytes(R"({"schema":"riscrte.board-hardware","schema_version":1,"board_id":"integration-test","revision":"unspecified","buses":[],"devices":[]})");
 files["probe.elf"]=readFile(fs::path(modules)/"probe.elf");
 files["probe.json"]=bytes(manifest("probe","1.0.0","probe.elf","["+requirement(cap)+","+kvReq+"]"));
 files["clock.json"]=bytes(manifest("clock","1.0.0","clock.elf","["+kvReq+"]"));files["clock.elf"]=elf("memcpy");files["unrelated.dat"]=Bytes(1025,0x6a);
 for(unsigned i=0;i<2;++i){std::string key=std::string("update-")+std::to_string(i);const char* suffix=i?"firmware":"apps";
  files[key+".elf"]=readFile(fs::path(modules)/(key+".elf"));
  files[key+".json"]=bytes(std::string("{\"type\":\"driver\",\"id\":\"software-update-")+suffix+"\",\"version\":\"0.1.0\",\"driver_abi\":2,\"architecture\":\"xtensa-esp32s3\",\"file_name\":\""+key+".elf\",\"requires\":["+requirement("platform.http-client")+","+requirement("platform.bank-store")+","+requirement("platform.clock")+"],\"provides\":["+requirement(i?SOFTWARE_UPDATE_FIRMWARE_CAPABILITY:SOFTWARE_UPDATE_APPS_CAPABILITY)+"]}");
 }
 files["boot.json"]=bytes(std::string("{\"board\":\"board.json\",\"default_app\":\"probe.elf\",\"drivers\":[{\"manifest\":\"update-0.json\"},{\"manifest\":\"update-1.json\"}],\"app_capabilities\":[{\"manifest\":\"probe.json\",\"grants\":[")+grant(cap,0)+","+grant(RISC_KEY_VALUE_CAPABILITY,1)+","+grant(RISC_KEY_VALUE_CAPABILITY,6)+"]},{\"manifest\":\"clock.json\",\"grants\":["+grant(RISC_KEY_VALUE_CAPABILITY,5)+"]}]}");
 if(scenario=="grant-bank"||scenario=="grant-http"||scenario=="namespace-missing"){
  JsonDocument boot;assert(RiscBoot::parse(reinterpret_cast<const char*>(files["boot.json"].data()),files["boot.json"].size(),boot));
  auto grants=boot["app_capabilities"][0]["grants"].as<JsonArray>();
  if(scenario=="namespace-missing")grants.remove(2);
  else {
   const char* raw=scenario=="grant-bank"?"platform.bank-store":"platform.http-client";
   JsonDocument app;assert(RiscBoot::parse(reinterpret_cast<const char*>(files["probe.json"].data()),files["probe.json"].size(),app));
   auto req=app["requires"].as<JsonArray>().add<JsonObject>();req["capability"]=raw;req["api"]=1;
   auto g=grants.add<JsonObject>();g["capability"]=raw;g["api"]=1;g["instance_id"]=0;
   std::string text;serializeJson(app,text);files["probe.json"]=bytes(text);
  }
  std::string text;serializeJson(boot,text);files["boot.json"]=bytes(text);
 }
 return files;
}
static std::string makeCatalog(){
 const char* repo="michaelrolphone-cmyk/RiscRTE-T-Watch-S3";auto hash=digest(payload);std::string req=requirement(RISC_KEY_VALUE_CAPABILITY);
 if(scenario=="authority"&&kind=="app")req=requirement(SOFTWARE_UPDATE_FIRMWARE_CAPABILITY);
 std::string m=manifest("clock","1.1.0","clock.elf","["+req+"]");
 std::string app="{\"kind\":\"app\",\"id\":\"clock\",\"version\":\"1.1.0\",\"tag\":\"app-clock-v1.1.0\",\"asset\":\"clock.elf\",\"url\":\"https://github.com/"+std::string(repo)+"/releases/download/app-clock-v1.1.0/clock.elf\",\"size\":"+std::to_string(payload.size())+",\"sha256\":\""+hash+"\",\"manifest\":"+m+"}";
 std::string firmware="{\"kind\":\"firmware\",\"version\":\"1.0.0\",\"tag\":\"firmware-v1.0.0\",\"asset\":\"twatch-s3-launcher-1.0.0.bin\",\"url\":\"https://github.com/"+std::string(repo)+"/releases/download/firmware-v1.0.0/twatch-s3-launcher-1.0.0.bin\",\"size\":8388608,\"sha256\":\""+hash+"\"";
 if(scenario!="authority"||kind!="firmware")firmware+=",\"ota\":{\"kind\":\"runtime-image\",\"runtime_version\":\"0.1.12\",\"layout\":\""+std::string(RiscUpdate::StoreAbi==2?"riscrte-paired-appdata-v2":"riscrte-paired-16m-v1")+"\",\"store_abi\":"+std::to_string(RiscUpdate::StoreAbi)+",\"asset\":\"riscrte-runtime-0.1.12.bin\",\"url\":\"https://github.com/"+std::string(repo)+"/releases/download/firmware-v1.0.0/riscrte-runtime-0.1.12.bin\",\"size\":"+std::to_string(payload.size())+",\"sha256\":\""+hash+"\"}";
 return "{\"schema\":1,\"firmware\":"+firmware+"},\"apps\":["+app+"],\"drivers\":[]}";
}
int main(int argc,char** argv){
 assert(argc==6);modules=argv[1];root=argv[2];kind=argv[4];scenario=argv[5];activeRoot=root+"/bootfs";stagedRoot=root+"/updatefs";
 assert(kind=="app"||kind=="firmware");
 if(scenario=="recover"){
  flash=readFile(fs::path(root)/"power-flash.bin");std::ifstream selected(fs::path(root)/"selected");selected>>activeBank;selectedBank=activeBank;
  // Recovery uses the running build version. Firmware-selected snapshots are
  // additionally verified by a separately compiled newer Runtime executable.
 }else{
  auto boot=readFile(argv[3]);assert(boot.size()==15104);memcpy(flash.data(),boot.data(),boot.size());
  #ifdef RISC_PAIRED_APP_DATA
  memset(flash.data()+0x270000,0x5a,0x80000);
#endif
  memset(flash.data()+0x9000,0xa5,0x6000);
  auto image=syntheticFirmware(RISC_BUILD_VERSION);memcpy(flash.data()+0x10000,image.data(),image.size());pack(0,initialFiles());
  uint8_t fw[32],store[32];SHA256(flash.data()+0x10000,imageSize,fw);SHA256(flash.data()+RiscUpdate::StoreOffset[0],RiscUpdate::StoreBytes,store);
  auto record=RiscUpdate::makeRecord(0,imageSize,fw,store);memcpy(flash.data()+RiscUpdate::JournalOffset,&record,sizeof(record));
 }
 originalFlash=flash;materialize(activeRoot,unpack(activeBank));
 if(scenario=="recover"&&activeBank==1&&kind=="firmware"&&std::strcmp(RISC_BUILD_VERSION,"0.1.12")){
  // An old Runtime must fail closed on a selected image identifying a newer
  // build. This process does not execute the synthetic firmware image.
  assert(!RiscBankStore::prepareBoot(owner,restartSafe,operationSafe));assert(writeCount==0&&confirms==0);
  std::cout<<kind<<" recover: old Runtime correctly refuses newer staged image; no target execution claim\n";return 0;
 }
 RiscCpu::NativeHttp::configure(owner,networkReady);
 RiscCpu::Hardware hardware{};hardware.owner=owner;hardware.now=[](){return ticks;};hardware.sleep=[](uint32_t n){ticks+=n;};
 hardware.gpioOpen=[](uint8_t,bool,bool,bool){assert(false);return false;};hardware.gpioWrite=[](uint8_t,bool){assert(false);return false;};hardware.gpioRead=[](uint8_t,bool*){assert(false);return false;};hardware.gpioPwm=[](uint8_t,uint32_t,uint16_t,uint16_t){assert(false);return false;};hardware.gpioClose=[](uint8_t){assert(false);return false;};
 hardware.i2cOpen=[](uint8_t,uint8_t,uint8_t,uint32_t){assert(false);return false;};hardware.i2cTransfer=[](uint8_t,uint8_t,const uint8_t*,size_t,uint8_t*,size_t,uint32_t){assert(false);return false;};hardware.i2cClose=[](uint8_t){assert(false);return false;};
 hardware.spiOpen=[](uint8_t,int16_t,int16_t,int16_t){assert(false);return false;};hardware.spiBegin=[](uint8_t,uint8_t,uint32_t,uint8_t,uint32_t){assert(false);return false;};hardware.spiTransfer=[](uint8_t,const uint8_t*,uint8_t*,size_t,uint32_t){assert(false);return false;};hardware.spiEnd=[](uint8_t,uint8_t,uint32_t){assert(false);return false;};hardware.spiClose=[](uint8_t){assert(false);return false;};
 hardware.httpClient=RiscCpu::NativeHttp::api();hardware.httpIdle=RiscCpu::NativeHttp::idle;hardware.httpSafe=RiscCpu::NativeHttp::safe;
 hardware.maintenanceIdle=RiscBankStore::exitSafe;cpu=new RiscCpu::Port(hardware);
 assert(RiscBankStore::prepareBoot(owner,restartSafe,operationSafe));assert(writeCount==0&&confirms==0);
 rt=new RiscBoot::Runtime({owner,[](risc_runtime_health_v1*){return true;},[](uint32_t n){ticks+=n;},[](const char*){return true;},bind,&kv,exitSafe,storageSafe,RiscBankStore::confirmBoot});
 bool prepared=rt->prepare(activeRoot.c_str());
 if(scenario=="grant-bank"||scenario=="grant-http"){
  assert(!prepared&&std::string(rt->error()).find("raw platform capability denied")!=std::string::npos);assert(writeCount==0&&confirms==0&&networkOpens==0);ensureActiveIntact();
  std::cout<<kind<<" "<<scenario<<" PASS (raw app policy denied before module load)\n";return 0;
 }
 if(!prepared){std::cerr<<rt->error()<<"\n";return 2;}
 payload=kind=="app"?elf(scenario=="elf-import"?"esp_partition_write":"memcpy"):syntheticFirmware(scenario=="firmware-old"?RISC_BUILD_VERSION:"0.1.12",scenario=="firmware-abi"?(RiscUpdate::StoreAbi==2?"1":"2"):(RiscUpdate::StoreAbi==2?"2":"1"));
 if(kind=="app")payload[400]=0x5a; // Distinct synthetic executable content, never target-executed.
 if(scenario=="elf-structure")payload[0]=0;
 catalog=makeCatalog();
 bool ok=rt->run();bool retained=scenario=="success"||scenario=="retry"||scenario=="network-retry"||scenario=="activation-unknown"||scenario=="close-retain";
 if(ok==retained){std::cerr<<"Unexpected Runtime outcome: "<<rt->error()<<"\n";return 3;}
 assert(rt->retained()==retained);assert(finalized==((scenario=="activation-unknown"||scenario=="close-retain")?0u:1u));ensureActiveIntact();
 if(retained)assert(!risc_runtime_get_api(1));
 else {assert(RiscCpu::NativeHttp::idle()&&RiscBankStore::exitSafe());assert(networkOpens==networkCloses);}
 std::cout<<kind<<" "<<scenario<<" PASS (real provider/Runtime/graph/CPU/native HTTP/bank, "<<writeCount<<" inactive writes, "<<confirms<<" health confirmations)\n";
 return 0;
}

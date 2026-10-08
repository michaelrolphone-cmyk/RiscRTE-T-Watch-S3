// Admit the complete supplied production store through the real Runtime and
// CpuPort. Nothing rewrites its board, driver manifests, app manifests or policy.
// The lowest hardware boundary is inert; prepare must not invoke native I/O.
#define private public
#include "bootstrap/Runtime.h"
#include "ports/esp32s3/CpuPort.h"
#undef private
#include <cstdio>
#if defined(STORE_ADMISSION_COHORT) && !defined(STORE_ADMISSION_COHORT_POLICY)
#include "cohort_elf_admission.h"
#endif
#ifdef STORE_ADMISSION_COHORT_POLICY
// The RF profile test reuses already verified accepted target bytes. This
// callback checks inventory only; it does not qualify future rebuilt ELFs.
namespace CohortElf {
static bool file(void* context,const char* path,bool) {
  FILE* input=fopen(path,"rb");if(!input)return false;
  const bool present=fgetc(input)!=EOF;const bool closed=fclose(input)==0;
  if(present && closed)++*static_cast<unsigned*>(context);
  return present && closed;
}
}
#ifdef STORE_ADMISSION_RUNTIME_FEATURES
static_assert(RiscBoot::Runtime::MaxAppPolicyGrants==16,"Runtime feature grant bound changed");
#else
static_assert(RiscBoot::Runtime::MaxAppPolicyGrants==12,"RF grant bound changed");
#endif
static_assert(RISC_APP_DATA_NAMESPACE_MAX==131072,"RF namespace quota changed");
static_assert(RISC_APP_DATA_FILE_MAX==65536 && RISC_APP_DATA_FILES_MAX>=3,"RF file bounds changed");
#endif
#ifdef STORE_ADMISSION_APP_DATA
#include "app_data_admission_backend.h"
#endif
#ifdef STORE_ADMISSION_UPDATE_PLATFORMS
#include <RiscHttpClientV1.h>
#include <RiscBankStoreV1.h>
#endif

namespace {
unsigned hardwareCalls = 0, storageCalls = 0;
#ifdef STORE_ADMISSION_COHORT
unsigned cooperativeYields = 0;
#endif
RiscCpu::Port* cpu = nullptr;
bool owner() { return true; }
#ifdef STORE_ADMISSION_UPDATE_PLATFORMS
risc_http_client_v1 httpApi{
  1,sizeof(httpApi),nullptr,
  [](void*,const risc_http_request_v1*,uint64_t*)->int32_t{return RISC_HTTP_CLOSED;},
  [](void*,uint64_t,void*,uint32_t,uint32_t*)->int32_t{return RISC_HTTP_CLOSED;},
  [](void*,uint64_t,risc_http_response_v1*)->int32_t{return RISC_HTTP_CLOSED;},
  [](void*,uint64_t)->int32_t{return RISC_HTTP_CLOSED;}
};
risc_bank_store_v1 bankApi{
  1,sizeof(bankApi),nullptr,
  [](void*,risc_bank_status_v1*){return false;},
  [](void*,const risc_bank_image_v1*,uint64_t*)->int32_t{return RISC_BANK_UNAVAILABLE;},
  [](void*,const char*,const void*,uint32_t,const risc_bank_image_v1*,uint64_t*)->int32_t{return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t,risc_bank_status_v1*)->int32_t{return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t,const void*,uint32_t)->int32_t{return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t)->int32_t{return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t)->int32_t{return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t)->int32_t{return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t){return false;},
  [](void*,uint32_t,void*,uint32_t,uint32_t*)->int32_t{return RISC_BANK_UNAVAILABLE;}
};
#endif
bool bind(RiscBoot::Runtime& runtime) {
  if (!cpu->bind(runtime)) return false;
#ifdef STORE_ADMISSION_UPDATE_PLATFORMS
  if (!runtime.registerPlatform(RISC_HTTP_CLIENT_CAPABILITY,RISC_HTTP_CLIENT_API_V1,
                                RiscBoot::Runtime::Scope::Global,0,&httpApi)) return false;
  if (!runtime.registerPlatform(RISC_BANK_STORE_CAPABILITY,RISC_BANK_STORE_API_V1,
                                RiscBoot::Runtime::Scope::Global,0,&bankApi)) return false;
#endif
  return true;
}
RiscCpu::Hardware hardware() {
  RiscCpu::Hardware h{};
#ifdef STORE_ADMISSION_HCI
  h.hciOpen=[](){++hardwareCalls;return false;};
  h.hciSend=[](uint8_t,const uint8_t*,size_t,uint32_t){++hardwareCalls;return false;};
  h.hciReceive=[](uint8_t*,uint8_t*,size_t,size_t*,uint32_t){++hardwareCalls;return false;};
  h.hciClose=[](){++hardwareCalls;return false;};
  h.hciIdle=[](){++hardwareCalls;return false;};h.hciSafe=[](){++hardwareCalls;return false;};
#endif
#ifdef STORE_ADMISSION_RUNTIME_FEATURES
  h.realtimeRead=[](risc_realtime_snapshot_v1*)->int32_t{++hardwareCalls;return RISC_REALTIME_IO;};
  h.realtimeSeed=[](int64_t,uint32_t)->int32_t{++hardwareCalls;return RISC_REALTIME_IO;};
#endif
  h.owner = owner;
#ifdef STORE_ADMISSION_RADIO_IQ
  h.radioIqReady=[](){++hardwareCalls;return false;};
#ifdef STORE_ADMISSION_IQ_LIFECYCLE
  h.radioIqPrepare=[](){++hardwareCalls;return false;};
  h.radioIqCleanup=[](){++hardwareCalls;return false;};
#endif
#endif
  h.now = []() -> uint64_t { ++hardwareCalls; return 0; };
  h.sleep = [](uint32_t) { ++hardwareCalls; };
  h.gpioOpen = [](uint8_t, bool, bool, bool) { ++hardwareCalls; return false; };
  h.gpioWrite = [](uint8_t, bool) { ++hardwareCalls; return false; };
  h.gpioRead = [](uint8_t, bool*) { ++hardwareCalls; return false; };
  h.gpioPwm = [](uint8_t, uint32_t, uint16_t, uint16_t) { ++hardwareCalls; return false; };
  h.gpioClose = [](uint8_t) { ++hardwareCalls; return false; };
  h.i2cOpen = [](uint8_t, uint8_t, uint8_t, uint32_t) { ++hardwareCalls; return false; };
  h.i2cTransfer = [](uint8_t, uint8_t, const uint8_t*, size_t, uint8_t*, size_t, uint32_t) { ++hardwareCalls; return false; };
  h.i2cClose = [](uint8_t) { ++hardwareCalls; return false; };
  h.spiOpen = [](uint8_t, int16_t, int16_t, int16_t) { ++hardwareCalls; return false; };
  h.spiBegin = [](uint8_t, uint8_t, uint32_t, uint8_t, uint32_t) { ++hardwareCalls; return false; };
  h.spiTransfer = [](uint8_t, const uint8_t*, uint8_t*, size_t, uint32_t) { ++hardwareCalls; return false; };
  h.spiEnd = [](uint8_t, uint8_t, uint32_t) { ++hardwareCalls; return false; };
  h.spiClose = [](uint8_t) { ++hardwareCalls; return false; };
  h.i2sOpen = [](uint8_t, uint8_t, uint8_t, uint8_t, uint32_t) { ++hardwareCalls; return false; };
  h.i2sWrite = [](uint8_t, const int16_t*, size_t, size_t*, uint32_t) { ++hardwareCalls; return false; };
#ifdef STORE_ADMISSION_I2S_RX
  h.i2sOpenRx = [](uint8_t, uint8_t, uint8_t, uint32_t) { ++hardwareCalls; return false; };
  h.i2sRead = [](uint8_t, int16_t*, size_t, size_t*, uint32_t) { ++hardwareCalls; return false; };
#endif
  h.i2sClose = [](uint8_t) { ++hardwareCalls; return false; };
#ifdef STORE_ADMISSION_RADIO
  h.radioJoin = [](const char*, const char*) { ++hardwareCalls; return false; };
  h.radioState = [](uint8_t*, int8_t*) { ++hardwareCalls; return false; };
  h.radioLeave = []() { ++hardwareCalls; return false; };
  h.radioAddresses = [](uint8_t*, uint8_t*) { ++hardwareCalls; return false; };
  h.radioScanStart = []() { ++hardwareCalls; return false; };
  h.radioScanPoll = [](garden_radio_scan_result_v1*) { ++hardwareCalls; return false; };
  h.radioScanCancel = []() { ++hardwareCalls; return false; };
  h.radioIdle = []() { ++hardwareCalls; return false; };
#endif
  return h;
}
}

int main(int argc, char** argv) {
#ifdef STORE_ADMISSION_COHORT
  if (argc != 3) return 2;
#else
  if (argc != 2) return 2;
#endif
  const RiscBoot::KeyValueBackend kv{
    nullptr,
    [](void*, uint32_t, const char*, void*, uint32_t, uint32_t*) -> int32_t {
      ++storageCalls; return RISC_KEY_VALUE_IO;
    },
    [](void*, uint32_t, const char*, const void*, uint32_t) -> int32_t {
      ++storageCalls; return RISC_KEY_VALUE_IO;
    }
#ifdef STORE_ADMISSION_KV_V2
    ,RISC_KEY_VALUE_V2_BLOB_MAX
#endif
  };
  RiscCpu::Port port(hardware());
  cpu = &port;
#ifdef STORE_ADMISSION_APP_DATA
  const auto appData=admissionAppData(&storageCalls);
#endif
  RiscBoot::Port runtimePort{owner, [](risc_runtime_health_v1*) { return true; },
#ifdef STORE_ADMISSION_COHORT
                            [](uint32_t) { ++cooperativeYields; },
#else
                            [](uint32_t) { ++hardwareCalls; },
#endif
                            [](const char*) { return true; }, bind, &kv
#ifdef STORE_ADMISSION_APP_DATA
                            ,nullptr,nullptr,nullptr,&appData
#endif
                            };
#ifdef STORE_ADMISSION_RUNTIME_FEATURES
  RiscRetainedWake::Image rtcImage{};
  RiscRetainedWake::Store wake(rtcImage);runtimePort.retainedWake=&wake;
#endif
  RiscBoot::Runtime runtime(runtimePort);
  const bool prepared = runtime.prepare(argv[1]);
  if (!prepared) {
    fprintf(stderr, "ADMISSION platforms=%zu drivers=%zu\n", runtime.platformCount_, runtime.driverCount_);
    for (size_t i=0;i<runtime.platformCount_;++i) {
      const auto& p=runtime.platforms_[i];
      fprintf(stderr, "PLAT %zu cap=%s api=%u scope=%u id=%llu\n", i,p.capability,p.api,
              unsigned(p.scope),(unsigned long long)p.id);
    }
    for (size_t i=0;i<runtime.driverCount_;++i) {
      const auto& d=runtime.drivers_[i];
      fprintf(stderr, "DRV %zu id=%s inst=%llu reqs=%zu\n", i,d.id,(unsigned long long)d.instance,d.count);
      for (size_t r=0;r<d.count;++r) {
        const auto& q=d.requirements[r];
        fprintf(stderr, "  REQ cap=%s api=%u trusted=%p providerInst=%llu\n", q.capability,q.api,q.trustedApi,
                (unsigned long long)q.providerInstance);
      }
    }
  }
#ifdef STORE_ADMISSION_COHORT
  RiscBoot::Runtime candidate({});unsigned admitted=0;
  const bool validated=prepared && runtime.validateCohort(candidate,argv[2],CohortElf::file,&admitted);
  printf("{\"prepared\":%s,\"cohort_validated\":%s,\"error\":\"%s\",\"hardware_calls\":%u,\"storage_calls\":%u,\"elf_count\":%u,\"cooperative_yields\":%u}\n",
         prepared?"true":"false",validated?"true":"false",candidate.error(),hardwareCalls,storageCalls,admitted,cooperativeYields);
#else
  // Runtime errors are constant diagnostics, with no input text or credentials.
  printf("{\"prepared\":%s,\"error\":\"%s\",\"hardware_calls\":%u,\"storage_calls\":%u,\"i2s_tables\":%zu}\n",
         prepared ? "true" : "false", runtime.error(), hardwareCalls, storageCalls, port.i2sCount_);
#endif
  return hardwareCalls || storageCalls ? 3 : 0;
}

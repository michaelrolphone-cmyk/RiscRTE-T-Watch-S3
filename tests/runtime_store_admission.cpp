// Admit the complete supplied production store through the real Runtime and
// CpuPort. Nothing rewrites its board, driver manifests, app manifests or policy.
// The lowest hardware boundary is inert; prepare must not invoke native I/O.
#define private public
#include "bootstrap/Runtime.h"
#include "ports/esp32s3/CpuPort.h"
#undef private
#include <cstdio>
#ifdef STORE_ADMISSION_UPDATE_PLATFORMS
#include <RiscHttpClientV1.h>
#include <RiscBankStoreV1.h>
#endif

namespace {
unsigned hardwareCalls = 0, storageCalls = 0;
RiscCpu::Port* cpu = nullptr;
bool owner() { return true; }
#ifdef STORE_ADMISSION_UPDATE_PLATFORMS
risc_http_client_v1 httpApi{
  1,sizeof(httpApi),nullptr,
  [](void*,const risc_http_request_v1*,uint64_t*){return RISC_HTTP_CLOSED;},
  [](void*,uint64_t,void*,uint32_t,uint32_t*){return RISC_HTTP_CLOSED;},
  [](void*,uint64_t,risc_http_response_v1*){return RISC_HTTP_CLOSED;},
  [](void*,uint64_t){return RISC_HTTP_CLOSED;}
};
risc_bank_store_v1 bankApi{
  1,sizeof(bankApi),nullptr,
  [](void*,risc_bank_status_v1*){return false;},
  [](void*,const risc_bank_image_v1*,uint64_t*){return RISC_BANK_UNAVAILABLE;},
  [](void*,const char*,const void*,uint32_t,const risc_bank_image_v1*,uint64_t*){return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t,risc_bank_status_v1*){return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t,const void*,uint32_t){return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t){return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t){return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t){return RISC_BANK_UNAVAILABLE;},
  [](void*,uint64_t){return false;},
  [](void*,uint32_t,void*,uint32_t,uint32_t*){return RISC_BANK_UNAVAILABLE;}
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
  h.owner = owner;
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
  if (argc != 2) return 2;
  const RiscBoot::KeyValueBackend kv{
    nullptr,
    [](void*, uint32_t, const char*, void*, uint32_t, uint32_t*) -> int32_t {
      ++storageCalls; return RISC_KEY_VALUE_IO;
    },
    [](void*, uint32_t, const char*, const void*, uint32_t) -> int32_t {
      ++storageCalls; return RISC_KEY_VALUE_IO;
    }};
  RiscCpu::Port port(hardware());
  cpu = &port;
  RiscBoot::Runtime runtime({owner, [](risc_runtime_health_v1*) { return true; },
                            [](uint32_t) { ++hardwareCalls; },
                            [](const char*) { return true; }, bind, &kv});
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
  // Runtime errors are constant diagnostics, with no input text or credentials.
  printf("{\"prepared\":%s,\"error\":\"%s\",\"hardware_calls\":%u,\"storage_calls\":%u,\"i2s_tables\":%zu}\n",
         prepared ? "true" : "false", runtime.error(), hardwareCalls, storageCalls, port.i2sCount_);
  return hardwareCalls || storageCalls ? 3 : 0;
}

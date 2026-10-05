// Admit the complete supplied production store through the real Runtime and
// CpuPort. Nothing rewrites its board, driver manifests, app manifests or policy.
// The lowest hardware boundary is inert; prepare must not invoke native I/O.
#include "bootstrap/Runtime.h"
#include "ports/esp32s3/CpuPort.h"
#include <cstdio>

namespace {
unsigned hardwareCalls = 0, storageCalls = 0;
RiscCpu::Port* cpu = nullptr;
bool owner() { return true; }
bool bind(RiscBoot::Runtime& runtime) { return cpu->bind(runtime); }
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
  // Runtime errors are constant diagnostics, with no input text or credentials.
  printf("{\"prepared\":%s,\"error\":\"%s\",\"hardware_calls\":%u,\"storage_calls\":%u}\n",
         prepared ? "true" : "false", runtime.error(), hardwareCalls, storageCalls);
  return hardwareCalls || storageCalls ? 3 : 0;
}

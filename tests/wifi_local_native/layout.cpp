// Compile with the actual selected Runtime command. Never link into firmware.
#include "ports/esp32s3/NativeAppDataMount.h"
#pragma push_macro("B110")
#pragma push_macro("B1000000")
#undef B110
#undef B1000000
#include "ports/esp32s3/NativeSettingsAssembly.cpp"
#include "ports/esp32s3/NativeSettingsBackend.cpp"
#include "ports/esp32s3/NativeSettingsWorker.cpp"
#include "ports/esp32s3/CpuPort.h"
#pragma pop_macro("B1000000")
#pragma pop_macro("B110")
static_assert(RISC_NATIVE_SETTINGS_LOCAL_ONLY == 1);
static_assert(RISC_NATIVE_SETTINGS_LOCAL_FRESH == 0);
static_assert(RISC_NATIVE_SETTINGS_VOLUME_INSTANCE == 0);
static_assert(RISC_NATIVE_SETTINGS_NAMESPACE_MASK == 2);
static_assert(RiscCpu::NativeSettingsWorker::StackBytes == 8192);
static_assert(RiscCpu::NativeSettingsWorker::MaxBindings == 2);
static_assert(!RiscCpu::NativeSettingsLifecycle::namespaceSelected(0));
static_assert(RiscCpu::NativeSettingsLifecycle::namespaceSelected(1));
#define SIZE(name, type) extern "C" { char measured_##name[sizeof(type)]; }
#define ALIGN(name, type) extern "C" { char measured_##name[alignof(type)]; }
SIZE(assembly, RiscCpu::NativeSettingsAssembly::State)
ALIGN(assembly_alignment, RiscCpu::NativeSettingsAssembly::State)
SIZE(backend, RiscCpu::NativeSettingsBackend::State)
SIZE(worker_binding, RiscCpu::NativeSettingsWorker::Binding)
ALIGN(worker_binding_alignment, RiscCpu::NativeSettingsWorker::Binding)
SIZE(worker_registry, RiscCpu::NativeSettingsWorker::Registry)
SIZE(task_control, StaticTask_t)
SIZE(runtime, RiscBoot::Runtime)
SIZE(cpu_port, RiscCpu::Port)
extern "C" {
char measured_worker_stack_bytes[RiscCpu::NativeSettingsWorker::StackBytes];
char measured_worker_count[RiscCpu::NativeSettingsWorker::MaxBindings];
}

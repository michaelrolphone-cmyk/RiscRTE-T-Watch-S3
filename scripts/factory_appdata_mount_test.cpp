// Host-only test of production AppData, NativeAppDataMount and NativeFileSource.
// ESP-IDF, RTOS and physical flash boundaries use Runtime's real-LittleFS fixture.
// The selected full-image bytes are read-only; mutations stay in modeled flash.
#include "ports/esp32s3/NativeAppData.h"
#include "ports/esp32s3/NativeAppDataMount.h"
#include "ports/esp32s3/NativeFileSource.h"
#include "native_littlefs_profile_fixture.h"
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <unistd.h>
#include <vector>

extern "C" void native_lfs_fixture_select_appdata(void);
extern "C" int fixture_load_raw(const void*, size_t);
extern "C" void* xTaskGetCurrentTaskHandle() {
    static thread_local int task;
    return &task;
}
extern "C" int xPortInIsrContext() { return 0; }

namespace RiscCpu {
static bool lease = false;
bool nativeRadioResourceTry() {
    if (lease) return false;
    lease = true;
    return true;
}
void nativeRadioResourceEnd() { assert(lease); lease = false; }
bool nativeRadioResourceHeldReady() { return lease; }
bool nativeRadioResourceReady() { return !lease; }
bool nativeBackgroundResourceTry() { return nativeRadioResourceTry(); }
void nativeBackgroundResourceEnd() { nativeRadioResourceEnd(); }
}

extern "C" off_t __wrap_lseek(int fd, off_t offset, int whence) {
    RiscAppDataMount::Identity identity{};
    if (!RiscAppDataMount::identity(identity)) { errno = EIO; return -1; }
    return identity.vfs->lseek_p(const_cast<void*>(identity.context), fd, offset, whence);
}

int main(int argc, char** argv) {
    assert(argc == 4);
    const bool reject = !std::strcmp(argv[2], "reject");
    const bool reboot = !std::strcmp(argv[2], "reboot");
    assert(reject || reboot || !std::strcmp(argv[2], "fresh"));

    FILE* input = std::fopen(argv[1], "rb");
    assert(input && !std::fseek(input, 0, SEEK_END));
    const long length = std::ftell(input);
    assert(length == 0x1000000 || (reboot && length == 0x80000));
    assert(!std::fseek(input, length == 0x1000000 ? 0x270000 : 0, SEEK_SET));
    std::vector<unsigned char> raw(0x80000);
    assert(std::fread(raw.data(), 1, raw.size(), input) == raw.size());
    assert(!std::fclose(input));

    // Do not call fixture_reset: that helper formats its test filesystem.
    native_lfs_fixture_select_appdata();
    assert(fixture_load_raw(raw.data(), raw.size()) == 0);
    const bool mounted = RiscAppData::prepare([] { return true; }, [] { return true; });
    if (reject) {
        assert(!mounted);
        assert(!RiscFileSource::prepare([] { return true; }, [] { return true; }));
        assert(!RiscFileSource::backend());
        native_lfs_fixture_counters counters{};
        native_lfs_fixture_get_counters(&counters);
        assert(!counters.calls[NATIVE_LFS_FLASH_PROG]);
        assert(!counters.calls[NATIVE_LFS_FLASH_ERASE]);
        assert(!counters.flash_program_bytes && !counters.flash_erase_bytes);
        std::vector<unsigned char> unchanged(raw.size());
        assert(native_lfs_fixture_snapshot(unchanged.data(), unchanged.size()) == unchanged.size());
        assert(unchanged == raw);
        std::printf("COUNTERS: reads=%llu program=0 erase=0 bytes_unchanged=yes\n",
                    static_cast<unsigned long long>(counters.calls[NATIVE_LFS_FLASH_READ]));
        std::puts("PASS: erased-appdata image rejects production mount/FileSource preparation without flash writes");
        return 0;
    }

    assert(mounted && RiscAppDataMount::ready());
    assert(RiscFileSource::prepare([] { return true; }, [] { return true; }));
    const auto* app = RiscAppData::backend();
    assert(app);
    const char saved[] = "factory-boot-test";
    uint32_t size = 0;
    uint64_t revision = 0;
    if (!reboot) assert(app->replace(app->context, 1, "boot-test", 0, saved, sizeof saved) == 0);
    assert(app->stat(app->context, 1, "boot-test", &size, &revision) == 0 && size == sizeof saved);
    char value[sizeof saved]{};
    assert(app->read(app->context, 1, "boot-test", revision, value, sizeof value, &size, &revision) == 0);
    assert(size == sizeof saved && !std::memcmp(value, saved, sizeof saved));

    const auto* source = RiscFileSource::backend();
    assert(source);
    std::vector<unsigned char> data(65536);
    for (unsigned i = 0; i < data.size(); ++i) data[i] = i % 251;
    assert(source->begin(source->context, data.size()) == 0);
    uint32_t actual = 0;
    for (unsigned offset = 0; offset < data.size(); offset += actual) {
        actual = 0;
        assert(source->write(source->context, data.data() + offset, 512, &actual) == 0 && actual == 512);
    }
    assert(source->finish(source->context) == 0);
    unsigned char result[512];
    for (unsigned offset = 0; offset < data.size(); offset += actual) {
        actual = 0;
        assert(source->readAt(source->context, offset, result, sizeof result, &actual) == 0 && actual == 512);
        assert(!std::memcmp(result, data.data() + offset, sizeof result));
    }
    assert(source->readAt(source->context, 4097, result, sizeof result, &actual) == 0 && actual == 512);
    assert(!std::memcmp(result, data.data() + 4097, sizeof result));
    assert(source->discard(source->context) == 0);
    assert(RiscFileSource::resetSafe() && RiscAppData::exitSafe());

    native_lfs_fixture_counters counters{};
    native_lfs_fixture_get_counters(&counters);
    assert(!counters.live_files && !counters.live_dirs);
    assert(!counters.flash_rejected_bounds && !counters.flash_rejected_program);
    std::printf("COUNTERS: reads=%llu program=%llu erase=%llu live_files=%zu live_dirs=%zu; all 65536 scratch bytes verified\n",
                static_cast<unsigned long long>(counters.calls[NATIVE_LFS_FLASH_READ]),
                static_cast<unsigned long long>(counters.calls[NATIVE_LFS_FLASH_PROG]),
                static_cast<unsigned long long>(counters.calls[NATIVE_LFS_FLASH_ERASE]),
                counters.live_files, counters.live_dirs);
    assert(native_lfs_fixture_snapshot(raw.data(), raw.size()) == raw.size());
    FILE* output = std::fopen(argv[3], "wb");
    assert(output);
    assert(std::fwrite(raw.data(), 1, raw.size(), output) == raw.size());
    assert(!std::fclose(output));
    std::printf("PASS: host-only %s; production mount/FileSource ready; full 64 KiB scratch roundtrip; saved AppData readable\n",
                reboot ? "separate-process cold remount" : "fresh mount of exact image appdata");
}

#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
runtime="$(cd "${1:?Pass exact Runtime source checkout}" && pwd)"
apps="$(cd "${2:?Pass exact System Apps source checkout}" && pwd)"
boot="${3:?Pass verified rollback bootloader}"
build="${BUILD_DIR:-$here/build}"
mkdir -p "$build/modules"
flags=(-Wall -Wextra -Werror -Wno-missing-field-initializers -Wno-misleading-indentation -Wno-deprecated-declarations -g)
san=()
if [[ "${SANITIZE:-0}" == 1 ]]; then san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer);fi
inc=(-I"$here/shim" -I"$runtime/test/native_http_shim" -I"$runtime/test/native_bank_stubs" -I"$runtime/test/drivers/stubs" -I"$runtime/lib/elf_loader/include" -I"$runtime/src" -I"$runtime/sdk/app" -I"$runtime/sdk/driver" -I"$runtime/sdk/hardware" -I"$runtime/lib/ArduinoJson/src" -I"$apps/lib/PortableApps/include" -I"$apps/lib/NativeApps/include")
cc "${san[@]}" -std=c11 "${inc[@]}" -c "$runtime/lib/elf_loader/src/esp_elf_validate.c" -o "$build/validate.o"
cc "${san[@]}" -std=c11 "${inc[@]}" -c "$runtime/test/native_http_shim/http_parser.c" -o "$build/parser.o"
cc "${san[@]}" -std=c11 "${flags[@]}" "${inc[@]}" -fPIC -fvisibility=hidden -shared "$here/probe_app.c" -o "$build/modules/probe.elf"
for kind in 0 1; do
 c++ "${san[@]}" -std=c++17 "${flags[@]}" "${inc[@]}" -fPIC -fvisibility=hidden -shared -DUPDATE_FIRMWARE="$kind" "$apps/Services/update/service.cpp" -o "$build/modules/update-$kind.elf"
done
sources=("$runtime/src/bootstrap/Json.cpp" "$runtime/src/bootstrap/Board.cpp" "$runtime/src/bootstrap/Runtime.cpp" "$runtime/src/runtime/drivers/ProviderGraphV2.cpp" "$runtime/src/runtime/drivers/ProviderModuleV2.cpp" "$runtime/src/ports/esp32s3/CpuPort.cpp" "$runtime/src/runtime/update/PairedBank.cpp" "$runtime/src/runtime/update/StoreAudit.cpp")
c++ "${san[@]}" -std=c++17 "${flags[@]}" "${inc[@]}" -DRISC_PAIRED_BANKS=1 -rdynamic -no-pie "${sources[@]}" "$here/integration.cpp" "$build/validate.o" "$build/parser.o" -Wl,--wrap=close -Wl,--wrap=fopen -Wl,--wrap=opendir -Wl,--wrap=stat -ldl -lcrypto -o "$build/integration"
c++ "${san[@]}" -std=c++17 "${flags[@]}" "${inc[@]}" -DRISC_PAIRED_BANKS=1 -DRISC_TEST_RECOVERY_NEW=1 -rdynamic -no-pie "${sources[@]}" "$here/integration.cpp" "$build/validate.o" "$build/parser.o" -Wl,--wrap=close -Wl,--wrap=fopen -Wl,--wrap=opendir -Wl,--wrap=stat -ldl -lcrypto -o "$build/integration-new-runtime"
run_case() {
 local kind="$1" scenario="$2" dir="$build/$1-$2"
 mkdir -p "$dir"
 ASAN_OPTIONS=detect_leaks=0 "$build/integration" "$build/modules" "$dir" "$boot" "$kind" "$scenario"
 case "$scenario" in power-*) ASAN_OPTIONS=detect_leaks=0 "$build/integration" "$build/modules" "$dir" "$boot" "$kind" recover;; esac
 if [[ "$kind:$scenario" == firmware:power-selected ]]; then ASAN_OPTIONS=detect_leaks=0 "$build/integration-new-runtime" "$build/modules" "$dir" "$boot" "$kind" recover; fi
 # Preserve unique flash evidence without keeping 16 MiB of mostly-erased bytes.
 if [[ -f "$dir/power-flash.bin" ]]; then gzip -f "$dir/power-flash.bin"; fi
}
pids=()
for kind in app firmware; do
 for scenario in success grant-bank grant-http namespace-missing cancel retry network network-retry timeout short corrupt unconfirmed authority firmware-old firmware-abi elf-import elf-unavailable elf-structure store-tamper mount-retain close-retain activation-unknown power-copy power-download power-ready power-selected; do
  case "$kind:$scenario" in app:firmware-*|firmware:elf-*|firmware:store-tamper|firmware:mount-retain) continue;; esac
  run_case "$kind" "$scenario" & pids+=("$!")
  if (( ${#pids[@]} >= ${JOBS:-1} )); then for pid in "${pids[@]}"; do wait "$pid"; done; pids=(); fi
 done
done
for pid in "${pids[@]}"; do wait "$pid"; done

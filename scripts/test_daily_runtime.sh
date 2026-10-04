#!/usr/bin/env bash
set -euo pipefail
watch="$(cd "$(dirname "$0")/.." && pwd)"
runtime="$(cd "${1:?Pass exact paired Runtime source}" && pwd)"
# Use the exact host-mapped deployment compiled by test_launcher_runtime.sh.
# It contains all seven physical drivers plus the seven production app ELFs.
store="$(cd "${2:?Pass prepared host deployment store}" && pwd)"
[[ "$(git -C "$runtime" rev-parse HEAD)" == 8609fb92ee56ad1c6fb0417051c3fc9796c0edca ]]
[[ -z "$(git -C "$runtime" status --porcelain --untracked-files=no)" ]]
for app in default clock springboard battery settings calculator stopwatch; do
  [[ -f "$store/$app.elf" && -f "$store/$app.json" ]]
done
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
incs=(-I"$watch/tests/runtime-stubs" -I"$runtime/src" -I"$runtime/sdk/app" -I"$runtime/sdk/driver" -I"$runtime/sdk/hardware" -I"$watch/sdk/driver" -I"$watch/include" -I"$watch" -I"$runtime/lib/ArduinoJson/src")
flags=(-O0 -g -fsanitize=undefined -fno-sanitize-recover=all -Wall -Wextra -Werror -Wno-missing-field-initializers)
c++ -std=c++17 "${flags[@]}" -rdynamic "${incs[@]}" \
  "$runtime/src/bootstrap/Board.cpp" "$runtime/src/bootstrap/Json.cpp" "$runtime/src/bootstrap/Runtime.cpp" \
  "$runtime/src/ports/esp32s3/CpuPort.cpp" "$runtime/src/runtime/drivers/ProviderModuleV2.cpp" "$runtime/src/runtime/drivers/ProviderGraphV2.cpp" \
  "$watch/tests/daily_runtime_test.cpp" -ldl -o "$build/daily-test"
"$build/daily-test" "$store"

#!/usr/bin/env bash
set -euo pipefail
watch="$(cd "$(dirname "$0")/.." && pwd)"
runtime="$(cd "${1:?Pass exact paired Runtime source}" && pwd)"
system="$(cd "${2:?Pass exact shared System Apps source}" && pwd)"
utilities="$(cd "${3:?Pass exact shared Utilities source}" && pwd)"
# The runtime pairing is part of the deployment contract, not a moving checkout.
[[ "$(git -C "$runtime" rev-parse HEAD)" == fe9d3c877ac98e52670d458f45b59fda8011a4fd ]]
[[ -z "$(git -C "$runtime" status --porcelain --untracked-files=no)" ]]
python3 - "$watch" "$system" "$utilities" <<'PYPINS'
import json,pathlib,subprocess,sys
watch,system,utilities=map(pathlib.Path,sys.argv[1:])
pins=json.loads((watch/'apps/shared-sources.json').read_text())
for name,path in [('system-apps',system),('utilities',utilities)]:
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()==pins[name]['commit']
 assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=path,text=True).strip()
PYPINS
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cp -R "$watch/dist/launcher-deployments/sx1262-915-bma423/store/." "$build/"
cmp "$runtime/sdk/app/RiscRuntimeV1.h" "$watch/sdk/app/RiscRuntimeV1.h"
incs=(-I"$watch/tests/runtime-stubs" -I"$runtime/src" -I"$runtime/sdk/app" -I"$runtime/sdk/driver" -I"$runtime/sdk/hardware" -I"$watch/sdk/driver" -I"$watch/include" -I"$watch" -I"$runtime/lib/ArduinoJson/src")
watchincs=(-I"$watch/sdk/app" -I"$watch/sdk/driver" -I"$watch/include" -I"$watch")
flags=(-O1 -g -fsanitize=undefined -fno-sanitize-recover=all -Wall -Wextra -Werror)
for name in gpio i2c pmu panel touch rtc; do
 src="$watch/drivers/twatch_$name/driver.c"
 if [[ "$name" == i2c ]]; then src="$watch/drivers/twatch_i2c/i2c_main.c"; fi
 cc -std=c11 "${flags[@]}" -fPIC -shared -fvisibility=hidden "${watchincs[@]}" "$src" -o "$build/$name/driver.elf"
done
cc -std=c11 "${flags[@]}" -DWATCH_CLOCK_LAUNCHER -fPIC -fvisibility=hidden "${watchincs[@]}" -c "$watch/apps/clock/crown.c" -o "$build/crown.o"
cc -std=c11 "${flags[@]}" -fPIC -fvisibility=hidden "${watchincs[@]}" -c "$watch/apps/clock/nova/nova.c" -o "$build/nova.o"
c++ -std=c++11 "${flags[@]}" -fPIC -shared -fvisibility=hidden "${watchincs[@]}" "$watch/apps/clock/effects/boot.cpp" "$build/crown.o" "$build/nova.o" -o "$build/default.elf"
cc -std=c11 "${flags[@]}" -DWATCH_CLOCK_LAUNCHER -DWATCH_CLOCK_RETURN -fPIC -fvisibility=hidden "${watchincs[@]}" -c "$watch/apps/clock/crown.c" -o "$build/crown-return.o"
c++ -std=c++11 "${flags[@]}" -fPIC -shared -fvisibility=hidden "${watchincs[@]}" "$watch/apps/clock/effects/boot.cpp" "$build/crown-return.o" "$build/nova.o" -o "$build/clock.elf"
portable=(-I"$system/lib/PortableApps/include" -I"$system/lib/NativeApps/include")
for name in springboard battery settings calculator stopwatch; do
 source="$system/Apps/$name.c";flags_app=(-DPORTABLE_TOUCH_ROTATION=0 -DPORTABLE_RTC_UTC8_DENVER -DPORTABLE_FORCE_FULL_FRAMES -DPORTABLE_INPUT_NAVIGATION -DPORTABLE_INPUT_NAVIGATION_LOCAL)
 if [[ "$name" == battery || "$name" == calculator || "$name" == stopwatch ]]; then source="$utilities/Apps/$name.c"; fi
 if [[ "$name" == settings ]]; then flags_app+=(-DPORTABLE_SETTINGS_APP -DPORTABLE_SLEEP_SETTINGS); fi
 if [[ "$name" == springboard ]]; then flags_app+=(-DPORTABLE_RETAINED_RGB565_HANDOFF -DPORTABLE_HANDOFF_EAGER_MS=60); fi
 if [[ "$name" == springboard ]]; then flags_app+=('-DPORTABLE_RETURN_APP="clock.elf"'); else flags_app+=('-DPORTABLE_RETURN_APP="springboard.elf"'); fi
 catalog="$watch/dist/launcher/catalog.c"
 if [[ "$name" == springboard ]]; then catalog="$watch/dist/launcher/daily_catalog.c"; fi
 cc -std=c11 "${flags[@]}" "${flags_app[@]}" -fPIC -shared -fvisibility=hidden "${portable[@]}" "${watchincs[@]}" "$source" "$system/lib/PortableApps/src/adapter.c" "$catalog" "$watch/apps/clock/portable_navigation.c" -o "$build/$name.elf"
done
c++ -std=c++17 "${flags[@]}" -O0 -Wno-missing-field-initializers -rdynamic "${incs[@]}" \
 "$runtime/src/bootstrap/Board.cpp" "$runtime/src/bootstrap/Json.cpp" "$runtime/src/bootstrap/Runtime.cpp" \
 "$runtime/src/ports/esp32s3/CpuPort.cpp" "$runtime/src/runtime/drivers/ProviderModuleV2.cpp" "$runtime/src/runtime/drivers/ProviderGraphV2.cpp" \
 "$watch/tests/launcher_runtime_test.cpp" -ldl -o "$build/test"
"$build/test" "$build"
c++ -std=c++17 "${flags[@]}" -O0 -Wno-missing-field-initializers -rdynamic "${incs[@]}" \
 "$runtime/src/bootstrap/Board.cpp" "$runtime/src/bootstrap/Json.cpp" "$runtime/src/bootstrap/Runtime.cpp" \
 "$runtime/src/ports/esp32s3/CpuPort.cpp" "$runtime/src/runtime/drivers/ProviderModuleV2.cpp" "$runtime/src/runtime/drivers/ProviderGraphV2.cpp" \
 "$watch/tests/deep_sleep_runtime_test.cpp" -ldl -o "$build/deep-test"
"$build/deep-test" "$build"

bash "$watch/scripts/test_daily_runtime.sh" "$runtime" "$build"

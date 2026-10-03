#!/usr/bin/env bash
set -euo pipefail
watch="$(cd "$(dirname "$0")/.." && pwd)"
runtime="$(cd "${1:?Pass exact paired Runtime source}" && pwd)"
system="$(cd "${2:?Pass exact shared System Apps source}" && pwd)"
utilities="$(cd "${3:?Pass exact shared Utilities source}" && pwd)"
# The runtime pairing is part of the deployment contract, not a moving checkout.
[[ "$(git -C "$runtime" rev-parse HEAD)" == a3d23da9cdc1b3a66c6429f29781856fa7fc8f75 ]]
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
portable=(-I"$system/lib/PortableApps/include" -I"$system/lib/NativeApps/include")
for name in springboard battery settings; do
 source="$system/Apps/$name.c";flags_app=(-DPORTABLE_TOUCH_ROTATION=0 -DPORTABLE_RTC_UTC8_DENVER)
 if [[ "$name" == battery ]]; then source="$utilities/Apps/battery.c"; fi
 if [[ "$name" == settings ]]; then flags_app+=(-DPORTABLE_SETTINGS_APP); fi
 cc -std=c11 "${flags[@]}" "${flags_app[@]}" -fPIC -shared -fvisibility=hidden "${portable[@]}" "$source" "$system/lib/PortableApps/src/adapter.c" "$watch/dist/launcher/catalog.c" -o "$build/$name.elf"
done
c++ -std=c++17 "${flags[@]}" -O0 -Wno-missing-field-initializers -rdynamic "${incs[@]}" \
 "$runtime/src/bootstrap/Board.cpp" "$runtime/src/bootstrap/Json.cpp" "$runtime/src/bootstrap/Runtime.cpp" \
 "$runtime/src/ports/esp32s3/CpuPort.cpp" "$runtime/src/runtime/drivers/ProviderModuleV2.cpp" "$runtime/src/runtime/drivers/ProviderGraphV2.cpp" \
 "$watch/tests/launcher_runtime_test.cpp" -ldl -o "$build/test"
"$build/test" "$build"

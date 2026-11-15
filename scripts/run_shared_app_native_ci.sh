#!/usr/bin/env bash
set -euo pipefail
: "${NATIVE_ROOT:?}" "${SOURCE_SHA:?}" "${GITHUB_REPOSITORY:?}"
product="$NATIVE_ROOT/sources/product"
. "$IDF_PATH/export.sh"
export ESP_IDF_VERSION=6.1.0
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 CCACHE_DISABLE=1 IDF_CCACHE_ENABLE=0 CMAKE_BUILD_PARALLEL_LEVEL=1
mkdir -p "$NATIVE_ROOT"/{inputs,metadata,logs}
exec > >(tee "$NATIVE_ROOT/logs/native-build.log") 2>&1
python -m pip install pyelftools==0.32
python - "$product" "$NATIVE_ROOT" <<'PY'
import json,os,sys
from pathlib import Path
product,root=map(Path,sys.argv[1:]);p=json.loads((product/'docs/shared-app-native/source-pins.json').read_text())
assert os.environ['GITHUB_REPOSITORY']=='michaelrolphone-cmyk/RiscRTE-T-Watch-S3'
assert p['publication_enabled'] is False
repos={'runtime':'RiscRTE','system':'RiscRTE-System-Apps','utilities':'RiscRTE-Utilities','drivers':'RiscRTE-Drivers','watch':'RiscRTE-Watch','image_helper':'RiscRTE-T-Watch-S3'}
(root/'metadata/source-roles.tsv').write_text(''.join(f'{role}\tmichaelrolphone-cmyk/{repo}\t{p[role+"_revision"]}\n' for role,repo in repos.items()))
(root/'metadata/ci.json').write_text(json.dumps({k:os.environ.get(k) for k in ['GITHUB_REPOSITORY','SOURCE_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_EVENT_NAME']},indent=2)+'\n')
PY
clone_source() {
  local repository="$1" revision="$2" destination="$3"
  [[ "$revision" =~ ^[0-9a-f]{40}$ ]]
  test ! -e "$destination"
  git init --quiet "$destination"
  git -C "$destination" remote add origin "https://github.com/$repository.git"
  git -C "$destination" fetch --no-tags --depth=1 origin "$revision"
  git -C "$destination" checkout --quiet --detach FETCH_HEAD
  test "$(git -C "$destination" rev-parse HEAD)" = "$revision"
  git -C "$destination" submodule update --init --recursive --depth=1
}
while IFS=$'\t' read -r role repository revision; do clone_source "$repository" "$revision" "$NATIVE_ROOT/sources/$role"; done < "$NATIVE_ROOT/metadata/source-roles.tsv"
test "$(git -C "$IDF_PATH" rev-parse HEAD)" = fff9895c82d744c7237be8847347bdd1b07c6643
compiler="$(command -v xtensa-esp-elf-gcc)"
"$compiler" --version | tee "$NATIVE_ROOT/metadata/compiler-version.txt"
grep -F 'esp-15.2.0_20251204' "$NATIVE_ROOT/metadata/compiler-version.txt"
test "$("$compiler" -dumpfullversion)" = 15.2.0
python "$product/scripts/fetch_shared_app_native_baseline.py" --output "$NATIVE_ROOT/inputs"
for header in RiscRuntimeV1.h RiscResidentShellV1.h RiscResidentAttentionV1.h; do
  cmp "$NATIVE_ROOT/sources/watch/sdk/app/$header" "$NATIVE_ROOT/sources/runtime/sdk/app/$header"
done
for copy in a b; do
 python "$NATIVE_ROOT/sources/watch/scripts/build.py" --system "$NATIVE_ROOT/sources/system" --utilities "$NATIVE_ROOT/sources/utilities" --cc "$(dirname "$compiler")/xtensa-esp32s3-elf-gcc" --role default --automatic-provision --output "$NATIVE_ROOT/home-$copy"
done
python "$NATIVE_ROOT/sources/watch/scripts/verify_shared_default.py" --first "$NATIVE_ROOT/home-a" --second "$NATIVE_ROOT/home-b" --receipt "$NATIVE_ROOT/metadata/home-repeat.json"
python "$product/scripts/test_shared_app_native_package.py"
python "$product/scripts/test_shared_app_native_admission.py"
python "$product/tests/shared_app_native/test_builder.py"
python "$product/scripts/test_shared_app_native_fetch.py"
source_args=(--source "product=$product" --source "sdk=$IDF_PATH")
while IFS=$'\t' read -r role repository revision; do source_args+=(--source "$role=$NATIVE_ROOT/sources/$role"); done < "$NATIVE_ROOT/metadata/source-roles.tsv"
python "$product/scripts/build_shared_app_native.py" "${source_args[@]}" --compiler "$compiler" --baseline "$NATIVE_ROOT/inputs/factory.bin" --feed "$NATIVE_ROOT/inputs/native-packages-v1.json" --first "$NATIVE_ROOT/home-a" --second "$NATIVE_ROOT/home-b" --native-build "$NATIVE_ROOT/build" --output "$NATIVE_ROOT/candidate"
python "$NATIVE_ROOT/sources/runtime/test/native_firmware_idf6_test.py" --build "$NATIVE_ROOT/build"

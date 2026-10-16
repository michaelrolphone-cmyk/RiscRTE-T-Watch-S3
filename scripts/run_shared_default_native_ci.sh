#!/usr/bin/env bash
set -euo pipefail
: "${NATIVE_ROOT:?}" "${GITHUB_SHA:?}" "${GITHUB_REPOSITORY:?}" "${GITHUB_OUTPUT:?}"
product="$NATIVE_ROOT/sources/product"
. "$IDF_PATH/export.sh"
export ESP_IDF_VERSION=6.1.0
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 CCACHE_DISABLE=1 IDF_CCACHE_ENABLE=0 CMAKE_BUILD_PARALLEL_LEVEL=1
mkdir -p "$NATIVE_ROOT"/{inputs,metadata,logs}
exec > >(tee "$NATIVE_ROOT/logs/native-release-build.log") 2>&1
cp "$product/.github/workflows/shared-default-native.yml" "$NATIVE_ROOT/metadata/workflow.yml"
python -m pip install pyelftools==0.32
python "$product/scripts/test_shared_default_package.py"
python "$product/scripts/test_shared_default_release.py"
python - "$product" "$NATIVE_ROOT" <<'PY'
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
from package_shared_default import pins,baseline_contract
p=pins(); c=baseline_contract(p)
repos={'runtime':'RiscRTE','system':'RiscRTE-System-Apps','utilities':'RiscRTE-Utilities','drivers':'RiscRTE-Drivers',
       'watch':'RiscRTE-Watch','image_helper':'RiscRTE-T-Watch-S3'}
root=Path(sys.argv[2])
(root/'metadata/source-roles.tsv').write_text(''.join(f'{r}\tmichaelrolphone-cmyk/{repo}\t{p[r+"_revision"]}\n' for r,repo in repos.items()))
assert p['sdk_revision']=='fff9895c82d744c7237be8847347bdd1b07c6643'
expected='michaelrolphone-cmyk/'+{'twatch':'RiscRTE-T-Watch-S3','waveshare':'RiscRTE-Wavshare-S3-Touch-AMOLED-2.06'}[p['product']]
assert os.environ['GITHUB_REPOSITORY']==expected
(root/'metadata/baseline.json').write_text(json.dumps(c))
with open(os.environ['GITHUB_OUTPUT'],'a') as out:
 for k in ('product','version','publication_enabled','release_tag','release_branch'):
  print(k+'='+str(p[k]).lower() if isinstance(p[k],bool) else k+'='+str(p[k]),file=out)
keys=('GITHUB_REPOSITORY','GITHUB_SHA','GITHUB_REF','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_WORKFLOW_REF','GITHUB_WORKFLOW_SHA')
(root/'metadata/ci-run.json').write_text(json.dumps({k:os.environ.get(k) for k in keys},sort_keys=True,indent=2)+'\n')
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
while IFS=$'\t' read -r role repository revision; do
  clone_source "$repository" "$revision" "$NATIVE_ROOT/sources/$role"
done < "$NATIVE_ROOT/metadata/source-roles.tsv"
test "$(git -C "$IDF_PATH" rev-parse HEAD)" = fff9895c82d744c7237be8847347bdd1b07c6643
compiler="$(command -v xtensa-esp-elf-gcc)"
"$compiler" --version | tee "$NATIVE_ROOT/metadata/compiler-version.txt"
grep -F 'esp-15.2.0_20251204' "$NATIVE_ROOT/metadata/compiler-version.txt"
test "$("$compiler" -dumpfullversion)" = 15.2.0
python - "$NATIVE_ROOT" <<'PY'
import hashlib,json,os,sys,urllib.request
from pathlib import Path
root=Path(sys.argv[1]); c=json.loads((root/'metadata/baseline.json').read_text()); repo=os.environ['GITHUB_REPOSITORY']
def read(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'RiscRTE-native-release'}),timeout=180) as r:return r.read()
r=json.loads(read('https://api.github.com/repos/'+repo+'/releases/tags/'+c['release_tag']))
t=json.loads(read('https://api.github.com/repos/'+repo+'/git/ref/tags/'+c['release_tag']))
assert not r['draft'] and r['tag_name']==c['release_tag']
assert t['object']['type']=='commit' and t['object']['sha']==c['source_revision']
a=[a for a in r['assets'] if a['name']==c['factory_asset']]; assert len(a)==1
url='https://github.com/'+repo+'/releases/download/'+c['release_tag']+'/'+c['factory_asset']
assert a[0]['browser_download_url']==url
data=read(url); assert len(data)==c['factory_bytes'] and hashlib.sha256(data).hexdigest()==c['factory_sha256']
(root/'inputs/released-factory.bin').write_bytes(data)
(root/'metadata/baseline-release.json').write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
(root/'metadata/baseline-tag.json').write_text(json.dumps(t,sort_keys=True,indent=2)+'\n')
PY
for build in a b; do
 python "$NATIVE_ROOT/sources/watch/scripts/build.py" --system "$NATIVE_ROOT/sources/system" \
  --utilities "$NATIVE_ROOT/sources/utilities" --cc "$(dirname "$compiler")/xtensa-esp32s3-elf-gcc" \
  --role default --output "$NATIVE_ROOT/default-$build"
done
source_args=(--source "product=$product" --source "sdk=$IDF_PATH")
while IFS=$'\t' read -r role repository revision; do source_args+=(--source "$role=$NATIVE_ROOT/sources/$role"); done < "$NATIVE_ROOT/metadata/source-roles.tsv"
python "$product/scripts/build_shared_default_native.py" "${source_args[@]}" --compiler "$compiler" \
 --baseline "$NATIVE_ROOT/inputs/released-factory.bin" --first "$NATIVE_ROOT/default-a" --second "$NATIVE_ROOT/default-b" \
 --native-build "$NATIVE_ROOT/build" --output "$NATIVE_ROOT/candidate"
python "$NATIVE_ROOT/sources/runtime/test/native_firmware_idf6_test.py" --build "$NATIVE_ROOT/build"
target="$(python -c "import json; print(json.load(open('$product/docs/native-idf61/released-baseline.json'))['target'])")"
python "$NATIVE_ROOT/sources/runtime/scripts/native_idf_iq_link.py" verify \
 --elf "$NATIVE_ROOT/build/riscrte_native.elf" --target "$target" --output "$NATIVE_ROOT/metadata/iq-linked.json"
python "$product/scripts/shared_default_release.py" --candidate "$NATIVE_ROOT/candidate" \
 --source-revision "$GITHUB_SHA" --runtime "$NATIVE_ROOT/sources/runtime" --image-helper "$NATIVE_ROOT/sources/image_helper" \
 --baseline "$NATIVE_ROOT/inputs/released-factory.bin" --metadata "$NATIVE_ROOT/metadata" --output "$NATIVE_ROOT/release"
(cd "$NATIVE_ROOT/release" && sha256sum --check --strict SHA256SUMS)
echo "checksums_sha256=$(sha256sum "$NATIVE_ROOT/release/SHA256SUMS" | cut -d' ' -f1)" >> "$GITHUB_OUTPUT"

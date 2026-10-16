#!/usr/bin/env python3
"""Add only Lists shared input to the complete published Contexts union.

Writes a held eight-file overlay and verified boot-store/bank artifacts. The
full-initial hash is streamed without allocating or writing an image.
Native firmware, presentation profiles, font bytes, SD checkpoints and historical inputs are unchanged. Only Lists and its shared text/scene continuity hosts are rebuilt.
"""
import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

from current_bootfs import build, read_image
from watch_boot_order_spiffs import build as ordered_build
from check_runtime_store_admission import admit_cohort, store_digest
from assemble_watch_points_union import require, sha, encoded, git, read_store, BOOTFS, BANK
from build_lists_shared_input import VERSION
from build_lists_text_host import TEXT_VERSION, HOST_PRIOR
from build_lists_scene_host import SCENE_VERSION, SCENE_PRIOR, SCENE_FLAGS
COMPONENT_BUDGET_BYTES = 45000
BASELINE_LISTS_SHA256 = '79dcedcce8ea351e9ae16d4745aee5311f72832e0d8d71841a14b7468185d9da'

ROOT = Path(__file__).resolve().parents[1]
BASE = '3cd9faa5e5f0c0d0c0fe6437232ee684fbe030fb'
BASE_STORE_SHA = '4c8c2ef3c88d7b23dfe163fd0205d87f92587967f9cb3670e49c9c1f2582d12f'
ANCESTOR = 'd3687db3ea6e6e5c8a36e5d01c5dfd2ba69ed453'
RUNTIME = '64c8e52e46fd91e8fdafd636db04eed88f0c51a9'
SYSTEM_BASE = '7fb13b09b4dac275a8111b224784f8a472f39264'
GRANT = dict(capability='ui.text-input', api=1, instance_id=0)
CHANGED = {'lists.elf', 'lists.json', 'text-input/driver.elf', 'text-input/manifest.json', 'ui-scene/driver.elf', 'ui-scene/manifest.json', 'boot.json', 'cohort.json'}


def component(files, system, revision):
    record = json.loads((files / 'lists-build-record.json').read_bytes())
    require(record['device'] == 'watch' and record['sources']['system-apps'] == system and record['version'] == VERSION,
            'Wrong Lists source')
    require(record['sources']['runtime'] == RUNTIME and record['product_recipe'] == revision,
            'Wrong Lists recipe')
    for key in ['baseline_features_preserved', 'original_fonts_retained', 'shared_text_input']:
        require(record[key], 'Missing Lists preservation proof: ' + key)
    data = {name: (files / name).read_bytes() for name in ['lists.elf', 'lists.json']}
    require(sha(data['lists.elf']) == record['sha256'] and
            len(data['lists.elf']) == record['bytes'] <= COMPONENT_BUDGET_BYTES,
            'Lists ELF custody differs')
    require(sha(data['lists.json']) == record['manifest_sha256'], 'Lists manifest custody differs')
    return data, record


def payload(old, components, revision):
    require(set(components) == {'lists.elf', 'lists.json', 'text-input/driver.elf', 'text-input/manifest.json', 'ui-scene/driver.elf', 'ui-scene/manifest.json'}, 'Unexpected Lists component member')
    expected = json.loads(old['lists.json'])
    require(expected['version'] == '0.1.0', 'Wrong Lists predecessor')
    expected['version'] = VERSION
    expected['requires'].append(dict(capability='ui.text-input', api=1))
    require(json.loads(components['lists.json']) == expected, 'Lists authority exceeds additive delta')
    require(json.loads(components['text-input/manifest.json']) == dict(json.loads(old['text-input/manifest.json']), version=TEXT_VERSION), 'Text host authority changed')
    require(json.loads(components['ui-scene/manifest.json']) == dict(json.loads(old['ui-scene/manifest.json']), version=SCENE_VERSION), 'Scene host authority changed')
    boot = json.loads(old['boot.json'])
    original = copy.deepcopy(boot)
    rows = [r for r in boot['app_capabilities'] if r['manifest'] == 'lists.json']
    require(len(rows) == 1 and GRANT not in rows[0]['grants'], 'Unexpected Lists authority')
    rows[0]['grants'].append(copy.deepcopy(GRANT))
    new = dict(old, **components)
    # Formatting only: the sole semantic addition remains the Lists grant.
    new['boot.json'] = (json.dumps(boot,sort_keys=True,separators=(',',':'))+'\n').encode()
    require(json.loads(new['boot.json'])==boot,'Compact boot metadata changed meaning')
    rows[0]['grants'].pop()
    require(boot == original, 'Unrelated boot change')
    cohort = json.loads(old['cohort.json'])
    require(cohort['version'] == '1.1.18' and cohort['source_revision'] == BASE, 'Wrong Contexts union predecessor')
    cohort['source_revision'] = revision
    new['cohort.json'] = encoded(cohort)
    require(set(new) == set(old) and {n for n in new if new[n] != old[n]} == CHANGED, 'Unexpected store delta')
    return new


def streamed_digest(source, replacements=None):
    replacements=sorted((offset,raw) for offset,raw in (replacements or {}).items())
    digest=hashlib.sha256(); position=0
    with source.open('rb') as stream:
        for offset,raw in replacements+[(0x1000000,b'')]:
            require(offset>=position,'Overlapping replacement')
            stream.seek(position)
            remaining=offset-position
            while remaining:
                chunk=stream.read(min(65536,remaining));require(chunk,'Short image input')
                digest.update(chunk);remaining-=len(chunk)
            digest.update(raw);position=offset+len(raw)
    require(position==0x1000000 and source.stat().st_size==position,'Wrong full image size')
    return digest.hexdigest()


def baseline(components, candidate):
    raw=(components/'handoff-qualified-20261012T1848Z.json').read_bytes()
    require(sha(raw)=='8547042d027bce9e193854fabf8e875c6c82d2d57ae7b5b797713d5ee76c0aa7','Wrong qualified baseline')
    handoff=json.loads(raw)
    prior=json.loads((components/'watch/candidate/receipts/final-normal.json').read_bytes())
    sanitized=json.loads((components/'watch/candidate/receipts/final-sanitized.json').read_bytes())
    require(prior==sanitized and prior['product_source']==BASE and prior['candidate_store_sha256']==BASE_STORE_SHA and prior['elf_count']==55 and prior['free_spiffs_blocks']==5,'Wrong Contexts baseline qualification')
    require(handoff['devices']['watch']['sources']['system-apps']==SYSTEM_BASE and handoff['devices']['watch']['compiled_recipe_commit']==BASE and not handoff['source']['depends_on_unpublished_sd_changes'],'Wrong Contexts provenance')
    for name in ('bootfs.bin','bank_state.bin'):
        p=components/'watch/candidate/components'/name; row=handoff['devices']['watch']['components'][name]
        require(sha(p.read_bytes())==row['sha256'] and p.stat().st_size==row['bytes'],'Changed baseline component: '+name)
    bootfs=(components/'watch/candidate/components/bootfs.bin').read_bytes();old=read_image(bootfs,0x510000)
    require(store_digest(old)==BASE_STORE_SHA and len(old)==113 and sum(n.endswith('.elf') for n in old)==55 and sha(old['lists.elf'])==BASELINE_LISTS_SHA256,'Wrong complete baseline store')
    ancestor=json.loads((candidate/'receipts/final-normal.json').read_bytes())
    require(ancestor['product_source']==ANCESTOR,'Wrong native ancestor')
    native=(candidate/'components/firmware.elf').read_bytes();firmware=(candidate/'components/firmware.bin').read_bytes()
    previous=candidate/'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin'
    require(sha(native)==prior['native_elf_sha256']==ancestor['native_elf_sha256'],'Wrong native ELF')
    require(streamed_digest(previous)==ancestor['full_image_sha256'],'Wrong native ancestor image')
    with previous.open('rb') as f:
        f.seek(0x10000);require(f.read(len(firmware))==firmware,'Wrong native bytes')
    require(streamed_digest(previous,{BOOTFS[0]:bootfs,BANK[0]:(components/'watch/candidate/components/bank_state.bin').read_bytes()})==prior['full_image_sha256'],'Contexts reconstruction differs')
    return old,prior,native,firmware,previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['baseline-components', 'native-candidate', 'lists-build', 'text-build', 'scene-build', 'runtime', 'system', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--system-commit', required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty product source')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    old, prior, native, firmware, previous = baseline(args.baseline_components, args.native_candidate)
    system = git(args.system, 'rev-parse', 'HEAD')
    system_tree = git(args.system, 'rev-parse', 'HEAD^{tree}')
    require(system == args.system_commit and not git(args.system, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty System source')
    data, record = component(args.lists_build, system, revision)
    text_record = json.loads((args.text_build/'text-build-record.json').read_bytes())
    require(text_record['device']=='watch' and text_record['version']==TEXT_VERSION and text_record['sources']=={'runtime':RUNTIME,'system-apps':system} and text_record['product_recipe']==revision and text_record['defines']==[], 'Wrong text host profile')
    require(sha(old['text-input/driver.elf'])==HOST_PRIOR['watch'][1] and json.loads(old['text-input/manifest.json'])['version']==HOST_PRIOR['watch'][0], 'Wrong text host predecessor')
    for name in ['driver.elf','manifest.json']:data['text-input/'+name]=(args.text_build/name).read_bytes()
    require(sha(data['text-input/driver.elf'])==text_record['sha256'] and sha(data['text-input/manifest.json'])==text_record['manifest_sha256'], 'Text host custody differs')
    scene_record = json.loads((args.scene_build/'scene-build-record.json').read_bytes())
    require(scene_record['device']=='watch' and scene_record['version']==SCENE_VERSION and scene_record['sources']=={'runtime':RUNTIME,'system-apps':system} and scene_record['product_recipe']==revision and scene_record['defines']==SCENE_FLAGS['watch'] and scene_record['all_compiled_font_bytes_preserved'], 'Wrong scene host profile')
    require(sha(old['ui-scene/driver.elf'])==SCENE_PRIOR['watch'][1] and json.loads(old['ui-scene/manifest.json'])['version']==SCENE_PRIOR['watch'][0], 'Wrong scene host predecessor')
    for name in ['driver.elf','manifest.json']:data['ui-scene/'+name]=(args.scene_build/name).read_bytes()
    require(sha(data['ui-scene/driver.elf'])==scene_record['sha256'] and sha(data['ui-scene/manifest.json'])==scene_record['manifest_sha256'], 'Scene host custody differs')
    new = payload(old, data, revision)
    boot = json.loads(new['boot.json'])
    grants = next(r['grants'] for r in boot['app_capabilities'] if r['manifest'] == 'lists.json')
    require(GRANT in grants, 'Lists grant receipt differs')
    bootfs, packing = ordered_build(new, build)
    require(packing['empty_blocks'] >= 2 and packing['file_count'] == 113, 'Watch reserve or inventory violated')
    require(read_image(bootfs, 0x510000) == new, 'Packed store roundtrip differs')
    require(git(args.runtime, 'rev-parse', 'HEAD') == RUNTIME, 'Wrong Runtime source')
    profile = args.runtime / 'watch-file-source-profile.ini'
    require(profile.read_bytes() == (ROOT / 'docs/file-source/watch-file-source-profile.ini').read_bytes(), 'Wrong native profile')
    sys.path.insert(0, str(args.runtime / 'scripts'))
    from paired_bank_images import initial_bank_state, parse_record
    bank = initial_bank_state(firmware, bootfs, True)
    full_sha=streamed_digest(previous,{BOOTFS[0]:bootfs,BANK[0]:bank})
    rec = parse_record(bank[:96], True)
    require(rec[3] == len(firmware) and rec[6] == hashlib.sha256(firmware).digest() and
            rec[7] == hashlib.sha256(bootfs).digest(), 'Bank digest differs')
    if not args.verify_only:
        require(not args.output.exists(), 'Use new output directory')
        (args.output / 'components').mkdir(parents=True)
        (args.output / 'receipts').mkdir()
        for name in sorted(CHANGED):
            dest = args.output / 'overlay' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(new[name])
        (args.output / 'components/bootfs.bin').write_bytes(bootfs)
        (args.output / 'components/bank_state.bin').write_bytes(bank)
        for name, obj in [('packing', packing), ('lists-build', record), ('baseline-contexts', prior), ('text-build', text_record), ('scene-build', scene_record)]:
            (args.output / 'receipts' / (name + '.json')).write_bytes(encoded(obj))
    require(read_store(args.output / 'overlay') == {name: new[name] for name in CHANGED}, 'Written overlay differs')
    require((args.output / 'components/bootfs.bin').read_bytes() == bootfs and
            (args.output / 'components/bank_state.bin').read_bytes() == bank, 'Written packed artifacts differ')
    admission = admit_cohort(args.runtime, native, old, new, app_policy_rows=24, native_profile=profile)
    require(admission['elf_count'] == 55, 'Incomplete admission')
    require(git(ROOT, 'rev-parse', 'HEAD') == revision and
            not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Product source changed during admission')
    proof = dict(product='Watch', version='1.1.18', product_source=revision,
        product_tree=git(ROOT, 'rev-parse', 'HEAD^{tree}'), system_source=system, system_tree=system_tree,
        source_candidate=BASE, changed_store_paths=sorted(CHANGED), preserved_store_paths=len(old)-len(CHANGED),
        free_spiffs_blocks=packing['empty_blocks'], store_files=len(new), all_unrelated_apps_and_providers_preserved=True,
        grant_delta=[dict(manifest='lists.json', grant=GRANT)], native_unchanged=True,
        font_bytes_presentation_profiles_unchanged=True, scene_host_updated=True, scene_host_build=scene_record, text_host_updated=True, text_host_build=text_record, boot_json_formatting_only_beyond_grant=True, boot_json_before_bytes=len(old['boot.json']), boot_json_after_bytes=len(new['boot.json']), full_image_bytes=0x1000000, full_image_sha256=full_sha,
        full_initial_erases_data=True, full_image_materialized=False, hardware_verified=False,
        delivered=False, delivery_hold_until_utc='2026-10-12T23:30:00Z', **admission)
    name = 'final-sanitized.json' if os.environ.get('SANITIZE') == '1' else 'final-normal.json'
    (args.output / 'receipts' / name).write_bytes(encoded(proof))
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()

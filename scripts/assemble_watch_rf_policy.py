#!/usr/bin/env python3
"""Apply the RF 0.3.5 modal-policy correction to the complete qualified Timecard union.

Writes a held exact-delta overlay and verified boot-store/bank artifacts. The
full-initial hash is streamed without allocating or writing an image.
No native firmware, host provider, SD checkpoint, or historical input is changed.
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
from build_rf_policy import VERSION, SYSTEM, SELECTION
COMPONENT_BUDGET_BYTES = 249392
BASELINE_RF_SHA256 = 'c0612e63664bfcb25f2bb3ea79286e97b36c6f62eb95a4ddb1c719868890bd05'

ROOT = Path(__file__).resolve().parents[1]
BASE = SELECTION['baseline']['compiled_recipe_commit']
BASE_STORE_SHA = SELECTION['baseline']['candidate_store_sha256']
ANCESTOR = 'd3687db3ea6e6e5c8a36e5d01c5dfd2ba69ed453'
RUNTIME = '64c8e52e46fd91e8fdafd636db04eed88f0c51a9'
GRANT = dict(capability='ui.text-input', api=1, instance_id=0)
CHANGED = {'waterfall.elf', 'waterfall.json', 'cohort.json'}


def component(files, system, revision):
    record = json.loads((files / 'waterfall-build-record.json').read_bytes())
    require(record['device'] == 'watch' and record['sources']['system-apps'] == system == SYSTEM and record['version'] == VERSION,
            'Wrong RF source')
    require(record['sources']['runtime'] == RUNTIME and record['product_recipe'] == revision,
            'Wrong RF recipe')
    for key in ['baseline_features_preserved', 'original_fonts_retained', 'shared_text_input']:
        require(record[key], 'Missing RF preservation proof: ' + key)
    data = {name: (files / name).read_bytes() for name in ['waterfall.elf', 'waterfall.json']}
    require(sha(data['waterfall.elf']) == record['sha256'] and
            len(data['waterfall.elf']) == record['bytes'] <= COMPONENT_BUDGET_BYTES,
            'RF ELF custody differs')
    require(sha(data['waterfall.json']) == record['manifest_sha256'], 'RF manifest custody differs')
    return data, record


def payload(old, components, revision):
    require(set(components) == {'waterfall.elf', 'waterfall.json'}, 'Unexpected RF component member')
    expected = json.loads(old['waterfall.json'])
    require(expected['version'] == '0.3.4', 'Wrong RF predecessor')
    require(expected['requires'].count(dict(capability='ui.text-input', api=1)) == 1, 'Wrong inherited RF authority')
    expected['version'] = VERSION
    require(json.loads(components['waterfall.json']) == expected, 'RF authority changed')
    rows = [r for r in json.loads(old['boot.json'])['app_capabilities'] if r['manifest'] == 'waterfall.json']
    require(len(rows) == 1 and rows[0]['grants'].count(GRANT) == 1, 'Unexpected RF authority')
    new = dict(old, **components)
    cohort = json.loads(old['cohort.json'])
    require(cohort['version'] == '1.1.18' and cohort['source_revision'] == BASE, 'Wrong Timecard union predecessor')
    cohort['source_revision'] = revision
    new['cohort.json'] = encoded(cohort)
    require(set(new) == set(old) and {n for n in new if new[n] != old[n]} == CHANGED, 'Unexpected store delta')
    require(new['boot.json'] == old['boot.json'], 'Boot authority or formatting changed')
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


def baseline(candidate, handoff_path, native_candidate):
    selected = SELECTION['baseline']
    require(SELECTION['finalized'] and BASE and SYSTEM, 'Final published qualified baseline is not selected')
    require(sha(handoff_path.read_bytes()) == selected['combined_handoff_sha256'], 'Wrong qualified Timecard handoff')
    raw = (candidate/'receipts/final-normal.json').read_bytes()
    require(sha(raw) == selected['receipt_sha256'], 'Changed Timecard qualification receipt')
    prior = json.loads(raw)
    sanitized = json.loads((candidate/'receipts/final-sanitized.json').read_bytes())
    require(prior == sanitized and prior['product_source'] == BASE and prior['system_source'] == selected['system_commit'] and
            prior['candidate_store_sha256'] == BASE_STORE_SHA and prior['elf_count'] == 55 and
            prior['free_spiffs_blocks'] == selected['free_spiffs_blocks'], 'Wrong Timecard baseline qualification')
    bootfs = (candidate/'components/bootfs.bin').read_bytes()
    old = read_image(bootfs, 0x510000)
    require(store_digest(old) == BASE_STORE_SHA and len(old) == 113 and
            sum(n.endswith('.elf') for n in old) == 55 and sha(old['waterfall.elf']) == BASELINE_RF_SHA256,
            'Wrong complete baseline store')
    ancestor = json.loads((native_candidate/'receipts/final-normal.json').read_bytes())
    require(ancestor['product_source'] == ANCESTOR, 'Wrong native ancestor')
    native = (native_candidate/'components/firmware.elf').read_bytes()
    firmware = (native_candidate/'components/firmware.bin').read_bytes()
    previous = native_candidate/'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin'
    require(sha(native) == prior['native_elf_sha256'] == ancestor['native_elf_sha256'], 'Wrong native ELF')
    require(streamed_digest(previous) == ancestor['full_image_sha256'], 'Wrong native ancestor image')
    with previous.open('rb') as f:
        f.seek(0x10000)
        require(f.read(len(firmware)) == firmware, 'Wrong native bytes')
    require(streamed_digest(previous, {BOOTFS[0]: bootfs, BANK[0]: (candidate/'components/bank_state.bin').read_bytes()}) ==
            prior['full_image_sha256'] == selected['full_image_sha256'], 'Timecard reconstruction differs')
    return old, prior, native, firmware, previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['baseline', 'baseline-handoff', 'native-candidate', 'waterfall-build', 'runtime', 'system', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty product source')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    old, prior, native, firmware, previous = baseline(args.baseline, args.baseline_handoff, args.native_candidate)
    system = git(args.system, 'rev-parse', 'HEAD')
    system_tree = git(args.system, 'rev-parse', 'HEAD^{tree}')
    require(system == SYSTEM and not git(args.system, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty System source')
    data, record = component(args.waterfall_build, system, revision)
    new = payload(old, data, revision)
    boot = json.loads(new['boot.json'])
    grants = next(r['grants'] for r in boot['app_capabilities'] if r['manifest'] == 'waterfall.json')
    require(GRANT in grants, 'RF grant receipt differs')
    new, bootfs, packing, metadata_compaction = compact_to_floor(new)
    changed = {name for name in new if new[name] != old[name]}
    require(new['boot.json'] == old['boot.json'], 'Boot authority or formatting changed')
    for name in set(new) - CHANGED:
        if name.endswith('.json'):
            require(json.loads(new[name]) == json.loads(old[name]), 'Unrelated decoded metadata changed: '+name)
        else:
            require(new[name] == old[name], 'Unrelated component changed: '+name)
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
        for name in sorted(changed):
            dest = args.output / 'overlay' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(new[name])
        (args.output / 'components/bootfs.bin').write_bytes(bootfs)
        (args.output / 'components/bank_state.bin').write_bytes(bank)
        for name, obj in [('packing', packing), ('waterfall-build', record), ('baseline-timecard', prior)]:
            (args.output / 'receipts' / (name + '.json')).write_bytes(encoded(obj))
    require(read_store(args.output / 'overlay') == {name: new[name] for name in changed}, 'Written overlay differs')
    require((args.output / 'components/bootfs.bin').read_bytes() == bootfs and
            (args.output / 'components/bank_state.bin').read_bytes() == bank, 'Written packed artifacts differ')
    admission = admit_cohort(args.runtime, native, old, new, app_policy_rows=24, native_profile=profile)
    require(admission['elf_count'] == 55, 'Incomplete admission')
    require(git(ROOT, 'rev-parse', 'HEAD') == revision and
            not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Product source changed during admission')
    proof = dict(product='Watch', version='1.1.18', product_source=revision,
        product_tree=git(ROOT, 'rev-parse', 'HEAD^{tree}'), system_source=system, system_tree=system_tree,
        source_candidate=BASE, changed_store_paths=sorted(changed), preserved_store_paths=len(old)-len(changed),
        free_spiffs_blocks=packing['empty_blocks'], store_files=len(new), existing_apps_and_providers_preserved=True,
        grant_delta=[], boot_authority_unchanged=True, native_unchanged=True, lossless_metadata_compaction=metadata_compaction, decoded_metadata_unchanged=True,
        shared_text_hosts_unchanged=True, scene_host_unchanged=True, clock_unchanged=True, watch_has_no_native_resident_shell=True, lifecycle_successor=True, boot_json_byte_identical=True, boot_json_before_bytes=len(old['boot.json']), boot_json_after_bytes=len(new['boot.json']), full_image_bytes=0x1000000, full_image_sha256=full_sha,
        full_initial_erases_data=True, full_image_materialized=False, hardware_verified=False,
        delivered=False, delivery_hold_until_utc='2026-10-12T23:30:00Z', **admission)
    name = 'final-sanitized.json' if os.environ.get('SANITIZE') == '1' else 'final-normal.json'
    (args.output / 'receipts' / name).write_bytes(encoded(proof))
    print(json.dumps(proof, indent=2))


def compact_to_floor(files):
    """Compact only unchanged JSON whitespace when required by the reserve floor."""
    new = dict(files)
    def attempt():
        try:
            return ordered_build(new, build)
        except ValueError as error:
            if str(error) != 'Current bootfs lacks SPIFFS free-block reserve':
                raise
            return None, None
    bootfs, packing = attempt()
    changes = []
    candidates = []
    for name, raw in new.items():
        if not name.endswith('.json') or name in CHANGED or name == 'boot.json':
            continue
        decoded = json.loads(raw)
        compact = (json.dumps(decoded, separators=(',', ':'))+'\n').encode()
        require(json.loads(compact) == decoded, 'Metadata decoded value changed: '+name)
        if len(compact) < len(raw):
            candidates.append((len(raw)-len(compact), name, compact))
    for saved, name, compact in sorted(candidates, key=lambda row: (-row[0], row[1])):
        if packing and packing['empty_blocks'] >= 2:
            break
        before = new[name]
        new[name] = compact
        require(json.loads(new[name]) == json.loads(before), 'Compaction is not lossless: '+name)
        changes.append(dict(path=name, bytes_saved=saved, before_sha256=sha(before), after_sha256=sha(compact), decoded_equal=True))
        bootfs, packing = attempt()
    require(packing and packing['empty_blocks'] >= 2, 'Lossless metadata compaction cannot retain reserve')
    return new, bootfs, packing, changes


if __name__ == '__main__':
    main()

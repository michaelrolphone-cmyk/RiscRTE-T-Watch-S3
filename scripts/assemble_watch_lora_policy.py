#!/usr/bin/env python3
"""Apply the Audio LoRa 0.1.15 modal-policy correction to the complete qualified Spectrum union.

Writes a held exact-delta overlay and verified boot-store/bank artifacts. The
full-initial hash is streamed without allocating or writing an image.
No native firmware, host provider, SD checkpoint, or historical input is changed.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from current_bootfs import build, read_image
from watch_boot_order_spiffs import build as ordered_build
from check_runtime_store_admission import admit_cohort, store_digest
from assemble_watch_points_union import require, sha, encoded, git, read_store, BOOTFS, BANK
from build_lora_policy import VERSION, SYSTEM, SELECTION, COMPONENT_BUDGET_BYTES, PRIOR_SHA

ROOT = Path(__file__).resolve().parents[1]
BASE = SELECTION['baseline']['compiled_recipe_commit']
BASE_STORE_SHA = SELECTION['baseline']['candidate_store_sha256']
ANCESTOR = 'd3687db3ea6e6e5c8a36e5d01c5dfd2ba69ed453'
RUNTIME = '64c8e52e46fd91e8fdafd636db04eed88f0c51a9'
GRANT = dict(capability='ui.text-input', api=1, instance_id=0)
CHANGED = {'lora_messages.elf', 'lora_messages.json', 'cohort.json'}
# Exact ordinary unsigned manifests inspected in the selected, hashed baseline.
COMPACTABLE_METADATA = {'ble_buttons.json', 'points_in_time.json', 'countdown.json', 'settings.json', 'frequency_generator.json', 'springboard.json', 'audio_spectrum.json', 'battery.json', 'ble_touchpad.json', 'calculator.json', 'ota_update.json', 'alarms.json', 'app_store.json', 'wifi_settings.json'}
MANIFEST_FIELDS = {'architecture', 'entry', 'file_name', 'id', 'requires', 'type', 'version',
    'driver_abi', 'hardware_compatibility', 'physical_verification', 'provides', 'status'}


def strict_json(raw):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique_object)


def unsigned_manifest(value):
    return isinstance(value, dict) and value.get('type') in ('application', 'driver') and set(value) <= MANIFEST_FIELDS



def component(files, system, revision):
    record = strict_json((files / 'lora_messages-build-record.json').read_bytes())
    require(record['device'] == 'watch' and record['sources']['system-apps'] == system == SYSTEM and record['version'] == VERSION,
            'Wrong LoRa source')
    require(record['sources']['runtime'] == RUNTIME and record['sources']['utilities'] == SELECTION['sources']['utilities'] and record['product_recipe'] == revision,
            'Wrong LoRa recipe')
    for key in ['baseline_features_preserved', 'original_fonts_retained', 'shared_text_input', 'modal_policy']:
        require(record[key], 'Missing LoRa preservation proof: ' + key)
    data = {name: (files / name).read_bytes() for name in ['lora_messages.elf', 'lora_messages.json']}
    require(sha(data['lora_messages.elf']) == record['sha256'] and
            len(data['lora_messages.elf']) == record['bytes'] <= COMPONENT_BUDGET_BYTES,
            'LoRa ELF custody differs')
    require(sha(data['lora_messages.json']) == record['manifest_sha256'], 'LoRa manifest custody differs')
    return data, record


def payload(old, components, revision):
    require(set(components) == {'lora_messages.elf', 'lora_messages.json'}, 'Unexpected LoRa component member')
    expected = strict_json(old['lora_messages.json'])
    require(expected['version'] == '0.1.14', 'Wrong LoRa predecessor')
    require(expected['requires'].count(dict(capability='ui.text-input', api=1)) == 1, 'Wrong inherited LoRa authority')
    expected['version'] = VERSION
    require(strict_json(components['lora_messages.json']) == expected, 'LoRa authority changed')
    rows = [r for r in strict_json(old['boot.json'])['app_capabilities'] if r['manifest'] == 'lora_messages.json']
    require(len(rows) == 1 and rows[0]['grants'].count(GRANT) == 1, 'Unexpected LoRa authority')
    new = dict(old, **components)
    cohort = strict_json(old['cohort.json'])
    require(cohort['version'] == '1.1.18' and cohort['source_revision'] == BASE, 'Wrong Spectrum union predecessor')
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
    require(SELECTION['finalized'] and BASE and SYSTEM, 'Exact qualified baseline and source are not selected')
    require(sha(handoff_path.read_bytes()) == selected['combined_handoff_sha256'], 'Wrong qualified Spectrum handoff')
    raw = (candidate/'receipts/final-normal.json').read_bytes()
    require(sha(raw) == selected['receipt_sha256'], 'Changed Timecard qualification receipt')
    prior = strict_json(raw)
    sanitized = strict_json((candidate/'receipts/final-sanitized.json').read_bytes())
    require(prior == sanitized and prior['product_source'] == BASE and prior['system_source'] == selected['system_commit'] and
            prior['candidate_store_sha256'] == BASE_STORE_SHA and prior['elf_count'] == 55 and
            prior['free_spiffs_blocks'] == selected['free_spiffs_blocks'], 'Wrong Spectrum baseline qualification')
    bootfs = (candidate/'components/bootfs.bin').read_bytes()
    old = read_image(bootfs, 0x510000)
    require(store_digest(old) == BASE_STORE_SHA and len(old) == 113 and
            sum(n.endswith('.elf') for n in old) == 55 and sha(old['lora_messages.elf']) == PRIOR_SHA,
            'Wrong complete baseline store')
    ancestor = strict_json((native_candidate/'receipts/final-normal.json').read_bytes())
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
    for name in ['baseline', 'baseline-handoff', 'native-candidate', 'lora-build', 'runtime', 'system', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty product source')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    old, prior, native, firmware, previous = baseline(args.baseline, args.baseline_handoff, args.native_candidate)
    system = git(args.system, 'rev-parse', 'HEAD')
    system_tree = git(args.system, 'rev-parse', 'HEAD^{tree}')
    require(system == SYSTEM and not git(args.system, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty System source')
    data, record = component(args.lora_build, system, revision)
    new = payload(old, data, revision)
    boot = strict_json(new['boot.json'])
    grants = next(r['grants'] for r in boot['app_capabilities'] if r['manifest'] == 'lora_messages.json')
    require(GRANT in grants and grants == record['required_grants'], 'LoRa grant receipt differs')
    new, bootfs, packing, metadata_compaction = compact_to_floor(new)
    changed = {name for name in new if new[name] != old[name]}
    verify_preservation(old, new)
    require(packing['empty_blocks'] >= 2 and packing['file_count'] == 113, 'Watch reserve or inventory violated')
    require(read_image(bootfs, 0x510000) == new, 'Packed store roundtrip differs')
    require(git(args.runtime, 'rev-parse', 'HEAD') == RUNTIME and not git(args.runtime, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty Runtime source')
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
        for name, obj in [('packing', packing), ('lora-build', record), ('baseline-spectrum', prior)]:
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
        shared_text_hosts_unchanged=True, scene_host_unchanged=True, clock_unchanged=True, watch_has_no_native_resident_shell=True, modal_policy_successor=True, boot_json_byte_identical=True, boot_json_before_bytes=len(old['boot.json']), boot_json_after_bytes=len(new['boot.json']), full_image_bytes=0x1000000, full_image_sha256=full_sha,
        full_initial_erases_data=True, full_image_materialized=False, hardware_verified=False,
        delivered=False, delivery_hold_until_utc='2026-10-12T23:30:00Z', **admission)
    name = 'final-sanitized.json' if os.environ.get('SANITIZE') == '1' else 'final-normal.json'
    (args.output / 'receipts' / name).write_bytes(encoded(proof))
    print(json.dumps(proof, indent=2))



def verify_preservation(old, new):
    require(set(old) == set(new), 'Store inventory changed')
    changed = {name for name in new if new[name] != old[name]}
    require(changed <= CHANGED | COMPACTABLE_METADATA, 'Unexpected changed-file list')
    require(new['boot.json'] == old['boot.json'], 'Boot authority or formatting changed')
    for name in set(old) - CHANGED:
        if name.endswith('.json'):
            require(strict_json(new[name]) == strict_json(old[name]), 'Decoded metadata changed: ' + name)
            if new[name] != old[name]:
                require(name in COMPACTABLE_METADATA and unsigned_manifest(strict_json(old[name])), 'Not ordinary unsigned metadata: ' + name)
        else:
            require(new[name] == old[name], 'Unrelated component changed: ' + name)


def compact_to_floor(files):
    """Use deterministic, lossless JSON whitespace changes only when necessary."""
    new = dict(files)
    def packed():
        try:
            return ordered_build(new, build)
        except ValueError as error:
            if str(error) != 'Current bootfs lacks SPIFFS free-block reserve':
                raise
            return None, None
    bootfs, packing = packed()
    candidates = []
    for name, raw in new.items():
        if name not in COMPACTABLE_METADATA:
            continue
        decoded = strict_json(raw)
        if not unsigned_manifest(decoded):
            continue
        compact = (json.dumps(decoded, separators=(',', ':')) + '\n').encode()
        require(strict_json(compact) == decoded, 'Invalid metadata compaction: ' + name)
        if len(compact) < len(raw):
            candidates.append((len(raw) - len(compact), name, compact))
    changes = []
    for saved, name, compact in sorted(candidates, key=lambda item: (-item[0], item[1])):
        if packing and packing['empty_blocks'] >= 2:
            break
        before = new[name]
        new[name] = compact
        changes.append(dict(path=name, bytes_saved=saved, before_sha256=sha(before),
                            after_sha256=sha(compact), decoded_equal=True))
        bootfs, packing = packed()
    require(packing and packing['empty_blocks'] >= 2, 'Lossless metadata compaction cannot retain reserve')
    return new, bootfs, packing, changes

if __name__ == '__main__':
    main()

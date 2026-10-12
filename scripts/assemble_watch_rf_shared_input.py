#!/usr/bin/env python3
"""Add only RF Waterfall shared input to the complete published Spectrum union.

Writes a held four-file overlay and verified boot-store/bank artifacts. The
full-initial image is reconstructed only in memory to verify partition custody.
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
from build_rf_shared_input import VERSION
COMPONENT_BUDGET_BYTES = 249392
BASELINE_RF_SHA256 = 'f05b5ec08db1b1a7f8c7e3133c69b504e8e293d90f76bedcf2d93f0089b1c46b'

ROOT = Path(__file__).resolve().parents[1]
BASE = 'e9eeefcbaf35eb67a71fc46c8079ede9bccce863'
BASE_STORE_SHA = '85f8a410b852377c9979b98c67aa1af6d5266919bdfcf3dfbc631e0ac70256f2'
ANCESTOR = 'd3687db3ea6e6e5c8a36e5d01c5dfd2ba69ed453'
RUNTIME = '64c8e52e46fd91e8fdafd636db04eed88f0c51a9'
SYSTEM = '7fb13b09b4dac275a8111b224784f8a472f39264'
GRANT = dict(capability='ui.text-input', api=1, instance_id=0)
CHANGED = {'waterfall.elf', 'waterfall.json', 'boot.json', 'cohort.json'}


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
    require(expected['version'] == '0.3.3', 'Wrong RF predecessor')
    expected['version'] = VERSION
    expected['requires'].append(dict(capability='ui.text-input', api=1))
    require(json.loads(components['waterfall.json']) == expected, 'RF authority exceeds additive delta')
    boot = json.loads(old['boot.json'])
    original = copy.deepcopy(boot)
    rows = [r for r in boot['app_capabilities'] if r['manifest'] == 'waterfall.json']
    require(len(rows) == 1 and GRANT not in rows[0]['grants'], 'Unexpected RF authority')
    rows[0]['grants'].append(copy.deepcopy(GRANT))
    new = dict(old, **components)
    new['boot.json'] = encoded(boot)
    rows[0]['grants'].pop()
    require(boot == original, 'Unrelated boot change')
    cohort = json.loads(old['cohort.json'])
    require(cohort['version'] == '1.1.18' and cohort['source_revision'] == BASE, 'Wrong Spectrum union predecessor')
    cohort['source_revision'] = revision
    new['cohort.json'] = encoded(cohort)
    require(set(new) == set(old) and {n for n in new if new[n] != old[n]} == CHANGED, 'Unexpected store delta')
    return new


def baseline(components, candidate):
    handoff = json.loads((components / 'handoff.json').read_bytes())
    prior = json.loads((components / 'watch/receipts/final-normal.json').read_bytes())
    sanitized = json.loads((components / 'watch/receipts/final-sanitized.json').read_bytes())
    require(prior == sanitized and prior['product_source'] == BASE and
            prior['candidate_store_sha256'] == BASE_STORE_SHA and prior['elf_count'] == 55 and
            prior['free_spiffs_blocks'] == 4, 'Wrong Spectrum baseline qualification')
    require(handoff['source']['system']['published_commit'] == SYSTEM and
            handoff['source']['runtime']['commit'] == RUNTIME and
            handoff['cohort']['product_source'] == BASE and handoff['store_files'] == 113 and
            handoff['cohort']['candidate_store_sha256'] == BASE_STORE_SHA and
            not handoff['source']['depends_on_unpublished_sd_changes'], 'Wrong published Spectrum provenance')
    bootfs = (components / 'watch/components/bootfs.bin').read_bytes()
    old = read_image(bootfs, 0x510000)
    require(store_digest(old) == BASE_STORE_SHA and len(old) == 113 and
            sum(n.endswith('.elf') for n in old) == 55 and
            sha(old['waterfall.elf']) == BASELINE_RF_SHA256, 'Wrong complete baseline store')
    overlay = read_store(components / 'watch/overlay')
    require(set(overlay) == set(prior['changed_store_paths']) and
            all(old[n] == raw for n, raw in overlay.items()), 'Spectrum overlay differs from qualified store')
    for name in ['bootfs.bin', 'bank_state.bin']:
        raw = (components / 'watch/components' / name).read_bytes()
        proof = handoff['local_artifacts']['watch/components/' + name]
        require(sha(raw) == proof['sha256'] and len(raw) == proof['bytes'], 'Spectrum packed artifact differs: ' + name)
    ancestor = json.loads((candidate / 'receipts/final-normal.json').read_bytes())
    require(ancestor['product_source'] == ANCESTOR, 'Wrong native ancestor')
    native = (candidate / 'components/firmware.elf').read_bytes()
    firmware = (candidate / 'components/firmware.bin').read_bytes()
    previous = (candidate / 'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin').read_bytes()
    require(sha(native) == prior['native_elf_sha256'] == ancestor['native_elf_sha256'], 'Wrong native ELF')
    require(sha(previous) == ancestor['full_image_sha256'] and
            previous[0x10000:0x10000 + len(firmware)] == firmware, 'Wrong native ancestor image')
    full = bytearray(previous)
    full[slice(*BOOTFS)] = bootfs
    full[slice(*BANK)] = (components / 'watch/components/bank_state.bin').read_bytes()
    require(len(full) == 0x1000000 and sha(full) == prior['full_image_sha256'] ==
            handoff['cohort']['full_image_sha256'], 'Spectrum full-image reconstruction differs')
    return old, prior, native, firmware, bytes(full)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['baseline-components', 'native-candidate', 'rf-build', 'runtime', 'system', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty product source')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    old, prior, native, firmware, previous = baseline(args.baseline_components, args.native_candidate)
    system = git(args.system, 'rev-parse', 'HEAD')
    system_tree = git(args.system, 'rev-parse', 'HEAD^{tree}')
    require(system == SYSTEM and not git(args.system, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty System source')
    data, record = component(args.rf_build, system, revision)
    new = payload(old, data, revision)
    boot = json.loads(new['boot.json'])
    grants = next(r['grants'] for r in boot['app_capabilities'] if r['manifest'] == 'waterfall.json')
    require(GRANT in grants, 'RF grant receipt differs')
    bootfs, packing = ordered_build(new, build)
    require(packing['empty_blocks'] >= 2 and packing['file_count'] == 113, 'Watch reserve or inventory violated')
    require(read_image(bootfs, 0x510000) == new, 'Packed store roundtrip differs')
    require(git(args.runtime, 'rev-parse', 'HEAD') == RUNTIME, 'Wrong Runtime source')
    profile = args.runtime / 'watch-file-source-profile.ini'
    require(profile.read_bytes() == (ROOT / 'docs/file-source/watch-file-source-profile.ini').read_bytes(), 'Wrong native profile')
    sys.path.insert(0, str(args.runtime / 'scripts'))
    from paired_bank_images import initial_bank_state, parse_record
    bank = initial_bank_state(firmware, bootfs, True)
    full = bytearray(previous)
    full[slice(*BOOTFS)] = bootfs
    full[slice(*BANK)] = bank
    for lo, hi in [(0, BOOTFS[0]), (BOOTFS[1], BANK[0]), (BANK[1], len(full))]:
        require(full[lo:hi] == previous[lo:hi], 'Unrelated partition changed')
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
        for name, obj in [('packing', packing), ('rf-build', record), ('baseline-spectrum', prior)]:
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
        free_spiffs_blocks=packing['empty_blocks'], store_files=len(new), existing_apps_and_providers_preserved=True,
        grant_delta=[dict(manifest='waterfall.json', grant=GRANT)], native_unchanged=True,
        shared_text_hosts_unchanged=True, full_image_bytes=len(full), full_image_sha256=sha(full),
        full_initial_erases_data=True, full_image_materialized=False, hardware_verified=False,
        delivered=False, delivery_hold_until_utc='2026-10-12T23:30:00Z', **admission)
    name = 'final-sanitized.json' if os.environ.get('SANITIZE') == '1' else 'final-normal.json'
    (args.output / 'receipts' / name).write_bytes(encoded(proof))
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()

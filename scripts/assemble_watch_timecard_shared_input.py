#!/usr/bin/env python3
"""Add only Timecard shared input to the complete published RF union.

Writes a held four-file overlay and verified boot-store/bank artifacts. The
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
from build_timecard_shared_input import VERSIONS
VERSION=VERSIONS['watch']
COMPONENT_BUDGET_BYTES = 150000
BASELINE_TIMECARD_SHA256 = '8d241dc09e9f6181778200527ee3456d40f9542c0aa8c84a113937ae5eb0423d'

ROOT = Path(__file__).resolve().parents[1]
BASE = '53ed0b0a71965075b98392d78274dae5fd48bf6f'
BASE_STORE_SHA = '3e41c1642d07a4fdbdecdf3780413509435d1e44a6ff26fadd43778111feb451'
ANCESTOR = 'd3687db3ea6e6e5c8a36e5d01c5dfd2ba69ed453'
RUNTIME = '64c8e52e46fd91e8fdafd636db04eed88f0c51a9'
SYSTEM = '7fb13b09b4dac275a8111b224784f8a472f39264'
GRANT = dict(capability='ui.text-input', api=1, instance_id=0)
CHANGED = {'timecard.elf', 'timecard.json', 'boot.json', 'cohort.json'}


def component(files, system, revision):
    record = json.loads((files / 'timecard-build-record.json').read_bytes())
    require(record['device'] == 'watch' and record['sources']['system-apps'] == system == SYSTEM and record['version'] == VERSION,
            'Wrong Timecard source')
    require(record['sources']['runtime'] == RUNTIME and record['product_recipe'] == revision,
            'Wrong Timecard recipe')
    for key in ['baseline_features_preserved', 'original_fonts_retained', 'shared_text_input']:
        require(record[key], 'Missing Timecard preservation proof: ' + key)
    data = {name: (files / name).read_bytes() for name in ['timecard.elf', 'timecard.json']}
    require(sha(data['timecard.elf']) == record['sha256'] and
            len(data['timecard.elf']) == record['bytes'] <= COMPONENT_BUDGET_BYTES,
            'Timecard ELF custody differs')
    require(sha(data['timecard.json']) == record['manifest_sha256'], 'Timecard manifest custody differs')
    return data, record


def payload(old, components, revision):
    require(set(components) == {'timecard.elf', 'timecard.json'}, 'Unexpected Timecard component member')
    expected = json.loads(old['timecard.json'])
    require(expected['version'] == '0.2.12', 'Wrong Timecard predecessor')
    expected['version'] = VERSION
    expected['requires'].append(dict(capability='ui.text-input', api=1))
    require(json.loads(components['timecard.json']) == expected, 'Timecard authority exceeds additive delta')
    boot = json.loads(old['boot.json'])
    original = copy.deepcopy(boot)
    rows = [r for r in boot['app_capabilities'] if r['manifest'] == 'timecard.json']
    require(len(rows) == 1 and GRANT not in rows[0]['grants'], 'Unexpected Timecard authority')
    rows[0]['grants'].append(copy.deepcopy(GRANT))
    new = dict(old, **components)
    # Formatting only: the sole semantic addition remains the Timecard grant.
    new['boot.json'] = (json.dumps(boot,sort_keys=True,separators=(',',':'))+'\n').encode()
    require(json.loads(new['boot.json'])==boot,'Compact boot metadata changed meaning')
    rows[0]['grants'].pop()
    require(boot == original, 'Unrelated boot change')
    cohort = json.loads(old['cohort.json'])
    require(cohort['version'] == '1.1.18' and cohort['source_revision'] == BASE, 'Wrong RF union predecessor')
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
    handoff=json.loads((components/'handoff.json').read_bytes())
    prior=json.loads((components/'watch/receipts/final-normal.json').read_bytes())
    sanitized=json.loads((components/'watch/receipts/final-sanitized.json').read_bytes())
    require(prior==sanitized and prior['product_source']==BASE and prior['candidate_store_sha256']==BASE_STORE_SHA and prior['elf_count']==55 and prior['free_spiffs_blocks']==3,'Wrong RF baseline qualification')
    require(handoff['source']['system']['commit']==SYSTEM and handoff['source']['watch']['commit']==BASE and not handoff['source']['depends_on_unpublished_sd_changes'],'Wrong RF provenance')
    for name in ('bootfs.bin','bank_state.bin'):
        p=components/'watch/components'/name; row=handoff['devices']['watch']['components'][name]
        require(sha(p.read_bytes())==row['sha256'] and p.stat().st_size==row['bytes'],'Changed baseline component: '+name)
    bootfs=(components/'watch/components/bootfs.bin').read_bytes();old=read_image(bootfs,0x510000)
    require(store_digest(old)==BASE_STORE_SHA and len(old)==113 and sum(n.endswith('.elf') for n in old)==55 and sha(old['timecard.elf'])==BASELINE_TIMECARD_SHA256,'Wrong complete baseline store')
    ancestor=json.loads((candidate/'receipts/final-normal.json').read_bytes())
    require(ancestor['product_source']==ANCESTOR,'Wrong native ancestor')
    native=(candidate/'components/firmware.elf').read_bytes();firmware=(candidate/'components/firmware.bin').read_bytes()
    previous=candidate/'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin'
    require(sha(native)==prior['native_elf_sha256']==ancestor['native_elf_sha256'],'Wrong native ELF')
    require(streamed_digest(previous)==ancestor['full_image_sha256'],'Wrong native ancestor image')
    with previous.open('rb') as f:
        f.seek(0x10000);require(f.read(len(firmware))==firmware,'Wrong native bytes')
    require(streamed_digest(previous,{BOOTFS[0]:bootfs,BANK[0]:(components/'watch/components/bank_state.bin').read_bytes()})==prior['full_image_sha256'],'RF reconstruction differs')
    return old,prior,native,firmware,previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['baseline-components', 'native-candidate', 'timecard-build', 'runtime', 'system', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty product source')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    old, prior, native, firmware, previous = baseline(args.baseline_components, args.native_candidate)
    system = git(args.system, 'rev-parse', 'HEAD')
    system_tree = git(args.system, 'rev-parse', 'HEAD^{tree}')
    require(system == SYSTEM and not git(args.system, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty System source')
    data, record = component(args.timecard_build, system, revision)
    new = payload(old, data, revision)
    boot = json.loads(new['boot.json'])
    grants = next(r['grants'] for r in boot['app_capabilities'] if r['manifest'] == 'timecard.json')
    require(GRANT in grants, 'Timecard grant receipt differs')
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
        for name, obj in [('packing', packing), ('timecard-build', record), ('baseline-rf', prior)]:
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
        grant_delta=[dict(manifest='timecard.json', grant=GRANT)], native_unchanged=True,
        shared_text_hosts_unchanged=True, boot_json_formatting_only_beyond_grant=True, boot_json_before_bytes=len(old['boot.json']), boot_json_after_bytes=len(new['boot.json']), full_image_bytes=0x1000000, full_image_sha256=full_sha,
        full_initial_erases_data=True, full_image_materialized=False, hardware_verified=False,
        delivered=False, delivery_hold_until_utc='2026-10-12T23:30:00Z', **admission)
    name = 'final-sanitized.json' if os.environ.get('SANITIZE') == '1' else 'final-normal.json'
    (args.output / 'receipts' / name).write_bytes(encoded(proof))
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()

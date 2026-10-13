#!/usr/bin/env python3
"""Qualify a later Scanner component cohort without assembling a device image."""
import argparse
import json
import os
from pathlib import Path
import assemble_watch_scanner_policy as a


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'baseline-handoff', 'native-candidate', 'scanner-build', 'runtime', 'system', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--provisional', action='store_true')
    args = p.parse_args()
    revision = a.git(a.ROOT, 'rev-parse', 'HEAD')
    a.require(not a.git(a.ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty qualification recipe')
    old, prior, native, firmware, previous = a.baseline(args.baseline, args.baseline_handoff, args.native_candidate)
    system = a.git(args.system, 'rev-parse', 'HEAD')
    a.require(system == a.SYSTEM and not a.git(args.system, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty System')
    data, record = a.component(args.scanner_build, system, revision)
    a.require(args.provisional or (a.SELECTION['finalized'] and record['source_publication'] == 'public-exact-commit' and
              record['sources'] == a.SELECTION['sources']), 'Unfinalized component source')
    a.require(record['metadata_gap_packing'] and record['metadata_gap_packing']['after_sha256'] == record['sha256'],
              'Missing Scanner metadata packing proof')
    for name, row in record['target_dependencies'].items():
        owner, relative = name.split(':', 1)
        a.require(a.sha((Path(record['source_roots'][owner]) / relative).read_bytes()) == row['sha256'], 'Changed component source: ' + name)
    new = a.payload(old, data, revision)
    new, companions = a.pack_companions(old, new)
    a.verify_preservation(old, new)
    grants = next(row['grants'] for row in a.strict_json(new['boot.json'])['app_capabilities'] if row['manifest'] == 'ble_scanner.json')
    a.require(grants == record['required_grants'], 'Changed Scanner grants')
    # Pack and read back in memory only. No candidate store, bank or flash image is written.
    packed, bootfs, packing, metadata = a.compact_to_floor(new)
    a.require(packed == new and not metadata, 'Unexpected additional JSON compaction')
    a.require(a.read_image(bootfs, 0x510000) == new and packing['empty_blocks'] >= 2, 'Reserve or SPIFFS roundtrip differs')
    a.require(a.git(args.runtime, 'rev-parse', 'HEAD') == a.RUNTIME and
              not a.git(args.runtime, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty Runtime')
    profile = args.runtime / 'watch-file-source-profile.ini'
    a.require(profile.read_bytes() == (a.ROOT/'docs/file-source/watch-file-source-profile.ini').read_bytes(), 'Wrong Runtime profile')
    admission = a.admit_cohort(args.runtime, native, old, new, app_policy_rows=24, native_profile=profile)
    changed = sorted(name for name in new if new[name] != old[name])
    a.require(set(changed) == a.CHANGED | set(a.PACKING_ONLY), 'Unexpected final component delta')
    a.require(admission['elf_count'] == 55 and len(new) == 113, 'Incomplete cohort')
    pages = a.page_demand(new)
    proof = dict(schema='scanner.modal-policy.component-cohort.v1', status='component-cohort-qualified',
        recipe_commit=revision, recipe_tree=a.git(a.ROOT, 'rev-parse', 'HEAD^{tree}'),
        source_publication=record['source_publication'], sources=record['sources'],
        baseline_handoff_sha256=a.sha(args.baseline_handoff.read_bytes()), baseline_recipe=a.BASE,
        scanner_elf_sha256=record['sha256'], scanner_elf_bytes=record['bytes'], scanner_metadata_packing=record['metadata_gap_packing'],
        companion_metadata_packing=companions, changed_store_paths=changed, unrelated_elf_count=52,
        store_files=len(new), free_spiffs_blocks=packing['empty_blocks'], required_free_spiffs_blocks=2,
        page_accounting=pages, remaining_object_pages_before_floor=19410-pages['used_object_pages'],
        remaining_eligible_json_object_pages=1, additional_json_compaction=[],
        boot_json_byte_identical=new['boot.json']==old['boot.json'], grant_delta=[], native_unchanged=True,
        in_memory_spiffs_sha256=a.sha(bootfs), spiffs_roundtrip_identical=True,
        candidate_store_materialized=False, bank_materialized=False, full_device_image_materialized=False,
        flashed=False, delivered=False, hardware_verified=False, later_build_only=True,
        tonight_sealed_artifacts_unchanged=True, **admission)
    a.require(a.git(a.ROOT, 'rev-parse', 'HEAD') == revision and
              not a.git(a.ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Recipe changed during admission')
    args.output.mkdir(parents=True, exist_ok=True)
    label = 'sanitized' if os.environ.get('SANITIZE') == '1' else 'normal'
    (args.output/(label+'.json')).write_text(json.dumps(proof, sort_keys=True, indent=2)+'\n')
    print(json.dumps({'status':proof['status'], 'elf_count':proof['elf_count'], 'free_blocks':proof['free_spiffs_blocks'],
                      'object_pages':pages['used_object_pages'], 'changed':changed, 'device_image_materialized':False}))


if __name__ == '__main__':
    main()

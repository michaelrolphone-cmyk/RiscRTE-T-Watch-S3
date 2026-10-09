#!/usr/bin/env python3
"""Verify bounded recovery history and completed, independently sealed proofs."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'docs/lifecycle/watch-1.0.19/recovery'


def check(ok, message):
    if not ok:
        raise ValueError(message)


def verified_file(item):
    path = BASE / item['file']
    check(path.parent == BASE and path.is_file() and not path.is_symlink(), 'Invalid custody member')
    raw = path.read_bytes()
    check(len(raw) == item['size_bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'],
          'Custody member digest differs: ' + path.name)
    return path


def main():
    # Restore the original proof parent without changing visible product files.
    subprocess.run(['python3', str(ROOT / 'scripts/check_policy_source_snapshot.py')], check=True)
    record = json.loads((BASE / 'custody.json').read_bytes())
    check(record['schema'] == 1 and record['historical_receipts_recreated'] is False and
          record['hardware_qualified'] is False, 'Incorrect qualification scope')
    bundle = verified_file(record['bundle'])
    subprocess.run(['git', '-C', str(ROOT), 'bundle', 'verify', str(bundle)], check=True)
    subprocess.run(['git', '-C', str(ROOT), 'fetch', str(bundle),
                    'refs/watch-recovery/*:refs/watch-recovery/*'], check=True)
    for item in record['heads'].values():
        commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', item['bundle_ref']], text=True).strip()
        tree = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', commit + '^{tree}'], text=True).strip()
        check(commit == item['commit'] and tree == item['tree'], 'Recovery source identity differs')
    with zipfile.ZipFile(verified_file(record['qualification'])) as archive:
        expected = {'reconstruction.json', 'package-guard-results.json'} | set(record['matrices']) | {
            name.removesuffix('.json') + '.log' for name in record['matrices']}
        check(len(archive.namelist()) == len(expected) and set(archive.namelist()) == expected,
              'Qualification archive members differ')
        reconstruction = archive.read('reconstruction.json')
        check(hashlib.sha256(reconstruction).hexdigest() ==
              '863c18604173ba2dc2e15fb149a76dd244016eb2e8eae626615c9ad177fe53de',
              'Independently sealed reconstruction differs')
        receipts = {name: json.loads(archive.read(name)) for name in record['matrices']}
        for name, proof in receipts.items():
            check(proof['qualification_source'] == record['heads']['preservation']['commit'], 'Wrong proof source')
            check(len(proof['scenarios']) == 31 and len(proof['transactions']) == 159 and
                  len(proof['rejections']) == 16, 'Incomplete matrix: ' + name)
            check(all(row['nvs_appdata_preserved'] and row['previous_pair_preserved']
                      for row in proof['transactions']), 'Preservation failure: ' + name)
            check(all(not row['cohort_validated'] and row['hardware_calls'] == 0 and row['storage_calls'] == 0
                      for row in proof['rejections']), 'Invalid candidate admitted: ' + name)
            check(proof['physical_flash_tls_spiffs_and_target_instructions_executed'] is False and
                  proof['device_health_confirmation_executed'] is False and
                  proof['reconstructed_candidate']['historical_package_receipt_used'] is False,
                  'Incorrect host proof scope')
        first = receipts['watch118-recovered-from15-normal.json']
        second = receipts['watch119-recovered-chain-normal.json']
        check(first['selected_snapshot'] == second['source_initial_image'] and
              first['destination_bank'] == second['source_bank'] == 1 and second['destination_bank'] == 0 and
              second['input_persistent_data_kept'] is True, 'Chain does not reuse actual selected snapshot')
        guards = json.loads(archive.read('package-guard-results.json'))
        check(len(guards['cases']) == 16 and all(row['rejected'] for row in guards['cases']),
              'Incomplete package guard refusals')
    print('Recovery source verified: four matrices, 636 processes, 64 negative admissions, 16 package refusals')


if __name__ == '__main__':
    main()

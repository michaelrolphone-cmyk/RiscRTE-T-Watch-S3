#!/usr/bin/env python3
"""Restore exact Watch20/21 recipes and verify sealed host qualification."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'docs/lifecycle/watch-1.0.21'


def require(value, message):
    if not value:
        raise ValueError(message)


def main():
    subprocess.run(['python3', str(ROOT / 'scripts/check_recovery_source_snapshot.py')], check=True)
    record = json.loads((BASE / 'custody.json').read_bytes())
    require(record['schema'] == 1 and record['prerequisite'] ==
            '896663b6bbe4a1a5b5d4183fadd83a2602444adb', 'Wrong prerequisite')
    for item in [record['bundle'], *[dict(file=name, **v) for name, v in record['proofs'].items()]]:
        path = BASE / item['file']
        require(path.parent == BASE and path.is_file() and not path.is_symlink(), 'Invalid member')
        raw = path.read_bytes()
        require(len(raw) == item['size_bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'],
                'Custody bytes differ: ' + path.name)
    bundle = BASE / record['bundle']['file']
    subprocess.run(['git', '-C', str(ROOT), 'bundle', 'verify', str(bundle)], check=True)
    subprocess.run(['git', '-C', str(ROOT), 'fetch', str(bundle),
                    'refs/watch-hid-custody/*:refs/watch-hid-custody/*'], check=True)
    expected = {'watch20': '15624cb108c2ba65b35cd6b20283a2edff2bb415',
                'watch21': 'b44d8ee0159464e9fd2be20c02092c6596573860'}
    for name, sha in expected.items():
        item = record['heads'][name]
        require(item['commit'] == sha, 'Original source changed')
        for ref, wanted in [(item['ref'], sha), (sha + '^{tree}', item['tree'])]:
            require(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', ref], text=True).strip() == wanted,
                    'Recovered source identity differs')
    for name in record['selected_files']:
        require((ROOT / name).read_bytes() == subprocess.check_output(
            ['git', '-C', str(ROOT), 'show', expected['watch21'] + ':' + name]), 'Recipe differs: ' + name)
    digests = {20: 'bda601dad85ebb8e9c824edcb97827bd818a9eacf684c38c271e1aa27e6d378a',
               21: '4ad9155ca9ec94c440e9d4c6c868947bae0a0d7868f9f416929ca18bbca8404b'}
    for version in (20, 21):
        build = json.loads((BASE / f'watch{version}-build.json').read_bytes())
        admission = json.loads((BASE / f'watch{version}-admission.json').read_bytes())
        require(build['source_revision'] == expected[f'watch{version}'] and len(build['files']) == 95,
                'Wrong source or store inventory')
        require(not build['hardware_qualified'] and not build['preserving_transaction_qualified'] and
                not build['live_feed_published'], 'Incorrect qualification scope')
        require(admission['actual_full_image'] == {'sha256': digests[version], 'size_bytes': 16777216},
                'Full image identity differs')
        for mode in ('normal', 'sanitized'):
            cohort = admission['results'][mode]['cohort']
            store = admission['results'][mode]['whole_store']
            require(cohort['prepared'] and cohort['cohort_validated'] and cohort['elf_count'] == 46 and
                    cohort['app_policy_rows'] == 16 and not cohort['target_instructions_executed'], 'Cohort proof failed')
            require(store['prepared'] and store['store_files'] == 95, 'Store proof failed')
            require(all(result['hardware_calls'] == result['storage_calls'] == 0 and not result['error']
                        for result in (cohort, store)), 'Admission performed I/O or failed')
        guards = json.loads((BASE / f'watch{version}-scope-refusals.json').read_bytes())
        require((guards['refusals'] == 100 and len(guards['refused']) == 100) if version == 20 else
                (guards['count'] == 100 and len(guards['refusals']) == 100), 'Scope mutation matrix incomplete')
    print('Exact Watch20/21 source, 2 normal/sanitized admissions and 200 scope refusals verified')


if __name__ == '__main__':
    main()

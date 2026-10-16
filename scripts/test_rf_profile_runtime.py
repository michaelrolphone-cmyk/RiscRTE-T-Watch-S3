#!/usr/bin/env python3
"""Exercise RF policy admission against the accepted production Runtime.

No app/firmware build, image generation, publication, or physical execution.
Candidate metadata reuses accepted ELFs to isolate actual Runtime policy rules;
future compiled RF target ELF admission remains an integration requirement.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile

from check_runtime_store_admission import compile_harness, store_digest
from current_apps_overlay import ROOT, config, encoded, require
from publish_complete_watch import CUSTODY, CUSTODY_HASHES, verify_accepted
from rf_spectrum_profile import PRIVATE_GRANTS, RUNTIME_SOURCE, upgrade_boot


def accepted_store(root=ROOT):
    inputs = Path(root) / 'release/complete-1.0.7'
    image = gzip.decompress((inputs / 'accepted.bin.gz').read_bytes())
    evidence = (inputs / 'accepted-app-evidence.zip').read_bytes()
    custody_root = Path(root) / CUSTODY.relative_to(ROOT)
    custody = {n: (custody_root / n).read_bytes() for n in CUSTODY_HASHES}
    return verify_accepted(image, evidence, custody)[0]


def candidate_metadata(accepted):
    following = dict(accepted)
    following['boot.json'] = encoded(upgrade_boot(json.loads(accepted['boot.json'])))
    manifest = json.loads(accepted['waterfall.json'])
    manifest['version'] = '0.2.0'
    manifest['requires'] += [{k: g[k] for k in ('capability', 'api')} for g in PRIVATE_GRANTS]
    following['waterfall.json'] = encoded(manifest)
    cohort = json.loads(accepted['cohort.json'])
    cohort['version'] = '1.0.8'
    cohort['source_revision'] = '1' * 40  # Metadata test identity, never an emitted release source.
    following['cohort.json'] = encoded(cohort)
    return following


def cases(accepted):
    good = candidate_metadata(accepted)
    yield 'accepted-to-rf-private-namespaces', accepted, good, True
    yield 'rf-self-admission', good, good, True
    for label in ('stale-hid-migration', 'retargeted-hid-migration', 'steal-spectrum-kv',
                  'steal-timecard-data', 'steal-spectrum-data', 'change-shared-preferences-api',
                  'remove-shared-preferences', 'thirteenth-grant', 'missing-private-requirement'):
        candidate = dict(good)
        boot = json.loads(good['boot.json'])
        row = next(r for r in boot['app_capabilities'] if r['manifest'] == 'waterfall.json')
        manifest = json.loads(good['waterfall.json'])
        if label in ('stale-hid-migration', 'retargeted-hid-migration'):
            boot['cohort_migration'] = json.loads(accepted['boot.json'])['cohort_migration']
            if label == 'retargeted-hid-migration':
                boot['cohort_migration']['to']['version'] = '1.0.8'
        elif label == 'steal-spectrum-kv': row['grants'][-2]['instance_id'] = 7
        elif label == 'steal-timecard-data': row['grants'][-1]['instance_id'] = 1
        elif label == 'steal-spectrum-data': row['grants'][-1]['instance_id'] = 2
        elif label == 'change-shared-preferences-api': row['grants'][-2]['instance_id'] = 1
        elif label == 'remove-shared-preferences':
            row['grants'] = [g for g in row['grants'] if not
                             (g['capability'] == 'storage.key-value' and g['api'] == 1)]
            manifest['requires'] = [g for g in manifest['requires'] if not
                                    (g['capability'] == 'storage.key-value' and g['api'] == 1)]
        elif label == 'thirteenth-grant':
            row['grants'].append({'capability': 'storage.key-value', 'api': 1, 'instance_id': 99})
        else:
            manifest['requires'] = [g for g in manifest['requires'] if g['capability'] != 'storage.app-data']
        candidate['boot.json'] = encoded(boot)
        candidate['waterfall.json'] = encoded(manifest)
        yield label, accepted, candidate, False


def run(runtime):
    runtime = Path(runtime).resolve()
    require(subprocess.check_output(['git', '-C', str(runtime), 'rev-parse', 'HEAD'], text=True).strip()
            == RUNTIME_SOURCE, 'RF admission requires accepted Runtime source')
    require(not subprocess.check_output(['git', '-C', str(runtime), 'status', '--porcelain',
                                         '--untracked-files=no'], text=True).strip(), 'Runtime source is dirty')
    config(profile='rf-spectrum', allow_pending=True)
    accepted = accepted_store()
    digest = store_digest(accepted)
    results = []
    with tempfile.TemporaryDirectory(prefix='watch-rf-policy-') as temp:
        root = Path(temp)
        harness = compile_harness(runtime, root / 'admit', app_data=True, cohort_policy=True)
        for label, before, following, expected in cases(accepted):
            for kind, store in (('active', before), ('candidate', following)):
                for name, raw in store.items():
                    path = root / kind / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
            result = subprocess.run([str(harness), str(root / 'active'), str(root / 'candidate')],
                                    text=True, capture_output=True, timeout=60)
            require(result.returncode == 0, 'RF Runtime process failed: ' + label + '\n' + result.stderr)
            outcome = json.loads(result.stdout)
            require(outcome['prepared'] and outcome['cohort_validated'] is expected
                    and not outcome['hardware_calls'] and not outcome['storage_calls'],
                    'RF Runtime policy case failed: ' + label + ' ' + str(outcome))
            for kind, store in (('active', before), ('candidate', following)):
                actual = {p.relative_to(root / kind).as_posix(): p.read_bytes()
                          for p in (root / kind).rglob('*') if p.is_file()}
                require(actual == store, 'RF admission changed ' + kind + ' inputs')
            results.append({'case': label, 'accepted': expected, **outcome})
    require(store_digest(accepted) == digest, 'Accepted source store changed')
    return {'schema': 1, 'runtime_source': RUNTIME_SOURCE, 'accepted_store_sha256': digest,
            'sanitized': os.environ.get('SANITIZE') == '1', 'cases': results,
            'candidate_is_metadata_test_only': True, 'future_target_elf_verified': False,
            'physical_verification': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.runtime), indent=2))

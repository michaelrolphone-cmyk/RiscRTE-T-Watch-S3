#!/usr/bin/env python3
"""Guard GUI-only changes against the physically confirmed original CI store."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def verify(path):
    baseline = json.loads((ROOT / 'docs/GUI_BASELINE.json').read_text())
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), 'Duplicate archive entries'
        files = {n.removeprefix('store/'): archive.read(n)
                 for n in names if n.startswith('store/')}
        source = json.loads(archive.read('shared-app-build.json'))
        assert source['touch_rotation'] == 0
        assert source['full_frames'] is True
        assert source['retained_handoff'] is True
        assert source['crown_navigation'] == 'app-local-original-pmu'
        assert source['shared_sources'] == json.loads((ROOT / 'apps/shared-sources.json').read_text())
    expected = baseline['baseline_store_sha256']
    assert set(files) == set(expected) and len(files) == 22, 'Physical/provider store closure changed'
    actual = {n: hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())}
    changed = sorted(n for n in files if actual[n] != expected[n])
    assert changed == sorted(baseline['changed_store_files']), changed
    # This separately protects all six packaged driver ELFs (seven mapped
    # physical instances), their manifests, and exact accepted board wiring.
    fixed = sorted(set(expected) - set(baseline['changed_store_files']))
    assert len(fixed) == 13
    assert all(actual[n] == expected[n] for n in fixed)
    boot = json.loads(files['boot.json'])
    assert boot['drivers'] == baseline['baseline_driver_instances'], 'Physical instance mapping changed'
    assert len(boot['drivers']) == 7
    assert {d['instance_id'] for d in boot['drivers']} == {1, 2, 3, 4, 5, 6, 8}
    for app in boot['app_capabilities']:
        assert {'capability': 'board.battery', 'api': 1, 'instance_id': 4} in app['grants']
        assert all(g['capability'] != 'input.navigation' for g in app['grants'])
    record = {**baseline, 'variant_store_sha256': actual,
              'verified_changed_files': changed, 'unchanged_file_count': len(fixed),
              'unchanged_store_files': fixed, 'full_frames': True,
              'crown_navigation': 'app-local-original-pmu'}
    out = Path(path).parent / 'gui-increment-proof.json'
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('Verified GUI-only inventory: 13 unchanged physical/board files; 9 application/policy files changed')
    return record

if __name__ == '__main__':
    assert len(sys.argv) == 2
    verify(sys.argv[1])

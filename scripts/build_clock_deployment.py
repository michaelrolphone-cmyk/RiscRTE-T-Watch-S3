#!/usr/bin/env python3
"""Stage explicit clock-only stores and immutable deployment ZIPs; never flash."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NOVA_NOTICES = ('Orbitron-OFL.txt', 'Rajdhani-OFL.txt', 'SOURCES.txt')
DEVICES = {1: 'gpio', 2: 'i2c', 4: 'pmu', 5: 'panel', 8: 'rtc'}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def selected_board(profile):
    board = copy.deepcopy(profile)
    board['devices'] = [d for d in board['devices'] if d['instance_id'] in DEVICES]
    if {d['instance_id'] for d in board['devices']} != DEVICES.keys():
        raise ValueError('Profile does not have the complete clock dependency closure')
    board['buses'] = [b for b in board['buses'] if b['instance_id'] in (101, 103)]
    pmu = next(d for d in board['devices'] if d['instance_id'] == 4)
    # Only LCD/backlight rails: do not energize radio/haptic to display a clock.
    pmu['config']['rails'] = [r for r in pmu['config']['rails'] if r['id'] in (1, 2)]
    if {r['id'] for r in pmu['config']['rails']} != {1, 2}:
        raise ValueError('Profile does not declare both required display rails')
    panel = next(d for d in board['devices'] if d['instance_id'] == 5)
    panel['config']['rotation'] = 2
    # Manufacturer's exact Watch-S3 ST7789 setup uses40MHz. Keep the source
    # eight-profile baseline and all unrelated buses unchanged.
    next(b for b in board['buses'] if b['instance_id'] == panel['config']['bus_instance_id'])['frequency_hz'] = 40000000
    return board


def build(profile_path, root=ROOT):
    profile = json.loads(profile_path.read_text())
    board = selected_board(profile)
    version = json.loads((root / 'apps/clock/manifest.json').read_text())['version']
    source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    catalog = json.loads((root / 'dist/catalog.json').read_text())['packages']
    manifests = [json.loads(p.read_text()) for p in (root / 'drivers').glob('*/manifest.json')]
    sdk = json.loads((root / 'sdk/app/SOURCES.json').read_text())
    runtime = json.loads((root / 'apps/clock/runtime-requirements.json').read_text())
    time_policy = json.loads((root / 'apps/clock/time-policy.json').read_text())
    files = {'store/default.elf': (root / 'dist/clock/default.elf').read_bytes(),
             'store/board.json': encoded(board),
             'store/default.json': (root / 'apps/clock/manifest.json').read_bytes(),
             'source-profile.json': profile_path.read_bytes(),
             'board-baseline.json': (root / 'releases/board-baseline.json').read_bytes(),
             'INSTALL.md': (root / 'docs/CLOCK_INSTALL.md').read_bytes(),
             'CROWN_SLEEP.md': (root / 'docs/CROWN_SLEEP.md').read_bytes(),
             'PMU_BATTERY.md': (root / 'docs/PMU_BATTERY.md').read_bytes(),
             'runtime-requirements.json': encoded(runtime),
             'time-policy.json': encoded(time_policy)}
    for name in NOVA_NOTICES:
        files['licenses/nova/' + name] = (root / 'apps/clock/nova/fonts' / name).read_bytes()
    boot = {'board': 'board.json', 'default_app': 'default.elf', 'drivers': [],
            'app_capabilities': [{'manifest': 'default.json', 'grants': [
                {'capability': 'display.output', 'api': 1, 'instance_id': 5},
                {'capability': 'rtc.clock', 'api': 2, 'instance_id': 8},
                {'capability': 'board.battery', 'api': 1, 'instance_id': 4}]}]}
    selected = []
    for device in board['devices']:
        candidates = [m for m in manifests if any(
            h['compatible'] == device['compatible'] and h['config_type'] == device['config_type']
            and device['chip']['revision'] in h['revisions'] for h in m.get('hardware_compatibility', []))
            and not m.get('legacy_manual_only')]
        if len(candidates) != 1:
            raise ValueError('Ambiguous/missing clock driver')
        manifest = candidates[0]
        package = next(p for p in catalog if p['id'] == manifest['id'])
        data = (root / 'dist' / package['archive']).read_bytes()
        if sha(data) != package['sha256'] or package['version'] != manifest['version']:
            raise ValueError('Stale or corrupt driver package')
        with zipfile.ZipFile(root / 'dist' / package['archive']) as archive:
            elf = archive.read('driver.elf')
            if json.loads(archive.read('source-manifest.json')) != manifest:
                raise ValueError('Source manifest differs from packaged driver')
        prefix = 'store/' + DEVICES[device['instance_id']]
        files[prefix + '/driver.elf'] = elf
        files[prefix + '/manifest.json'] = encoded(manifest)
        files['packages/' + package['archive']] = data
        boot['drivers'].append({'manifest': DEVICES[device['instance_id']] + '/manifest.json',
                                'instance_id': device['instance_id']})
        selected.append({**package, 'instance_id': device['instance_id']})
    files['store/boot.json'] = encoded(boot)
    record = {'schema': 'riscrte.watch-clock-deployment', 'schema_version': 1,
              'app_id': 'twatch-clock', 'app_version': version, 'source_sha': source_sha,
              'profile': profile['revision'], 'physical_verification': 'pending',
              'runtime_sdk': sdk, 'runtime_requirements': runtime, 'drivers': selected,
              'time_policy': time_policy,
              'clock_policy': {'idle_sleep_ms': 60000,
                               'boot_final_hold_ms': 250, 'screen_scrub': False},
              'transformations': ['Select device instances1,2,4,5,8 and buses101,103',
                                  'Limit PMU setup to declared ALDO2/ALDO3 rails1/2',
                                  'Set selected display SPI bus103 to40MHz and rotation180'],
              'entries': [{'path': name, 'size_bytes': len(data), 'sha256': sha(data)}
                          for name, data in sorted(files.items())]}
    files['deployment-record.json'] = encoded(record)
    out = root / 'dist/clock-deployments' / profile['revision']
    out.mkdir(parents=True, exist_ok=True)
    # A versioned ZIP is authoritative. The staging tree is convenience only.
    for name, data in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    name = f"twatch-clock-{version}-{profile['revision']}.zip"
    archive_path = out.parent / name
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_STORED) as z:
        for path, data in sorted(files.items()):
            info = zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    return {'profile': profile['revision'], 'archive': name,
            'sha256': sha(archive_path.read_bytes()), 'source_sha': source_sha}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, help='Explicit profile stem, or all for eight separate bundles')
    args = parser.parse_args()
    paths = sorted((ROOT / 'hardware').glob('*.json'))
    if args.profile != 'all':
        paths = [p for p in paths if p.stem == args.profile]
    if not paths:
        raise SystemExit('Unknown profile; no implicit variant selected')
    catalog = {'schema': 1, 'deployments': [build(path) for path in paths]}
    (ROOT / 'dist/clock-deployments/catalog.json').write_bytes(encoded(catalog))
    print(f"Built {len(paths)} explicit clock bundles; no hardware access")


if __name__ == '__main__':
    main()

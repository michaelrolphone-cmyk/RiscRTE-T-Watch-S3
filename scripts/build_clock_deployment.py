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
NOVA_NOTICES = ('Orbitron-OFL.txt', 'Rajdhani-OFL.txt', 'ShareTechMono-OFL.txt', 'SOURCES.txt')
DEVICES = {1: 'gpio', 2: 'i2c', 4: 'pmu', 5: 'panel', 8: 'rtc'}
LAUNCHER_DEVICES = {**DEVICES, 3: 'i2ctouch', 6: 'touch'}
ALARM_DEVICES = {**LAUNCHER_DEVICES, 9:'haptic', 12:'speaker'}
WIFI_DEVICES = {**ALARM_DEVICES, 15:'wifi'}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def selected_board(profile, devices=DEVICES, alarms=False):
    board = copy.deepcopy(profile)
    board['devices'] = [d for d in board['devices'] if d['instance_id'] in devices]
    if {d['instance_id'] for d in board['devices']} != devices.keys():
        raise ValueError('Profile does not have the complete clock dependency closure')
    board['buses'] = [b for b in board['buses'] if b['instance_id'] in ((101, 102, 103) if 3 in devices else (101, 103))]
    pmu = next(d for d in board['devices'] if d['instance_id'] == 4)
    # Only LCD/backlight rails: do not energize radio/haptic to display a clock.
    pmu['config']['rails'] = [r for r in pmu['config']['rails'] if r['id'] in ((1,2,5) if alarms else (1,2))]
    if {r['id'] for r in pmu['config']['rails']} != ({1,2,5} if alarms else {1,2}):
        raise ValueError('Profile does not declare both required display rails')
    panel = next(d for d in board['devices'] if d['instance_id'] == 5)
    panel['config']['rotation'] = 2
    # Manufacturer's exact Watch-S3 ST7789 setup uses40MHz. Keep the source
    # eight-profile baseline and all unrelated buses unchanged.
    next(b for b in board['buses'] if b['instance_id'] == panel['config']['bus_instance_id'])['frequency_hz'] = 40000000
    return board


def build(profile_path, root=ROOT, launcher=False, alarms=False, points=False, wifi=False):
    if wifi and not points:raise ValueError("Wi-Fi preserves the complete Points baseline")
    if points and not alarms:raise ValueError("Points requires alarm service deployment")
    if alarms and not launcher:raise ValueError("Alarms requires launcher deployment")
    profile = json.loads(profile_path.read_text())
    devices = WIFI_DEVICES if wifi else ALARM_DEVICES if alarms else LAUNCHER_DEVICES if launcher else DEVICES
    flavor = 'wifi-launcher' if wifi else 'points-launcher' if points else 'alarm-launcher' if alarms else 'launcher' if launcher else 'clock'
    app_dir='dist/'+flavor
    board = selected_board(profile, devices, alarms)
    version = json.loads((root / 'apps/clock/manifest.json').read_text())['version']
    source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    catalog = json.loads((root / 'dist/catalog.json').read_text())['packages']
    manifests = [json.loads(p.read_text()) for p in (root / 'drivers').glob('*/manifest.json')]
    sdk = json.loads((root / 'sdk/app/SOURCES.json').read_text())
    runtime = json.loads((root / ('apps/wifi-runtime-requirements.json' if wifi else 'apps/alarm-runtime-requirements.json' if alarms else 'apps/clock/runtime-requirements.json')).read_text())
    time_policy = json.loads((root / 'apps/clock/time-policy.json').read_text())
    files = {'store/default.elf': (root / 'dist' / flavor / 'default.elf').read_bytes(),
             'store/board.json': encoded(board),
             'store/default.json': (root / (app_dir+'/default.json' if launcher else 'apps/clock/manifest.json')).read_bytes(),
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
    if launcher:
        for name in ('clock','springboard','battery','settings','calculator','stopwatch')+(('alarms','countdown') if alarms else ())+(('points_in_time',) if points else ())+(('wifi_settings',) if wifi else ()):
            files['store/'+name+'.elf']=(root/app_dir/(name+'.elf')).read_bytes()
            files['store/'+name+'.json']=(root/app_dir/(name+'.json')).read_bytes()
        for name in ('catalog.json','font-sources.json','time-sources.json','LICENSE-FontAwesome.txt','LICENSE-Orbitron.txt','LICENSE-Rajdhani.txt','RTC_PROVENANCE.json','settings_fonts/LICENSE-Orbitron.txt','settings_fonts/LICENSE-Rajdhani.txt','settings_fonts/SOURCES.json'):
            files['shared/'+name]=(root/app_dir/name).read_bytes()
        files['settings-time-policy.json']=encoded({'rtc_basis_offset_minutes':480,'display_zone':'America/Denver','write_policy':'inverse-roundtrip','gap':'reject','fold':'explicit-MDT-or-MST','touch_rotation':0})
        files['shared-app-build.json']=(root/app_dir/'build-record.json').read_bytes()
        for name in ('default','clock','springboard','battery','settings','calculator','stopwatch')+(('alarms','countdown') if alarms else ())+(('points_in_time',) if points else ())+(('wifi_settings',) if wifi else ()):
            grants=[{'capability':'display.output','api':1,'instance_id':5},
                    {'capability':'input.touch.raw','api':1,'instance_id':6}]
            grants.append({'capability':'rtc.clock','api':2,'instance_id':8}) if name in ('default','clock','springboard','settings','stopwatch','alarms','countdown','points_in_time','wifi_settings') else None
            grants.append({'capability':'board.battery','api':1,'instance_id':4})
            if name in ('default','clock','settings'):grants.append({'capability':'storage.key-value','api':1,'instance_id':1})
            if name in ('alarms','countdown'):grants.append({'capability':'storage.key-value','api':1,'instance_id':3})
            if points and name in ('default','clock','points_in_time'):grants.append({'capability':'storage.key-value','api':1,'instance_id':5})
            if points and name=='points_in_time':grants.append({'capability':'storage.key-value','api':1,'instance_id':1})
            if name=='stopwatch':grants.append({'capability':'storage.key-value','api':1,'instance_id':2})
            if name=='wifi_settings':
                grants.extend([{'capability':'storage.key-value','api':1,'instance_id':6},{'capability':'net.wifi','api':1,'instance_id':15}])
            if alarms:grants.append({'capability':'alarm.service','api':1,'instance_id':0})
            policy={'manifest':name+'.json','grants':grants}
            if name=='default':boot['app_capabilities'][0]=policy
            else:boot['app_capabilities'].append(policy)
        files['INSTALL.md']=(root/'docs/LAUNCHER_INSTALL.md').read_bytes()
        files['DEEP_SLEEP.md']=(root/'docs/DEEP_SLEEP.md').read_bytes()
    selected = []
    artifact_paths = {}
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
        path = artifact_paths.setdefault(manifest['id'], devices[device['instance_id']])
        prefix = 'store/' + path
        if prefix + '/driver.elf' in files:
            if files[prefix + '/driver.elf'] != elf or files[prefix + '/manifest.json'] != encoded(manifest):
                raise ValueError('Package instances disagree on artifact/manifest')
        files[prefix + '/driver.elf'] = elf
        files[prefix + '/manifest.json'] = encoded(manifest)
        files['packages/' + package['archive']] = data
        boot['drivers'].append({'manifest': path + '/manifest.json',
                                'instance_id': device['instance_id']})
        selected.append({**package, 'instance_id': device['instance_id']})
    if alarms:
        files['store/alarm-service/driver.elf']=(root/app_dir/'alarm-service.elf').read_bytes()
        files['store/alarm-service/manifest.json']=(root/app_dir/'alarm-service.json').read_bytes()
        boot['drivers'].append({'manifest':'alarm-service/manifest.json','key_value':[
            {'key':'alarm_cfg','namespace':3,'access':'read'},
            {'key':'timer_cfg','namespace':3,'access':'read'},
            {'key':'alarm_occ','namespace':4,'access':'read-write'},
            {'key':'timer_occ','namespace':4,'access':'read-write'},
            {'key':'alert_mode','namespace':1,'access':'read'}]+([{'key':'points_cfg','namespace':5,'access':'read'},{'key':'points_occ','namespace':4,'access':'read-write'}] if points else [])})
        files['ALARM_INTEGRATION.md']=(root/'docs/ALARM_INTEGRATION.md').read_bytes()
        files['shared/alarm-service-build.json']=(root/app_dir/'alarm-service-build.json').read_bytes()
        files['shared/alarm-sources.json']=(root/('apps/wifi-sources.json' if wifi else 'apps/points-sources.json' if points else 'apps/alarm-sources.json')).read_bytes()
        if wifi:files['WIFI_SETTINGS.md']=(root/'docs/WIFI_SETTINGS.md').read_bytes()
        if points:files['POINTS_IN_TIME.md']=(root/'docs/POINTS_IN_TIME.md').read_bytes()
    files['store/boot.json'] = encoded(boot)
    record = {'schema': 'riscrte.watch-'+flavor+'-deployment', 'schema_version': 1,
              'app_id': 'twatch-clock', 'app_version': version, 'source_sha': source_sha,
              'profile': profile['revision'], 'physical_verification': 'pending',
              'runtime_sdk': sdk, 'runtime_requirements': runtime, 'drivers': selected,
              'time_policy': time_policy,
              'clock_policy': {'idle_sleep_ms': 60000,
                               'boot_final_hold_ms': 250, 'screen_scrub': False},
              'transformations': ['Select explicit '+flavor+' device closure '+','.join(map(str,sorted(devices))),
                                  'Limit PMU setup to declared display/haptic rails1/2/5' if alarms else 'Limit PMU setup to declared ALDO2/ALDO3 rails1/2',
                                  'Set selected display SPI bus103 to40MHz and rotation180'],
              'entries': [{'path': name, 'size_bytes': len(data), 'sha256': sha(data)}
                          for name, data in sorted(files.items())]}
    files['deployment-record.json'] = encoded(record)
    out = root / ('dist/'+flavor+'-deployments') / profile['revision']
    out.mkdir(parents=True, exist_ok=True)
    # A versioned ZIP is authoritative. The staging tree is convenience only.
    for name, data in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    name = f"twatch-{flavor}-{version}-{profile['revision']}.zip"
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
    parser.add_argument('--wifi', action='store_true')
    parser.add_argument('--points', action='store_true')
    parser.add_argument('--alarms',action='store_true',help='Explicit nine-app alarm development deployment')
    parser.add_argument('--launcher',action='store_true',help='Separate touch launcher deployment; clock remains default')
    args = parser.parse_args()
    paths = sorted((ROOT / 'hardware').glob('*.json'))
    if args.profile != 'all':
        paths = [p for p in paths if p.stem == args.profile]
    if not paths:
        raise SystemExit('Unknown profile; no implicit variant selected')
    catalog = {'schema': 1, 'deployments': [build(path, launcher=args.launcher,alarms=args.alarms,points=args.points,wifi=args.wifi) for path in paths]}
    (ROOT / ('dist/'+('wifi-launcher' if args.wifi else 'points-launcher' if args.points else 'alarm-launcher' if args.alarms else 'launcher' if args.launcher else 'clock')+'-deployments/catalog.json')).write_bytes(encoded(catalog))
    print(f"Built {len(paths)} explicit clock bundles; no hardware access")


if __name__ == '__main__':
    main()

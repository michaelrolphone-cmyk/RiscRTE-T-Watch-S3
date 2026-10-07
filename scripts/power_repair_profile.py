#!/usr/bin/env python3
"""Explicit Watch 1.0.10 power-repair profile; earlier accepted lanes stay fixed."""
import copy
import io
import json
import re
import zipfile
from pathlib import Path

from current_apps_overlay import APPS, NEW_APPS, ROOT, encoded, metadata, require, sha
from rf_spectrum_profile import STORAGE

PROFILE = 'power-repair'
VERSION = '1.0.10'
RUNTIME_VERSION = '0.1.53'
PRIOR_SOURCE = '273b58d64ccc9a7dd66f0659271a942f244edcdf'
PRIOR_ARCHIVE = {'size_bytes': 10451352, 'sha256': 'fad1e9dcadd862b6f1c14753253010ae61f85fbe896dbeb1c20e87fb4fb28339'}
POWER_DRIVERS = {'pmu': '0.6.2', 'panel': '0.4.2', 'imu': '0.4.2'}


def prior_configuration(root=ROOT):
    return json.loads((Path(root) / 'apps/rf-spectrum-sources.json').read_text())


def runtime_requirements(root=ROOT, *, allow_pending=False):
    value = json.loads((Path(root) / 'apps/power-repair-runtime-requirements.json').read_text())
    require(value['firmware_version'] == RUNTIME_VERSION, 'Wrong power-repair Runtime version')
    require((allow_pending and value['source_sha'] is None) or
            re.fullmatch('[0-9a-f]{40}', value.get('source_sha') or '') is not None,
            'Power-repair Runtime source pin is pending')
    prior = json.loads((Path(root) / 'apps/rf-spectrum-runtime-requirements.json').read_text())
    for key in ('required_behavior', 'abi_changed', 'public_runtime_api_prefix_changed', 'rf_storage'):
        require(value[key] == prior[key], 'Power-repair changed RF Runtime contract: ' + key)
    require({k: v for k, v in value['deployment'].items() if k != 'migration'} ==
            {k: v for k, v in prior['deployment'].items() if k != 'migration'},
            'Power-repair changed accepted flash/NVS/app-data layout')
    return value


def validate_configuration(c, root=ROOT, *, allow_pending=False):
    prior = prior_configuration(root)
    require(c.get('features') == {'low_battery': True, 'rf_spectrum': True, 'power_repair': True}
            and c.get('product_version') == VERSION, 'Incomplete power-repair features/version')
    require(c.get('power_drivers') == POWER_DRIVERS, 'Wrong power-repair driver generations')
    require(c['rf_storage'] == STORAGE and set(c['app_versions']) == set(APPS), 'Power-repair RF inventory/storage changed')
    for name in APPS:
        require(re.fullmatch(r'\d+\.\d+\.\d+', c['app_versions'][name]) is not None and
                tuple(map(int, c['app_versions'][name].split('.'))) >
                tuple(map(int, prior['app_versions'][name].split('.'))), 'Rebuilt app version was not incremented: ' + name)
    for key in ('source_app_versions', 'service_version', 'sdr', 'hid', 'ble_sensors', 'ble_telemetry', 'telemetry_battery'):
        require(c[key] == prior[key], 'Power-repair changed complete RF source input: ' + key)
    for name in ('system-apps', 'utilities', 'productivity'):
        require(c['sources'][name] == prior['sources'][name], 'Power-repair changed app source: ' + name)
    native = runtime_requirements(root, allow_pending=allow_pending)
    require(c['sources']['runtime'] == {**prior['sources']['runtime'], 'commit': native['source_sha']},
            'Power-repair app/native Runtime pins disagree')


def prior_apps(raw, root=ROOT):
    from build_rf_watch_candidate import safe_archive
    require(metadata(raw) == PRIOR_ARCHIVE, 'Completed RF 1.0.8 input custody differs')
    members = safe_archive(raw)
    record = json.loads(members['current-apps-build.json'])
    require(record['watch_source'] == PRIOR_SOURCE and record['configuration'] == prior_configuration(root)
            and record['profile'] == 'watch-rf-spectrum-apps-v1' and len(record['apps']) == 22,
            'Wrong completed RF 1.0.8 source/profile')
    files = {n: members['files/' + n] for n in record['files']}
    require({n: metadata(b) for n, b in files.items()} == record['files'], 'Prior RF target bytes differ')
    return files, record


def baseline_inputs(path, root=ROOT):
    """Recover baseline authoring inputs from exact delivered RF evidence.

    This does not call that old archive a new build. Every target is recompiled.
    The original 15-app archive is not rewritten or assigned a different hash.
    """
    files, record = prior_apps(Path(path).read_bytes(), root)
    keep = set(APPS) - set(NEW_APPS)
    store = {n + ext: files[n + ext] for n in keep for ext in ('.elf', '.json')}
    store.update({'board.json': encoded(record['baseline_board']), 'boot.json': encoded(record['baseline_boot'])})
    # The existing builder performs this explicit historical API1-to-API2 step.
    # Restore only its input schema, without using any historical target bytes.
    audio = json.loads(store['audio_spectrum.json'])
    audio['requires'] = [q for q in audio['requires'] if q['capability'] != 'storage.app-data'
                         and not (q['capability'] == 'storage.key-value' and q['api'] == 1)]
    for q in audio['requires']:
        if q['capability'] == 'storage.key-value': q['api'] = 1
    store['audio_spectrum.json'] = encoded(audio)
    catalog = [v for v in record['catalog'] if v['file_name'] not in {n + '.elf' for n in NEW_APPS}]
    return {**{'store/' + n: b for n, b in store.items()}, 'shared/catalog.json': encoded(catalog),
            'power-baseline-sha256': record['baseline_sha256'].encode()}


def driver_custody(root=ROOT):
    root = Path(root)
    inputs = {}
    for folder in ('drivers/twatch_pmu', 'drivers/twatch_panel', 'drivers/twatch_imu', 'include', 'sdk/driver', 'vendor/SensorLib'):
        for p in sorted((root / folder).rglob('*')):
            if p.is_file(): inputs[p.relative_to(root).as_posix()] = sha(p.read_bytes())
    return {'versions': POWER_DRIVERS, 'source_sha256': inputs,
            'files': {folder + '/driver.elf': metadata((root / 'dist' / ('twatch-' + folder) / 'driver.elf').read_bytes())
                      for folder in POWER_DRIVERS}}


def verify_profile(files, record, root=ROOT):
    from current_apps_overlay import configure_boot
    from build_current_apps import definitions
    c = record['configuration'];validate_configuration(c, root)
    require(record['boot'] == configure_boot(record['baseline_boot'], PROFILE), 'Power-repair RF boot authority changed')
    require(record.get('runtime_requirements') == runtime_requirements(root) and record.get('rf_storage') == STORAGE,
            'Power-repair Runtime/storage proof differs')
    require(record.get('baseline_artifact') == PRIOR_ARCHIVE, 'Missing completed RF input custody')
    for row in record['boot']['app_capabilities']:
        manifest = json.loads(files[row['manifest']])
        granted = {(g['capability'], g['api']) for g in row['grants']}
        required = [(g['capability'], g['api']) for g in manifest['requires']]
        require(len(required) == len(set(required)) and set(required) == granted and len(required) <= 12,
                'Power-repair manifest/grant parity differs: ' + row['manifest'])
    for name in APPS:
        require(sorted(record['apps'][name]['defines']) == sorted(definitions(name, c['app_versions'][name], True, rf_spectrum=True)),
                'Power-repair lost RF compiler feature: ' + name)
    for filename in ('utilities:Apps/waterfall.c', 'utilities:Apps/rf_application.inc',
                     'system-apps:lib/NativeApps/src/SingleFloatDivisionCompat.c'):
        require(filename in record['apps']['waterfall']['target_dependencies'], 'RF target input missing: ' + filename)
    power = record['power_drivers']
    require(power['versions'] == POWER_DRIVERS, 'Wrong driver version evidence')
    require(power['source_sha256'] and all((Path(root) / n).is_file() and sha((Path(root) / n).read_bytes()) == h
            for n, h in power['source_sha256'].items()), 'Power-repair driver source changed')
    for folder, version in POWER_DRIVERS.items():
        manifest = json.loads(files[folder + '/manifest.json'])
        require(manifest == json.loads((Path(root) / 'drivers' / ('twatch_' + folder) / 'manifest.json').read_text())
                and manifest['version'] == version, 'Power driver manifest differs: ' + folder)
        require(power['files'][folder + '/driver.elf'] == metadata(files[folder + '/driver.elf']),
                'Power driver ELF custody differs: ' + folder)

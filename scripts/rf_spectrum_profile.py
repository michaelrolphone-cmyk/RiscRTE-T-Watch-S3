#!/usr/bin/env python3
"""Watch 1.0.8 RF app authority, isolated from accepted publication inputs."""
import copy
import json
import re
from pathlib import Path

from current_apps_overlay import APPS, ROOT, require

PROFILE = 'rf-spectrum'
VERSION = '1.0.8'
RUNTIME_SOURCE = '4a0891fc0ec10dcd100c6248768cabecaafec888'
SYSTEM_SOURCE = 'fcdb5b0a54a11a407bf68c6e35ac2548471cd9f1'
DRIVERS_SOURCE = '4088b6892c2e2654b0342f04a7d191068e4a8e2e'
STORAGE = {'key_value_api': 2, 'key_value_instance': 13,
           'app_data_api': 1, 'app_data_instance': 3,
           'required_bytes': 129004, 'quota_bytes': 131072,
           'shared_preferences_api': 1, 'shared_preferences_instance': 1}
PRIVATE_GRANTS = [
    {'capability': 'storage.key-value', 'api': 2, 'instance_id': 13},
    {'capability': 'storage.app-data', 'api': 1, 'instance_id': 3},
]


def accepted_configuration(root=ROOT):
    return json.loads((Path(root) / 'release/complete-1.0.7/acceptance.json').read_text())['configuration']


def runtime_requirements(root=ROOT):
    value = json.loads((Path(root) / 'apps/rf-spectrum-runtime-requirements.json').read_text())
    require(value['source_sha'] == RUNTIME_SOURCE and value['firmware_version'] == '0.1.41',
            'RF profile must retain accepted Runtime 0.1.41')
    require(value['rf_storage'] == STORAGE and value['public_runtime_api_prefix_changed'] is False
            and value['abi_changed'] is False, 'RF storage/runtime ABI differs')
    behavior = value['required_behavior']
    require(behavior['app_grant_capacity'] == behavior['app_requirement_capacity'] == 12
            and behavior['explicit_key_value_v2'] and behavior['explicit_app_data_namespaces']
            and behavior['persistent_namespace_ownership_preserved'], 'RF Runtime authority bounds differ')
    accepted = json.loads((Path(root) / 'apps/apex-runtime-requirements.json').read_text())['deployment']
    require({k: v for k, v in value['deployment'].items() if k != 'migration'} ==
            {k: v for k, v in accepted.items() if k != 'migration'}, 'RF native layout changed')
    return value


def validate_configuration(c, root=ROOT, *, allow_pending=False):
    accepted = accepted_configuration(root)
    require(c.get('features') == {'low_battery': True, 'rf_spectrum': True}
            and c.get('product_version') == VERSION, 'RF spectrum and low battery must be automatic')
    require(c.get('rf_storage') == STORAGE, 'RF private namespace/quota differs')
    require(set(c.get('app_versions', {})) == set(APPS), 'RF profile must retain all 22 applications')
    for name, old in accepted['app_versions'].items():
        version = c['app_versions'][name]
        require(isinstance(version, str) and re.fullmatch(r'\d+\.\d+\.\d+', version) is not None,
                'Invalid RF deployment version: ' + name)
        require(tuple(map(int, version.split('.'))) > tuple(map(int, old.split('.'))),
                'RF rebuilt app requires a new deployment version: ' + name)
    expected = {**accepted['source_app_versions'], 'waterfall': '0.2.0'}
    require(c.get('source_app_versions') == expected and c['app_versions']['waterfall'] == '0.2.0',
            'RF source versions differ from reviewed app inputs')
    for name in ('productivity', 'runtime'):
        require(c['sources'][name] == accepted['sources'][name], 'RF accepted source changed: ' + name)
    require(c['sources']['system-apps'] == {**accepted['sources']['system-apps'], 'commit': SYSTEM_SOURCE},
            'RF reviewed System QuickActions/launch-guard source differs')
    require(c['sources']['utilities']['repository'] == accepted['sources']['utilities']['repository'],
            'RF Utilities repository differs')
    pin = c['sources']['utilities']['commit']
    require((allow_pending and pin is None) or
            (isinstance(pin, str) and re.fullmatch('[0-9a-f]{40}', pin) is not None),
            'Final RF Utilities source pin is pending; pin the clean completed source before building')
    for key in ('sdr', 'hid', 'ble_sensors', 'ble_telemetry', 'telemetry_battery'):
        expected = {**accepted[key], 'commit': DRIVERS_SOURCE}
        if key == 'sdr':
            expected['version'] = '0.2.0'
        require(c.get(key) == expected, 'RF provider pin/version differs: ' + key)
    runtime_requirements(root)


def upgrade_boot(accepted_boot):
    """Add only unused RF namespaces, retaining accepted app/provider authority."""
    b = copy.deepcopy(accepted_boot)
    rows = b['app_capabilities']
    require(len(rows) == 22 and {r['manifest'] for r in rows} == {n + '.json' for n in APPS},
            'RF profile requires the complete 22-app boot policy')
    waterfall = next(r for r in rows if r['manifest'] == 'waterfall.json')
    require([g for g in waterfall['grants'] if g['capability'].startswith('storage.')] ==
            [{'capability': 'storage.key-value', 'api': 1, 'instance_id': 1}],
            'RF prior shared preferences authority differs')
    for row in rows:
        for grant in row['grants']:
            require(not any(grant['capability'] == added['capability'] and
                            grant['instance_id'] == added['instance_id'] for added in PRIVATE_GRANTS),
                    'RF private namespace already owned')
    require(not any(k['namespace'] == 13 for d in b['drivers'] for k in d.get('key_value', [])),
            'RF KV namespace already owned by a provider')
    waterfall['grants'].extend(copy.deepcopy(PRIVATE_GRANTS))
    require(len(waterfall['grants']) == 12 and all(len(r['grants']) <= 12 for r in rows),
            'RF profile exceeds existing Runtime grant bounds')
    # These are unused private namespaces. A shared-KV migration would confer
    # unrelated authority and the accepted HID record is stale for 1.0.8.
    b.pop('cohort_migration', None)
    return b


def validate_waterfall_manifest(manifest):
    require(manifest.get('version') == '0.2.0' and manifest.get('min_firmware_version') == '0.1.41',
            'RF source app/Runtime version differs')
    requirements = [(q['capability'], q['api']) for q in manifest['requires']]
    require(len(requirements) == 6 and set(requirements) == {
        ('display.output', '>=1'), ('input.touch.raw', '>=1'), ('radio.iq', '>=1'),
        ('storage.key-value', '>=2'), ('alarm.service', '>=1'), ('storage.app-data', '>=1')},
        'RF source capability requirements differ')
    require(manifest.get('optional') == [{'capability': 'board.battery', 'api': '>=1'},
                                         {'capability': 'input.navigation', 'api': '>=1'}],
            'RF source optional battery/navigation contract differs')


def verify_profile(files, record, root=ROOT):
    from current_apps_overlay import configure_boot
    from build_current_apps import definitions
    c = record['configuration']
    require(record['boot'] == configure_boot(record['baseline_boot'], PROFILE), 'RF boot proof differs')
    require(record.get('runtime_requirements') == runtime_requirements(root), 'RF Runtime proof differs')
    require(record.get('rf_storage') == STORAGE, 'RF storage proof differs')
    for row in record['boot']['app_capabilities']:
        manifest = json.loads(files[row['manifest']])
        granted = {(g['capability'], g['api']) for g in row['grants']}
        required = [(g['capability'], g['api']) for g in manifest['requires']]
        require(len(required) == len(set(required)) and set(required) == granted
                and len(required) <= 12, 'RF manifest/grant parity differs: ' + row['manifest'])
    for name in APPS:
        require(sorted(record['apps'][name]['defines']) ==
                sorted(definitions(name, c['app_versions'][name], True, rf_spectrum=True)),
                'RF compiler profile differs: ' + name)
    dependencies = record['apps']['waterfall']['target_dependencies']
    require('system-apps:lib/NativeApps/src/SingleFloatDivisionCompat.c' in dependencies,
            'RF float-division compatibility source missing')
    for filename in ('Apps/waterfall.c', 'Apps/rf_application.inc'):
        require('utilities:' + filename in dependencies, 'RF controller target input missing: ' + filename)

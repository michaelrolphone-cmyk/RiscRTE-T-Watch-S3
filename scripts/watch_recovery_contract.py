"""Fail-closed complete-store contract for the Watch 1.1.5 recovery successor."""
import json
from pathlib import PurePosixPath

PRESERVED_APPS = frozenset({'default', 'clock', 'lists', 'model_viewer'})

def version(value):
    parts = value.split('.')
    if len(parts) != 3 or any(not p.isdecimal() for p in parts):
        raise ValueError('Invalid semantic version')
    return tuple(map(int, parts))

def inspect_baseline(files):
    for name in files:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name or '\\' in name:
            raise ValueError('Unsafe store path')
    cohort = json.loads(files['cohort.json'])
    if (cohort['product'], cohort['version']) != ('twatch-s3', '1.1.5'):
        raise ValueError('Wrong delivered Watch product')
    boot = json.loads(files['boot.json'])
    policies = boot['app_capabilities']
    if len(policies) != 25 or len(boot['drivers']) != 30:
        raise ValueError('Complete 25-app/30-provider Watch required')
    if 'shared_settings' in boot.get('installation', {}):
        raise ValueError('Shared settings product opt-in is not qualified')
    apps = {}
    ids = set()
    for policy in policies:
        if 'image_source' in policy:
            raise ValueError('Delivered Watch has no SD-resident apps')
        manifest = json.loads(files[policy['manifest']])
        app_id = PurePosixPath(policy['manifest']).stem
        if app_id in apps or manifest['id'] in ids or policy['manifest'] != app_id + '.json':
            raise ValueError('Duplicate or mismatched application identity')
        if manifest['file_name'] != app_id + '.elf' or manifest['file_name'] not in files:
            raise ValueError('Missing or mismatched application ELF')
        ids.add(manifest['id'])
        apps[app_id] = manifest
    if not PRESERVED_APPS <= apps.keys():
        raise ValueError('Missing preserved Watch applications')
    return boot, apps

def validate_overlay(baseline, candidate):
    boot, apps = inspect_baseline(baseline)
    if baseline.keys() != candidate.keys():
        raise ValueError('Overlay added or removed store files')
    rebuilt = set(apps) - PRESERVED_APPS
    allowed = {name + suffix for name in rebuilt for suffix in ('.elf', '.json')}
    allowed |= {'ui-scene/driver.elf', 'ui-scene/manifest.json'}
    for name in baseline:
        if name not in allowed and candidate[name] != baseline[name]:
            raise ValueError('Changed preserved authority or content: ' + name)
    for name in [app + '.json' for app in rebuilt] + ['ui-scene/manifest.json']:
        old, new = json.loads(baseline[name]), json.loads(candidate[name])
        if version(new['version']) <= version(old['version']):
            raise ValueError('Rebuilt version did not advance: ' + name)
        old.pop('version'); new.pop('version')
        if old != new:
            raise ValueError('Changed existing application/provider contract: ' + name)
    return {'apps': len(apps), 'providers': len(boot['drivers']),
            'rebuilt_apps': sorted(rebuilt), 'preserved_apps': sorted(PRESERVED_APPS),
            'unchanged_authority_and_other_files': True}

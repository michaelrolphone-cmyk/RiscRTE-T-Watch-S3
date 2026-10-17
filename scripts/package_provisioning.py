#!/usr/bin/env python3
"""Exact additive provisioning composition over immutable T-Watch 1.1.43."""
import copy
import json
from pathlib import Path
import re
from package_alarm_sleep import encoded, record, require, sha, clean_source
import serial_files_product

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/provisioning-native'
CHANGED = ['boot.json', 'cohort.json', 'default.elf', 'default.json']
ADDED = ['installed-apps/driver.elf', 'installed-apps/manifest.json',
         'pkg-internal/driver.elf', 'pkg-internal/manifest.json']
ALARM_SHA = '189ce61b0e4a2b08cbd83ff90564a4c79a6c5e9a3d74b4ad4dcc2a61b4b51604'


def pins():
    p = json.loads((DOCS / 'source-pins.json').read_bytes())
    require(p['schema'] == 1 and p['product'] == 'twatch' and p['product_id'] == 'twatch-s3', 'Product identity differs')
    require(p['changed_store_files'] == CHANGED and p['added_store_files'] == ADDED, 'Change scope differs')
    require(p['baseline_version'] == '1.1.43', 'Exact delivered baseline required')
    require(sha((DOCS / 'released-baseline.json').read_bytes()) == p['baseline_contract_sha256'], 'Released baseline changed')
    for path, expected in p['historical_contracts'].items():
        require(sha((ROOT / path).read_bytes()) == expected, 'Historical contract changed: ' + path)
    for role in ('runtime', 'watch', 'system', 'utilities', 'sdk', 'drivers', 'image_helper'):
        require(re.fullmatch('[0-9a-f]{40}', p[role + '_revision']), 'Immutable pin required: ' + role)
    require(p['release_tag'] == 'test-provisioning-' + p['version'], 'Release identity differs')
    require(p['release_branch'] == 'release/provisioning-' + p['version'], 'Release branch differs')
    return p


def baseline_contract(p):
    c = json.loads((DOCS / 'released-baseline.json').read_bytes())
    require(c['version'] == p['baseline_version'] and c['product'] == p['product'], 'Baseline identity differs')
    return c


def check_baseline(before, contract):
    require({n: record(b) for n, b in sorted(before.items())} == contract['files'], 'Complete released store inventory differs')
    require(len(before) == 121 and sum(n.endswith('.elf') for n in before) == contract['elf_count'] == 59, 'Released inventory differs')
    require(sha(before['alarm-service/driver.elf']) == ALARM_SHA, 'Alarm fix changed')
    require(record(before['settings.elf']) == pins()['settings'], 'Retained Settings differs')
    require('installation' not in json.loads(before['boot.json']), 'Baseline installation authority differs')


def grant(capability, instance=0, api=1):
    return {'capability': capability, 'api': api, 'instance_id': instance}


def provision(boot, manifest):
    result = copy.deepcopy(boot)
    require('installation' not in result, 'Unexpected preexisting installation authority')
    require(len(result['drivers']) == 34 and len(result['app_capabilities']) == 26, 'Baseline graph changed')
    rows = [r for r in result['app_capabilities'] if r['manifest'] == 'default.json']
    require(len(rows) == 1, 'Exactly one Home policy required')
    required = {(r['capability'], r['api']) for r in manifest['requires']}
    optional = {(r['capability'], r['api']) for r in manifest.get('optional', [])}
    require(('software.installed-apps', 1) in required and ('storage.preferences', 1) in required, 'Selected provisioning Home required')
    require(('storage.volume', 1) in optional and ('storage.volume', 1) not in required, 'Removable volume must remain optional')
    require(not any(g['capability'] in ('storage.volume', 'software.installed-apps') for g in rows[0]['grants']), 'Unexpected baseline authority')
    # Namespace6 is the already-existing explicit Wi-Fi settings namespace.
    # Adding this Home reader is tested separately against preserving ownership.
    for g in (grant('software.installed-apps'), grant('storage.key-value', 6)):
        require(g not in rows[0]['grants'], 'Provisioning grant already exists')
        rows[0]['grants'].append(g)
    result['drivers'] += [
        {'manifest': 'installed-apps/manifest.json', 'app_data': [
            {'name': 'installed.apps', 'namespace': 2000, 'access': 'read-write'}]},
        {'manifest': 'pkg-internal/manifest.json'}]
    envelope = [grant(c, n, a) for c, a, n in (
        ('display.output', 1, 5), ('input.touch.raw', 1, 6),
        ('board.battery', 1, 4), ('alarm.service', 1, 0),
        ('runtime.realtime', 1, 0), ('storage.key-value', 1, 0),
        ('storage.app-data', 1, 0))]
    result['installation'] = {'volume_instance': 0, 'internal_volume_instance': 0,
        'namespace_range': {'first': 3000, 'count': 128}, 'grants': envelope,
        'provider_grants': [g for g in envelope if g['capability'] not in ('storage.key-value', 'storage.app-data')]}
    require(not any(r.get('image_source') for r in result['drivers'] + result['app_capabilities']), 'T-Watch must remain internal-only')
    return result


def providers(catalog, internal, p):
    receipt = json.loads((catalog / 'build.json').read_bytes())
    require(all(receipt.get(k) is True for k in ('boot_profiles', 'native_feed', 'internal_packages')), 'Selected provider feature missing')
    require(receipt['feed_product'] == p['product_id'] and receipt['feed_url'] == p['feed_url'] and receipt['time_server'] == p['time_server'], 'Provider feed/time inputs differ')
    files = {}
    for source, target in ((catalog, 'installed-apps'), (internal, 'pkg-internal')):
        for name in ('driver.elf', 'manifest.json'):
            raw = (source / name).read_bytes()
            expected = p['providers'][target + '/' + name]
            require(record(raw) == expected, 'Pinned provider artifact differs: ' + target + '/' + name)
            files[target + '/' + name] = raw
    manifest = json.loads(files['installed-apps/manifest.json'])
    require({'capability': 'platform.provision-request', 'api': 1} in manifest['requires'] and
            {'capability': 'platform.package-volume', 'api': 1} in manifest['requires'], 'Native request/package endpoint required')
    require(sha(files['installed-apps/driver.elf']) == receipt['elf_sha256'], 'Provider receipt differs')
    return files


def expected_cohort(before, p, revision, firmware):
    require(re.fullmatch('[0-9a-f]{40}', revision), 'Immutable product revision required')
    versions = {x for x in re.findall(rb'RISC_RUNTIME_VERSION:([^\x00]*)\x00', firmware) if x}
    require(len(versions) == 1, 'Unique native Runtime version required')
    return dict(json.loads(before['cohort.json']), version=p['version'], source_revision=revision,
                runtime_version=versions.pop().decode('ascii'), firmware_size=len(firmware), firmware_sha256=sha(firmware))


def compose(before, default, manifest, provider_files, p, revision, firmware):
    check_baseline(before, baseline_contract(p))
    require(set(provider_files) == set(ADDED), 'Complete provider addition required')
    after = dict(before, **provider_files)
    after.update({'default.elf': default, 'default.json': manifest,
        'boot.json': (json.dumps(provision(json.loads(before['boot.json']), json.loads(manifest)), sort_keys=True, separators=(',', ':')) + '\n').encode(),
        'cohort.json': encoded(expected_cohort(before, p, revision, firmware))})
    verify_store(before, after, default, manifest, provider_files, p, revision, firmware)
    return after


def verify_store(before, after, default, manifest, provider_files, p, revision, firmware):
    require(set(after) == set(before) | set(ADDED), 'Store inventory changed')
    require(sorted(n for n in before if before[n] != after[n]) == CHANGED, 'Unrelated retained payload changed')
    require(record(default) == {'bytes': p['default_bytes'], 'sha256': p['default_sha256']}, 'Canonical Home differs')
    require(sha(manifest) == p['default_manifest_sha256'], 'Canonical Home manifest differs')
    require(after['default.elf'] == default and after['default.json'] == manifest, 'Packaged Home differs')
    require(json.loads(manifest)['id'] == json.loads(before['default.json'])['id'] == 'twatch-clock', 'Home identity changed')
    require(json.loads(after['boot.json']) == provision(json.loads(before['boot.json']), json.loads(manifest)), 'Unrelated boot authority changed')
    require(json.loads(after['cohort.json']) == expected_cohort(before, p, revision, firmware), 'Cohort/native binding differs')
    for n in ADDED:
        require(after[n] == provider_files[n] and record(after[n]) == p['providers'][n], 'Provider differs: ' + n)
    require(after['settings.elf'] == before['settings.elf'] and record(after['settings.elf']) == p['settings'], 'Retained Settings changed')
    require(after['alarm-service/driver.elf'] == before['alarm-service/driver.elf'], 'Alarm fix changed')
    require(len(after) == 125 and sum(n.endswith('.elf') for n in after) == 61, 'Incomplete product store')
    successor = verify_previous_provisioning(after, p)
    return {'previous_provisioning': successor, 'changed_store_files': CHANGED, 'added_store_files': ADDED, 'store_files': len(after),
            'unchanged_store_payloads': len(before) - len(CHANGED), 'unchanged_elf_count': 58,
            'elf_count': 61, 'driver_instances': 36, 'settings': p['settings'], 'alarm_sha256': ALARM_SHA,
            'default': record(default), 'default_manifest': record(manifest)}


def verify_previous_provisioning(after, p):
    raw = (DOCS / 'previous-provisioning.json').read_bytes()
    require(sha(raw) == p['previous_provisioning_contract_sha256'], 'Previous provisioning contract changed')
    previous = json.loads(raw)
    require(previous['version'] == '1.1.44' and previous['source_revision'] == '08e683507fbf0a375c3a36a602ad6cc257cb457e', 'Previous product source differs')
    require(set(after) == set(previous['files']), 'Previous provisioning inventory differs')
    changed = sorted(n for n in after if record(after[n]) != previous['files'][n])
    require(changed == previous['expected_changes'] == ['cohort.json', 'default.elf'], 'Unrelated .44 provisioning payload changed')
    cohort = json.loads(after['cohort.json']); old = previous['cohort']
    native_fields = {'version', 'source_revision', 'firmware_size', 'firmware_sha256'}
    require({k:v for k,v in cohort.items() if k not in native_fields} == {k:v for k,v in old.items() if k not in native_fields}, 'Unrelated .44 cohort field changed')
    return dict(version=previous['version'], source_revision=previous['source_revision'],
                factory_sha256=previous['factory_sha256'], changed_store_files=changed,
                unchanged_store_payloads=len(after)-len(changed), unchanged_elf_count=60,
                boot_authority_unchanged=True, manifest_unchanged=True)

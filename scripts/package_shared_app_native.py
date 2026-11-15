#!/usr/bin/env python3
"""Published-only native/Home update; no app, provider, policy or SD migration."""
import json
from pathlib import Path
import re
import hashlib

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'docs/shared-app-native/baseline-1.1.46.json'
REPLACEMENTS = frozenset(('default.elf', 'default.json', 'cohort.json'))

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def record(data):
    return {'bytes': len(data), 'sha256': sha(data)}

def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()

def version(value):
    require(isinstance(value, str) and re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value), 'Invalid version')
    return tuple(map(int, value.split('.')))

def identity(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value), 'Exact source revision required')

def baseline_contract():
    result = json.loads(CONTRACT.read_bytes())
    require(result['schema'] == 1 and result['version'] == '1.1.46' and
            result['source_revision'] == 'ab9ff33975680c5bb8d9a2e7ed346d0300732a4e' and
            result['release_id'] == 415753487, 'Selected release identity differs')
    require(len(result['files']) == 125, 'Selected inventory incomplete')
    return result

def check_baseline(before, contract=None):
    contract = baseline_contract() if contract is None else contract
    require({n: record(b) for n, b in sorted(before.items())} == contract['files'], 'Exact released internal inventory required')
    boot = json.loads(before['boot.json'])
    require(len(boot['drivers']) == 36 and len(boot['app_capabilities']) == 26, 'Released authority graph differs')
    require(sum(n.endswith('.elf') for n in before) == 61, 'Released internal ELF count differs')
    return boot

def _pin(data, pin, label):
    require(isinstance(data, bytes) and isinstance(pin, dict) and
            type(pin.get('bytes')) is int and pin['bytes'] > 0 and
            isinstance(pin.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'Invalid ' + label + ' pin')
    require(record(data) == {k: pin[k] for k in ('bytes', 'sha256')}, label + ' digest differs')

def compose(before, home_elf, home_manifest, firmware,
            product_version, product_revision, expected_inputs):
    contract = baseline_contract()
    check_baseline(before, contract)
    require(version(product_version) > version(contract['version']), 'Fresh product version required')
    identity(product_revision)
    require(set(expected_inputs) == {'home', 'firmware'}, 'Exact qualified input categories required')
    home, native = expected_inputs['home'], expected_inputs['firmware']
    require(set(home) == {'elf', 'manifest', 'version'}, 'Exact Home pins required')
    require(set(native) == {'bytes', 'sha256', 'runtime_version', 'runtime_revision'}, 'Exact native pins required')
    identity(native['runtime_revision'])
    _pin(home_elf, home['elf'], 'Home ELF')
    _pin(home_manifest, home['manifest'], 'Home manifest')
    _pin(firmware, native, 'Native firmware')
    require(home_elf[:4] == b'\x7fELF', 'Home must be a target ELF; structural qualification remains caller-owned')
    require(0 < len(firmware) <= 0x260000, 'Native image exceeds retained partition')
    old_manifest, new_manifest = json.loads(before['default.json']), json.loads(home_manifest)
    require(new_manifest == dict(old_manifest, version=home['version']), 'Home authority or metadata changed beyond version')
    require(version(home['version']) > version(old_manifest['version']), 'Fresh Home version required')
    native_versions = {v for v in re.findall(rb'RISC_RUNTIME_VERSION:([^\x00]*)\x00', firmware) if v}
    require(native_versions == {native['runtime_version'].encode('ascii')}, 'Native embedded identity differs or is ambiguous')
    old_cohort = json.loads(before['cohort.json'])
    require(version(native['runtime_version']) > version(old_cohort['runtime_version']), 'Fresh Runtime version required')
    cohort = dict(old_cohort, version=product_version, source_revision=product_revision,
                  runtime_version=native['runtime_version'], firmware_size=len(firmware), firmware_sha256=sha(firmware))
    after = dict(before)
    after.update({'default.elf': home_elf, 'default.json': home_manifest, 'cohort.json': encoded(cohort)})
    changed = sorted(n for n in after if after[n] != before[n])
    require(set(after) == set(before) and set(changed) <= REPLACEMENTS, 'Unexpected store mutation')
    require(after['boot.json'] == before['boot.json'], 'Boot policy changed')
    receipt = {'schema': 1, 'product_version': product_version, 'product_revision': product_revision,
               'baseline_source': contract['source_revision'], 'qualified_inputs': expected_inputs,
               'changed_store_files': changed, 'retained_internal_files': len(before) - len(changed),
               'internal_files': len(before), 'internal_elfs': 61, 'providers': 36,
               'external_files': 0, 'feed_updated': False,
               'boot_authority_byte_identical': True, 'data_mapping_preserved': True,
               'publication_enabled': False, 'hardware_tested': False,
               'scope': 'Pure decoded-store composition; caller must qualify actual native ELF, paired bank image and native loader admission. No feed/catalog update or flash authorization.'}
    return after, receipt

#!/usr/bin/env python3
"""Package the bounded Watch 1.0.4 -> 1.0.5 native+bootfs update offline.

The accepted initial image is a custody input, never an upgrade payload. No
release, catalog, full image, Runtime source, or device is changed here.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

from build_wifi_common import zip_bytes
from current_bootfs import build as build_store
from current_cohort import create, encode, package, parse, verify as verify_identity
from check_runtime_store_admission import admit_cohort, validate_paths
from read_only_spiffs import read_image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '674729dbade10c15368731745844e6dc2f6ebd0b'
RUNTIME = '0a4f3d18c5d830d32678092fa99284810334b485'
VERSION = '1.0.5'
RUNTIME_VERSION = '0.1.34'
DIAGNOSTICS = 'a27bf228ecd99f2896638a30b55802560701180d'
CANDIDATE_VERSION = '0.1.37'
FULL_SHA = 'd4a1f41035e272adb0ec5d0c64b63835c771cc773a19805463cfe7ab2eb3c67e'
COHORT_SHA = 'a51c3c2bfc220740afd8a9ae1560e2ce8332e3dcc71736ce182c54f4b257aa83'
NATIVE_SHA = '00f5b15ef3701125557e3c5641edab3bcedd79bf53c47a2318c1899cc4257e38'
ELF_SHA = 'e82f53e12bfdfe00a4b371a1fc53403d0b12455ca8a6424eb9ff374645188bf7'
STORE_BYTES = 0x510000
STORE_OFFSETS = (0x2f0000, 0xae0000)
FIRMWARE_OFFSETS = (0x10000, 0x800000)
NEW_APPS = ('ble_touchpad', 'ble_buttons')
NEW_PROVIDERS = ('ble-hid', 'ble-sensors', 'battery-telem', 'ble-telemetry')
NEW_FILES = {n + suffix for n in NEW_APPS for suffix in ('.elf', '.json')} | {
    folder + '/' + name for folder in NEW_PROVIDERS for name in ('manifest.json', 'driver.elf')}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def metadata(data):
    return {'size_bytes': len(data), 'sha256': sha(data)}


def document(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def checked_source(root, expected=None):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    require(expected is None or head == expected, 'Wrong source revision: ' + str(root))
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                       cwd=root, text=True).strip(), 'Dirty source: ' + str(root))
    return head


def native_identity(runtime, candidate, installed=False):
    head = checked_source(runtime)
    version = candidate['firmware_version']
    require(candidate['source_sha'] == head, 'Native candidate source differs from clean checkout')
    if installed or version == RUNTIME_VERSION:
        require(head == RUNTIME and version == RUNTIME_VERSION, 'Wrong accepted installed Runtime identity')
    else:
        require(version == CANDIDATE_VERSION, 'Unsupported candidate Runtime version')
        for ancestor in (RUNTIME, DIAGNOSTICS):
            require(subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, head],
                                   cwd=runtime, capture_output=True).returncode == 0,
                    'Candidate Runtime lacks required ancestor: ' + ancestor)
    return head, version


def read_native(native_dir, runtime, *, installed=False):
    root = Path(native_dir)
    candidate = document((root / 'candidate.json').read_bytes())
    head, version = native_identity(runtime, candidate, installed)
    require(candidate['target'] == 'esp32s3-16mb-appdata-iq'
            and candidate['layout'] == 'riscrte-paired-appdata-v2'
            and candidate['store_abi'] == 2 and candidate['flash_bytes'] == 0x1000000,
            'Wrong native candidate target/layout')
    expected = {'firmware.bin', 'firmware.elf', 'bootloader.bin', 'partitions.bin',
                'appdata.bin', 'appdata-image.json', 'partitions-paired-appdata.csv',
                'platformio.ini', 'requirements-ci.txt', 'radio-iq-proof.json'}
    require(set(candidate['assets']) == expected, 'Native candidate asset inventory differs')
    require({p.name for p in root.iterdir()} <= expected | {'candidate.json', 'SHA256SUMS'},
            'Unrecorded native candidate member')
    for name, item in candidate['assets'].items():
        require(PurePosixPath(name).name == name and name not in ('', '.', '..'), 'Unsafe native member')
        data = (root / name).read_bytes()
        require(len(data) == item['bytes'] and sha(data) == item['sha256'], 'Native member differs: ' + name)
    if (root / 'SHA256SUMS').exists():
        checksums = ''.join(f'{sha(p.read_bytes())}  {p.name}\n'
                            for p in sorted(root.iterdir()) if p.name != 'SHA256SUMS')
        require((root / 'SHA256SUMS').read_text() == checksums, 'Native SHA256SUMS differs')
    firmware, elf = (root / 'firmware.bin').read_bytes(), (root / 'firmware.elf').read_bytes()
    if installed or version == RUNTIME_VERSION:
        require(sha(firmware) == NATIVE_SHA and sha(elf) == ELF_SHA, 'Native firmware/ELF differs from accepted 1.0.4')
    # Import selected Runtime helpers in a separate interpreter. Watch's scripts
    # have similarly named modules; they must not substitute candidate verifiers.
    validator = r"""
import json, sys
from pathlib import Path
source, root = map(Path, sys.argv[1:])
sys.path.insert(0, str(source / 'scripts'))
from paired_candidate import native_proof, partitions, APP_DATA_EXPECTED
from release_assets import esp_image, elf
from check_versions import firmware
from paired_bank_images import BOOTLOADER_SHA256
from radio_iq_proof import prove
from app_data_image import verify_initial
import hashlib
record = json.loads((root / 'candidate.json').read_text())
blobs = {n: (root / n).read_bytes() for n in ('firmware.bin', 'firmware.elf', 'bootloader.bin', 'partitions.bin')}
for name in ('firmware.bin', 'bootloader.bin'):
    esp_image(blobs[name])
    if blobs[name][3] >> 4 != 4: raise ValueError('Native image lacks 16 MiB flag')
elf(blobs['firmware.elf'])
actual = partitions(blobs['partitions.bin'], APP_DATA_EXPECTED)
if json.loads(json.dumps(actual)) != record['partitions']: raise ValueError('Native partition record differs')
if hashlib.sha256(blobs['bootloader.bin']).hexdigest() != BOOTLOADER_SHA256: raise ValueError('Unreviewed native bootloader')
version = firmware((source / 'platformio.ini').read_text())
if version != record['firmware_version']: raise ValueError('Native source version differs')
for marker in [('RTE_SOURCE=' + record['source_sha']).encode() + b'\0',
               ('RISC_RUNTIME_VERSION:' + version).encode() + b'\0', b'RISC_PAIRED_STORE_ABI:2\0']:
    if not all(marker in blobs[n] for n in ('firmware.bin', 'firmware.elf')): raise ValueError('Native compiled identity differs')
if record['target'].encode() + b'\0' not in blobs['firmware.bin']: raise ValueError('Native compiled target differs')
if len(blobs['firmware.bin']) > APP_DATA_EXPECTED['app0'][3] or b'RISC_PAIRED_STORE_ABI:1\0' in blobs['firmware.bin']:
    raise ValueError('Native paired ABI/bounds differ')
for name in ('platformio.ini', 'partitions-paired-appdata.csv', 'requirements-ci.txt'):
    if (root / name).read_bytes() != (source / name).read_bytes(): raise ValueError('Native source member differs: ' + name)
proof = native_proof(blobs['firmware.elf'])
proof['radio_iq'] = prove(blobs['firmware.elf'])
proof = json.loads(json.dumps(proof))
if proof != record['native_proof']: raise ValueError('Native post-link proof differs')
if proof['radio_iq'] != json.loads((root / 'radio-iq-proof.json').read_text()): raise ValueError('Native IQ proof file differs')
if verify_initial(root) != record['initial_appdata']: raise ValueError('Initial app-data custody differs')
print(json.dumps(proof, sort_keys=True))
"""
    subprocess.run([sys.executable, '-c', validator, str(Path(runtime).resolve()), str(root.resolve())],
                   check=True, stdout=subprocess.DEVNULL)
    return firmware, elf, candidate


TRANSACTION_SOURCES = ('src/ports/esp32s3/NativeBankStore.cpp', 'src/ports/esp32s3/NativeBankStore.h',
    'src/runtime/update/PairedBank.cpp', 'src/runtime/update/PairedBank.h',
    'src/runtime/update/Version.h', 'src/runtime/update/StoreAudit.cpp',
    'src/runtime/update/StoreAudit.h', 'src/runtime/update/Cohort.h', 'sdk/driver/RiscBankStoreV1.h')
GRAPH_SOURCES = ('src/bootstrap/Runtime.cpp', 'src/bootstrap/Runtime.h', 'src/bootstrap/CohortRuntime.inc',
    'src/runtime/update/CohortMigration.h', 'lib/elf_loader/src/esp_elf_validate.c')


def runtime_evidence(previous_runtime, runtime, previous_native, native):
    files = {}
    for name in TRANSACTION_SOURCES + GRAPH_SOURCES:
        old = sha((Path(previous_runtime) / name).read_bytes())
        new = sha((Path(runtime) / name).read_bytes())
        files[name] = {'installed_sha256': old, 'candidate_sha256': new, 'identical': old == new}
    return {'installed_source': previous_native['source_sha'], 'candidate_source': native['source_sha'],
            'installed_version': previous_native['firmware_version'], 'candidate_version': native['firmware_version'],
            'candidate_required_ancestors': [RUNTIME, DIAGNOSTICS] if native['firmware_version'] == CANDIDATE_VERSION else [RUNTIME],
            'compared_sources': files,
            'listed_transaction_sources_identical': all(files[p]['identical'] for p in TRANSACTION_SOURCES),
            'installed_graph_uses_installed_native_exports': True,
            'candidate_self_admission_uses_candidate_native_exports': True}


def read_previous(bundle, native_dir, runtime):
    """Bind every source representation to the accepted hosted bytes."""
    bundle = Path(bundle)
    firmware, elf, native = read_native(native_dir, runtime, installed=True)
    release = bundle / 'firmware-v1.0.4'
    full = (release / 'twatch-s3-launcher-1.0.4.bin').read_bytes()
    payload = (release / 'twatch-s3-cohort-1.0.4.bin').read_bytes()
    require(len(full) == 0x1000000 and sha(full) == FULL_SHA, 'Accepted 1.0.4 initial-image custody differs')
    require(sha(payload) == COHORT_SHA and payload[:len(firmware)] == firmware
            and len(payload) == len(firmware) + STORE_BYTES, 'Accepted 1.0.4 cohort custody differs')
    store = payload[len(firmware):]
    require(full[0x10000:0x10000 + len(firmware)] == firmware
            and full[0x2f0000:0x800000] == store and (bundle / 'bootfs.bin').read_bytes() == store,
            'Prior native/store representations differ')
    previous = read_image(store, STORE_BYTES)
    validate_paths(previous)
    extracted = {p.relative_to(bundle / 'store').as_posix(): p.read_bytes()
                 for p in (bundle / 'store').rglob('*') if p.is_file()}
    require(extracted == previous, 'Prior extracted store differs')
    identity = parse(previous['cohort.json'])
    verify_identity(identity, firmware, version='1.0.4', runtime_version=RUNTIME_VERSION, source_revision=SOURCE)
    record = document((release / 'release-record.json').read_bytes())
    require(record['source_sha'] == SOURCE and record['version'] == '1.0.4'
            and record['sha256'] == FULL_SHA and record['size'] == len(full), 'Prior release record differs')
    _, expected_ota = package(identity, firmware, store)
    require(record['ota'] == expected_ota, 'Prior release OTA record differs')
    bank = module('next_watch_bank_images', Path(runtime) / 'scripts/paired_bank_images.py')
    require(full[0xff2000:0xff4000] == bank.initial_bank_state(firmware, store, app_data=True),
            'Prior paired journal differs')
    return full, previous, identity, firmware, elf, native


def grants(rows):
    result = []
    for row in rows:
        require(set(row) == {'capability', 'api', 'instance_id'}
                and type(row['api']) is int and type(row['instance_id']) is int, 'Invalid grant')
        result.append((row['capability'], row['api'], row['instance_id']))
    require(len(result) == len(set(result)), 'Duplicate grant')
    return set(result)


def migration():
    return {'schema': 1, 'from': {'product': 'twatch-s3', 'version': '1.0.4', 'source_revision': SOURCE},
            'to': {'product': 'twatch-s3', 'version': VERSION},
            'shared_key_value': [{'application_id': n, 'api': 1, 'namespace': 1} for n in NEW_APPS]}


def manifest_authority(value):
    # Versions/UI descriptions may change; executable identity and all authority remain exact.
    return {key: item for key, item in value.items()
            if key not in ('version', 'description', 'display_name', 'status', 'physical_verification')}


def check_policy(previous, following):
    """Additional bounded Watch checks; real Runtime admission is still mandatory."""
    require(following['board.json'] == previous['board.json'], 'Hardware board declaration changed')
    before, after = document(previous['boot.json']), document(following['boot.json'])
    require(set(following) == set(previous) | NEW_FILES, 'Unexpected store inventory change')
    require(after.get('cohort_migration') == migration(), 'Wrong or expanded migration origin/authority')
    old_rows = {row['manifest']: row for row in before['app_capabilities']}
    new_rows = {row['manifest']: row for row in after['app_capabilities']}
    require(len(old_rows) == len(before['app_capabilities']) and len(new_rows) == len(after['app_capabilities']),
            'Duplicate application policy')
    require(set(new_rows) == set(old_rows) | {n + '.json' for n in NEW_APPS}, 'Unexpected application inventory')
    owners = {}
    for name, row in old_rows.items():
        original, current = document(previous[name]), document(following[name])
        if name == 'ble_scanner.json':
            old_grants, current_grants = grants(row['grants']), grants(new_rows[name]['grants'])
            require(current_grants == old_grants | {('bluetooth.sensors', 1, 0)}, 'BLE Scanner sensor grant differs')
            old_authority, current_authority = manifest_authority(original), manifest_authority(current)
            old_requires = {(r['capability'], r['api']) for r in old_authority.pop('requires')}
            current_requires = {(r['capability'], r['api']) for r in current_authority.pop('requires')}
            require(current_requires == old_requires | {('bluetooth.sensors', 1)} and old_authority == current_authority,
                    'BLE Scanner sensor manifest authority differs')
        else:
            require(new_rows[name] == row, 'Existing app grants changed: ' + name)
            require(manifest_authority(original) == manifest_authority(current), 'Existing app manifest authority changed: ' + name)
        owners[original['id']] = sorted(grants(new_rows[name]['grants']))
    prior_drivers = before['drivers']
    suffix = after['drivers'][len(prior_drivers):]
    require(after['drivers'][:len(prior_drivers)] == prior_drivers and len(suffix) == len(NEW_PROVIDERS)
            and [row['manifest'] for row in suffix] == [name + '/manifest.json' for name in NEW_PROVIDERS],
            'Existing provider bindings or new provider ordering changed')
    for row in prior_drivers:
        name = row['manifest']
        require(manifest_authority(document(previous[name])) == manifest_authority(document(following[name])),
                'Existing provider identity/authority changed: ' + name)
    stripped = copy.deepcopy(after)
    stripped['app_capabilities'] = [row for row in after['app_capabilities'] if row['manifest'] in old_rows]
    stripped['drivers'] = prior_drivers
    if 'ble_scanner.json' in old_rows:
        stripped['app_capabilities'] = [copy.deepcopy(old_rows[row['manifest']]) if row['manifest'] == 'ble_scanner.json' else row
                                        for row in stripped['app_capabilities']]
    stripped['cohort_migration'] = before['cohort_migration']
    require(stripped == before, 'Unexpected boot authority change')
    common = {('display.output', 1, 5), ('input.touch.raw', 1, 6), ('board.battery', 1, 4),
              ('bluetooth.hid', 1, 0), ('alarm.service', 1, 0), ('storage.key-value', 1, 1),
              ('rtc.clock', 2, 8), ('net.wifi', 1, 15), ('bluetooth.hci', 1, 16), ('motion.accel', 1, 7)}
    for name in NEW_APPS:
        row = new_rows[name + '.json']
        expected = common | ({('storage.key-value', 1, 11)} if name == 'ble_buttons' else set())
        require(grants(row['grants']) == expected, 'Extra or missing new app grant: ' + name)
        app = document(following[name + '.json'])
        require(app['id'] == name and app['file_name'] == name + '.elf', 'Wrong new app identity')
        require(len(app['requires']) == len({(r['capability'], r['api']) for r in app['requires']})
                and {(r['capability'], r['api']) for r in app['requires']} == {(c, a) for c, a, _ in expected},
                'New manifest requirements differ: ' + name)
    hid = next(row for row in suffix if row['manifest'] == 'ble-hid/manifest.json')
    require(set(hid) == {'manifest', 'key_value'} and hid['manifest'] == 'ble-hid/manifest.json',
            'HID must be a logical Global0 provider without a hardware instance')
    require(hid['key_value'] == [{'key': key, 'namespace': 10, 'access': 'read-write'}
                                 for key in ('hid_ours', 'hid_peer', 'hid_ccc', 'hid_identity')],
            'HID bound key authority differs')
    for row in before['app_capabilities']:
        require(all(g['instance_id'] not in (10, 11) for g in row['grants'] if g['capability'] == 'storage.key-value'),
                'New private namespace is already owned by an app')
    for row in before['drivers']:
        require(all(k['namespace'] not in (10, 11) for k in row.get('key_value', [])),
                'New private namespace is already owned by a provider')
    provider = document(following[hid['manifest']])
    require(provider['id'] == 'ble-hid' and provider['driver_abi'] == 2
            and provider['file_name'] == 'driver.elf' and 'hardware_compatibility' not in provider,
            'HID provider must not invent hardware')
    require(provider['requires'] == [{'capability': c, 'api': 1} for c in
                                    ('bluetooth.hci', 'platform.clock', 'storage.key-value.bound')]
            and provider['provides'] == [{'capability': 'bluetooth.hid', 'api': 1}], 'HID dependency authority differs')
    logical = {
        'ble-sensors/manifest.json': ([('bluetooth.hci', 1), ('platform.clock', 1)], [('bluetooth.sensors', 1)]),
        'battery-telem/manifest.json': ([('board.battery', 1)], [('sensor.telemetry', 1)]),
        'ble-telemetry/manifest.json': ([('bluetooth.hci', 1), ('platform.clock', 1), ('sensor.telemetry', 1)], [('bluetooth.telemetry', 1)]),
    }
    for row in suffix:
        if row['manifest'] == 'ble-hid/manifest.json':continue
        require(set(row) == {'manifest'}, 'New BLE sensor/telemetry providers must be logical Global0 providers')
        provider = document(following[row['manifest']]);expected_requires, expected_provides = logical[row['manifest']]
        expected_id = 'telemetry-battery' if row['manifest'] == 'battery-telem/manifest.json' else row['manifest'].split('/',1)[0]
        require(provider['id'] == expected_id and provider['driver_abi'] == 2 and provider['file_name'] == 'driver.elf' and 'hardware_compatibility' not in provider,
                'BLE sensor/telemetry provider must not invent hardware')
        require([(r['capability'], r['api']) for r in provider['requires']] == expected_requires
                and [(r['capability'], r['api']) for r in provider['provides']] == expected_provides,
                'BLE sensor/telemetry dependency authority differs: ' + row['manifest'])
    hci = [r for r in after['drivers'] if any(p['capability'] == 'bluetooth.hci'
           for p in document(following[r['manifest']])['provides'])]
    require(len(hci) == 1 and hci[0].get('instance_id') == 16, 'BLE providers require unique existing HCI provider')
    return {'prior_app_owners': owners, 'prior_provider_bindings': prior_drivers,
            'new_shared_migration': migration(), 'hardware_board_sha256': sha(previous['board.json'])}


def check_requirements(requirements, native):
    require(isinstance(requirements, dict) and requirements.get('schema') == 1,
            'Runtime requirements descriptor missing or invalid')
    require(requirements.get('repository') == 'https://github.com/michaelrolphone-cmyk/RiscRTE'
            and requirements.get('source_sha') == native['source_sha']
            and requirements.get('firmware_version') == native['firmware_version'],
            'Runtime requirements source/version differs from exact candidate')
    deployment = requirements.get('deployment', {})
    for key in ('target', 'layout', 'flash_bytes', 'store_abi'):
        require(deployment.get(key) == native[key], 'Runtime requirements deployment differs: ' + key)
    expected = {name: {'offset': row[2], 'size': row[3]}
                for name, row in native['partitions'].items() if name != 'nvs'}
    require(deployment.get('partitions') == expected, 'Runtime requirements partition geometry differs')
    require(deployment.get('ordinary_ota_includes_appdata') is False
            and deployment.get('existing_8MiB_ota_compatible') is False
            and deployment.get('radio_iq') is True, 'Runtime requirements OTA/data/IQ policy differs')
    behavior = requirements.get('required_behavior', {})
    require(behavior.get('store_abi') == 2, 'Runtime requirements behavior ABI differs')
    for key in ('paired_cohort_updates', 'cohort_graph_elf_admission',
                'persistent_namespace_ownership_preserved', 'exact_app_authority_preservation',
                'explicit_shared_preferences_migration', 'paired_firmware_store', 'immutable_active_bank',
                'rollback_until_health_confirmation', 'default_app_health_confirmation',
                'explicit_app_data_namespaces', 'provider_bound_key_value', 'namespaced_key_value'):
        require(behavior.get(key) is True, 'Runtime requirements safety behavior differs: ' + key)
    return requirements


def prepare(previous_bundle, apps_dir, runtime, native_dir, output, source_root=ROOT, *,
            previous_runtime, previous_native_dir):
    source_root, output = Path(source_root).resolve(), Path(output)
    require(not output.exists(), 'Output must be new')
    head = checked_source(source_root)
    c = document((source_root / 'apps/current-cohort.json').read_bytes())
    require(c == {'schema': 1, 'product': 'twatch-s3', 'version': VERSION}, 'Final 1.0.5 config is not ready')
    overlay = module('next_watch_overlay', source_root / 'scripts/current_apps_overlay.py')
    configuration = overlay.config(source_root)
    firmware, elf, native = read_native(native_dir, runtime)
    require(configuration['sources']['runtime']['commit'] == native['source_sha'],
            'Watch configuration differs from exact candidate Runtime source')
    requirements_bytes = (source_root / 'apps/apex-runtime-requirements.json').read_bytes()
    requirements = check_requirements(document(requirements_bytes), native)
    files, apps = overlay.verify(Path(apps_dir), head, source_root)
    full, previous, old_identity, old_firmware, old_elf, old_native = read_previous(
        previous_bundle, previous_native_dir, previous_runtime)
    following = {**previous, **files, 'boot.json': encoded(apps['boot'])}
    identity = create(VERSION, native['firmware_version'], head, firmware)
    following['cohort.json'] = encode(identity)
    policy = check_policy(previous, following)
    admission = admit_cohort(previous_runtime, old_elf, previous, following)
    self_admission = admit_cohort(runtime, elf, following, following)
    store, packing = build_store(following)
    payload, ota = package(identity, firmware, store)
    proof = {'schema': 1, 'watch_source': head, 'configuration': configuration,
             'source_cohort': old_identity, 'target_cohort': identity,
             'source_initial_image_sha256': sha(full), 'source_cohort_sha256': COHORT_SHA,
             'native_candidate_sha256': sha((Path(native_dir) / 'candidate.json').read_bytes()),
             'native_elf_sha256': sha(elf),
             'runtime_evidence': runtime_evidence(previous_runtime, runtime, old_native, native),
             'runtime_requirements': requirements, 'runtime_requirements_sha256': sha(requirements_bytes),
             'previous_native_sha256': sha(old_firmware), 'previous_native_elf_sha256': sha(old_elf), 'ota': ota, 'policy': policy, 'packing': packing,
             'installed_runtime_admission': admission, 'target_self_admission': self_admission,
             'files': {name: metadata(data) for name, data in sorted(following.items())},
             'payload_members': ['native', 'bootfs'], 'initial_image_is_destructive': True,
             'initial_image_emitted': False, 'publication_performed': False, 'hardware_qualified': False}
    output.mkdir(parents=True)
    for name, data in following.items():
        path = output / 'store' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (output / ota['asset']).write_bytes(payload)
    (output / 'bootfs.bin').write_bytes(store)
    licenses = Path(apps_dir) / 'licenses'
    (output / 'LICENSES.zip').write_bytes(zip_bytes({p.relative_to(licenses).as_posix(): p.read_bytes()
                                                  for p in licenses.rglob('*') if p.is_file()}))
    (output / 'runtime-requirements.json').write_bytes(requirements_bytes)
    (output / 'next-watch-build-proof.json').write_bytes(encoded(proof))
    (output / 'INSTALL.txt').write_text(
        'Watch 1.0.5 offline candidate for the accepted Watch 1.0.4.\n'
        'One ordinary paired-cohort update carries native + bootfs only. Run the upgrade proof first.\n'
        'Installed Runtime 0.1.34 must admit this exact cohort before activation. NVS and app-data are excluded.\n'
        'No native bridge is required. Prior pair remains available for rollback until health confirmation.\n'
        'Full initial images are destructive provisioning images and must never be used for this upgrade.\n'
        'Do not flash this OTA payload at offset zero or write an empty app-data image.\n'
        'This command does not publish assets/catalogs, install a device, or qualify physical hardware.\n')
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('previous-bundle', 'apps-dir', 'runtime', 'native-dir', 'previous-runtime', 'previous-native-dir', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = prepare(args.previous_bundle, args.apps_dir, args.runtime, args.native_dir, args.output, args.source_root,
                     previous_runtime=args.previous_runtime, previous_native_dir=args.previous_native_dir)
    print(json.dumps(result['ota'], sort_keys=True))


if __name__ == '__main__':
    main()

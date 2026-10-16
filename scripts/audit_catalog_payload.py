#!/usr/bin/env python3
"""Audit the delivered T-Watch 1.1.43 inventory and serial payload admission."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'docs/catalog-payload/admission-1.1.43/baseline.json'
FACTORY = 'TWatch-1.1.43-Shared-Default-factory-erases-data-0x0.bin'
EVIDENCE = 'TWatch-1.1.43-Shared-Default-Evidence.zip'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def record(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def exact(data, expected, label):
    require(record(data) == expected, 'Exact bytes differ: ' + label)
    return data


def git_sources(contract, roots):
    result = {}
    for row in contract['source_evidence']:
        raw = subprocess.check_output(['git', '-C', str(roots[row['repository']]),
                                       'show', row['revision'] + ':' + row['path']])
        exact(raw, {k: row[k] for k in ('bytes', 'sha256')}, row['path'])
        result[row['repository'], row['path']] = raw
    return result


def module(source, name):
    namespace = {'__name__': name}
    exec(compile(source, name, 'exec'), namespace)
    return namespace


def classify(files, contract):
    require({n: record(b) for n, b in sorted(files.items())} == contract['store_files'],
            'Complete delivered store inventory differs')
    boot = json.loads(files['boot.json'])
    require(boot['default_app'] == 'default.elf', 'Default boot target differs')
    require('installation' not in boot, 'Unexpected installation authority')
    policies, drivers = boot['app_capabilities'], boot['drivers']
    require(len(policies) == 26 and len(drivers) == 34, 'Boot composition differs')
    require(not any('image_source' in r for r in policies + drivers),
            'Unaccounted external executable consumer')
    require(not any(g['capability'] in ('storage.files', 'storage.volume')
                    for r in policies for g in r.get('grants', [])),
            'Unexpected application file-volume mapping')
    manifests, executable = {}, set()
    for name, raw in files.items():
        if not name.endswith('.json'):
            continue
        obj = json.loads(raw)
        if obj.get('type') not in ('application', 'driver'):
            continue
        leaf = obj['file_name']
        require(PurePosixPath(leaf).name == leaf and '\\' not in leaf,
                'Unexpected manifest executable path')
        path = str(PurePosixPath(name).parent / leaf)
        require(path in files and path.endswith('.elf'), 'Missing internal executable: ' + path)
        executable.add(path)
        manifests[name] = {'type': obj['type'], 'executable': path}
    require(executable == {n for n in files if n.endswith('.elf')},
            'Orphan or unaccounted executable')
    require(len(executable) == 59 and len(manifests) == 59, 'Manifest/executable inventory differs')
    require({r['manifest'] for r in policies} ==
            {n for n, r in manifests.items() if r['type'] == 'application'},
            'Application-policy coverage differs')
    require({r['manifest'] for r in drivers} ==
            {n for n, r in manifests.items() if r['type'] == 'driver'},
            'Driver-policy coverage differs')
    appdata = [{'manifest': r['manifest'], 'grants': [g for g in r.get('grants', [])
                if g['capability'].startswith('storage.')]} for r in policies]
    return {'file_count': len(files), 'bytes': sum(len(b) for b in files.values()),
            'elf_count': len(executable), 'json_count': len(files) - len(executable),
            'application_count': 26, 'driver_manifest_count': 33, 'driver_instance_count': 34,
            'external_executable_sources': [], 'missing_internal_executables': [],
            'manifest_consumers': manifests, 'application_storage_grants': appdata,
            'ownership': 'firmware-owned paired boot store; no serial write destination'}


def partitions(factory, contract):
    result = []
    for expected in contract['partitions']:
        raw = factory[expected['offset']:expected['offset'] + expected['bytes']]
        exact(raw, {'bytes': expected['bytes'], 'sha256': expected['sha256']}, expected['name'])
        require((raw == b'\xff' * len(raw)) == expected['erased'], 'Erased partition claim differs')
        result.append(expected)
    return result


def zip_contents(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        require(len(z.namelist()) == len(set(z.namelist())), 'Duplicate evidence member')
        return {n: z.read(n) for n in z.namelist()}


def verify_native(assets, proof, source, contract):
    files = zip_contents(assets[EVIDENCE])
    require(files['qualification.json'] == assets['qualification.json'], 'Detached qualification differs')
    for artifact, member in [('firmware.bin', 'build/riscrte_native.bin'),
                             ('bootloader.bin', 'build/bootloader/bootloader.bin'),
                             ('partitions.bin', 'build/partition_table/partition-table.bin'),
                             ('default.elf', 'default.elf'), ('default.json', 'default.json'),
                             ('source-lock.json', 'build-evidence/source-lock.json')]:
        require(files[member] == assets[artifact], 'Evidence/public member differs: ' + member)
    lock = json.loads(assets['source-lock.json'])
    for name, row in lock['native_files'].items():
        member = 'build/' + row['path']
        exact(files[member], {k: row[k] for k in ('bytes', 'sha256')}, member)
    native = files['build/riscrte_native.elf']
    for fragment in (b'NativeSerialStorage', b'NativeSerialFiles', b'ReopenedFiles'):
        require(fragment in native, 'Serial implementation absent from native ELF')
    require(b'/appdata/.serial-files\0' in assets['firmware.bin'], 'Private serial root absent')
    for (repo, name), raw in source.items():
        if repo == 'runtime' and name.startswith('src/') and name.endswith('.cpp'):
            require(proof['native']['source_files'].get('runtime/' + name) == record(raw)['sha256'],
                    'Pinned Runtime source not bound to native receipt: ' + name)
    profile = source['product', 'profiles/native-idf61.cmake'].decode()
    serial = module(source['product', 'scripts/serial_files_product.py'], 'pinned_serial_product')
    require(serial['check_profile'](profile, 'twatch') == contract['serial_contract'],
            'Unexpected native serial admission')
    commands = json.loads(files['build/compile_commands.json'])
    selected = [r for r in commands if r['file'].endswith('/src/ports/esp32s3/NativeSerialStorage.cpp')]
    require(len(selected) == 1, 'Native serial compilation is missing or ambiguous')
    command = selected[0].get('command', ' '.join(selected[0].get('arguments', [])))
    for flag in contract['serial_contract']['flags']:
        require('-D' + flag + '=1' in command, 'Serial selection missing from actual compilation')
    require('-DRISC_NATIVE_SERIAL_SD=1' not in command and
            '-DRISC_NATIVE_SERIAL_BOOT_FILES=1' not in command, 'Unexpected serial destination compiled')
    for name in ('admission', 'admission_sanitized'):
        row = proof[name]
        require(row['cohort_validated'] is True and row['prepared'] is True and
                row['elf_count'] == 59 and row['error'] == '' and
                row['native_elf_sha256'] == record(native)['sha256'] and
                row['native_composition']['runtime_commit'] == contract['runtime_revision'],
                'Published full-cohort admission does not bind this firmware')
    require(proof['admission']['sanitized'] is False and proof['admission_sanitized']['sanitized'] is True,
            'Normal/sanitized evidence roles differ')
    require(proof['hardware_tested'] is False and proof['device_accessed'] is False,
            'Unexpected hardware evidence claim')
    return {'status': 'published-receipts-identity-verified-not-rerun',
            'normal_and_sanitized_elf_count': 59, 'hardware_tested': False,
            'native_elf': record(native), 'source_files_checked': sum(
                repo == 'runtime' and name.startswith('src/') and name.endswith('.cpp') for repo, name in source),
            'native_artifacts_checked': len(lock['native_files'])}


def verify_schema(schema):
    payload = schema['properties']['payload']['properties']
    require(payload['volumes']['minItems'] == 1 and payload['files']['minItems'] == 1 and
            payload['totals']['properties']['file_count']['minimum'] == 1,
            'Frozen nonempty-payload contract changed')


def require_paired_candidate(report):
    require(report['associated_serial_payload']['files'] and report['paired_candidate_available'],
            'No supported nonempty firmware-associated serial payload/consumer mapping for this release')


def audit(contract, assets, source):
    require(set(assets) == set(contract['assets']), 'Complete public asset inventory differs')
    for name, expected in contract['assets'].items():
        exact(assets[name], expected, name)
    require(contract['candidate_version'] is None and contract['publication_enabled'] is False,
            'Audit cannot reserve or publish a candidate')
    release, pins, proof = (json.loads(assets[n]) for n in
                            ('release.json', 'source-pins.json', 'qualification.json'))
    require(release['source_revision'] == contract['source_revision'] and
            release['version'] == contract['version'] and release['release_tag'] == contract['release_tag'],
            'Release identity differs')
    require(pins['runtime_revision'] == contract['runtime_revision'] and
            pins['serial_files'] == contract['serial_contract'] == proof['serial_files'],
            'Runtime/admission lineage differs')
    require(source['product', 'docs/shared-default/source-pins.json'] == assets['source-pins.json'],
            'Published pins differ from product source')
    for name, expected in release['artifacts'].items():
        exact(assets[name], expected, 'release artifact ' + name)
    rows = [line.split('  ', 1) for line in assets['SHA256SUMS'].decode().splitlines()]
    require(len(rows) == len({name for _, name in rows}) and
            {name for _, name in rows} == set(assets) - {'SHA256SUMS'}, 'Checksum inventory differs')
    for digest, name in rows:
        require(record(assets[name])['sha256'] == digest, 'Published checksum differs: ' + name)
    for archive, expected in contract['archive_members'].items():
        members = zip_contents(assets[archive])
        require({n: record(b) for n, b in members.items()} == expected,
                'Complete archive member inventory differs: ' + archive)
    ci = zip_contents(assets['ci-provenance.zip'])
    run = json.loads(ci['ci-run.json'])
    require(run['GITHUB_SHA'] == contract['source_revision'] and
            int(run['GITHUB_RUN_ID']) == release['ci']['run_id'] and
            ci['workflow.yml'] == source['product', '.github/workflows/shared-default-native.yml'],
            'Published CI/source provenance differs')
    lock = json.loads(assets['source-lock.json'])
    require(release['source_lock'] == proof['input_lock'] == lock and
            proof['source_revision'] == contract['source_revision'], 'Native source-lock lineage differs')
    factory = assets[FACTORY]
    require(factory[0x2f0000:0x840000] == assets['store.bin'], 'Factory/store pairing differs')
    for offset, name in [(0, 'bootloader.bin'), (0x8000, 'partitions.bin'), (0x10000, 'firmware.bin')]:
        require(factory[offset:offset + len(assets[name])] == assets[name], 'Factory component differs: ' + name)
    part = partitions(factory, contract)
    image = module(source['product', 'scripts/watch_factory_appdata.py'], 'pinned_appdata')
    image['verify'](factory)
    decoder = module(source['product', 'scripts/read_only_spiffs.py'], 'pinned_spiffs')
    files = decoder['read_image'](assets['store.bin'], 0x550000)
    inventory = classify(files, contract)
    require(files['default.elf'] == assets['default.elf'] and files['default.json'] == assets['default.json'],
            'Default extraction differs')
    baseline = proof['baseline_contract']['files']
    unchanged = set(files) - set(release['changed_store_files'])
    require(len(unchanged) == 117 and all(record(files[n]) == baseline[n] for n in unchanged),
            'Unrelated store preservation differs')
    inherited = verify_native(assets, proof, source, contract)
    verify_schema(json.loads(source['schema', 'docs/catalog-payload/1.0.0/manifest.schema.json']))
    return {'schema': 1, 'audit_status': 'passed', 'product': 'twatch',
            'release_tag': contract['release_tag'], 'upstream_release_id': contract['upstream_release_id'],
            'catalog': contract['catalog'], 'source_revision': contract['source_revision'],
            'runtime_revision': contract['runtime_revision'], 'public_assets': contract['assets'], 'asset_roles': contract['asset_roles'],
            'archive_members': contract['archive_members'],
            'firmware_store': inventory, 'factory_partitions': part,
            'factory_appdata': {'contents': 'empty', 'bytes': 0x80000,
                'sha256': contract['appdata_initial']['sha256'],
                'proof': 'matches pinned empty-image hash; generator/remount reproduction is recorded separately'},
            'associated_serial_payload': {'files': [], 'required_file_count': 0,
                'status': 'no existing companion consumer or writable firmware-store mapping'},
            'serial_admission': contract['serial_contract'],
            'paired_candidate_available': False, 'paired_manifest_generated': False,
            'candidate_version_reserved': False, 'product_release_published': False,
            'blockers': ['No admitted serial destination reaches the actual firmware-associated boot-store files',
                'No existing companion payload or application consumer of the private serial workspace',
                'Frozen payload 1.0.0 requires nonempty files and volumes; an empty manifest is invalid'],
            'missing_builder_inputs': ['trusted supported installer method ID',
                'accepted hardware revision bounds', 'trusted namespace capability/budget profile',
                'immutable manifest/container catalog association after a usable product mapping exists'],
            'flash': {'supported_asset': FACTORY, 'offset': 0, 'bytes': 16777216,
                'saved_settings_and_internal_data': 'erased', 'preserving_update_kit': False,
                'current_usable_order': 'factory image already includes required internal store',
                'separate_payload_order': 'unavailable without a usable payload/consumer mapping',
                'future_factory_pair_order': 'firmware, then payload, then full readback and consumer verification'},
            'preservation': {'unrelated_store_files_identical_to_release_baseline': 117,
                'serial_mutation_scope': 'selected individual files and necessary parents only',
                'replacement': 'explicit destructive non-atomic per-file replacement'},
            'inherited_qualification': inherited, 'source_evidence': contract['source_evidence'],
            'hardware_tested': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--product', type=Path, default=ROOT)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-paired', action='store_true')
    args = parser.parse_args()
    contract = json.loads(BASELINE.read_text())
    if args.download:
        args.assets.mkdir(parents=True, exist_ok=True)
        for name, expected in contract['assets'].items():
            dest = args.assets / name
            if not dest.exists():
                raw = urllib.request.urlopen(contract['asset_urls'][name], timeout=90).read()
                exact(raw, expected, name)
                with dest.open('xb') as stream:
                    stream.write(raw)
    assets = {p.name: p.read_bytes() for p in args.assets.iterdir() if p.is_file()}
    source = git_sources(contract, {'product': args.product, 'runtime': args.runtime, 'schema': args.runtime})
    report = audit(contract, assets, source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded(report))
    if args.require_paired:
        require_paired_candidate(report)
    print('PASS: 16 public assets; 121 internal files; paired candidate unavailable without real admission')


if __name__ == '__main__':
    main()

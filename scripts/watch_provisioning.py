#!/usr/bin/env python3
"""Freeze and verify initial provisioning for the accepted Watch 1.0.7 payload.

The complete accepted Watch 1.0.7 store is unchanged. Its exact native image
is paired with a generic seed. This is not Watch 1.0.8,
an OTA update, a release publisher, or a device installer. No private inputs.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from current_cohort import create, encode, parse, verify
from read_only_spiffs import read_image
from watch_release_index import require

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'michaelrolphone-cmyk/RiscRTE-T-Watch-S3'
VERSION = '1.0.7'
RUNTIME_SOURCE = '4a0891fc0ec10dcd100c6248768cabecaafec888'
STORE_SHA = 'd7df281cd6bb35f833d7b1bfff25199d0d8d2d890e2c5cf3bb7585007a6f7572'
STORE_BYTES = 2273021
LICENSES_SHA = '80c78794f8ea969cc831ca6e774dfa497b484ad3937e3a49d6778d540177aebc'
LICENSES_BYTES = 87073
FIRMWARE_SHA = '776748a2331f6f6c5de0fc769bd13c8731c503a026217a767a18e86bac37dc3b'
FIRMWARE_BYTES = 1238288
NATIVE_ELF_SHA = '426b85cdfd68b21a8acbbf20c489bed67b2b7f2b234549fb9944f4ff2518085f'
CANDIDATE_SHA = '2d9dc26eecc81eb74b9357b6972913a753c4db840a5f8bab4566b02447af805b'
HEARTBEAT_SHA = 'ee8d7e93629431a894400056cc7c7853676fcc1ce874204a5452672caa14a41b'
ACCEPTED_FIRMWARE_SHA = '776748a2331f6f6c5de0fc769bd13c8731c503a026217a767a18e86bac37dc3b'
PAYLOAD_PATH = 'provisioning/watch-' + VERSION
PAYLOAD_NAMES = {'files', 'seed.zip', 'LICENSES.zip', 'payload.json', 'COMPLETE'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def metadata(data):
    return {'bytes': len(data), 'sha256': sha(data)}


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def runtime_tools(runtime):
    runtime = Path(runtime).resolve()
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=runtime, text=True).strip()
    require(actual == RUNTIME_SOURCE, 'Exact pinned Runtime source required')
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                        cwd=runtime), 'Clean pinned Runtime required')
    sys.path.insert(0, str(runtime / 'scripts'))
    import provision_device
    import provision_profile
    require(Path(provision_device.__file__).parent == runtime / 'scripts' and
            Path(provision_profile.__file__).parent == runtime / 'scripts', 'Runtime module path differs')
    return provision_device, provision_profile


def archive_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    return stream.getvalue()


def unpack(raw, profile):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(0 < len(names) <= 128 and len(names) == len(set(names)), 'Archive inventory differs')
        for item in archive.infolist():
            profile.relative(item.filename, 192)
            require(not item.is_dir() and item.external_attr >> 28 in (0, 8) and
                    not item.flag_bits & 1 and 0 < item.file_size <= 32 * 1024 * 1024,
                    'Archive member refused')
        require(sum(item.file_size for item in archive.infolist()) <= 64 * 1024 * 1024,
                'Archive size bound')
        return {name: archive.read(name) for name in names}


def accepted_store(path, profile):
    raw = profile.read(path, STORE_BYTES)
    require(metadata(raw) == {'bytes': STORE_BYTES, 'sha256': STORE_SHA}, 'Accepted store ZIP differs')
    files = unpack(raw, profile)
    require(len(files) == 89 and len([p for p in files if p.endswith('.elf')]) == 43,
            'Complete accepted store required')
    old = parse(files['cohort.json'])
    require(old['version'] == '1.0.7' and old['firmware_sha256'] == ACCEPTED_FIRMWARE_SHA and
            old['firmware_size'] == 1238288, 'Accepted cohort differs')
    return files


def checked_seed(directory, device):
    directory = device.safe_path(directory)
    require(directory.is_dir(), 'Seed directory required')
    frozen = {item.name: device.read(item, 32 * 1024 * 1024) for item in directory.iterdir()}
    with tempfile.TemporaryDirectory(prefix='watch-seed-check-') as temporary:
        work = Path(temporary)
        write_files(work / 'input', frozen)
        record, blobs = device.verify_seed(work / 'input', work)
    require(record['source_sha'] == RUNTIME_SOURCE and record['firmware_version'] == '0.1.41' and
            record['target'] == 'esp32s3-16mb-appdata-iq' and record['store_abi'] == 2 and
            metadata(blobs['firmware.bin']) == {'bytes': FIRMWARE_BYTES, 'sha256': FIRMWARE_SHA} and
            sha(blobs['firmware.elf']) == NATIVE_ELF_SHA and
            sha(blobs['candidate.json']) == CANDIDATE_SHA,
            'Exact generic IQ seed required')
    generic = {name: frozen[name] for name in ('board.json', 'boot.json', 'default.elf')}
    require(all(generic[name] == (device.seed.ROOT / 'data' / name).read_bytes()
                for name in ('board.json', 'boot.json')) and
            sha(generic['default.elf']) == HEARTBEAT_SHA and
            read_image(frozen['bootfs0.bin'], 0x510000) == generic,
            'Exact three-file generic seed store required')
    return record, frozen


def write_files(directory, files):
    for name, data in sorted(files.items()):
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            require(stream.write(data) == len(data), 'Short payload write')


def payload_receipt(profile, source, seed_record, seed_files, seed_zip, files):
    charged, available = profile.spiffs_charge([len(data) for data in files.values()], 0x510000)
    require(charged <= available, 'Native store capacity exceeded')
    return {
        'schema': 'riscrte.watch-provisioning-payload', 'schema_version': 1,
        'candidate_version': VERSION, 'feature_baseline': '1.0.7',
        'source_revision': source, 'runtime_source': RUNTIME_SOURCE,
        'target': seed_record['target'], 'layout': seed_record['layout'],
        'accepted_store_zip': {'bytes': STORE_BYTES, 'sha256': STORE_SHA},
        'licenses_zip': {'bytes': LICENSES_BYTES, 'sha256': LICENSES_SHA},
        'accepted_native': {'bytes': 1238288, 'sha256': ACCEPTED_FIRMWARE_SHA},
        'seed_native': metadata(seed_files['firmware.bin']), 'seed_zip': metadata(seed_zip),
        'changed_paths': [], 'file_count': len(files), 'elf_count': 43,
        'charged_spiffs_pages': charged, 'available_spiffs_pages': available,
        'files': {name: metadata(data) for name, data in sorted(files.items())},
        'scope': 'Initial-only provisioning of unchanged accepted Watch 1.0.7; not the latest RF/power build or an OTA. Hardware provisioning is unrun.'}


def freeze(runtime, archive, seed, output, source):
    device, profile = runtime_tools(runtime)
    output = profile.destination(output)
    require(re.fullmatch('[0-9a-f]{40}', source) is not None and source == subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'Exact packaging source required')
    original = accepted_store(archive, profile)
    licenses = profile.read(Path(archive).with_name('LICENSES.zip'), LICENSES_BYTES)
    require(metadata(licenses) == {'bytes': LICENSES_BYTES, 'sha256': LICENSES_SHA},
            'Accepted license ZIP differs')
    seed_record, seed_files = checked_seed(seed, device)
    files = dict(original)
    verify(parse(files['cohort.json']), seed_files['firmware.bin'], version=VERSION)
    require(files == original, 'Accepted store must remain byte-identical')
    seed_zip = archive_bytes(seed_files)
    receipt = payload_receipt(profile, source, seed_record, seed_files, seed_zip, files)
    output.mkdir()
    try:
        write_files(output / 'files', files)
        public_files = {'seed.zip': seed_zip, 'LICENSES.zip': licenses, 'payload.json': encoded(receipt)}
        write_files(output, public_files)
        require(profile.store_files(output / 'files') == files and all(
                profile.read(output / name, 32 * 1024 * 1024) == data
                for name, data in public_files.items()), 'Payload output readback differs')
        (output / 'COMPLETE').write_bytes(b'riscrte.watch-provisioning-payload.v1\n')
    except BaseException:
        shutil.rmtree(output)
        raise
    return receipt


def verify_payload(runtime, payload, archive):
    device, profile = runtime_tools(runtime)
    payload = profile.safe_path(payload)
    require({p.name for p in payload.iterdir()} == PAYLOAD_NAMES, 'Payload inventory differs')
    require(profile.read(payload / 'COMPLETE', 64) == b'riscrte.watch-provisioning-payload.v1\n',
            'Incomplete payload')
    receipt = profile.decode(profile.read(payload / 'payload.json', 65536))
    require(metadata(profile.read(payload / 'LICENSES.zip', LICENSES_BYTES)) ==
            {'bytes': LICENSES_BYTES, 'sha256': LICENSES_SHA}, 'Accepted license ZIP differs')
    original = accepted_store(archive, profile)
    files = profile.store_files(payload / 'files')
    require(files == original, 'Accepted product bytes changed')
    seed_raw = profile.read(payload / 'seed.zip', 32 * 1024 * 1024)
    with tempfile.TemporaryDirectory(prefix='watch-payload-') as temporary:
        seed_path = Path(temporary) / 'seed'
        write_files(seed_path, unpack(seed_raw, profile))
        seed_record, seed_files = checked_seed(seed_path, device)
    verify(parse(files['cohort.json']), seed_files['firmware.bin'], version=VERSION)
    require(receipt == payload_receipt(profile, receipt['source_revision'], seed_record, seed_files,
                                       seed_raw, files),
            'Payload receipt differs')
    return receipt, files


def bind(runtime, payload, archive, revision, output):
    _, profile = runtime_tools(runtime)
    output = profile.destination(output)
    receipt, files = verify_payload(runtime, payload, archive)
    require(re.fullmatch('[0-9a-f]{40}', revision) is not None, 'Full payload commit required')
    # The URL must point at an existing commit that contains these exact bytes.
    committed = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', revision, '--',
                                         PAYLOAD_PATH], cwd=ROOT, text=True).splitlines()
    expected = {PAYLOAD_PATH + '/files/' + n: b for n, b in files.items()}
    expected.update({PAYLOAD_PATH + '/' + n: profile.read(Path(payload) / n, 32 * 1024 * 1024)
                     for n in ('seed.zip', 'LICENSES.zip', 'payload.json', 'COMPLETE')})
    require(set(committed) == set(expected), 'Committed payload inventory differs')
    for name, data in expected.items():
        require(subprocess.check_output(['git', 'show', revision + ':' + name], cwd=ROOT) == data,
                'Committed payload bytes differ')
    base = f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}/{PAYLOAD_PATH}/'
    inventory = profile.pin_store(Path(payload) / 'files', receipt['layout'], base + 'files/',
                                  target=receipt['target'])
    profile.verify_inventory(inventory, files)
    output.mkdir()
    try:
        write_files(output, {
            'inventory.json': profile.encode(inventory),
            'deployment.json': encoded({'schema': 'riscrte.watch-provisioning-deployment', 'schema_version': 1,
                'candidate_version': VERSION, 'feature_baseline': '1.0.7', 'payload_revision': revision,
                'base_url': base + 'files/', 'seed_url': base + 'seed.zip', 'seed_zip': receipt['seed_zip'],
                'licenses_url': base + 'LICENSES.zip', 'licenses_zip': receipt['licenses_zip'],
                'seed_native': receipt['seed_native'], 'runtime_source': RUNTIME_SOURCE,
                'scope': receipt['scope']})})
        (output / 'COMPLETE').write_bytes(b'riscrte.watch-provisioning-deployment.v1\n')
    except BaseException:
        shutil.rmtree(output)
        raise
    return inventory


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Immutable payload redirect refused')


def verify_endpoints(runtime, deployment):
    _, profile = runtime_tools(runtime)
    inventory = profile.decode(profile.read(Path(deployment) / 'inventory.json', 128 * 1024))
    profile.validate_inventory(inventory)
    record = profile.decode(profile.read(Path(deployment) / 'deployment.json', 8192))
    require(set(record) == {'schema', 'schema_version', 'candidate_version', 'feature_baseline',
                'payload_revision', 'base_url', 'seed_url', 'seed_zip', 'seed_native',
                'licenses_url', 'licenses_zip', 'runtime_source', 'scope'} and
            record['schema'] == 'riscrte.watch-provisioning-deployment' and
            type(record['schema_version']) is int and record['schema_version'] == 1 and
            record['candidate_version'] == VERSION and record['feature_baseline'] == '1.0.7' and
            record['runtime_source'] == RUNTIME_SOURCE and
            record['seed_native'] == {'bytes': FIRMWARE_BYTES, 'sha256': FIRMWARE_SHA} and
            record['licenses_zip'] == {'bytes': LICENSES_BYTES, 'sha256': LICENSES_SHA} and
            profile.read(Path(deployment) / 'COMPLETE', 64) == b'riscrte.watch-provisioning-deployment.v1\n',
            'Deployment identity differs')
    revision = record['payload_revision']
    require(re.fullmatch('[0-9a-f]{40}', revision) is not None, 'Full payload commit required')
    base = f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}/{PAYLOAD_PATH}/'
    require(record['base_url'] == base + 'files/' and record['seed_url'] == base + 'seed.zip' and
            record['licenses_url'] == base + 'LICENSES.zip' and
            all(item['url'] == base + 'files/' + item['path'] for item in inventory['files']),
            'Immutable endpoint identity differs')
    opener = urllib.request.build_opener(NoRedirect)
    entries = [*inventory['files'], {'url': record['seed_url'], **record['seed_zip']},
               {'url': record['licenses_url'], **record['licenses_zip']}]
    for item in entries:
        with opener.open(item['url'], timeout=60) as response:
            require(response.status == 200, 'Payload HTTP status differs')
            data = response.read(item['bytes'] + 1)
        require(metadata(data) == {k: item[k] for k in ('bytes', 'sha256')},
                'Downloaded immutable payload differs')
    return {'verified_https_files': len(entries), 'payload_revision': revision,
            'target_instructions_executed': False, 'device_accessed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    freeze_parser = sub.add_parser('freeze')
    for name in ('archive', 'seed', 'output'):
        freeze_parser.add_argument('--' + name, type=Path, required=True)
    freeze_parser.add_argument('--source', required=True)
    for command in ('verify', 'bind'):
        child = sub.add_parser(command)
        for name in ('payload', 'archive'):
            child.add_argument('--' + name, type=Path, required=True)
        if command == 'bind':
            child.add_argument('--revision', required=True)
            child.add_argument('--output', type=Path, required=True)
    fetch = sub.add_parser('verify-endpoints')
    fetch.add_argument('--deployment', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'freeze':
        result = freeze(args.runtime, args.archive, args.seed, args.output, args.source)
    elif args.command == 'verify':
        result, _ = verify_payload(args.runtime, args.payload, args.archive)
    elif args.command == 'bind':
        result = bind(args.runtime, args.payload, args.archive, args.revision, args.output)
    else:
        result = verify_endpoints(args.runtime, args.deployment)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()

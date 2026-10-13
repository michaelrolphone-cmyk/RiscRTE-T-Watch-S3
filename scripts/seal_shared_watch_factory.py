#!/usr/bin/env python3
"""Seal the 1.1.22 ABI3 store, admit all 58 ELFs, then compose a factory BIN.

Offline only. No build, publication, OTA migration or device access. Factory
assembly requires separate successful normal and ASan/UBSan admission receipts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

import current_bootfs
import current_cohort
import current_flash_layout
import expanded_layout
from check_runtime_store_admission import native_composition, store_digest, validate_paths
from read_only_spiffs import read_image
from shared_watch_expanded_store import TARGET_INVENTORY_SHA, encode as staging_encode

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.1.22'
RUNTIME_VERSION = '0.2.23'
TARGET = 'esp32s3-16mb-appdata-expanded-iq'
BASELINE_SHA = '4e43fc376021779a2d7a5cada96aee255735d5db1eb0e896c5aacf65bb3889bc'
COUNTS = {'files': 119, 'elfs': 58, 'apps': 25, 'providers': 34}
NATIVE_FILES = ('firmware.bin', 'firmware.elf', 'bootloader.bin', 'partitions.bin')
FACTORY_NAME = 'T-Watch-S3-1.1.22-full-0x0.bin'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def document(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(
                          'Invalid JSON constant: ' + value)))


def file_bytes(path, limit=64 * 1024 * 1024):
    path = Path(path)
    require(not path.is_symlink() and path.is_file() and 0 < path.stat().st_size <= limit,
            'Missing, empty, oversized or linked input: ' + str(path))
    raw = path.read_bytes()
    require(0 < len(raw) <= limit, 'Input changed size: ' + str(path))
    return raw


def source_head(root, expected):
    require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{40}', expected),
            'An exact source SHA is required')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True,
                                       env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'}).strip()
    require(git('rev-parse', 'HEAD') == expected, 'Source HEAD differs: ' + str(root))
    require(not git('status', '--porcelain', '--untracked-files=all'),
            'Source must be clean, including untracked inputs: ' + str(root))
    return expected


def inventory(store):
    return {name: metadata(raw) for name, raw in sorted(store.items())}


def count_store(store):
    boot = document(store['boot.json'])
    return {'files': len(store), 'elfs': sum(n.endswith('.elf') for n in store),
            'apps': len(boot['app_capabilities']), 'providers': len(boot['drivers'])}


def verify_staging(staging):
    staging = Path(staging)
    raw = file_bytes(staging / 'staging.json', 1024 * 1024)
    record = document(raw)
    require(record.get('schema') == 1 and record.get('version') == VERSION and
            record.get('baseline_sha256') == BASELINE_SHA and
            record.get('status') == 'unsealed component staging only' and
            record.get('flashable') is False and record.get('native_cohort_admitted') is False,
            'Wrong unsealed staging identity')
    root = staging / 'UNSEALED-STORE'
    require(root.is_dir() and not root.is_symlink(), 'Missing regular staging directory')
    store = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Linked staging member: ' + str(path))
        if path.is_dir():
            continue
        name = path.relative_to(root).as_posix()
        store[name] = file_bytes(path)
    validate_paths(store)
    require('cohort.json' in store and inventory(store) == record.get('inventory'),
            'Complete staging inventory differs')
    require(sha(staging_encode(inventory(store))) == TARGET_INVENTORY_SHA,
            'Source-frozen qualified staging inventory differs')
    require(count_store(store) == COUNTS and all(record.get(k) == v for k, v in COUNTS.items()),
            'Incomplete staging app/provider/file counts')
    return store, raw


def verify_markers(blobs, runtime_sha):
    for name in ('firmware.bin', 'firmware.elf'):
        data = blobs[name]
        for prefix, expected in ((b'RTE_SOURCE=', runtime_sha.encode()),
                                 (b'RISC_RUNTIME_VERSION:', RUNTIME_VERSION.encode()),
                                 (b'RISC_PAIRED_STORE_ABI:', b'3')):
            require(set(re.findall(re.escape(prefix) + rb'([^\x00\s]+)\x00', data)) == {expected},
                    'Native source/version/ABI markers differ: ' + name)
        require(set(re.findall(rb'esp32s3-16mb-[a-z0-9-]+\x00', data)) ==
                {TARGET.encode() + b'\0'} and
                not any(marker in data for marker in (b'RISC_OWNER_INSTALLER:',
                    b'RTE_OWNER_MAINTENANCE=1\0', b'esp32s3-16mb-appdata-iq\0',
                    b'esp32s3-16mb-appdata\0', b'esp32s3-16mb-paired\0')),
                'Native target or owner-installer marker differs: ' + name)
        current_cohort.native_layout(data)
    require(len(blobs['firmware.bin']) <= expanded_layout.PARTITIONS['app0'][3],
            'Native firmware exceeds expanded slot')


# Run selected Runtime helpers in an isolated interpreter: product modules with
# the same names must never substitute for the exact source-bound verifiers.
NATIVE_VALIDATOR = r'''
import hashlib, json, sys
from pathlib import Path
source, build = map(Path, sys.argv[1:])
sys.path.insert(0, str(source / 'scripts'))
from release_assets import esp_image, elf
from paired_candidate import native_proof, partitions, EXPANDED_EXPECTED
from paired_bank_images import BOOTLOADER_SHA256
from radio_iq_proof import prove
from check_versions import firmware
blobs = {n: (build / n).read_bytes() for n in ('firmware.bin', 'firmware.elf', 'bootloader.bin', 'partitions.bin')}
for name in ('firmware.bin', 'bootloader.bin'):
    esp_image(blobs[name])
    if blobs[name][3] >> 4 != 4: raise ValueError('Native image lacks 16 MiB flag')
elf(blobs['firmware.elf'])
if hashlib.sha256(blobs['bootloader.bin']).hexdigest() != BOOTLOADER_SHA256:
    raise ValueError('Newly built bootloader differs from reviewed bootloader')
# ESP-IDF's fixed app descriptor embeds the exact input ELF SHA at file 0xb0.
if blobs['firmware.bin'][32:36] != bytes.fromhex('3254cdab') or blobs['firmware.bin'][176:208] != hashlib.sha256(blobs['firmware.elf']).digest():
    raise ValueError('Firmware app descriptor does not bind the supplied native ELF')
proof = native_proof(blobs['firmware.elf'])
proof['radio_iq'] = prove(blobs['firmware.elf'], expanded=True)
print(json.dumps({'native_proof': proof, 'partitions': partitions(blobs['partitions.bin'], EXPANDED_EXPECTED),
                  'runtime_version': firmware((source / 'platformio.ini').read_text()),
                  'firmware_elf_digest_verified': True}, sort_keys=True))
'''


def read_native(runtime, runtime_sha):
    runtime = Path(runtime).resolve()
    source_head(runtime, runtime_sha)
    build = runtime / '.pio/build/watch-expanded'
    blobs = {name: file_bytes(build / name) for name in NATIVE_FILES}
    verify_markers(blobs, runtime_sha)
    expanded_layout.verify_partition_table(blobs['partitions.bin'])
    proof = document(subprocess.check_output([sys.executable, '-c', NATIVE_VALIDATOR,
                                             str(runtime), str(build)]))
    require(proof['runtime_version'] == RUNTIME_VERSION, 'Runtime source version differs')
    composition = native_composition(runtime, blobs['firmware.elf'],
                                     runtime / 'watch-expanded-profile.ini', 24)
    require(composition.get('store_abi') == 3 and composition.get('profile') == 'env:watch-expanded'
            and composition.get('bounds') == {'RISC_INSTALLED_APP_CAPACITY': 64,
                'RISC_PROVIDER_CAPACITY': 40, 'RISC_APP_POLICY_ROWS': 24,
                'RISC_APP_REQUIREMENT_ROWS': 24}, 'Native expanded composition differs')
    # Catch a target build or source change during proof collection.
    require(all(file_bytes(build / name) == raw for name, raw in blobs.items()),
            'Native build changed during verification')
    source_head(runtime, runtime_sha)
    return blobs, {'runtime_revision': runtime_sha, 'assets': inventory(blobs),
                   **proof, 'native_composition': composition}


def prepare(staging, runtime, runtime_sha, product_sha):
    source_head(ROOT, product_sha)
    store, staging_raw = verify_staging(staging)
    original = dict(store)
    blobs, native = read_native(runtime, runtime_sha)
    identity = current_cohort.create(VERSION, RUNTIME_VERSION, product_sha,
                                     blobs['firmware.bin'], expanded=True)
    store['cohort.json'] = current_cohort.encode(identity, expanded=True)
    require({n for n in store if store[n] != original[n]} == {'cohort.json'},
            'Sealing must replace exactly cohort.json')
    image, packing = current_bootfs.build(store, size=expanded_layout.STORE_BYTES)
    require(count_store(store) == COUNTS and packing['empty_blocks'] >= 2,
            'Sealed store lost contents or free-block reserve')
    source_head(ROOT, product_sha)
    record = {'schema': 1, 'kind': 'shared-watch-sealed-store', 'version': VERSION,
              'runtime_version': RUNTIME_VERSION, 'product_revision': product_sha,
              'runtime_revision': runtime_sha, 'layout': expanded_layout.LAYOUT, 'store_abi': 3,
              'counts': COUNTS, 'staging': metadata(staging_raw), 'cohort': identity,
              'staging_inventory_sha256': TARGET_INVENTORY_SHA,
              'inventory': inventory(store), 'store_sha256': store_digest(store),
              'bootfs': packing, 'native': native, 'replaced_files': ['cohort.json'],
              'factory_warning': expanded_layout.FACTORY_WARNING,
              'target_instructions_executed': False, 'hardware_qualified': False,
              'admission_required': ['normal', 'asan-ubsan'], 'factory_bin_created': False}
    return store, image, blobs, record


def write_new(path, raw):
    with Path(path).open('xb') as stream:
        require(stream.write(raw) == len(raw), 'Short artifact write')
    require(file_bytes(path) == raw, 'Artifact readback differs')


def seal_store(args):
    require(not args.output.exists() and not args.output.is_symlink(), 'Choose a fresh seal output')
    _, image, _, record = prepare(args.staging, args.runtime, args.runtime_sha, args.product_sha)
    args.output.mkdir(parents=True, exist_ok=False)
    write_new(args.output / 'bootfs.bin', image)
    write_new(args.output / 'sealed-store.json', encode(record))
    return record


def load_seal(args):
    store, image, blobs, record = prepare(args.staging, args.runtime, args.runtime_sha, args.product_sha)
    require(file_bytes(args.sealed / 'bootfs.bin') == image and
            document(file_bytes(args.sealed / 'sealed-store.json')) == record,
            'Sealed store or evidence differs from exact reproducible inputs')
    return store, image, blobs, record


def receipt_binding(seal):
    return {'schema': 1, 'kind': 'shared-watch-store-admission',
            'product_revision': seal['product_revision'], 'runtime_revision': seal['runtime_revision'],
            'seal_sha256': sha(encode(seal)), 'bootfs_sha256': seal['bootfs']['sha256'],
            'native_elf_sha256': seal['native']['assets']['firmware.elf']['sha256'],
            'store_sha256': seal['store_sha256'], 'expected_elfs': COUNTS['elfs']}


def verify_receipt(receipt, seal, mode):
    binding = receipt_binding(seal)
    require(all(type(receipt.get(k)) is type(v) and receipt[k] == v for k, v in binding.items()),
            'Admission receipt input binding differs')
    require(receipt.get('mode') == mode and receipt.get('sanitizers') ==
            (['address', 'undefined'] if mode == 'asan-ubsan' else []) and
            receipt.get('leak_detection') is False, 'Admission receipt instrumentation differs')
    proof = receipt.get('result', {})
    require(proof.get('prepared') is True and proof.get('cohort_validated') is True and
            type(proof.get('elf_count')) is int and proof['elf_count'] == COUNTS['elfs'] and
            all(type(proof.get(k)) is int and proof[k] == 0 for k in ('hardware_calls', 'storage_calls')) and
            proof.get('target_instructions_executed') is False and
            type(proof.get('app_policy_rows')) is int and proof['app_policy_rows'] == 24,
            'Incomplete or unsafe 58-ELF admission receipt')
    require(proof.get('active_store_sha256') == seal['store_sha256'] and
            proof.get('candidate_store_sha256') == seal['store_sha256'] and
            proof.get('native_elf_sha256') == binding['native_elf_sha256'] and
            proof.get('native_composition') == seal['native']['native_composition'],
            'Admission result does not bind the exact store/native composition')
    return receipt


def admission(args):
    require(not args.output.exists() and not args.output.is_symlink(), 'Choose a fresh receipt path')
    store, _, blobs, seal = load_seal(args)
    from check_runtime_store_admission import admit_cohort
    old = {key: os.environ.get(key) for key in ('SANITIZE', 'ASAN_OPTIONS', 'UBSAN_OPTIONS')}
    try:
        os.environ['SANITIZE'] = '1' if args.mode == 'asan-ubsan' else '0'
        os.environ['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1:abort_on_error=1'
        os.environ['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
        result = admit_cohort(args.runtime, blobs['firmware.elf'], store, store, app_policy_rows=24,
                              native_profile=args.runtime / 'watch-expanded-profile.ini')
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    source_head(ROOT, args.product_sha)
    source_head(args.runtime, args.runtime_sha)
    receipt = {**receipt_binding(seal), 'mode': args.mode,
               'sanitizers': ['address', 'undefined'] if args.mode == 'asan-ubsan' else [],
               'leak_detection': False, 'result': result}
    verify_receipt(receipt, seal, args.mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_new(args.output, encode(receipt))
    return receipt


def factory_appdata(baseline, witness, runtime):
    raw = file_bytes(baseline)
    require(len(raw) == expanded_layout.FLASH_BYTES and sha(raw) == BASELINE_SHA,
            'Factory appdata baseline differs')
    data = raw[0x270000:0x2f0000]
    require(sha(data) == current_flash_layout.APP_DATA_SHA, 'Factory appdata slice differs')
    witness_raw = file_bytes(witness, 16384)
    with tempfile.TemporaryDirectory(prefix='watch-appdata-witness-') as tmp:
        root = Path(tmp)
        (root / 'appdata.bin').write_bytes(data)
        (root / 'appdata-image.json').write_bytes(witness_raw)
        result = document(subprocess.check_output([sys.executable, '-c',
            'import json,sys;sys.path.insert(0,sys.argv[1]);'
            'from app_data_image import verify_initial;print(json.dumps(verify_initial(sys.argv[2])))',
            str(Path(runtime).resolve() / 'scripts'), str(root)]))
    require(result == document(witness_raw), 'Appdata formatting witness differs')
    return data, witness_raw


def assemble_factory(blobs, image, appdata):
    components = {name: blobs[name] for name in ('bootloader.bin', 'partitions.bin', 'firmware.bin')}
    components.update({'bootfs.bin': image, 'appdata.bin': appdata,
                       'otadata.bin': expanded_layout.initial_otadata(),
                       'bank_state.bin': expanded_layout.initial_bank_state(blobs['firmware.bin'], image)})
    deployment = {'layout': expanded_layout.LAYOUT, 'target': TARGET, 'radio_iq': True,
                  'store_abi': 3, 'flash_bytes': expanded_layout.FLASH_BYTES,
                  'partitions': expanded_layout.DEPLOYMENT_PARTS,
                  'factory_warning': expanded_layout.FACTORY_WARNING}
    raw, entries = current_flash_layout.assemble(components, deployment, initialize_app_data=True)
    require(raw[0x840000:0xff0000] == b'\xff' * (0xff0000 - 0x840000),
            'Inactive native/store bank is not erased')
    partitions = {name: {'type': kind, 'subtype': subtype, 'offset': offset, 'bytes': size,
                         'sha256': sha(raw[offset:offset + size]),
                         'erased': raw[offset:offset + size] == b'\xff' * size}
                  for name, (kind, subtype, offset, size) in expanded_layout.PARTITIONS.items()}
    return raw, entries, partitions


def factory(args):
    require(not args.output.exists() and not args.output.is_symlink(), 'Choose a fresh factory output')
    store, image, blobs, seal = load_seal(args)
    receipts = {}
    for mode, path in (('normal', args.normal_receipt), ('asan-ubsan', args.sanitized_receipt)):
        raw = file_bytes(path, 1024 * 1024)
        verify_receipt(document(raw), seal, mode)
        receipts[mode] = metadata(raw)
    appdata, witness = factory_appdata(args.baseline_bin, args.appdata_witness, args.runtime)
    raw, entries, partitions = assemble_factory(blobs, image, appdata)
    require(read_image(raw[0x2f0000:0x840000], expanded_layout.STORE_BYTES) == store,
            'Full factory store readback differs')
    source_head(ROOT, args.product_sha)
    source_head(args.runtime, args.runtime_sha)
    record = {'schema': 1, 'kind': 'shared-watch-factory', 'version': VERSION,
              'product_revision': args.product_sha, 'runtime_revision': args.runtime_sha,
              'layout': expanded_layout.LAYOUT, 'store_abi': 3, 'target': TARGET,
              'image': {'file': FACTORY_NAME, 'flash_offset': '0x0', **metadata(raw)},
              'components': [{**item, 'file': PurePosixPath(item['file']).name} for item in entries],
              'partitions': partitions, 'bootfs': seal['bootfs'], 'counts': COUNTS,
              'seal_sha256': sha(encode(seal)), 'admission_receipts': receipts,
              'initial_appdata': {'baseline_sha256': BASELINE_SHA, 'offset': 0x270000,
                  **metadata(appdata), 'witness': metadata(witness),
                  'witness_preserved_byte_for_byte': True,
                  'witness_layout': document(witness)['layout']},
              'factory_warning': expanded_layout.FACTORY_WARNING, 'erases_saved_settings': True,
              'ota_migration': False, 'inactive_bank_erased': True,
              'target_instructions_executed': False, 'hardware_qualified': False,
              'scope': 'Software-only factory composition. No device access, flashing or hardware/RF qualification.'}
    args.output.mkdir(parents=True, exist_ok=False)
    write_new(args.output / FACTORY_NAME, raw)
    write_new(args.output / 'factory.json', encode(record))
    write_new(args.output / 'appdata-image.json', witness)
    checksums = ''.join(f'{sha(file_bytes(path))}  {path.name}\n' for path in sorted(args.output.iterdir()))
    write_new(args.output / 'SHA256SUMS', checksums.encode())
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('seal-store', 'admission', 'factory'):
        p = commands.add_parser(name)
        for flag in ('staging', 'runtime', 'output'):
            p.add_argument('--' + flag, type=Path, required=True)
        for flag in ('runtime-sha', 'product-sha'):
            p.add_argument('--' + flag, required=True)
        if name != 'seal-store':
            p.add_argument('--sealed', type=Path, required=True)
        if name == 'admission':
            p.add_argument('--mode', choices=('normal', 'asan-ubsan'), required=True)
        if name == 'factory':
            for flag in ('normal-receipt', 'sanitized-receipt', 'baseline-bin'):
                p.add_argument('--' + flag, type=Path, required=True)
            p.add_argument('--appdata-witness', type=Path,
                           default=ROOT / 'docs/watch-recovery/appdata-image.json')
    args = parser.parse_args()
    record = {'seal-store': seal_store, 'admission': admission, 'factory': factory}[args.command](args)
    print(json.dumps(record, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()

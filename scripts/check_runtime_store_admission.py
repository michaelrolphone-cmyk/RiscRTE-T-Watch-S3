#!/usr/bin/env python3
"""Admit untouched archive/SPIFFS/BIN stores using the paired production Runtime.

This closes the gap between policy-custody checks and executable boot admission.
It does not run target instructions or qualify physical hardware. The separate
production-store execution test covers actual app/provider source and lifecycle.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile
from read_only_spiffs import read_image

ROOT = Path(__file__).resolve().parents[1]
BOOTFS_OFFSET = 0x310000
BOOTFS_SIZE = 0x4f0000
BIN_SIZE = 0x800000
MKSPIFFS_SHA256 = '4ddf79a1ab9a3baf502cdb979bea7ed173bbe46727a9902649cc09e6a28a5ad2'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def store_digest(store):
    entries = [{'path': name, 'size_bytes': len(data), 'sha256': sha(data)}
               for name, data in sorted(store.items())]
    return sha(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode())


def preserve_store(store, baseline):
    """A runtime-only repair must preserve every previously delivered store byte."""
    expected = json.loads(Path(baseline).read_text())['files']
    actual = {name: {'size_bytes': len(data), 'sha256': sha(data)}
              for name, data in store.items()}
    if actual != expected:
        changed = sorted(name for name in set(actual) | set(expected)
                         if actual.get(name) != expected.get(name))
        raise ValueError('Delivered store changed: ' + ', '.join(changed))


def compile_harness(runtime, output):
    runtime, output = Path(runtime).resolve(), Path(output)
    includes = [runtime / p for p in ('src', 'sdk/app', 'sdk/driver', 'sdk/hardware',
                                     'lib/ArduinoJson/src', 'test/drivers/stubs')]
    sources = [runtime / p for p in ('src/bootstrap/Json.cpp', 'src/bootstrap/Board.cpp',
               'src/bootstrap/Runtime.cpp', 'src/runtime/drivers/ProviderGraphV2.cpp',
               'src/runtime/drivers/ProviderModuleV2.cpp', 'src/ports/esp32s3/CpuPort.cpp')]
    command = ['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
               '-Wno-missing-field-initializers', '-rdynamic']
    if os.environ.get('SANITIZE') == '1':
        command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-fno-omit-frame-pointer', '-no-pie']
    cpu_header=(runtime / 'src/ports/esp32s3/CpuPort.h').read_text()
    if 'radioJoin' in cpu_header:
        command += ['-DSTORE_ADMISSION_RADIO']
    if 'i2sOpenRx' in cpu_header:
        command += ['-DSTORE_ADMISSION_I2S_RX']
    command += ['-I' + str(p) for p in includes]
    command += [str(p) for p in sources]
    command += [str(ROOT / 'tests/runtime_store_admission.cpp'), '-ldl', '-o', str(output)]
    subprocess.run(command, check=True, timeout=180)
    return output


def archive_store(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive member')
        store = {name[6:]: archive.read(name) for name in names
                 if name.startswith('store/') and not name.endswith('/')}
    validate_paths(store)
    return store


def validate_paths(store):
    if not {'boot.json', 'board.json', 'default.json', 'default.elf'} <= set(store):
        raise ValueError('Complete production store required')
    for name in store:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name or '\\' in name:
            raise ValueError('Unsafe store member: ' + name)


def unpack_image(raw, tool=None):
    if tool is None:
        files = read_image(raw)
        validate_paths(files)
        return files
    tool = Path(tool).resolve()
    if sha(tool.read_bytes()) != MKSPIFFS_SHA256:
        raise ValueError('SPIFFS tool differs from pinned Arduino ESP32 binary')
    if len(raw) != BOOTFS_SIZE:
        raise ValueError('Incorrect SPIFFS partition size')
    with tempfile.TemporaryDirectory(prefix='risc-spiffs-') as temporary:
        root = Path(temporary)
        image = root / 'bootfs.bin'
        image.write_bytes(raw)
        store = root / 'store'
        store.mkdir()
        subprocess.run([str(tool), '-u', str(store), '-p', '256', '-b', '4096',
                        '-s', str(BOOTFS_SIZE), str(image)], check=True, timeout=60,
                       stdout=subprocess.DEVNULL)
        files = {p.relative_to(store).as_posix(): p.read_bytes()
                 for p in store.rglob('*') if p.is_file()}
    validate_paths(files)
    return files


def admit(harness, store, expected_error=None):
    validate_paths(store)
    before = store_digest(store)
    with tempfile.TemporaryDirectory(prefix='risc-store-') as temporary:
        root = Path(temporary)
        for name, data in store.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        result = subprocess.run([str(harness), str(root)], check=True, timeout=30,
                                capture_output=True, text=True)
        outcome = json.loads(result.stdout)
        after = {p.relative_to(root).as_posix(): p.read_bytes()
                 for p in root.rglob('*') if p.is_file()}
        if after != store:
            raise ValueError('Admission modified the actual store')
    if outcome['hardware_calls'] or outcome['storage_calls']:
        raise ValueError('Boot admission invoked native I/O')
    if expected_error is None:
        if not outcome['prepared']:
            raise ValueError('Production store admission failed: ' + str(outcome))
    elif outcome['prepared'] or outcome['error'] != expected_error:
        raise ValueError('Baseline did not fail with the expected admission error: ' + str(outcome))
    return dict(outcome, store_files=len(store), store_sha256=before)


def admit_many(runtime, stores, expected_error=None):
    with tempfile.TemporaryDirectory(prefix='risc-admission-') as temporary:
        harness = compile_harness(runtime, Path(temporary) / 'admit')
        results = [dict(label=label, **admit(harness, store, expected_error))
                   for label, store in stores]
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--archive', nargs='+', type=Path, default=[])
    parser.add_argument('--image', nargs='+', type=Path, default=[])
    parser.add_argument('--bin', nargs='+', type=Path, default=[])
    parser.add_argument('--mkspiffs', type=Path)
    parser.add_argument('--read-only-spiffs', action='store_true',
                        help='Decode the pinned SPIFFS format without running a packer')
    parser.add_argument('--expect-error')
    parser.add_argument('--expect-count', type=int)
    parser.add_argument('--preserved-store', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not (args.archive or args.image or args.bin):
        parser.error('At least one actual archive, image or BIN is required')
    if (args.image or args.bin) and not (args.mkspiffs or args.read_only_spiffs):
        parser.error('--mkspiffs or --read-only-spiffs is required for image/BIN extraction')
    if args.expect_count is not None and len(args.archive) + len(args.image) + len(args.bin) != args.expect_count:
        parser.error('Actual store input count differs from --expect-count')
    inputs, stores = [], []
    for path in [*args.archive, *args.image, *args.bin]:
        raw = path.read_bytes()
        if path in args.archive:
            store = archive_store(raw)
        else:
            if path in args.bin:
                if len(raw) != BIN_SIZE:
                    raise ValueError('Incorrect full BIN size')
                image = raw[BOOTFS_OFFSET:BOOTFS_OFFSET + BOOTFS_SIZE]
            else:
                image = raw
            store = unpack_image(image, args.mkspiffs)
        inputs.append({'file': path.name, 'sha256': sha(raw), 'size_bytes': len(raw)})
        if args.preserved_store:
            preserve_store(store, args.preserved_store)
        stores.append((path.name, store))
    results = admit_many(args.runtime, stores, args.expect_error)
    record = {'schema': 1, 'runtime_source': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=args.runtime, text=True).strip(),
        'expected_error': args.expect_error, 'inputs': inputs, 'results': results,
        'policy_substitutions': 0, 'physical_verification': 'pending'}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()

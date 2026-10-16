#!/usr/bin/env python3
"""Offline, initial-flash-only Watch appdata packaging and admission.

Never formats a device or changes a data-preserving update. Full initial images
overwrite saved data. A successful ELF cohort check is not a flash mount test.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess

IMAGE_BYTES = 0x1000000
OFFSET, SIZE = 0x270000, 0x80000
INITIAL_SHA = '5f03c248f2de31c4da9ae8d9bc2033df064cee5e37694a9982f70fbb2f1d2ef0'
RUNTIME = '06da76aa7f074220b74a282badca0ed0061f1643'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def partition(raw):
    require(len(raw) == IMAGE_BYTES, 'Expected a full 16 MiB initial image')
    table = raw[0x8000:0x9000]
    entries = []
    for at in range(0, len(table), 32):
        row = table[at:at + 32]
        if row[:2] == b'\xeb\xeb':
            require(row[2:16] == b'\xff' * 14 and row[16:] == hashlib.md5(table[:at]).digest(),
                    'Partition table MD5 differs')
            require(table[at + 32:] == b'\xff' * (len(table) - at - 32), 'Partition table tail differs')
            break
        require(row[:2] == b'\xaa\x50', 'Missing partition table checksum or invalid entry')
        _, kind, subtype, offset, size, name, flags = struct.unpack('<HBBII16sI', row)
        require(size and offset >= 0x9000 and offset + size <= IMAGE_BYTES, 'Partition bounds invalid')
        require(not any(offset < p[3] + p[4] and p[3] < offset + size for p in entries), 'Overlapping partitions')
        entries.append((name.rstrip(b'\0'), kind, subtype, offset, size, flags))
    else:
        raise ValueError('Partition table checksum missing')
    require(len({p[0] for p in entries}) == len(entries), 'Duplicate partition label')
    selected = [p for p in entries if p[0] == b'appdata']
    require(selected == [(b'appdata', 1, 0x41, OFFSET, SIZE, 0)], 'Watch appdata geometry differs')
    return raw[OFFSET:OFFSET + SIZE]


def verify(raw):
    data = partition(raw)
    require(sha(data) == INITIAL_SHA, 'Initial appdata is erased, corrupt, nonempty, or unqualified')
    return dict(partition='appdata', offset=OFFSET, bytes=SIZE, sha256=sha(data),
                initial_flash_only=True, target_hardware_executed=False)


def runtime_tools(runtime):
    runtime = Path(runtime).resolve()
    actual = subprocess.check_output(['git', '-C', str(runtime), 'rev-parse', 'HEAD'], text=True).strip()
    require(actual == RUNTIME, 'Use the exact recovered Watch Runtime source')
    require(not subprocess.check_output(['git', '-C', str(runtime), 'diff', 'HEAD', '--',
                'scripts/app_data_image.py', 'scripts/app_data_format.c'], text=True), 'Appdata generator source changed')
    spec = importlib.util.spec_from_file_location('watch_pinned_app_data_image', runtime / 'scripts/app_data_image.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.INITIAL_IMAGE_SHA256 == INITIAL_SHA, 'Appdata generator profile changed')
    return module


def pack(source, image, output):
    """Replace only a blank factory partition; refuse existing user contents."""
    require(len(image) == SIZE and sha(image) == INITIAL_SHA, 'Unqualified initial appdata bytes')
    raw = Path(source).read_bytes()
    require(partition(raw) == b'\xff' * SIZE, 'Input appdata is not erased; refuse overwrite')
    result = raw[:OFFSET] + image + raw[OFFSET + SIZE:]
    verify(result)
    with Path(output).open('xb') as stream:
        require(stream.write(result) == len(result), 'Short full-image write')
    require(Path(output).read_bytes() == result, 'Full-image readback differs')
    return dict(full_sha256=sha(result), full_bytes=len(result), flash_offset='0x0',
                changed_region=[OFFSET, OFFSET + SIZE], all_other_bytes_preserved=True,
                erases_saved_data=True, **verify(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('format')
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--littlefs-source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('pack')
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--appdata', type=Path, required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('verify')
    p.add_argument('--image', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'format':
        result = runtime_tools(args.runtime).build_from_source(args.littlefs_source, args.output)
    elif args.command == 'pack':
        runtime_tools(args.runtime).verify_initial(args.appdata)
        result = pack(args.input, (args.appdata / 'appdata.bin').read_bytes(), args.output)
    else:
        result = verify(args.image.read_bytes())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()

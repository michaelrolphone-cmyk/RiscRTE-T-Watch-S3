#!/usr/bin/env python3
"""Create non-bootable 16 MiB CI fixtures with exact supplied partition/appdata bytes.

These files contain no firmware. They are only inputs to the host storage test.
The old fixture has erased appdata; recovered embeds the selected filesystem.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from verify_factory_appdata_mount import (APPDATA_BYTES, APPDATA_OFFSET, FLASH_BYTES,
                                         TABLE_BYTES, TABLE_OFFSET, parse_appdata, sha256)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--partition-table', type=Path, required=True, help='Exact ESP partition binary (at most 4 KiB); shorter inputs are padded with 0xff')
    parser.add_argument('--formatted-appdata', type=Path, required=True, help='Exact 512 KiB formatted appdata filesystem')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    table = args.partition_table.read_bytes()
    appdata = args.formatted_appdata.read_bytes()
    if not table or len(table) > TABLE_BYTES or len(table) % 32:
        parser.error('Partition table must have 32-byte alignment and occupy at most 4 KiB')
    if len(appdata) != APPDATA_BYTES or appdata == b'\xff' * APPDATA_BYTES:
        parser.error('Formatted appdata must be exactly 512 KiB and not entirely erased')
    table = table.ljust(TABLE_BYTES, b'\xff')
    parse_appdata(table)
    args.output.mkdir(parents=True, exist_ok=True)
    selection = dict(schema=1, kind='generated-nonbootable-host-fixtures',
                     warning='No firmware or bootloader; never flash these CI fixture files.',
                     partition_table_sha256=hashlib.sha256(table).hexdigest())
    for role in ['old', 'recovered']:
        path = args.output / (role + '-host-fixture.bin')
        with path.open('wb') as stream:
            block = b'\xff' * (1024 * 1024)
            for _ in range(FLASH_BYTES // len(block)):
                stream.write(block)
            stream.seek(TABLE_OFFSET)
            stream.write(table)
            if role == 'recovered':
                stream.seek(APPDATA_OFFSET)
                stream.write(appdata)
        selection[role] = dict(filename=path.name, sha256=sha256(path))
    selection['recovered']['appdata_sha256'] = hashlib.sha256(appdata).hexdigest()
    path = args.output / 'selection.json'
    path.write_text(json.dumps(selection, indent=2) + '\n')
    print(f'Created non-bootable host fixtures and exact input pins: {path}')


if __name__ == '__main__':
    main()

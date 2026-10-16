"""Explicit ABI3 factory geometry. Pure bytes only; never touches a device.

A full 0x0 factory BIN ERASES CURRENT SETTINGS, NVS and app-data. The unchanged
512 KiB appdata capacity is not preservation of its contents. No OTA migration.
"""
import hashlib
import struct
import zlib

LAYOUT = 'riscrte-paired-appdata-v3'
STORE_ABI = 3
STORE_BYTES = 0x550000
FLASH_BYTES = 0x1000000
FACTORY_WARNING = 'FULL FACTORY BIN at 0x0 ERASES CURRENT SETTINGS, NVS and app-data. No automatic flashing; not an OTA migration.'
PARTITIONS = {
    'nvs': (1, 2, 0x9000, 0x6000),
    'app0': (0, 0x10, 0x10000, 0x260000),
    'appdata': (1, 0x41, 0x270000, 0x80000),
    'bootfs0': (1, 0x82, 0x2f0000, STORE_BYTES),
    'app1': (0, 0x11, 0x840000, 0x260000),
    'bootfs1': (1, 0x82, 0xaa0000, STORE_BYTES),
    'otadata': (1, 0, 0xff0000, 0x2000),
    'bank_state': (1, 0x40, 0xff2000, 0x2000),
}
DEPLOYMENT_PARTS = {name: {'offset': value[2], 'size': value[3]}
                    for name, value in PARTITIONS.items() if name != 'nvs'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def partition_table():
    previous = 0x9000
    rows = []
    for name, (kind, subtype, offset, size) in PARTITIONS.items():
        require(offset >= previous and offset + size <= FLASH_BYTES and
                offset % 4096 == size % 4096 == 0 and
                (kind != 0 or offset % 0x10000 == 0), 'Expanded flash extent')
        rows.append(struct.pack('<HBBII16sI', 0x50aa, kind, subtype, offset, size, name.encode(), 0))
        previous = offset + size
    raw = b''.join(rows)
    table = raw + b'\xeb\xeb' + b'\xff' * 14 + hashlib.md5(raw).digest()
    return table + b'\xff' * (3072 - len(table))


def verify_partition_table(data):
    # Canonical row order, reserved bytes, digest and erased padding all bound.
    require(data == partition_table(), 'Expanded partition table differs')


def bank_record(bank, firmware, store):
    from current_cohort import native_layout
    native_layout(firmware)
    require(type(bank) is int and bank in (0, 1) and
            32 <= len(firmware) <= 0x260000 and len(store) == STORE_BYTES,
            'Expanded bank payload bounds')
    data = struct.pack('<6I32s32sI', 0x314b4252, 1, bank, len(firmware), len(store), STORE_ABI,
                       hashlib.sha256(firmware).digest(), hashlib.sha256(store).digest(), 0)
    return data + struct.pack('<I', zlib.crc32(data) & 0xffffffff)


def initial_bank_state(firmware, store):
    return bank_record(0, firmware, store) + b'\xff' * (8192 - 96)


def initial_otadata():
    sequence = struct.pack('<I', 1)
    row = sequence + b'\xff' * 20 + struct.pack('<II', 2, zlib.crc32(sequence, 0xffffffff) & 0xffffffff)
    return row + b'\xff' * (8192 - len(row))


def verify_factory_components(components):
    verify_partition_table(components['partitions.bin'])
    require(components['bank_state.bin'] == initial_bank_state(components['firmware.bin'], components['bootfs.bin']),
            'Expanded factory bank journal differs')
    require(components['otadata.bin'] == initial_otadata(), 'Expanded factory OTA metadata differs')

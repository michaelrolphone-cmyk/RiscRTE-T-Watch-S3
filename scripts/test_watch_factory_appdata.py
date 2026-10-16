#!/usr/bin/env python3
"""Offline factory packaging regressions, using a source-reproduced appdata image."""
import argparse
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

import watch_factory_appdata as w

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--appdata', required=True, type=Path)
args, rest = p.parse_known_args()
INITIAL = args.appdata.read_bytes()
w.require(len(INITIAL) == w.SIZE and w.sha(INITIAL) == w.INITIAL_SHA, 'Wrong test appdata')


def fixture(entries=None):
    if entries is None:
        entries = [(1, 0x41, w.OFFSET, w.SIZE, b'appdata', 0)]
    table = b''.join(struct.pack('<HBBII16sI', 0x50aa, *entry) for entry in entries)
    table += b'\xeb\xeb' + b'\xff' * 14 + hashlib.md5(table).digest()
    raw = bytearray(b'\xff' * w.IMAGE_BYTES)
    raw[0x8000:0x8000 + len(table)] = table
    return bytes(raw)


class Packaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blank = fixture()
        cls.good = cls.blank[:w.OFFSET] + INITIAL + cls.blank[w.OFFSET + w.SIZE:]

    def test_exact_qualified_partition(self):
        self.assertEqual(w.verify(self.good)['sha256'], w.INITIAL_SHA)

    def test_blank_fails_admission(self):
        with self.assertRaises(ValueError):
            w.verify(self.blank)

    def test_truncated_and_extra_bytes(self):
        for raw in [self.good[:-1], self.good + b'\xff']:
            with self.assertRaises(ValueError):
                w.verify(raw)

    def test_corrupt_appdata_fails(self):
        raw = bytearray(self.good)
        raw[w.OFFSET + 64] ^= 1
        with self.assertRaises(ValueError):
            w.verify(raw)

    def test_table_checksum_fails(self):
        raw = bytearray(self.good)
        raw[0x8030] ^= 1
        with self.assertRaises(ValueError):
            w.verify(raw)

    def test_wrong_partition_type_geometry_and_flags(self):
        rows = [(0, 0x41, w.OFFSET, w.SIZE, b'appdata', 0),
                (1, 0x41, w.OFFSET + 4096, w.SIZE, b'appdata', 0),
                (1, 0x41, w.OFFSET, w.SIZE - 4096, b'appdata', 0),
                (1, 0x41, w.OFFSET, w.SIZE, b'appdata', 1),
                (1, 0x41, w.OFFSET, w.SIZE, b'other', 0)]
        for row in rows:
            with self.assertRaises(ValueError):
                w.partition(fixture([row]))

    def test_overlap_and_duplicate_labels(self):
        app = (1, 0x41, w.OFFSET, w.SIZE, b'appdata', 0)
        for row in [(1, 0x41, w.OFFSET, w.SIZE, b'other', 0),
                    (1, 0x41, 0x800000, w.SIZE, b'appdata', 0)]:
            with self.assertRaises(ValueError):
                w.partition(fixture([app, row]))

    def test_pack_preserves_every_other_byte(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'before').write_bytes(self.blank)
            result = w.pack(d / 'before', INITIAL, d / 'after')
            self.assertTrue(result['all_other_bytes_preserved'])
            self.assertEqual((d / 'after').read_bytes(), self.good)
            self.assertEqual((d / 'before').read_bytes(), self.blank)
            with self.assertRaises(FileExistsError):
                w.pack(d / 'before', INITIAL, d / 'after')

    def test_pack_refuses_existing_data_and_unqualified_input(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'existing').write_bytes(self.good)
            with self.assertRaises(ValueError):
                w.pack(d / 'existing', INITIAL, d / 'after')
            with self.assertRaises(ValueError):
                w.pack(d / 'existing', b'\xff' * w.SIZE, d / 'after')
            self.assertFalse((d / 'after').exists())


if __name__ == '__main__':
    unittest.main(argv=['test_watch_factory_appdata.py', *rest])

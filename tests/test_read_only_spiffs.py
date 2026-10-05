"""Compare the bounded read-only decoder to a real packed production store."""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from build_wifi_common import read_zip
from read_only_spiffs import read_image


class ReadOnlySpiffs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = ROOT/'dist/wifi-common'
        archives = list(folder.glob('*-wifi-launcher-common.zip'))
        if len(archives) != 1:
            raise RuntimeError('Build the actual Wi-Fi common archive/image first')
        files = read_zip(archives[0])
        cls.expected = {name[6:]: data for name, data in files.items() if name.startswith('store/')}
        cls.raw = archives[0].with_name(archives[0].stem+'-bootfs.bin').read_bytes()
        cls.header = cls.free = None
        for block in range(len(cls.raw)//4096):
            for entry in range(15):
                lookup = block*4096+entry*2
                obj = struct.unpack_from('<H', cls.raw, lookup)[0]
                page = (block*16+entry+1)*256
                if obj == 65535 and cls.free is None:
                    cls.free = (lookup, page)
                if obj not in (0, 65535) and obj & 0x8000 and cls.header is None:
                    ident, span, flags = struct.unpack_from('<HHB', cls.raw, page)
                    if span == 0 and flags & 128 and not flags & 7:
                        cls.header = (lookup, page, ident)
        assert cls.header is not None and cls.free is not None

    def test_all_real_store_files_match(self):
        self.assertEqual(len(self.expected), 44)
        self.assertEqual(read_image(self.raw), self.expected)

    def rejects(self, edit):
        changed = bytearray(self.raw)
        edit(changed)
        with self.assertRaises((AssertionError, ValueError, KeyError)):
            read_image(changed)

    def test_wrong_geometry_rejected(self):
        with self.assertRaises(AssertionError):
            read_image(self.raw[:-1])

    def test_lookup_and_header_identity_mismatch_rejected(self):
        lookup, _, ident = self.header
        self.rejects(lambda data: struct.pack_into('<H', data, lookup, ident ^ 1))

    def test_unfinalized_index_rejected(self):
        _, page, _ = self.header
        def edit(data):
            data[page+4] |= 2
        self.rejects(edit)

    def test_out_of_range_data_page_rejected(self):
        _, page, _ = self.header
        self.rejects(lambda data: struct.pack_into('<H', data, page+49, 65535))

    def test_duplicate_live_index_rejected(self):
        _, page, ident = self.header
        lookup, destination = self.free
        def edit(data):
            struct.pack_into('<H', data, lookup, ident)
            data[destination:destination+256] = data[page:page+256]
        self.rejects(edit)


if __name__ == '__main__':
    unittest.main()

import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import current_bootfs
from read_only_spiffs import read_image


class CurrentBootfs(unittest.TestCase):
    def test_exact_contents_cross_index_and_block_boundaries(self):
        store = {'boot.json': b'{}', 'driver/manifest.json': b'{}',
                 'driver/driver.elf': bytes(range(256)) * 180, 'empty': b''}
        image, record = current_bootfs.build(store)
        self.assertEqual(read_image(image, current_bootfs.IMAGE_SIZE), store)
        self.assertEqual(record['file_count'], 4)
        self.assertEqual(record['payload_bytes'], sum(map(len, store.values())))
        self.assertEqual(record['occupied_blocks'] + record['empty_blocks'], 1296)
        self.assertEqual(record['sha256'], hashlib.sha256(image).hexdigest())

    def test_creation_order_does_not_change_image_or_evidence(self):
        store = {'z': b'last', 'a': b'first', 'nested/b': b'b' * 32000}
        self.assertEqual(current_bootfs.build(store),
                         current_bootfs.build(dict(reversed(list(store.items())))))

    def test_name_limit_includes_slash_and_nul_and_rejects_non_ascii(self):
        for name in ('x' * 30, 'folder/' + 'x' * 23):
            self.assertEqual(read_image(current_bootfs.build({name: b'x'})[0],
                                        current_bootfs.IMAGE_SIZE), {name: b'x'})
        for name in ('x' * 31, '\u00e9', '\u00e9' * 16):
            with self.assertRaisesRegex(ValueError, 'oversized'):
                current_bootfs.build({name: b'x'})

    def test_bad_inputs_fail_before_generator(self):
        for name in ('', '/', '/absolute', '../escape', 'a/../b', 'a//b',
                     'a/./b', 'a/', '.', 'a\\b', 'nul\x00x'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                current_bootfs.build({name: b'x'})
        with self.assertRaises(ValueError):
            current_bootfs.build({'x': 'not bytes'})
        with self.assertRaises(ValueError):
            current_bootfs.build({})

    def test_geometry_and_source_custody(self):
        with self.assertRaisesRegex(ValueError, 'geometry'):
            current_bootfs.build({'a': b'a'}, 0x4f0000)
        with patch.object(current_bootfs, 'GENERATOR_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'source differs'):
                current_bootfs.build({'a': b'a'})

    def test_capacity_failure_has_no_partial_output(self):
        with self.assertRaisesRegex(RuntimeError, 'exceeded'):
            current_bootfs.build({'huge': b'x' * current_bootfs.IMAGE_SIZE})

    def test_free_block_reserve(self):
        with self.assertRaisesRegex(ValueError, 'free-block reserve'):
            current_bootfs.build({'large': b'x' * 4835000})
        _, record = current_bootfs.build({'large': b'x' * 4825000})
        self.assertGreaterEqual(record['empty_blocks'], 2)


if __name__ == '__main__':
    unittest.main()

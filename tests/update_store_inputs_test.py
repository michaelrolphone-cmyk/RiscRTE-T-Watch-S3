"""Fail-closed input/authority checks for the additive paired host gate."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update_test_production_store_runtime as gate


class UpdateInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.image = Path(self.temporary.name) / 'paired.bin'
        self.image.write_bytes(b'\xff' * gate.BOOTFS_SIZE)
        self.metadata = {'schema': 1, 'layout': 'riscrte-paired-16m-v1', 'store_abi': 1,
            'partition_label': 'bootfs0', 'image': self.image.name, 'size_bytes': gate.BOOTFS_SIZE,
            'sha256': hashlib.sha256(self.image.read_bytes()).hexdigest(), 'page_size': 256,
            'block_size': 4096, 'tool_sha256': gate.MKSPIFFS_SHA256, 'files': 4}
        self.files = {name: b'fixture' for name in ('boot.json', 'board.json', 'default.json', 'default.elf')}

    def extract(self, metadata=None):
        self.image.with_suffix('.json').write_text(json.dumps(metadata or self.metadata))
        with patch.object(gate, 'unpack_image', return_value=self.files) as unpack:
            result = gate.paired_image_store(self.image, '/fixture/pinned-mkspiffs')
            unpack.assert_called_once()
            return result

    def test_checked_raw_partition_has_no_full_bin_offset_inference(self):
        self.assertEqual(self.extract(), self.files)

    def test_wrong_layout_abi_partition_schema_rejected_before_unpack(self):
        for key, value in [('schema', 2), ('schema', True), ('layout', 'legacy-8m'),
                           ('store_abi', 2), ('store_abi', True), ('partition_label', 'bootfs1')]:
            with self.subTest(key=key, value=value):
                metadata = dict(self.metadata, **{key: value})
                self.image.with_suffix('.json').write_text(json.dumps(metadata))
                with patch.object(gate, 'unpack_image') as unpack:
                    with self.assertRaises(ValueError):
                        gate.paired_image_store(self.image, '/fixture/pinned-mkspiffs')
                    unpack.assert_not_called()

    def test_bad_hash_size_name_or_extraction_parameters_rejected(self):
        for key, value in [('sha256', '0' * 64), ('size_bytes', 0x1000000), ('image', 'other.bin'),
                           ('page_size', 512), ('block_size', 8192), ('tool_sha256', '0' * 64)]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    self.extract(dict(self.metadata, **{key: value}))

    def test_full_bin_is_not_a_raw_partition(self):
        self.image.write_bytes(b'\xff' * 0x1000000)
        self.metadata['sha256'] = hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.metadata['size_bytes'] = self.image.stat().st_size
        with self.assertRaises(ValueError):
            self.extract()

    def test_extracted_file_count_must_match(self):
        with self.assertRaises(ValueError):
            self.extract(dict(self.metadata, files=5))

    def test_updaters_have_exact_eight_grants(self):
        def grant(cap, api, instance):
            return {'capability': cap, 'api': api, 'instance_id': instance}
        policies = [{'manifest': name, 'grants': [grant('storage.key-value', 1, 1), grant('storage.key-value', 1, 5)]}
                    for name in ('default.json', 'clock.json', 'points_in_time.json')]
        policies += [{'manifest': 'other' + str(i) + '.json', 'grants': []} for i in range(8)]
        update = [grant('display.output', 1, 5), grant('input.touch.raw', 1, 6), grant('rtc.clock', 2, 8),
                  grant('board.battery', 1, 4), grant('storage.key-value', 1, 6), grant('net.wifi', 1, 15),
                  grant('software.update.firmware', 1, 0), grant('alarm.service', 1, 0)]
        policies.append({'manifest': 'ota_update.json', 'grants': update})
        boot = {'default_app': 'default.elf', 'app_capabilities': policies}
        def content(b):
            return {'boot.json': json.dumps(b).encode(), 'default.json': b'{"version":"0.8.0"}',
                    'ota_update.json': b'{}'}
        gate._policies(content(boot))
        for replacement in (grant('storage.key-value', 1, 1), grant('platform.bank-store', 1, 0),
                            grant('net.wifi', 1, 0)):
            bad = copy.deepcopy(boot)
            bad['app_capabilities'][-1]['grants'][4] = replacement
            with self.assertRaises(ValueError):
                gate._policies(content(bad))
        bad = copy.deepcopy(boot)
        bad['app_capabilities'][-1]['grants'].append(grant('storage.key-value', 1, 1))
        with self.assertRaises(ValueError):
            gate._policies(content(bad))


if __name__ == '__main__':
    unittest.main()

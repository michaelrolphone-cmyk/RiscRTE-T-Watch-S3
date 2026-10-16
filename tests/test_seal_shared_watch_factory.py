"""Offline factory sealing gates; real staging is an explicit opt-in fixture."""
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import seal_shared_watch_factory as factory
import expanded_layout


class FactoryRecipe(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime_sha = 'a' * 40
        self.product_sha = 'b' * 40
        self.store = {'boot.json': factory.encode({'app_capabilities': [{}] * 25, 'drivers': [{}] * 34}),
                      'board.json': b'{}', 'default.json': b'{}', 'cohort.json': b'old identity',
                      'default.elf': b'old native app'}
        self.store.update({f'app{i}.elf': b'elf-' + str(i).encode() for i in range(57)})
        self.store.update({f'item{i}.json': b'{}' for i in range(57)})
        self.assertEqual(factory.count_store(self.store), factory.COUNTS)
        self.staging = self.root / 'stage'
        self.staging.mkdir()
        for name, raw in self.store.items():
            path = self.staging / 'UNSEALED-STORE' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.staging_record = {'schema': 1, 'version': factory.VERSION,
            'baseline_sha256': factory.BASELINE_SHA, 'status': 'unsealed component staging only',
            'flashable': False, 'native_cohort_admitted': False,
            **factory.COUNTS, 'inventory': factory.inventory(self.store)}
        self.save_staging()
        self.staging_pin = patch.object(factory, 'TARGET_INVENTORY_SHA',
            factory.sha(factory.staging_encode(factory.inventory(self.store))))
        self.staging_pin.start()
        self.addCleanup(self.staging_pin.stop)
        self.native = b'\xe9' + b'\0'.join([b'RTE_SOURCE=' + self.runtime_sha.encode(),
            b'RISC_RUNTIME_VERSION:0.2.23', b'RISC_PAIRED_STORE_ABI:3', factory.TARGET.encode()]) + b'\0'
        self.blobs = {'firmware.bin': self.native, 'firmware.elf': self.native,
                      'bootloader.bin': b'loader', 'partitions.bin': expanded_layout.partition_table()}
        self.native_record = {'assets': factory.inventory(self.blobs),
                             'native_composition': {'profile': 'env:watch-expanded', 'store_abi': 3}}
        self.seal = {'product_revision': self.product_sha, 'runtime_revision': self.runtime_sha,
                     'bootfs': {'sha256': 'c' * 64}, 'native': self.native_record,
                     'store_sha256': 'd' * 64}

    def save_staging(self):
        (self.staging / 'staging.json').write_bytes(factory.encode(self.staging_record))

    def receipt(self, mode='normal'):
        return {**factory.receipt_binding(self.seal), 'mode': mode,
            'sanitizers': ['address', 'undefined'] if mode == 'asan-ubsan' else [],
            'leak_detection': False,
            'result': {'prepared': True, 'cohort_validated': True, 'elf_count': 58,
                       'hardware_calls': 0, 'storage_calls': 0, 'app_policy_rows': 32,
                       'target_instructions_executed': False,
                       'active_store_sha256': self.seal['store_sha256'],
                       'candidate_store_sha256': self.seal['store_sha256'],
                       'native_elf_sha256': self.native_record['assets']['firmware.elf']['sha256'],
                       'native_composition': self.native_record['native_composition']}}

    def test_inventory_complete_and_unchanged(self):
        store, raw = factory.verify_staging(self.staging)
        self.assertEqual(store, self.store)
        self.assertEqual(factory.document(raw), self.staging_record)

    def test_missing_extra_or_altered_staging_rejected(self):
        path = self.staging / 'UNSEALED-STORE/default.elf'
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            factory.verify_staging(self.staging)
        path.unlink()
        with self.assertRaises(ValueError):
            factory.verify_staging(self.staging)
        path.write_bytes(self.store['default.elf'])
        (path.parent / 'extra').write_bytes(b'not inventoried')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            factory.verify_staging(self.staging)

    def test_consistently_rehashed_staging_is_still_rejected(self):
        path = self.staging / 'UNSEALED-STORE/default.elf'
        path.write_bytes(b'different qualified-looking component')
        self.staging_record['inventory']['default.elf'] = factory.metadata(path.read_bytes())
        self.save_staging()
        with self.assertRaisesRegex(ValueError, 'Source-frozen'):
            factory.verify_staging(self.staging)

    def test_false_counts_and_source_baseline_rejected(self):
        for key, value in (('files', 118), ('providers', 33), ('apps', 24),
                           ('baseline_sha256', 'e' * 64), ('version', '1.1.21'), ('flashable', True)):
            old = self.staging_record[key]
            self.staging_record[key] = value
            self.save_staging()
            with self.assertRaises(ValueError):
                factory.verify_staging(self.staging)
            self.staging_record[key] = old

    def test_linked_staging_member_and_duplicate_json_rejected(self):
        path = self.staging / 'UNSEALED-STORE/default.elf'
        path.unlink()
        path.symlink_to(self.staging / 'staging.json')
        with self.assertRaisesRegex(ValueError, 'Linked'):
            factory.verify_staging(self.staging)
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            factory.document(b'{"schema":1,"schema":1}')

    def test_markers_exclusive_both_bin_and_elf(self):
        factory.verify_markers(self.blobs, self.runtime_sha)
        markers = [b'RISC_PAIRED_STORE_ABI:1\0', b'RISC_PAIRED_STORE_ABI:2\0',
                   b'RTE_SOURCE=' + b'f' * 40 + b'\0', b'RISC_RUNTIME_VERSION:0.2.24\0',
                   b'esp32s3-16mb-appdata-iq\0', b'esp32s3-16mb-appdata-expanded\0',
                   b'RISC_OWNER_INSTALLER:1\0',
                   b'RTE_OWNER_MAINTENANCE=1\0']
        for name in ('firmware.bin', 'firmware.elf'):
            for marker in markers:
                with self.subTest(name=name, marker=marker), self.assertRaises(ValueError):
                    factory.verify_markers({**self.blobs, name: self.native + marker}, self.runtime_sha)
            with self.assertRaises(ValueError):
                factory.verify_markers({**self.blobs, name: b'no markers'}, self.runtime_sha)

    def test_only_cohort_changes_and_packing_roundtrips(self):
        with patch.object(factory, 'source_head'), patch.object(factory, 'read_native',
                return_value=(self.blobs, self.native_record)):
            store, image, _, record = factory.prepare(self.staging, self.root, self.runtime_sha, self.product_sha)
        self.assertEqual({n for n in store if store[n] != self.store[n]}, {'cohort.json'})
        identity = factory.current_cohort.parse(store['cohort.json'], expanded=True)
        self.assertEqual(identity['source_revision'], self.product_sha)
        self.assertEqual(identity['version'], '1.1.22')
        self.assertEqual(identity['runtime_version'], '0.2.23')
        self.assertEqual(factory.read_image(image, 0x550000), store)
        self.assertGreaterEqual(record['bootfs']['empty_blocks'], 2)
        self.assertFalse(record['factory_bin_created'])

    def test_seal_no_overwrite(self):
        args = SimpleNamespace(output=self.staging)
        with self.assertRaisesRegex(ValueError, 'fresh seal'):
            factory.seal_store(args)
        with self.assertRaises(FileExistsError):
            factory.write_new(self.staging / 'staging.json', b'overwrite')

    def test_clean_source_exact_sha_and_untracked_refusal(self):
        with patch.object(factory.subprocess, 'check_output', side_effect=[self.product_sha + '\n', '']) as git:
            self.assertEqual(factory.source_head(self.root, self.product_sha), self.product_sha)
        self.assertIn('--untracked-files=all', git.call_args.args[0])
        self.assertEqual(git.call_args.kwargs['env']['GIT_NO_LAZY_FETCH'], '1')
        for head, status in ((self.runtime_sha, ''), (self.product_sha, '?? recipe.py')):
            with patch.object(factory.subprocess, 'check_output', side_effect=[head, status]):
                with self.assertRaises(ValueError):
                    factory.source_head(self.root, self.product_sha)
        with self.assertRaisesRegex(ValueError, 'exact source'):
            factory.source_head(self.root, 'HEAD')

    def test_receipts_require_both_instrumentation_modes(self):
        for mode in ('normal', 'asan-ubsan'):
            receipt = self.receipt(mode)
            self.assertEqual(factory.verify_receipt(receipt, self.seal, mode), receipt)
            with self.assertRaises(ValueError):
                factory.verify_receipt(receipt, self.seal, 'normal' if mode == 'asan-ubsan' else 'asan-ubsan')
        bad = self.receipt('asan-ubsan')
        bad['sanitizers'] = ['address']
        with self.assertRaises(ValueError):
            factory.verify_receipt(bad, self.seal, 'asan-ubsan')

    def test_receipt_stale_missing_or_falsely_counted_rejected(self):
        bad_values = {'prepared': False, 'cohort_validated': False, 'elf_count': 55,
                      'hardware_calls': 1, 'storage_calls': 1, 'app_policy_rows': 16,
                      'target_instructions_executed': True, 'active_store_sha256': 'wrong',
                      'candidate_store_sha256': 'wrong', 'native_elf_sha256': 'wrong',
                      'native_composition': {}}
        for key, value in bad_values.items():
            bad = self.receipt()
            bad['result'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                factory.verify_receipt(bad, self.seal, 'normal')
        for key in factory.receipt_binding(self.seal):
            bad = self.receipt()
            bad.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError):
                factory.verify_receipt(bad, self.seal, 'normal')
        bad = self.receipt()
        bad['result']['hardware_calls'] = False
        with self.assertRaises(ValueError):
            factory.verify_receipt(bad, self.seal, 'normal')

    def test_factory_blocked_before_appdata_or_output_without_receipts(self):
        bad_path = self.root / 'bad-receipt.json'
        bad_path.write_bytes(factory.encode(self.receipt('normal')))
        args = SimpleNamespace(output=self.root / 'factory', normal_receipt=bad_path,
                               sanitized_receipt=bad_path)
        with patch.object(factory, 'load_seal', return_value=({}, b'', self.blobs, self.seal)), \
                patch.object(factory, 'factory_appdata') as appdata:
            with self.assertRaises(ValueError):
                factory.factory(args)
            appdata.assert_not_called()
        self.assertFalse(args.output.exists())

    def test_factory_exact_offsets_all_partitions_and_inactive_erasure(self):
        image, appdata = b'\x88' * 0x550000, b'\x77' * 0x80000
        with patch.object(factory.current_flash_layout, 'APP_DATA_SHA', factory.sha(appdata)):
            raw, entries, parts = factory.assemble_factory(self.blobs, image, appdata)
        self.assertEqual(len(raw), 0x1000000)
        self.assertEqual(raw[0x2f0000:0x840000], image)
        self.assertEqual(raw[0x270000:0x2f0000], appdata)
        self.assertEqual(set(parts), set(expanded_layout.PARTITIONS))
        for name in ('nvs', 'app1', 'bootfs1'):
            self.assertTrue(parts[name]['erased'])
        self.assertEqual(raw[0x840000:0xff0000], b'\xff' * 0x7b0000)
        self.assertEqual(struct.unpack_from('<6I', raw, 0xff2000),
                         (0x314b4252, 1, 0, len(self.native), 0x550000, 3))
        self.assertEqual(len(entries), 7)

    def test_factory_rejects_other_native_table_or_unverified_appdata(self):
        with self.assertRaises(ValueError):
            factory.assemble_factory(self.blobs, b'x' * 0x550000, b'\xff' * 0x80000)
        table = bytearray(self.blobs['partitions.bin'])
        table[0] ^= 1
        with self.assertRaises(ValueError):
            factory.assemble_factory({**self.blobs, 'partitions.bin': bytes(table)},
                                     b'x' * 0x550000, b'\xff' * 0x80000)

    @unittest.skipUnless(os.environ.get('WATCH_SHARED_STAGING'), 'explicit real staging fixture not selected')
    def test_real_staging_inventory(self):
        self.staging_pin.stop()
        store, _ = factory.verify_staging(Path(os.environ['WATCH_SHARED_STAGING']))
        self.assertEqual(factory.count_store(store), factory.COUNTS)


if __name__ == '__main__':
    unittest.main()

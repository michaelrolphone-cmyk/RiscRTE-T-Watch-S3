#!/usr/bin/env python3
"""Fail-closed contract tests; no flashing, publication or Xtensa execution."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_idf61_candidate as recipe
from native_idf61_qualification import preservation_model

PARSER = argparse.ArgumentParser()
PARSER.add_argument('--runtime', type=Path, required=True)
PARSER.add_argument('--image-helper', type=Path, required=True)
PARSER.add_argument('--sdk', type=Path, required=True)
PARSER.add_argument('--baseline', type=Path, required=True)
OPTIONS, REST = PARSER.parse_known_args()
SOURCES = {'product': ROOT, 'runtime': OPTIONS.runtime.resolve(), 'image_helper': OPTIONS.image_helper.resolve(), 'sdk': OPTIONS.sdk.resolve()}
recipe.setup_modules(SOURCES)
CONTRACT = json.loads(recipe.CONTRACT.read_bytes())
BASELINE, OLD_NATIVE, BEFORE = recipe.baseline_bytes(OPTIONS.baseline, CONTRACT, SOURCES)
spec = importlib.util.spec_from_file_location('elf_fixture', OPTIONS.runtime / 'test/make_scoped_provider_elf.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class NativeCandidateContracts(unittest.TestCase):
    def test_runtime_owned_setup_loop_are_not_arduino(self):
        native = ['app_main', 'setup()', 'loop()', 'ArduinoJson::detail::RamString::typeSortKey']
        self.assertEqual(recipe.arduino_runtime_symbols(native), [])
        for name in ('initArduino()', 'loopTask(void*)', 'initVariant()', 'HardwareSerial::begin()', 'String::concat(char const*)', 'HWCDC::write(unsigned char)'):
            with self.subTest(symbol=name):
                self.assertEqual(recipe.arduino_runtime_symbols([name]), [name])

    def test_product_qualification_import_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'native_idf61_qualification.py'
            fake.write_text('raise RuntimeError("wrong product helper")')
            with mock.patch.object(sys, 'path', [tmp, *sys.path]):
                module = recipe.local_qualification()
            self.assertEqual(Path(module.__file__).resolve(), ROOT / 'scripts/native_idf61_qualification.py')

    def test_exact_baseline_inventory(self):
        self.assertEqual(len(BEFORE), CONTRACT['store_file_count'])
        self.assertEqual(sum(name.endswith('.elf') for name in BEFORE), CONTRACT['elf_count'])
        self.assertEqual(recipe.descriptor(OLD_NATIVE), CONTRACT['app_descriptor'])

    def test_exact_released_factory_required(self):
        changed = bytearray(BASELINE)
        changed[0x270001] ^= 1
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'different.bin'
            path.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, 'Exact released factory'):
                recipe.baseline_bytes(path, CONTRACT, SOURCES)

    def test_missing_and_hidden_private_imports_rejected(self):
        for name in ('xTaskGetTickCount', 'vPortExitCritical', 'esp_intr_alloc'):
            with self.subTest(name=name):
                for image in (fixture.image([name]), fixture.image(['memcpy'], name)):
                    with self.assertRaisesRegex(ValueError, 'Private OS/CPU'):
                        recipe.reject_private({'private/driver.elf': image}, SOURCES['runtime'])

    def test_ordinary_provider_still_accepted(self):
        image = bytes(fixture.image(['memcpy', 'memmove', 'memset', 'strcmp']))
        result = recipe.reject_private({'ordinary/driver.elf': image}, SOURCES['runtime'])
        self.assertEqual(result['ordinary/driver.elf'], ['memcpy', 'memmove', 'memset', 'strcmp'])

    def test_all_released_payloads_kept(self):
        lock = {'candidate_version': '0.0.0-idf61.0123456789ab', 'sources': {'product': {'revision': 'a'*40}}}
        after = recipe.compose_store(BEFORE, OLD_NATIVE, lock)
        self.assertEqual({name for name in BEFORE if BEFORE[name] != after[name]}, {'cohort.json'})
        for path in ('boot.json', 'board.json', 'default.elf', 'default.json', 'springboard.elf', 'springboard.json'):
            self.assertEqual(BEFORE[path], after[path])

    def test_app_descriptor_required(self):
        with self.assertRaisesRegex(ValueError, 'descriptor'):
            recipe.descriptor(b'\0'*288)

    def test_artifact_corruption_and_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'test.bin').write_bytes(b'x')
            row = {'path': 'test.bin', 'bytes': 1, 'sha256': recipe.sha(b'x')}
            lock = {'native_files': {key: dict(row) for key in recipe.ARTIFACT_KEYS}}
            recipe.checked_artifacts(lock, root)
            (root / 'test.bin').write_bytes(b'y')
            with self.assertRaisesRegex(ValueError, 'differs from lock'):
                recipe.checked_artifacts(lock, root)
            with self.assertRaisesRegex(ValueError, 'Non-canonical'):
                recipe.safe_path(root, '../test.bin')
            (root / 'symlink').symlink_to('/etc/hosts')
            with self.assertRaisesRegex(ValueError, 'outside build'):
                recipe.safe_path(root, 'symlink')

    def test_incomplete_artifact_lock_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Incomplete native'):
            recipe.checked_artifacts({'native_files': {}}, Path('.'))

    def test_mutable_and_dirty_source_rejected(self):
        with self.assertRaisesRegex(ValueError, 'immutable'):
            recipe.clean_source(ROOT, 'main')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q', root], check=True)
            (root / 'a').write_text('source')
            subprocess.run(['git', '-C', root, 'add', 'a'], check=True)
            subprocess.run(['git', '-C', root, '-c', 'user.name=test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'test'], check=True)
            revision = recipe.git(root, 'rev-parse', 'HEAD').decode().strip()
            recipe.clean_source(root, revision)
            (root / 'a').write_text('mutated')
            with self.assertRaisesRegex(ValueError, 'Dirty source'):
                recipe.clean_source(root, revision)

    def test_factory_and_transition_are_distinct(self):
        from current_bootfs import build
        lock = {'candidate_version': '0.0.0-idf61.0123456789ab', 'sources': {'product': {'revision': 'a'*40}}}
        store, _ = build(recipe.compose_store(BEFORE, OLD_NATIVE, lock), size=0x550000)
        new_bootloader = b'\xaa'*14032
        factory, transition = recipe.make_images(BASELINE, OLD_NATIVE, new_bootloader, store)
        self.assertNotEqual(factory[:0x8000], transition[:0x8000])
        self.assertEqual(transition[:0x10000], BASELINE[:0x10000])
        self.assertEqual(factory[0x9000:0xf000], BASELINE[0x9000:0xf000])
        self.assertEqual(factory[0x270000:0x2f0000], BASELINE[0x270000:0x2f0000])
        from prepare_preserving_update import plan
        with self.assertRaisesRegex(ValueError, 'Bootloader/partition mismatch'):
            plan(BASELINE, BASELINE, factory, CONTRACT['factory_sha256'])
        proof = preservation_model(BASELINE, transition, CONTRACT['factory_sha256'])
        self.assertEqual(proof['cases'], 496)
        self.assertFalse(proof['bootloader_compatibility_tested'])
        self.assertFalse(proof['hardware_tested'])

    def test_repeated_packing_is_identical(self):
        from current_bootfs import build
        first, record = build(BEFORE, size=0x550000)
        second, repeated = build(dict(reversed(list(BEFORE.items()))), size=0x550000)
        self.assertEqual(first, second)
        self.assertEqual(record, repeated)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], *REST])

"""Semantic custody negatives over real target deployments, never fixture firmware.

Run after the eight alarm deployment archives have been built. Set
TWATCH_MKSPIFFS for actual pack/unpack checks; ALARM_RUNTIME_ARTIFACT enables the
independent pinned Runtime CI ZIP checks during final assembly preparation.
"""
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_alarm_common as common
import build_alarm_store as image
import build_alarm_flash_bundle as flash


def refreshed(files):
    files = dict(files)
    record = json.loads(files.pop('deployment-record.json'))
    record['entries'] = [{'path': n, 'size_bytes': len(b), 'sha256': common.sha(b)}
                         for n, b in sorted(files.items())]
    files['deployment-record.json'] = common.encoded(record)
    return files


class AlarmCommonCustody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        version = json.loads((ROOT / 'apps/clock/manifest.json').read_text())['version']
        cls.archives = sorted((ROOT / 'dist/alarm-launcher-deployments').glob(
            'twatch-alarm-launcher-' + version + '-*.zip'))
        if len(cls.archives) != 8:
            raise RuntimeError('Build exactly eight current alarm target deployments before these tests')
        cls.head = json.loads(common.read_zip(cls.archives[0])['deployment-record.json'])['source_sha']
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.out = Path(cls.temporary.name)
        cls.row = common.build(cls.archives, cls.out / 'common', cls.head)
        cls.path = cls.out / 'common' / cls.row['archive']
        cls.files = common.read_zip(cls.path)

    def changed_inputs(self, directory, change, all_inputs=False):
        paths = []
        for index, original in enumerate(self.archives):
            if index and not all_inputs:
                paths.append(original)
                continue
            files = common.read_zip(original)
            change(files)
            path = Path(directory) / original.name
            path.write_bytes(common.zip_bytes(refreshed(files)))
            paths.append(path)
        return paths

    def reject_input(self, change, message, all_inputs=False):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.changed_inputs(directory, change, all_inputs)
            output = Path(directory) / 'output'
            with self.assertRaisesRegex((ValueError, AssertionError), message):
                common.build(paths, output, self.head)
            self.assertFalse(output.exists())

    def test_common_reconstructs_eight_exact_input_archives(self):
        record = common.verify(self.path, expected_head=self.head)
        self.assertEqual(record['source_sha'], self.head)
        self.assertEqual(record['pull_request_head_sha'], self.head)
        self.assertEqual(record['common_alarm_launcher']['store_files'], 38)
        self.assertEqual(len(record['common_alarm_launcher']['inputs']), 8)
        with tempfile.TemporaryDirectory() as directory:
            row = common.build(list(reversed(self.archives)), Path(directory), self.head)
            self.assertEqual(self.path.read_bytes(), (Path(directory) / row['archive']).read_bytes())

    def test_missing_duplicate_and_stale_head_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for archives, head in ((self.archives[:-1], self.head),
                                   ([self.archives[0], *self.archives[:-1]], self.head),
                                   (self.archives, '0' * 40)):
                with self.assertRaises(ValueError):
                    common.build(archives, Path(directory) / 'output', head)

    def test_rehashed_extra_file_and_board_drift_are_rejected(self):
        def extra(files):
            files['store/unexpected.elf'] = b'not authorized'
        self.reject_input(extra, 'exactly 38')
        def board(files):
            value = json.loads(files['store/board.json'])
            value['buses'][0]['frequency_hz'] += 1
            files['store/board.json'] = common.encoded(value)
        self.reject_input(board, 'wiring')
        def formatting(files):
            files['store/board.json'] += b'\n'
        self.reject_input(formatting, 'Noncanonical')

    def test_rehashed_stale_clock_and_shared_app_records_are_rejected(self):
        for name in ('default', 'clock', 'settings', 'stopwatch'):
            def change(files, name=name):
                metadata = json.loads(files['shared-app-build.json'])
                metadata['apps'][name]['repository_sha'] = '0' * 40
                files['shared-app-build.json'] = common.encoded(metadata)
            with self.subTest(app=name):
                self.reject_input(change, 'Stale application', all_inputs=True)

    def test_rehashed_service_and_driver_payloads_are_rejected(self):
        def service(files):
            data = files['store/alarm-service/driver.elf'] + b'changed'
            files['store/alarm-service/driver.elf'] = data
            metadata = json.loads(files['shared/alarm-service-build.json'])
            metadata.update(elf_sha256=common.sha(data), size_bytes=len(data))
            files['shared/alarm-service-build.json'] = common.encoded(metadata)
        self.reject_input(service, 'Canonical alarm service', all_inputs=True)
        def driver(files):
            files['store/rtc/driver.elf'] += b'changed'
        self.reject_input(driver, 'driver ELF differs', all_inputs=True)

    def test_rehashed_shared_pin_and_service_source_tampering_are_rejected(self):
        def pins(files):
            metadata = json.loads(files['shared-app-build.json'])
            metadata['shared_sources']['system-apps']['commit'] = '0' * 40
            files['shared-app-build.json'] = common.encoded(metadata)
        self.reject_input(pins, 'Shared source pins', all_inputs=True)
        def source(files):
            metadata = json.loads(files['shared/alarm-service-build.json'])
            metadata['source_sha256'] = '0' * 64
            files['shared/alarm-service-build.json'] = common.encoded(metadata)
        self.reject_input(source, 'Canonical alarm service', all_inputs=True)

    def test_common_custody_cannot_be_rehashed_to_hide_missing_source(self):
        files = dict(self.files)
        record = json.loads(files['deployment-record.json'])
        record['common_alarm_launcher']['inputs'][0]['sha256'] = '0' * 64
        files['deployment-record.json'] = common.encoded(record)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.zip'
            path.write_bytes(common.zip_bytes(refreshed(files)))
            with self.assertRaisesRegex(ValueError, 'Reconstructed original'):
                common.verify(path)

    @unittest.skipUnless(os.environ.get('TWATCH_MKSPIFFS'), 'Set TWATCH_MKSPIFFS for exact tool round-trip')
    def test_real_spiffs_round_trip_and_tampered_image(self):
        tool = Path(os.environ['TWATCH_MKSPIFFS'])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            metadata = image.build(self.path, tool, output)
            self.assertEqual(metadata['files'], 38)
            self.assertEqual(metadata['size_bytes'], 0x4f0000)
            expected = {n[6:]: b for n, b in self.files.items() if n.startswith('store/')}
            # Another internally valid SPIFFS image must not stand in for the deployment.
            expected['default.elf'] += b'different'
            with self.assertRaisesRegex(ValueError, 'round-trip differs'):
                image.check_image(output / metadata['image'], expected, tool)


class AlarmFlashCustody(unittest.TestCase):
    def test_source_requires_the_reviewed_tree_and_clean_tracked_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            source = root / 'source.c'
            source.write_text('reviewed source\n')
            subprocess.run(['git', 'add', 'source.c'], cwd=root, check=True)
            subprocess.run(['git', '-c', 'user.name=Test Fixture', '-c',
                            'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'],
                           cwd=root, check=True)
            tree = flash.git(root, 'rev-parse', 'HEAD^{tree}')
            flash.verify_watch_source(root, tree)
            with self.assertRaisesRegex(ValueError, 'reviewed tree'):
                flash.verify_watch_source(root, '0' * 40)
            source.write_text('unreviewed source\n')
            with self.assertRaisesRegex(ValueError, 'tracked modifications'):
                flash.verify_watch_source(root, tree)

    def test_external_ci_receipt_binds_head_tree_and_artifact(self):
        raw, head, tree = b'ci artifact', '1' * 40, '2' * 40
        receipt = {'repository': 'michaelrolphone-cmyk/RiscRTE-T-Watch-S3', 'head': head,
                   'tree': tree, 'conclusion': 'success', 'expired': False,
                   'artifact_name': 'twatch-alarm-integration-' + head,
                   'artifact_sha256': common.sha(raw), 'run_id': 123, 'artifact_id': 456}
        flash.verify_receipt(receipt, raw, head, tree)
        for key, value in (('head', '3' * 40), ('tree', '3' * 40), ('expired', True),
                           ('conclusion', 'failure'), ('artifact_sha256', '0' * 64),
                           ('run_id', True), ('artifact_name', 'twatch-launcher-deployments')):
            with self.subTest(field=key), self.assertRaises(ValueError):
                flash.verify_receipt({**receipt, key: value}, raw, head, tree)

    def test_partition_assembly_has_exact_components_and_erased_nvs(self):
        components = {'bootloader.bin': b'boot', 'partitions.bin': b'partitions',
                      'firmware.bin': b'runtime', 'bootfs.bin': b'\xa5' * image.SIZE}
        merged, parts = flash.assemble_components(components)
        self.assertEqual(len(merged), 0x800000)
        self.assertEqual(merged[0x9000:0xf000], b'\xff' * 0x6000)
        self.assertEqual(merged[image.OFFSET:], components['bootfs.bin'])
        self.assertEqual([p['offset'] for p in parts], ['0x0', '0x8000', '0x10000', '0x310000'])
        for name, replacement in (('bootloader.bin', b'x' * 0x8001),
                                   ('firmware.bin', b'x' * 0x300001),
                                   ('bootfs.bin', b'x')):
            with self.subTest(component=name), self.assertRaises(ValueError):
                flash.assemble_components({**components, name: replacement})

    @unittest.skipUnless(os.environ.get('ALARM_RUNTIME_ARTIFACT'), 'Set ALARM_RUNTIME_ARTIFACT for pinned Runtime CI checks')
    def test_exact_runtime_and_rehashed_wrong_components(self):
        path = Path(os.environ['ALARM_RUNTIME_ARTIFACT'])
        self.assertEqual(common.sha(path.read_bytes()), flash.RUNTIME_ZIP_SHA256)
        files = common.read_zip(path)
        self.assertEqual(flash.verify_runtime(files)['source_sha'], flash.RUNTIME_SHA)
        for name in flash.RUNTIME_ASSETS:
            modified = dict(files)
            altered = bytearray(modified[name])
            altered[-1] ^= 1
            modified[name] = bytes(altered)
            candidate = json.loads(modified['candidate.json'])
            candidate['assets'][name]['sha256'] = common.sha(modified[name])
            modified['candidate.json'] = common.encoded(candidate)
            with self.subTest(component=name), self.assertRaisesRegex(ValueError, 'Wrong pinned runtime'):
                flash.verify_runtime(modified)
        candidate = json.loads(files['candidate.json'])
        candidate['flash_bytes'] = 0x800000
        with self.assertRaisesRegex(ValueError, '16MiB pair'):
            flash.verify_runtime({**files, 'candidate.json': common.encoded(candidate)})


if __name__ == '__main__':
    unittest.main()

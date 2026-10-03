"""Common-store regressions use all eight real profiles and synthetic ELF fixtures.

Actual target ELFs are separately checked by the CI common builder and the
existing deployment/store verifiers. No fixture ELF is a deployable artifact.
"""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_clock_common as common
import build_clock_deployment as deployment
from verify_clock_deployment import verify


def elf_fixture(label):
    data = bytearray(52)
    data[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HH', data, 16, 3, 94)
    return bytes(data) + label.encode()


def write_zip(path, files):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)


class CommonClock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name) / 'inputs'
        cls.root.mkdir()
        for name in ('hardware', 'drivers', 'apps/clock/nova/fonts'):
            shutil.copytree(ROOT / name, cls.root / name)
        for name in ('board.json', 'apps/clock/manifest.json', 'apps/clock/runtime-requirements.json', 'sdk/app/SOURCES.json',
                     'releases/board-baseline.json', 'docs/CLOCK_INSTALL.md', 'docs/CROWN_SLEEP.md'):
            target = cls.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        (cls.root / 'dist/clock').mkdir(parents=True)
        (cls.root / 'dist/clock/default.elf').write_bytes(elf_fixture('synthetic-app'))
        packages = []
        for path in sorted((cls.root / 'drivers').glob('*/manifest.json')):
            manifest = json.loads(path.read_text())
            name = f"driver-{manifest['id']}-{manifest['version']}.rte.zip"
            archive = cls.root / 'dist' / name
            write_zip(archive, {'source-manifest.json': deployment.encoded(manifest),
                                'driver.elf': elf_fixture(manifest['id'])})
            packages.append({'id': manifest['id'], 'version': manifest['version'],
                             'archive': name, 'sha256': deployment.sha(archive.read_bytes())})
        (cls.root / 'dist/catalog.json').write_bytes(deployment.encoded({'packages': packages}))
        with patch.object(deployment.subprocess, 'check_output', return_value='a' * 40 + '\n'):
            for profile in sorted((cls.root / 'hardware').glob('*.json')):
                deployment.build(profile, root=cls.root)
        cls.archives = sorted((cls.root / 'dist/clock-deployments').glob('*.zip'))

    def mutate(self, directory, mutate):
        original = self.archives[0]
        with zipfile.ZipFile(original) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        record = json.loads(files.pop('deployment-record.json'))
        mutate(files, record)
        record['entries'] = [{'path': name, 'size_bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest()}
                             for name, data in sorted(files.items())]
        files['deployment-record.json'] = deployment.encoded(record)
        changed = Path(directory) / original.name
        write_zip(changed, files)
        return [changed, *self.archives[1:]]

    def test_all_eight_match_and_provenance_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            row = common.build(self.archives, out, self.root, pr_head_sha='c' * 40)
            archive = out / row['archive']
            record = verify(archive)
            self.assertEqual(row['sha256'], deployment.sha(archive.read_bytes()))
            self.assertEqual(record['source_sha'], 'a' * 40)
            self.assertEqual(record['pull_request_head_sha'], 'c' * 40)
            self.assertEqual(record['profile'], common.PROFILE)
            self.assertEqual(record['common_clock']['store_files'], 14)
            self.assertEqual(len(record['common_clock']['inputs']), 8)
            with zipfile.ZipFile(archive) as merged:
                self.assertNotIn('source-profile.json', merged.namelist())
                for name in deployment.NOVA_NOTICES:
                    self.assertEqual(merged.read('licenses/nova/' + name),
                                     (ROOT / 'apps/clock/nova/fonts' / name).read_bytes())
                self.assertEqual({n for n in merged.namelist() if n.startswith('store/')}, common.STORE_PATHS)
                self.assertEqual(json.loads(merged.read('store/board.json'))['revision'], common.PROFILE)
                for item, original in zip(record['common_clock']['inputs'], self.archives):
                    self.assertEqual(item['sha256'], deployment.sha(original.read_bytes()))
                    with zipfile.ZipFile(original) as source:
                        self.assertEqual(merged.read(f"sources/{item['profile']}/deployment-record.json"),
                                         source.read('deployment-record.json'))
                        self.assertEqual(merged.read(f"sources/{item['profile']}/source-profile.json"),
                                         source.read('source-profile.json'))
                        files = {name: source.read(name) for name in source.namelist()}
                        expected = common.normalized_store(files, item['profile'])
                        self.assertEqual({name: merged.read(name) for name in common.STORE_PATHS}, expected)
                        self.assertEqual(json.loads(source.read('store/board.json'))['revision'], item['profile'])
            second = common.build(list(reversed(self.archives)), out / 'second', self.root, pr_head_sha='c' * 40)
            self.assertEqual(row, second)
            self.assertEqual(archive.read_bytes(), (out / 'second' / second['archive']).read_bytes())

    def test_font_notices_are_mandatory_even_with_rehashed_membership(self):
        for notice in deployment.NOVA_NOTICES:
            def omit(files, record):
                del files['licenses/nova/' + notice]
            with self.subTest(notice=notice), tempfile.TemporaryDirectory() as directory:
                archives = self.mutate(directory, omit)
                with self.assertRaisesRegex(ValueError, 'Missing NOVA font license/provenance'):
                    verify(archives[0])

    def test_selected_wiring_driver_and_app_differences_are_rejected(self):
        def wiring(files, record):
            board = json.loads(files['store/board.json'])
            board['buses'][0]['frequency_hz'] = 200000
            files['store/board.json'] = deployment.encoded(board)

        def driver(files, record):
            files['store/panel/driver.elf'] += b'different-driver'

        def app(files, record):
            files['store/default.elf'] += b'different-app'

        def boot_bytes(files, record):
            files['store/boot.json'] += b'\n'

        for mutation in (wiring, driver, app, boot_bytes):
            with self.subTest(mutation=mutation.__name__), tempfile.TemporaryDirectory() as directory:
                archives = self.mutate(directory, mutation)
                verify(archives[0])  # Valid and rehashed individually; unsafe to collapse.
                with self.assertRaisesRegex(ValueError, 'Selected store differs'):
                    common.build(archives, Path(directory) / 'out', self.root)
                self.assertFalse((Path(directory) / 'out').exists())

    def test_only_revision_value_can_be_normalized(self):
        def whitespace(files, record):
            files['store/board.json'] += b'\n'
        with tempfile.TemporaryDirectory() as directory:
            archives = self.mutate(directory, whitespace)
            verify(archives[0])
            with self.assertRaisesRegex(ValueError, 'canonical deployment encoding'):
                common.build(archives, Path(directory) / 'out', self.root)

    def test_missing_duplicate_extra_file_and_mixed_generation_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'out'
            with self.assertRaisesRegex(ValueError, 'all eight'):
                common.build(self.archives[:-1], out, self.root)
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                common.build([self.archives[0], *self.archives[:-1]], out, self.root)

        def extra(files, record):
            files['store/unexpected.txt'] = b'not in the clock closure'

        def generation(files, record):
            record['source_sha'] = 'b' * 40

        for mutation, error in ((extra, '14 selected'), (generation, 'mix generations')):
            with self.subTest(mutation=mutation.__name__), tempfile.TemporaryDirectory() as directory:
                archives = self.mutate(directory, mutation)
                verify(archives[0])
                with self.assertRaisesRegex(ValueError, error):
                    common.build(archives, Path(directory) / 'out', self.root)

    def test_existing_verifier_rejects_corrupt_input_before_common_output(self):
        with tempfile.TemporaryDirectory() as directory:
            original = self.archives[0]
            with zipfile.ZipFile(original) as archive:
                files = {name: archive.read(name) for name in archive.namelist()}
            files['store/default.elf'] += b'not-rehashed'
            changed = Path(directory) / original.name
            write_zip(changed, files)
            with self.assertRaisesRegex(ValueError, 'checksum'):
                common.build([changed, *self.archives[1:]], Path(directory) / 'out', self.root)


if __name__ == '__main__':
    unittest.main()

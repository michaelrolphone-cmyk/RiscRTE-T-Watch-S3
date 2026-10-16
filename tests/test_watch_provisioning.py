import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import watch_provisioning as provisioning
from check_runtime_store_admission import admit_cohort
from current_bootfs import build as build_spiffs


@unittest.skipUnless(all(os.environ.get(name) for name in
                     ('WATCH_PROVISION_RUNTIME', 'WATCH_PROVISION_STORE', 'WATCH_PROVISION_SEED')),
                     'requires exact public provisioning inputs; run provisioning workflow')
class WatchProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = Path(os.environ['WATCH_PROVISION_RUNTIME']).resolve()
        cls.archive = Path(os.environ['WATCH_PROVISION_STORE']).resolve()
        cls.seed = Path(os.environ['WATCH_PROVISION_SEED']).resolve()
        cls.device, cls.profile = provisioning.runtime_tools(cls.runtime)
        cls.source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        cls.temporary = tempfile.TemporaryDirectory(prefix='watch-provision-test-')
        cls.parent = Path(cls.temporary.name)
        cls.payload = cls.parent / 'original'
        cls.receipt = provisioning.freeze(cls.runtime, cls.archive, cls.seed, cls.payload, cls.source)
        cls.original = provisioning.accepted_store(cls.archive, cls.profile)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.working = tempfile.TemporaryDirectory(dir=self.parent)
        self.root = Path(self.working.name)

    def tearDown(self):
        self.working.cleanup()

    def clone_payload(self):
        return Path(shutil.copytree(self.payload, self.root / 'payload'))

    def test_exact_accepted_bytes_and_native_binding(self):
        receipt, files = provisioning.verify_payload(self.runtime, self.payload, self.archive)
        self.assertEqual(receipt, self.receipt)
        self.assertEqual([n for n in files if files[n] != self.original[n]], [])
        self.assertEqual(len(files), 89)
        self.assertEqual(len([n for n in files if n.endswith('.elf')]), 43)
        self.assertEqual(receipt['feature_baseline'], '1.0.7')
        cohort = provisioning.parse(files['cohort.json'])
        self.assertEqual(cohort['version'], '1.0.7')
        self.assertEqual(cohort['firmware_sha256'], provisioning.FIRMWARE_SHA)
        boot = json.loads(files['boot.json'])
        original_boot = json.loads(self.original['boot.json'])
        self.assertEqual(boot, original_boot)

    def test_deterministic_seed_archive(self):
        second = self.root / 'second'
        provisioning.freeze(self.runtime, self.archive, self.seed, second, self.source)
        self.assertEqual({p.relative_to(self.payload).as_posix(): p.read_bytes()
                          for p in self.payload.rglob('*') if p.is_file()},
                         {p.relative_to(second).as_posix(): p.read_bytes()
                          for p in second.rglob('*') if p.is_file()})

    def test_actual_native_exports_and_full_graph_admission(self):
        files = self.profile.store_files(self.payload / 'files')
        native = (self.seed / 'firmware.elf').read_bytes()
        result = admit_cohort(self.runtime, native, files, files)
        self.assertEqual(result['elf_count'], 43)
        self.assertEqual(result['hardware_calls'], 0)
        self.assertEqual(result['storage_calls'], 0)
        for name in ('default.elf', 'pmu/driver.elf', 'board.json'):
            candidate = dict(files)
            candidate[name] = b'corrupt'
            rejected = admit_cohort(self.runtime, native, files, candidate, expected_valid=False)
            self.assertFalse(rejected['cohort_validated'])
        # Reusing historical migration authority would block self-validation
        # of this different product version before any target ELF is admitted.
        old_migration = dict(files)
        cohort = provisioning.parse(files['cohort.json']); cohort['version'] = '1.0.9'
        old_migration['cohort.json'] = provisioning.encode(cohort)
        rejected = admit_cohort(self.runtime, native, old_migration, old_migration, expected_valid=False)
        self.assertEqual(rejected['elf_count'], 0)

    def test_corrupt_archive_refused_before_output(self):
        bad = self.root / 'bad.zip'
        raw = bytearray(self.archive.read_bytes()); raw[-1] ^= 1; bad.write_bytes(raw)
        output = self.root / 'output'
        with self.assertRaisesRegex(ValueError, 'Accepted store ZIP differs'):
            provisioning.freeze(self.runtime, bad, self.seed, output, self.source)
        self.assertFalse(output.exists())

    def test_other_native_bytes_cannot_reuse_the_accepted_cohort(self):
        with self.assertRaisesRegex(ValueError, 'Cohort native image differs'):
            provisioning.verify(provisioning.parse(self.original['cohort.json']),
                                (self.seed / 'firmware.bin').read_bytes() + b'changed')

    def test_seed_firmware_corruption_refused(self):
        seed = Path(shutil.copytree(self.seed, self.root / 'seed'))
        firmware = bytearray((seed / 'firmware.bin').read_bytes())
        firmware[-1] ^= 1; (seed / 'firmware.bin').write_bytes(firmware)
        with self.assertRaisesRegex(ValueError, 'seed digest mismatch'):
            provisioning.freeze(self.runtime, self.archive, seed, self.root / 'output', self.source)
        self.assertFalse((self.root / 'output').exists())

    def test_self_consistent_non_generic_seed_is_refused(self):
        seed = Path(shutil.copytree(self.seed, self.root / 'seed'))
        record = json.loads((seed / 'seed.json').read_bytes())
        generic = {name: (seed / name).read_bytes() for name in ('board.json', 'boot.json', 'default.elf')}
        board = json.loads(generic['board.json']); board['board_id'] = 'different-board'
        generic['board.json'] = provisioning.encoded(board)
        image, _ = build_spiffs(generic)
        changes = {'board.json': generic['board.json'], 'bootfs0.bin': image,
                   'bank_state.bin': self.device.seed.initial_bank_state(
                       (seed / 'firmware.bin').read_bytes(), image, True)}
        for name, data in changes.items():
            (seed / name).write_bytes(data); record['assets'][name] = provisioning.metadata(data)
        (seed / 'seed.json').write_bytes(provisioning.encoded(record))
        (seed / 'SHA256SUMS').write_text(''.join(
            f'{provisioning.sha((seed / name).read_bytes())}  {name}\n'
            for name in sorted([*record['assets'], 'seed.json'])))
        with self.assertRaisesRegex(ValueError, 'Exact three-file generic seed store required'):
            provisioning.checked_seed(seed, self.device)

    def test_output_never_overwritten(self):
        with self.assertRaisesRegex(ValueError, 'output already exists'):
            provisioning.freeze(self.runtime, self.archive, self.seed, self.payload, self.source)

    def test_symlink_destination_refused(self):
        (self.root / 'link').symlink_to(self.payload, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            provisioning.freeze(self.runtime, self.archive, self.seed, self.root / 'link' / 'out', self.source)

    def test_caught_interruption_removes_only_partial_output(self):
        output = self.root / 'output'
        sentinel = self.root / 'keep'; sentinel.write_bytes(b'unchanged')
        real_write = provisioning.write_files
        def interrupted(directory, files):
            real_write(directory, dict(list(files.items())[:1]))
            raise KeyboardInterrupt()
        checked = provisioning.checked_seed(self.seed, self.device)
        with patch.object(provisioning, 'write_files', side_effect=interrupted):
            # Interrupt only output creation, after seed verification.
            with patch.object(provisioning, 'checked_seed', return_value=checked):
                with self.assertRaises(KeyboardInterrupt):
                    provisioning.freeze(self.runtime, self.archive, self.seed, output, self.source)
        self.assertFalse(output.exists())
        self.assertEqual(sentinel.read_bytes(), b'unchanged')

    def test_missing_completion_marker_refused(self):
        payload = self.clone_payload(); (payload / 'COMPLETE').unlink()
        with self.assertRaisesRegex(ValueError, 'Payload inventory differs'):
            provisioning.verify_payload(self.runtime, payload, self.archive)

    def test_extra_private_input_refused(self):
        payload = self.clone_payload(); (payload / 'wifi.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Payload inventory differs'):
            provisioning.verify_payload(self.runtime, payload, self.archive)

    def test_tampered_board_and_metadata_refused(self):
        payload = self.clone_payload()
        (payload / 'files' / 'board.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'Accepted product bytes changed'):
            provisioning.verify_payload(self.runtime, payload, self.archive)
        (payload / 'files' / 'board.json').write_bytes(self.original['board.json'])
        receipt = json.loads((payload / 'payload.json').read_bytes())
        receipt['extra'] = 'unexpected'; (payload / 'payload.json').write_bytes(provisioning.encoded(receipt))
        with self.assertRaisesRegex(ValueError, 'Payload receipt differs'):
            provisioning.verify_payload(self.runtime, payload, self.archive)

    def test_path_and_symlink_archive_members_refused(self):
        for name, mode in [('../escape', 0o100644), ('link', 0o120777)]:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                info = zipfile.ZipInfo(name); info.external_attr = mode << 16
                archive.writestr(info, b'x')
            with self.assertRaises(ValueError):
                provisioning.unpack(stream.getvalue(), self.profile)

    def test_bind_requires_real_exact_commit_and_pins_every_file(self):
        repository = self.root / 'repo'; repository.mkdir()
        subprocess.run(['git', 'init', '-q', str(repository)], check=True)
        destination = repository / provisioning.PAYLOAD_PATH
        shutil.copytree(self.payload, destination)
        subprocess.run(['git', 'add', '.'], cwd=repository, check=True)
        subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                        'commit', '-qm', 'Freeze test payload'], cwd=repository, check=True)
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repository, text=True).strip()
        output = self.root / 'deployment'
        with patch.object(provisioning, 'ROOT', repository):
            inventory = provisioning.bind(self.runtime, self.payload, self.archive, revision, output)
            with self.assertRaisesRegex(ValueError, 'Full payload commit required'):
                provisioning.bind(self.runtime, self.payload, self.archive, 'main', self.root / 'invalid')
        self.assertEqual(len(inventory['files']), 89)
        self.assertTrue(all('/' + revision + '/' in item['url'] for item in inventory['files']))
        self.assertIn('board.json', [item['path'] for item in inventory['files']])
        self.assertNotIn('wifi', json.loads((output / 'inventory.json').read_bytes()))
        self.assertEqual(json.loads((output / 'deployment.json').read_bytes())['seed_zip'], self.receipt['seed_zip'])


if __name__ == '__main__':
    unittest.main()

"""Board baseline provenance, no-bump protection and publication failure recovery."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import copy
import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import board_baseline as board
import publish_drivers as p


class BoardReleases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, data in board.inputs().items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (self.root / 'dist').mkdir()
        (self.root / 'dist/catalog.json').write_text('{"schema":1,"packages":[]}')
        self.sha = 'a' * 40
        self.value = '1.0.0'
        self.tag = p.tag_for(board.IDENTITY, self.value)
        self.plan = {'schema': 1, 'source_sha': self.sha,
                     'packages': p.candidates({board.IDENTITY: self.value}, [])}
        self.build()
        self.record = p.stage(self.plan, self.root)['packages'][0]

    def build(self):
        with patch.object(board.subprocess, 'check_output', return_value=self.sha + '\n'):
            board.build(self.root)

    def test_first_publish_and_deterministic_archive(self):
        self.assertEqual(len(self.plan['packages']), 1)
        self.assertEqual(self.record['kind'], 'board-baseline')
        first = (self.root / 'dist' / self.record['archive']).read_bytes()
        self.build()
        self.assertEqual(first, (self.root / 'dist' / self.record['archive']).read_bytes())
        with zipfile.ZipFile(self.root / 'dist' / self.record['archive']) as z:
            self.assertEqual(len([n for n in z.namelist() if n.startswith('hardware/')]), 8)
            provenance = json.loads(z.read('baseline-record.json'))
            self.assertEqual(provenance['source_sha'], self.sha)
            for entry in provenance['entries']:
                self.assertEqual(p.digest(z.read(entry['path'])), entry['sha256'])
            self.assertIn('sdk/driver/RiscHardwareConfigV1.h', z.namelist())
            self.assertIn('platform-resources.json', z.namelist())

    def test_unchanged_and_modified_without_bump(self):
        existing = [{'tag_name': self.tag, 'draft': False}]
        self.assertEqual(p.candidates({board.IDENTITY: self.value}, existing), [])
        def download(*args):
            (Path(args[args.index('--dir') + 1]) / 'release-record.json').write_text(json.dumps(self.record))
        with patch.object(p, 'gh', side_effect=download):
            p.verify_board_version('owner/repo', existing, self.root)
            for name in ('hardware/sx1262-433-bma423.json', 'docs/twatch-board-v1.schema.json',
                         'platform-resources.json', 'sdk/driver/RiscHardwareConfigV1.h'):
                with self.subTest(name=name):
                    path = self.root / name
                    original = path.read_bytes()
                    path.write_bytes(original + b'\n')
                    with self.assertRaises(ValueError):
                        p.verify_board_version('owner/repo', existing, self.root)
                    path.write_bytes(original)

    def test_optional_reset_rules_in_both_schemas(self):
        original = json.loads((self.root / 'hardware/sx1262-433-bma423.json').read_text())
        for schema_name in ('board-manifest-v1.schema.json', 'twatch-board-v1.schema.json'):
            validator = jsonschema.Draft202012Validator(json.loads((self.root / 'docs' / schema_name).read_text()))
            for config_type in ('display.spi', 'touch.i2c'):
                profile = copy.deepcopy(original)
                profile['devices'] = [next(d for d in profile['devices'] if d['config_type'] == config_type)]
                config = profile['devices'][0]['config']
                for pin, delay, valid in [(-1, 0, True), (-1, 1, False), (7, 0, False),
                                          (7, 1, True), (7, 500, True), (7, 501, False)]:
                    with self.subTest(schema=schema_name, type=config_type, pin=pin, delay=delay):
                        config.update(reset=pin, reset_assert_ms=delay, reset_recovery_ms=delay)
                        self.assertEqual(validator.is_valid(profile), valid)

    def test_bumped_version_is_new_candidate(self):
        self.assertEqual(p.candidates({board.IDENTITY: '1.0.1'}, [
            {'tag_name': self.tag, 'draft': False}])[0]['tag'], 'board-lilygo-t-watch-s3-v1.0.1')

    def test_incorrect_record_rejected(self):
        manifest, _, _, fingerprint = board.snapshot(self.root)
        for key, value in [('kind', 'driver'), ('id', 'other'), ('version', '2.0.0'), ('source_digest', 'bad')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                board.verify_record({**self.record, key: value}, manifest, fingerprint)

    def test_source_changed_after_build(self):
        path = self.root / 'board.json'
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'exact source baseline'):
            p.stage(self.plan, self.root)

    def test_archive_corruption(self):
        (self.root / 'dist' / self.record['archive']).write_bytes(b'corrupted')
        with self.assertRaises(ValueError):
            p.stage(self.plan, self.root)

    def test_version_namespace_collision(self):
        with self.assertRaisesRegex(ValueError, 'namespace'):
            p.candidates({board.IDENTITY: self.value}, [
                {'tag_name': f'driver-{board.IDENTITY}-v{self.value}', 'draft': False}])

    def test_interrupted_upload_resume_and_uploaded_byte_verification(self):
        remote = []
        stored = {}
        fail_record = True
        corrupt_download = False
        def fake_gh(*args):
            nonlocal fail_record
            if args[0] == 'api' and '--method' in args:
                remote.append({'tag_name': self.tag, 'target_commitish': self.sha,
                               'draft': True, 'assets': []})
                return json.dumps(remote[0])
            elif args[:2] == ('release', 'upload'):
                file = Path(args[3])
                if file.name == 'release-record.json' and fail_record:
                    fail_record = False
                    raise RuntimeError('simulated interrupted upload')
                self.assertNotIn(file.name, stored)  # no overwrite, even on retry
                stored[file.name] = file.read_bytes()
                remote[0]['assets'].append({'name': file.name})
            elif args[:2] == ('release', 'download'):
                names = [args[args.index('--pattern') + 1]] if '--pattern' in args else stored
                for name in names:
                    value = b'corrupt' if corrupt_download else stored[name]
                    (Path(args[args.index('--dir') + 1]) / name).write_bytes(value)
            elif args[:2] == ('release', 'edit'):
                self.assertEqual(set(stored), {self.record['archive'], 'release-record.json'})
                remote[0]['draft'] = False
            elif args[0] == 'api':
                return json.dumps({'sha': self.sha})
            return ''
        with patch.object(p, 'ROOT', self.root), patch.object(p, 'verify_existing_tag'), \
             patch.object(p, 'releases', side_effect=lambda repo: remote), \
             patch.object(p, 'gh', side_effect=fake_gh):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                p.publish_one('owner/repo', self.record)
            self.assertTrue(remote[0]['draft'])
            self.assertEqual(len(stored), 1)
            corrupt_download = True
            with self.assertRaises(ValueError):
                p.publish_one('owner/repo', self.record)
            self.assertTrue(remote[0]['draft'])
            corrupt_download = False
            p.publish_one('owner/repo', self.record)
            self.assertFalse(remote[0]['draft'])
            p.publish_one('owner/repo', self.record)  # completed retry verifies bytes
            stored[self.record['archive']] = b'collision'
            with self.assertRaisesRegex(ValueError, 'refusing overwrite'):
                p.publish_one('owner/repo', self.record)


if __name__ == '__main__':
    unittest.main()

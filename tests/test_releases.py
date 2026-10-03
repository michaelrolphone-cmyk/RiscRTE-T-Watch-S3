"""Offline tests: version planning, artifact custody, resumable publication."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).resolve().parents[1] / 'scripts/publish_drivers.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def release(v='1.0.0', draft=False):
    return {'tag_name': f'driver-test-v{v}', 'draft': draft}


class Planning(unittest.TestCase):
    def test_initial(self):
        self.assertEqual(len(p.candidates({'test': '1.0.0'}, [])), 1)

    def test_unchanged(self):
        self.assertEqual(p.candidates({'test': '1.0.0'}, [release()]), [])

    def test_numeric_increment(self):
        self.assertEqual(len(p.candidates({'test': '1.10.0'}, [release('1.9.0')])), 1)

    def test_rollback(self):
        with self.assertRaises(ValueError):
            p.candidates({'test': '0.9.0'}, [release()])

    def test_resume_draft(self):
        self.assertEqual(len(p.candidates({'test': '1.0.0'}, [release(draft=True)])), 1)

    def test_duplicate_release(self):
        with self.assertRaises(ValueError):
            p.candidates({'test': '1.0.0'}, [release(), release()])

    def test_version_format(self):
        for value in ['01.0.0', '1.2', '1.0.0-beta', None, '1.0.0\n']:
            with self.assertRaises(ValueError):
                p.version(value)

    def test_independent_packages(self):
        self.assertEqual([x['id'] for x in p.candidates(
            {'test': '1.0.0', 'other': '0.1.0'}, [release()])], ['other'])


class Custody(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'dist').mkdir()
        self.name = 'driver-test-1.0.0-xtensa-esp32s3.rte.zip'
        self.path = self.root / 'dist' / self.name
        self.plan = {'source_sha': 'a' * 40, 'packages': p.candidates({'test': '1.0.0'}, [])}
        self.make_archive()

    def make_archive(self, embedded_version='1.0.0', bad_payload=False):
        payload = b'fixture ELF'
        manifest = {'id': 'test', 'version': embedded_version, 'architecture': 'xtensa-esp32s3',
                    'kind': 'driver', 'entries': [{'name': 'driver.elf', 'size_bytes': len(payload),
                    'sha256': hashlib.sha256(payload).hexdigest()}]}
        with zipfile.ZipFile(self.path, 'w') as z:
            z.writestr('.package.json', json.dumps(manifest))
            z.writestr('driver.elf', b'corrupted' if bad_payload else payload)
        self.record = dict(id='test', version='1.0.0', kind='driver', architecture='xtensa-esp32s3',
                           archive=self.name, size_bytes=self.path.stat().st_size,
                           sha256=p.digest(self.path.read_bytes()))
        (self.root / 'dist/catalog.json').write_text(json.dumps({'packages': [self.record]}))

    def test_valid(self):
        self.assertEqual(p.stage(self.plan, self.root)['packages'][0]['source_sha'], 'a' * 40)

    def test_tampered_archive(self):
        self.path.write_bytes(b'tamper')
        with self.assertRaises(ValueError):
            p.stage(self.plan, self.root)

    def test_wrong_embedded_version(self):
        self.make_archive(embedded_version='2.0.0')
        with self.assertRaises(ValueError):
            p.stage(self.plan, self.root)

    def test_tampered_payload(self):
        self.make_archive(bad_payload=True)
        with self.assertRaises(ValueError):
            p.stage(self.plan, self.root)

    def test_draft_resume_and_immutable_retries(self):
        record = p.stage(self.plan, self.root)['packages'][0]
        remote = {'tag_name': record['tag'], 'target_commitish': 'a' * 40, 'draft': True, 'assets': []}
        stored = {}
        calls = []
        def fake_gh(*args):
            calls.append(args)
            if args[:2] == ('release', 'upload'):
                file = Path(args[3]); stored[file.name] = file.read_bytes()
                remote['assets'].append({'name': file.name})
            elif args[:2] == ('release', 'download'):
                dest = Path(args[args.index('--dir') + 1])
                names = [args[args.index('--pattern') + 1]] if '--pattern' in args else stored
                for name in names:
                    (dest / name).write_bytes(stored[name])
            elif args[:2] == ('release', 'edit'):
                remote['draft'] = False
            elif args[0] == 'api':
                return json.dumps({'sha': 'a' * 40})
            return ''
        with patch.object(p, 'ROOT', self.root), patch.object(p, 'verify_existing_tag'), \
             patch.object(p, 'releases', return_value=[remote]), patch.object(p, 'gh', side_effect=fake_gh):
            p.publish_one('owner/repo', record)
            self.assertFalse(remote['draft'])
            uploads = len([c for c in calls if c[:2] == ('release', 'upload')])
            p.publish_one('owner/repo', record)
            self.assertEqual(uploads, len([c for c in calls if c[:2] == ('release', 'upload')]))
            stored[self.name] = b'tamper'
            with self.assertRaises(ValueError):
                p.publish_one('owner/repo', record)

    def test_first_publication_creates_draft(self):
        record = p.stage(self.plan, self.root)['packages'][0]
        remote = {'tag_name': record['tag'], 'target_commitish': 'a' * 40, 'draft': True, 'assets': []}
        stored = {}
        def fake_gh(*args):
            if args[:2] == ('release', 'create'):
                self.assertIn('--draft', args)
                self.assertEqual(args[args.index('--target') + 1], 'a' * 40)
            elif args[:2] == ('release', 'upload'):
                file = Path(args[3]); stored[file.name] = file.read_bytes()
            elif args[:2] == ('release', 'download'):
                for name, data in stored.items():
                    (Path(args[args.index('--dir') + 1]) / name).write_bytes(data)
            elif args[:2] == ('release', 'edit'):
                self.assertEqual(set(stored), {self.name, 'release-record.json'})
            elif args[0] == 'api':
                return json.dumps({'sha': 'a' * 40})
            return ''
        with patch.object(p, 'ROOT', self.root), patch.object(p, 'verify_existing_tag'), \
             patch.object(p, 'releases', side_effect=[[], [remote]]), \
             patch.object(p, 'gh', side_effect=fake_gh) as gh:
            p.publish_one('owner/repo', record)
            self.assertEqual(gh.call_args_list[0].args[:2], ('release', 'create'))

    def test_draft_from_different_commit(self):
        record = p.stage(self.plan, self.root)['packages'][0]
        remote = {'tag_name': record['tag'], 'target_commitish': 'b' * 40, 'draft': True}
        with patch.object(p, 'verify_existing_tag'), patch.object(p, 'releases', return_value=[remote]), \
             patch.object(p, 'gh') as gh:
            with self.assertRaises(ValueError):
                p.publish_one('owner/repo', record)
            gh.assert_not_called()


if __name__ == '__main__':
    unittest.main()

import copy
import importlib.util
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import watch_release_index as idx
import publish_watch_product as pub


def app(version='0.5.2'):
    return pub.record('app', 'default', version, 'default.elf', b'accepted-elf',
                      manifest={'type': 'application', 'version': version, 'file_name': 'default.elf',
                                'architecture': 'xtensa-esp32s3'})


class IndexTests(unittest.TestCase):
    def test_add_idempotent_preserve(self):
        index = {**copy.deepcopy(idx.EMPTY_INDEX), 'services': [{'id': 'kept'}], 'providers': []}
        result = idx.update_index(index, 'apps', app())
        self.assertEqual(result['services'], [{'id': 'kept'}])
        self.assertEqual(result, idx.update_index(result, 'apps', app()))
        self.assertEqual(index['apps'], [])

    def test_immutable_and_rollback(self):
        result = idx.update_index(copy.deepcopy(idx.EMPTY_INDEX), 'apps', app())
        changed = app(); changed['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Immutable'):
            idx.update_index(result, 'apps', changed)
        with self.assertRaisesRegex(ValueError, 'rollback'):
            idx.update_index(result, 'apps', app('0.5.1'))
        self.assertEqual(idx.update_index(result, 'apps', app('0.5.3'))['apps'][0]['version'], '0.5.3')

    def test_wrong_urls_tags_assets_versions(self):
        for key, value in [('url', 'https://example.com/default.elf'), ('tag', 'app-default-v9.0.0'),
                           ('asset', '../default.elf'), ('version', '01.0.0'), ('size', True),
                           ('sha256', 'f' * 63), ('source_repo', 'other/repository')]:
            with self.subTest(key=key):
                r = app(); r[key] = value
                with self.assertRaises(ValueError): idx.validate_record('apps', r)

    def test_duplicate_identity(self):
        index = copy.deepcopy(idx.EMPTY_INDEX); index['apps'] = [app(), app()]
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            idx.update_index(index, 'apps', app())

    def test_firmware(self):
        r = pub.record('firmware', '', '1.0.0', 'twatch-s3-launcher-1.0.0.bin', b'bin')
        result = idx.update_index(copy.deepcopy(idx.EMPTY_INDEX), 'firmware', r)
        self.assertEqual(result, idx.update_index(result, 'firmware', r))
        changed = {**r, 'sha256': 'a' * 64}
        with self.assertRaisesRegex(ValueError, 'Immutable'):
            idx.update_index(result, 'firmware', changed)


class ArtifactTests(unittest.TestCase):
    def test_product_pins(self):
        p = pub.read_config()
        self.assertEqual(p['accepted_bin_sha256'], '6f0cba6da17fce769d03807aefce44b0e5fc445d349b8b7dc0f6782d376d80c5')
        self.assertEqual(p['version'], '1.0.0')
        self.assertEqual(p['component_versions']['default'], '0.5.2')
        self.assertEqual(p['component_versions']['runtime'], '0.1.6')
        self.assertNotIn(5, p['contributing_pull_requests']['RiscRTE'])
        self.assertNotIn(9, p['contributing_pull_requests']['RiscRTE-T-Watch-S3'])

    def test_zip_paths_and_duplicates(self):
        for name in ('../bad', '/absolute'):
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                pub.checked_zip(pub.archive({name: b'x'}))
        z = pub.checked_zip(pub.archive({'safe/file': b'data'}))
        self.assertEqual(z.read('safe/file'), b'data')
        z.close()

    def test_release_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = app(); output = Path(tmp)
            release = pub.write_release(output, r, {'default.elf': b'elf', 'default.json': b'{}'}, 'a' * 40, False)
            self.assertIn('SHA256SUMS', release['assets'])
            self.assertIn(pub.sha(b'elf'), (output / r['tag'] / 'SHA256SUMS').read_text())

    def test_download_verifies_full_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'inventory'):
                pub.verify_downloads({'assets': [{'name': 'bad'}]}, {'expected': {}}, Path(tmp) / 'unused')


class PublicationTests(unittest.TestCase):
    def release(self):
        return {'tag': 'app-default-v0.5.2', 'source_sha': 'a' * 40, 'latest': False,
                'assets': {'default.elf': {'size': 3, 'sha256': pub.sha(b'elf')}}}

    def test_wrong_existing_source_refuses_before_upload(self):
        existing = {'tag_name': 'app-default-v0.5.2', 'target_commitish': 'b' * 40, 'assets': [], 'draft': True}
        no_tag = __import__('subprocess').CompletedProcess([], 1, b'', b'HTTP 404')
        with patch.object(pub, 'release_by_tag', return_value=existing), patch.object(pub.subprocess, 'run', return_value=no_tag), patch.object(pub, 'gh') as gh:
            with self.assertRaisesRegex(ValueError, 'source collision'):
                pub.publish_one(self.release(), Path('/unused'))
            gh.assert_not_called()

    def test_published_missing_asset_refuses(self):
        existing = {'tag_name': 'app-default-v0.5.2', 'target_commitish': 'a' * 40, 'assets': [], 'draft': False}
        no_tag = __import__('subprocess').CompletedProcess([], 1, b'', b'HTTP 404')
        with patch.object(pub, 'release_by_tag', return_value=existing), patch.object(pub.subprocess, 'run', return_value=no_tag), patch.object(pub, 'gh') as gh:
            with self.assertRaisesRegex(ValueError, 'missing assets'):
                pub.publish_one(self.release(), Path('/unused'))
            gh.assert_not_called()

    def test_tag_collision_refuses(self):
        present = __import__('subprocess').CompletedProcess([], 0, b'{}', b'')
        with patch.object(pub, 'release_by_tag', return_value=None), patch.object(pub.subprocess, 'run', return_value=present), patch.object(pub, 'api', return_value={'sha': 'b' * 40}), patch.object(pub, 'gh') as gh:
            with self.assertRaisesRegex(ValueError, 'tag source collision'):
                pub.publish_one(self.release(), Path('/unused'))
            gh.assert_not_called()


class DraftFlowTests(unittest.TestCase):
    def test_upload_by_id_verify_then_publish_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            r = app()
            release = pub.write_release(root, r, {'default.elf': b'elf', 'release-record.json': pub.encoded(r)}, 'a' * 40, False)
            state = {'id': 42, 'tag_name': r['tag'], 'target_commitish': 'a' * 40,
                     'draft': True, 'prerelease': False, 'assets': [], 'html_url': 'https://example.test/release'}
            stored, calls = {}, []
            def fake_gh(*args):
                calls.append(args)
                self.assertEqual(args[0], 'api')
                endpoint = args[1]
                if '--input' in args:
                    path = Path(args[args.index('--input') + 1])
                    self.assertIn('/releases/42/assets?', endpoint)
                    self.assertNotIn(path.name, stored)
                    stored[path.name] = path.read_bytes()
                    state['assets'].append({'id': len(stored), 'name': path.name})
                    return pub.encoded(state['assets'][-1])
                if '/releases/assets/' in endpoint:
                    n = int(endpoint.rsplit('/', 1)[1])
                    name = next(x['name'] for x in state['assets'] if x['id'] == n)
                    return stored[name]
                if 'draft=false' in args:
                    self.assertEqual(set(stored), set(release['assets']))
                    self.assertGreaterEqual(len([c for c in calls if '/releases/assets/' in c[1]]), len(stored))
                    state['draft'] = False
                    return pub.encoded(state)
                self.assertIn('draft=true', args)
                return pub.encoded(state)
            def fake_api(endpoint):
                return {'sha': 'a' * 40} if '/commits/' in endpoint else copy.deepcopy(state)
            no_tag = __import__('subprocess').CompletedProcess([], 1, b'', b'HTTP 404')
            with patch.object(pub, 'release_by_tag', side_effect=[None, copy.deepcopy(state)]), patch.object(pub, 'api', side_effect=fake_api), patch.object(pub, 'gh', side_effect=fake_gh), patch.object(pub.subprocess, 'run', return_value=no_tag):
                pub.publish_one(release, root)
                self.assertFalse(state['draft'])
            uploads = len([c for c in calls if '--input' in c])
            with patch.object(pub, 'release_by_tag', return_value=copy.deepcopy(state)), patch.object(pub, 'api', side_effect=fake_api), patch.object(pub, 'gh', side_effect=fake_gh), patch.object(pub.subprocess, 'run', return_value=no_tag):
                pub.publish_one(release, root)
            self.assertEqual(uploads, len([c for c in calls if '--input' in c]))


@unittest.skipUnless(os.environ.get('WATCH_PRODUCT_STAGE'), 'Exact staged artifact supplied after stage')
class StageNegativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.stage = Path(self.temp.name) / 'stage'
        shutil.copytree(os.environ['WATCH_PRODUCT_STAGE'], self.stage)
        self.plan_path = self.stage / 'publication-plan.json'
        self.plan = json.loads(self.plan_path.read_text())

    def write_plan(self):
        self.plan_path.write_bytes(pub.encoded(self.plan))

    def test_exact(self):
        pub.verify_stage(self.stage)

    def test_bin_plus_metadata_tamper(self):
        r = next(r for r in self.plan['releases'] if r['latest'])
        name = self.plan['index']['firmware']['asset']
        path = self.stage / r['tag'] / name
        data = bytearray(path.read_bytes()); data[500] ^= 1; path.write_bytes(data)
        r['assets'][name] = {'size': len(data), 'sha256': pub.sha(data)}
        self.write_plan()
        with self.assertRaises(ValueError): pub.verify_stage(self.stage)

    def test_omitted_drivers(self):
        self.plan['driver_records'] = []; self.write_plan()
        with self.assertRaises(ValueError): pub.verify_stage(self.stage)

    def test_arbitrary_source(self):
        self.plan['releases'][0]['source_sha'] = 'b' * 40; self.write_plan()
        with self.assertRaises(ValueError): pub.verify_stage(self.stage)

    def test_wrong_latest(self):
        self.plan['releases'][0]['latest'] = True; self.write_plan()
        with self.assertRaises(ValueError): pub.verify_stage(self.stage)

    def test_index_mismatch(self):
        self.plan['index']['firmware']['sha256'] = '0' * 64; self.write_plan()
        with self.assertRaises(ValueError): pub.verify_stage(self.stage)

    def test_flashing_text_tamper(self):
        r = next(r for r in self.plan['releases'] if r['latest'])
        path = self.stage / r['tag'] / 'FLASHING.md'
        data = path.read_bytes() + b'\nInjected extra instruction\n'; path.write_bytes(data)
        r['assets']['FLASHING.md'] = {'size': len(data), 'sha256': pub.sha(data)}
        self.write_plan()
        with self.assertRaises(ValueError): pub.verify_stage(self.stage)


if __name__ == '__main__':
    unittest.main()

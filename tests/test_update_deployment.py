"""Exercise real built update ELFs and reject rehashed privilege/custody mutations."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from build_clock_deployment import build as build_deployment, encoded
from build_update_common import build as build_common, verify as verify_common, zip_bytes
from build_wifi_common import read_zip, sha
from verify_update_deployment import grants, verify, verify_files
from verify_wifi_deployment import verify as verify_current_wifi


class UpdateAuthority(unittest.TestCase):
    def test_exact_eight_grants_kind_split_and_paths(self):
        for app, capability in [('ota_update', 'software.update.firmware'), ('app_store', 'software.update.apps')]:
            policy = grants(app)
            self.assertEqual(len(policy), 8)
            self.assertEqual(policy[4], {'capability': 'storage.key-value', 'api': 1, 'instance_id': 6})
            self.assertEqual(policy[5], {'capability': 'net.wifi', 'api': 1, 'instance_id': 15})
            self.assertEqual(policy[6], {'capability': capability, 'api': 1, 'instance_id': 0})
            self.assertFalse(any(g['capability'].startswith('platform.') for g in policy))
        for short in ('update-fw', 'update-apps'):
            for name in ('driver.elf', 'manifest.json'):
                self.assertLess(len(('/'+short+'/'+name).encode()), 32)

    def test_frozen_wifi_lane_byte_identity_when_built(self):
        paths = sorted((ROOT/'dist/wifi-launcher-deployments').glob('*.zip'))
        if not paths:
            self.skipTest('Frozen Wi-Fi lane is verified when its separate build is present')
        self.assertEqual(len(paths), 8)
        baseline = json.loads((ROOT/'scripts/update-preservation-baseline.json').read_text())
        for path in paths:
            files = read_zip(path)
            record = json.loads(files['deployment-record.json'])
            store = {n[6:]: b for n, b in files.items() if n.startswith('store/')}
            self.assertEqual(len(store), 44)
            if record['source_sha'] != baseline['watch_source_sha']:
                # Current builds have explicitly versioned Clock/PMU changes.
                # Their own verifier retains exact preserved executable checks.
                verify_current_wifi(path)
                continue
            for name, expected in baseline['files'].items():
                self.assertEqual(sha(store[name]), expected['sha256'], (path.name, name))
                self.assertEqual(len(store[name]), expected['size_bytes'], (path.name, name))
            profile = next(p for p in baseline['inputs'] if p['profile'] == record['profile'])
            self.assertEqual(sha(store['board.json']), profile['board_sha256'])

    def test_invalid_update_selections_fail_before_io(self):
        for selected in [('app_store',), ('ota_update', 'ota_update'), ('app_store', 'ota_update'), ('unknown',)]:
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                build_deployment(Path('/does-not-exist'), wifi=True, updates=selected)
        with self.assertRaises(ValueError):
            build_deployment(Path('/does-not-exist'), updates=())


class UpdateDeployment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = Path(os.environ.get('UPDATE_DEPLOYMENT_DIR', ROOT/'dist/update-launcher-deployments'))
        cls.paths = sorted(directory.glob('*.zip'))
        if len(cls.paths) != 8:
            raise RuntimeError('Build all eight update deployment archives before running integration fixtures')
        cls.files = read_zip(cls.paths[0])
        cls.record = json.loads(cls.files['deployment-record.json'])
        cls.selected = tuple(cls.record['updates']['apps'])

    def test_eight_profiles_and_preserved_inventory(self):
        profiles = set()
        for path in self.paths:
            record = verify(path)
            profiles.add(record['profile'])
            self.assertEqual(record['updates']['apps'], list(self.selected))
        self.assertEqual(len(profiles), 8)
        self.assertEqual(len([n for n in self.files if n.startswith('store/')]), 44+4*len(self.selected))

    def mutation_rejected(self, mutate):
        files = dict(self.files)
        mutate(files)
        record = json.loads(files['deployment-record.json'])
        record['entries'] = [{'path': n, 'size_bytes': len(b), 'sha256': sha(b)}
                             for n, b in sorted(files.items()) if n != 'deployment-record.json']
        files['deployment-record.json'] = encoded(record)
        with self.assertRaises((ValueError, KeyError)):
            verify_files(files)

    @staticmethod
    def edit_json(files, name, edit):
        value = json.loads(files[name])
        edit(value)
        files[name] = encoded(value)

    def test_rehashed_existing_grant_changes_rejected(self):
        for grant in [{'capability': 'platform.http-client', 'api': 1, 'instance_id': 0},
                      {'capability': 'storage.key-value', 'api': 1, 'instance_id': 6}]:
            with self.subTest(grant=grant):
                self.mutation_rejected(lambda f: self.edit_json(f, 'store/boot.json',
                    lambda boot: boot['app_capabilities'][0]['grants'].append(grant)))

    def test_rehashed_new_grant_and_provider_changes_rejected(self):
        if not self.selected:
            self.skipTest('Paired-only stage has no updater authority')
        for grant_index, field, value in [(4, 'instance_id', 1), (5, 'instance_id', 0),
                                         (6, 'capability', 'platform.bank-store'), (6, 'instance_id', 1)]:
            with self.subTest(index=grant_index, value=value):
                self.mutation_rejected(lambda f: self.edit_json(f, 'store/boot.json',
                    lambda boot: boot['app_capabilities'][-1]['grants'][grant_index].update({field: value})))
        self.mutation_rejected(lambda f: self.edit_json(f, 'store/boot.json',
            lambda boot: boot['drivers'][-1].update(key_value=[{'key': 'wifi_cfg', 'namespace': 6, 'access': 'read'}])))
        self.mutation_rejected(lambda f: self.edit_json(f, 'store/update-fw/manifest.json',
            lambda manifest: manifest['provides'][0].update(capability='software.update.apps')))
        self.mutation_rejected(lambda f: self.edit_json(f, 'shared/update-fw-build.json',
            lambda record: record['source_sha256'].update({'Services/update/service.cpp': '0'*64})))

    def test_provider_target_cannot_be_rehashed_away(self):
        if not self.selected:
            self.skipTest('Paired-only stage has no update provider')
        def mutate(files):
            name = 'store/update-fw/driver.elf'
            files[name] += b'unreviewed target bytes'
            self.edit_json(files, 'shared/update-fw-build.json',
                           lambda r: r.update(sha256=sha(files[name]), size_bytes=len(files[name])))
            self.edit_json(files, 'shared/update-build.json',
                           lambda r: r['providers']['ota_update'].update(sha256=sha(files[name])))
        self.mutation_rejected(mutate)

    def test_unchanged_executable_cannot_be_rehashed_away(self):
        def mutate(files):
            data = files['store/clock.elf']+b'changed'
            files['store/clock.elf'] = data
            self.edit_json(files, 'shared-app-build.json',
                           lambda record: record['apps']['clock'].update(sha256=sha(data)))
        self.mutation_rejected(mutate)
        self.mutation_rejected(lambda files: files.pop('store/wifi/driver.elf'))
        self.mutation_rejected(lambda files: files.update({'store/new-app.elf': b'unapproved'}))

    def test_layout_source_versions_and_catalog_fail_closed(self):
        mutations = [
            ('runtime-requirements.json', lambda r: r['deployment'].update(existing_8MiB_ota_compatible=True)),
            ('store/default.json', lambda m: m.update(version='0.7.0')),
            ('shared/update-sources.json', lambda p: p['runtime'].update(commit='0'*40)),
            ('shared/catalog.json', lambda c: c.append({'file_name': 'unapproved.elf'})),
            ('shared-app-build.json', lambda m: m.update(return_targets={})),
            ('store/board.json', lambda b: b['devices'][0].update(instance_id=99)),
        ]
        for name, edit in mutations:
            with self.subTest(name=name):
                self.mutation_rejected(lambda f: self.edit_json(f, name, edit))

    def test_common_reconstructs_all_eight_and_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = build_common(self.paths, Path(tmp), self.record['source_sha'])
            archive = Path(tmp)/row['archive']
            record = verify_common(archive, expected_head=self.record['source_sha'])
            self.assertEqual(len(record['common_update_launcher']['inputs']), 8)
            files = read_zip(archive)
            record['common_update_launcher']['inputs'][0]['sha256'] = '0'*64
            files['deployment-record.json'] = encoded(record)
            archive.write_bytes(zip_bytes(files))
            with self.assertRaises(ValueError):
                verify_common(archive)
            with self.assertRaises(ValueError):
                build_common(self.paths[:-1], Path(tmp)/'missing', self.record['source_sha'])
            with self.assertRaises(ValueError):
                build_common([self.paths[0]]*8, Path(tmp)/'duplicate', self.record['source_sha'])


if __name__ == '__main__':
    unittest.main()

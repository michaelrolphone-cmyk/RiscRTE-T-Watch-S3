"""RF packaging guards use actual accepted custody, without generating images."""
import copy
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_rf_watch_candidate as builder
import rf_watch_candidate as candidate
import test_rf_watch_upgrade as upgrade
from current_apps_overlay import APPS, config, configure_board, encoded, payloads
from current_cohort import create, encode
from rf_spectrum_profile import PRIVATE_GRANTS, RUNTIME_SOURCE, upgrade_boot


class RfCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.origin = candidate.accepted()
        cls.configuration = config(profile='rf-spectrum')
        cls.firmware = cls.origin['full'][0x10000:0x10000 + cls.origin['identity']['firmware_size']]

    def fixture(self):
        following = dict(self.origin['store'])
        for name in APPS:
            manifest = candidate.document(following[name + '.json'])
            manifest['version'] = self.configuration['app_versions'][name]
            if name == 'waterfall':
                manifest['requires'] += [{k: g[k] for k in ('capability', 'api')} for g in PRIVATE_GRANTS]
            following[name + '.json'] = encoded(manifest)
        manifest = candidate.document(following['s3-radio-iq/manifest.json'])
        manifest['version'] = '0.2.0';following['s3-radio-iq/manifest.json'] = encoded(manifest)
        boot = upgrade_boot(candidate.document(following['boot.json']))
        following['boot.json'] = encoded(boot)
        following['cohort.json'] = encode(create('1.0.8', '0.1.41', '1' * 40, self.firmware))
        apps = copy.deepcopy(self.origin['apps'])
        apps.update(configuration=self.configuration, watch_source='1' * 40, boot=boot)
        files = {name: following[name] for name in payloads('rf-spectrum')}
        native = {'blobs': {'firmware.bin': self.firmware}}
        return following, files, apps, native

    def test_origin_is_exact_device_cohort_not_later_release_merge(self):
        self.assertEqual(self.origin['identity']['source_revision'], '5c317f80b471d754111dbbe5a14fe97fd0dc377c')
        self.assertEqual(self.origin['identity']['version'], '1.0.7')
        self.assertEqual(candidate.sha(self.origin['full']), candidate.IMAGE_SHA)
        self.assertEqual(len(self.origin['store']), 89)
        self.assertEqual(sum(name.endswith('.elf') for name in self.origin['store']), 43)

    def test_rf_policy_retains_every_application_provider_and_storage_owner(self):
        following, files, apps, native = self.fixture()
        store, identity, proof = candidate.compose(self.origin, native, files, apps, '1' * 40)
        self.assertEqual(store, following)
        self.assertEqual(identity['version'], '1.0.8')
        self.assertEqual(proof['new_private_grants'], PRIVATE_GRANTS)
        self.assertTrue(proof['board_bytes_preserved'])
        self.assertTrue(proof['all_prior_persistent_owners_preserved'])
        self.assertFalse(proof['shared_migration_added'])

    def test_existing_identity_inventory_and_grants_cannot_change(self):
        good, _, _, _ = self.fixture()
        for change in ('owner', 'grant', 'provider', 'file', 'version', 'waterfall-authority', 'board', 'migration'):
            with self.subTest(change=change):
                store = dict(good)
                if change == 'file': del store['ble_scanner.elf']
                elif change == 'board': store['board.json'] += b' '
                elif change in ('grant', 'migration'):
                    boot = candidate.document(store['boot.json'])
                    if change == 'grant': boot['app_capabilities'][0]['grants'].pop()
                    else: boot['cohort_migration'] = candidate.document(self.origin['store']['boot.json'])['cohort_migration']
                    store['boot.json'] = encoded(boot)
                else:
                    name = 'waterfall.json' if change == 'waterfall-authority' else 'ble-hid/manifest.json' if change == 'provider' else 'default.json'
                    manifest = candidate.document(store[name])
                    if change == 'version': manifest['version'] = '0.10.3'
                    elif change == 'waterfall-authority': manifest['requires'].append({'capability': 'storage.volume', 'api': 1})
                    else: manifest['id'] = 'different-owner'
                    store[name] = encoded(manifest)
                with self.assertRaises(ValueError): candidate.check_policy(self.origin['store'], store, self.configuration)

    def test_baseline_and_hardware_proof_must_match_exact_profile(self):
        for key in ('baseline_sha256', 'catalog', 'baseline_boot', 'baseline_board'):
            following, files, apps, native = self.fixture()
            apps[key] = None
            with self.assertRaisesRegex(ValueError, 'accepted baseline'):
                candidate.compose(self.origin, native, files, apps, '1' * 40)
        following, files, apps, native = self.fixture()
        apps['motion_model'] = 'bma456h'
        apps['board'] = configure_board(apps['baseline_board'], motion_model='bma456h', radio_model='selectable')
        files['board.json'] = encoded(apps['board'])
        with self.assertRaisesRegex(ValueError, 'only an accepted bma423'):
            candidate.compose(self.origin, native, files, apps, '1' * 40)
        store, _, proof = candidate.compose(self.origin, native, files, apps, '1' * 40, initial_only=True)
        self.assertEqual(store['board.json'], files['board.json'])
        self.assertFalse(proof['board_bytes_preserved'])

    def test_old_cohort_cannot_be_named_as_future_ota_or_initial(self):
        bootfs = self.origin['full'][0x2f0000:0x800000]
        with self.assertRaisesRegex(ValueError, 'version differs'):
            candidate.paired_payload(self.origin['identity'], self.firmware, bootfs, 'bma423')
        with self.assertRaisesRegex(ValueError, 'version differs'):
            candidate.initial_image({'blobs': {'firmware.bin': self.firmware}}, bootfs, Path('/unused'), 'bma423')
        with self.assertRaisesRegex(ValueError, 'accepted bma423'):
            candidate.paired_payload(self.origin['identity'], self.firmware, bootfs, 'bma456h')

    def test_runtime_custody_covers_every_asset_and_accepted_component(self):
        custody = candidate.document((ROOT / 'apps/rf-spectrum-native-custody.json').read_bytes())
        self.assertEqual(custody['source_sha'], RUNTIME_SOURCE)
        self.assertEqual(custody['firmware_version'], '0.1.41')
        self.assertEqual(custody['assets']['firmware.bin'], candidate.metadata(self.firmware))
        self.assertEqual(custody['assets']['firmware.elf']['sha256'],
                         '426b85cdfd68b21a8acbbf20c489bed67b2b7f2b234549fb9944f4ff2518085f')
        for component in self.origin['acceptance']['components']:
            name = Path(component['file']).name
            if name in custody['assets']:
                self.assertEqual(custody['assets'][name], {k: component[k] for k in ('size_bytes', 'sha256')})

    def test_native_tampering_fails_before_any_post_link_process(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);native = root / 'native';native.mkdir();(root / 'apps').mkdir()
            custody = candidate.document((ROOT / 'apps/rf-spectrum-native-custody.json').read_bytes())
            record = {'source_sha': RUNTIME_SOURCE, 'firmware_version': '0.1.41', 'assets': {}}
            for name in custody['assets']:
                raw = name.encode();(native / name).write_bytes(raw)
                custody['assets'][name] = candidate.metadata(raw)
                record['assets'][name] = {'bytes': len(raw), 'sha256': candidate.sha(raw)}
            (native / 'candidate.json').write_bytes(encoded(record));(native / 'SHA256SUMS').write_text('unused')
            custody['candidate_sha256'] = candidate.sha((native / 'candidate.json').read_bytes())
            (root / 'apps/rf-spectrum-native-custody.json').write_bytes(encoded(custody))
            for name in custody['assets']:
                with self.subTest(member=name):
                    (native / name).write_bytes(b'changed')
                    with patch.object(candidate, 'checked_source'), patch.object(candidate.subprocess, 'run') as run:
                        with self.assertRaisesRegex(ValueError, 'Accepted native bytes differ'):
                            candidate.read_native(native, root / 'runtime', root)
                        run.assert_not_called()
                    (native / name).write_bytes(name.encode())

    def test_archive_duplicates_traversal_and_symlinks_are_rejected(self):
        for name in ('../escape', '/absolute', 'a/../escape', 'a\\escape'):
            raw = io.BytesIO()
            with zipfile.ZipFile(raw, 'w') as archive: archive.writestr(name, b'data')
            with self.assertRaisesRegex(ValueError, 'Unsafe'): builder.safe_archive(raw.getvalue())
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as archive:
            link = zipfile.ZipInfo('link');link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16;archive.writestr(link, '../escape')
        with self.assertRaisesRegex(ValueError, 'Unsafe'): builder.safe_archive(raw.getvalue())
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as archive:
            archive.writestr('a', b'first');archive.writestr('a', b'second')
        with self.assertRaisesRegex(ValueError, 'Duplicate'): builder.safe_archive(raw.getvalue())

    def test_install_text_separates_preserving_ota_from_destructive_initial(self):
        ota, initial = {'asset': 'paired.bin'}, {'asset': 'initial.bin'}
        text = builder.instructions('both', 'bma423', ota, initial)
        self.assertIn('Preserves NVS', text);self.assertIn('Erases NVS', text)
        self.assertIn('never a raw full-image', text);self.assertIn('Flash offset: 0x0', text)
        self.assertNotIn('PAIRED UPDATE:', builder.instructions('initial', 'bma456h', None, initial))
        self.assertNotIn('INITIAL FLASH:', builder.instructions('paired', 'bma423', ota, None))

    def test_metadata_harness_proof_cannot_qualify_complete_candidate(self):
        with self.assertRaisesRegex(ValueError, 'does not qualify'):
            upgrade.validate_proof({'schema': 1, 'scope': 'accepted-harness-self-test-only',
                                    'complete_target_artifact': False}, None, None, None, None)

    def test_no_packaged_artifact_is_written_before_source_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'candidate'
            with patch.object(builder, 'checked_source', return_value='1' * 40), \
                 patch.object(builder, 'verify_apps', side_effect=ValueError('incomplete target artifact')), \
                 patch.object(builder, 'prove') as prove:
                with self.assertRaisesRegex(ValueError, 'incomplete target'):
                    builder.prepare('/apps', '/runtime', '/native', output)
                prove.assert_not_called();self.assertFalse(output.exists())

    def test_bootfs_requests_exclude_appdata_and_bound_exact_active_store(self):
        following, _, _, _ = self.fixture()
        identity = candidate.parse(following['cohort.json'])
        request = upgrade.cohort_request(identity, self.firmware, b'candidate-store', b'accepted-store')
        self.assertEqual(request['active_store_sha256'], candidate.sha(b'accepted-store'))
        self.assertEqual(request['sha256'], candidate.sha(self.firmware + b'candidate-store'))
        self.assertEqual(request['store_size'], len(b'candidate-store'))
        self.assertFalse(any('appdata' in key or 'nvs' in key for key in request))


if __name__ == '__main__':
    unittest.main()

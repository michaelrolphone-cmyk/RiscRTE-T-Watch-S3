"""Real accepted bytes and fail-closed publication gates; no network or compiler."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import publish_accepted_watch_112 as complete
import publish_watch_product as pub


class AcceptedWatch112Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = complete.load_inputs()
        cls.source = complete.PUBLISHED_SOURCE
        cls.plan, cls.payloads = complete.derive(cls.inputs, cls.source)
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name) / 'stage'
        cls.output.mkdir()
        for tag, files in cls.payloads.items():
            directory = cls.output / tag
            directory.mkdir()
            for name, raw in files.items():
                (directory / name).write_bytes(raw)
        (cls.output / 'accepted-inputs.zip').write_bytes(pub.archive(cls.inputs))
        (cls.output / 'publication-plan.json').write_bytes(pub.encoded(cls.plan))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_stage_regenerates_every_record_and_asset(self):
        self.assertEqual(complete.verify_stage(self.output), self.plan)
        self.assertEqual(len(self.plan['app_records']), 22)
        self.assertEqual(len(self.plan['installed_providers']), 22)
        originals = complete.parse(self.inputs['existing-new-driver-records.json'])
        self.assertEqual({identity: record['version'] for identity, record in originals.items()},
                         {'twatch-imu': '0.4.2', 'twatch-panel': '0.4.2', 'twatch-pmu': '0.6.2'})
        self.assertEqual(len(self.plan['product']['reused_driver_records']), 20)
        self.assertEqual(len(self.plan['releases']), 25)

    def test_exact_full_image_and_all_deployed_components_preserved(self):
        files = self.payloads[complete.TAG]
        self.assertEqual(pub.sha(files[complete.ASSET]), complete.IMAGE_SHA)
        self.assertEqual(len(files[complete.ASSET]), 16 * 1024 * 1024)
        store = complete.read_image(files[complete.ASSET][0x2f0000:0x800000], 0x510000)
        self.assertEqual(complete.zip_files(files['accepted-store.zip']), store)
        self.assertEqual(len(store), 91)
        cohort = complete.parse(store['cohort.json'])
        self.assertEqual(cohort['runtime_version'], '0.1.55')
        self.assertEqual(cohort['source_revision'], complete.ACCEPTED_SOURCE)
        for record in self.plan['app_records']:
            for suffix in ('.elf', '.json'):
                name = record['id'] + suffix
                self.assertEqual(self.payloads[record['tag']][name], store[name])
        packages = complete.zip_files(files['provider-packages.zip'])
        for provider in self.plan['installed_providers']:
            package = complete.zip_files(packages[provider['package']['asset']])
            folder = provider['directory']
            self.assertEqual(package['driver.elf'], store[folder + '/driver.elf'])
            self.assertEqual(complete.parse(package['source-manifest.json']), complete.parse(store[folder + '/manifest.json']))

    def test_no_paired_payload_or_catalog_route_promoted(self):
        files = self.payloads[complete.TAG]
        self.assertEqual({n for n in files if n.endswith('.bin')}, {complete.ASSET})
        self.assertNotIn('ota', self.plan['index']['firmware'])
        self.assertTrue(self.plan['initial_only'])
        self.assertFalse(self.plan['paired_payload_published'])
        provenance = complete.parse(files['product-provenance.json'])
        self.assertEqual(provenance['paired_payload'], {'sha256': complete.PAIRED_SHA, 'published': False, 'catalog_route_published': False})
        self.assertFalse(provenance['binary_rebuilt'])
        self.assertTrue(provenance['owner_acceptance']['embedded_provenance_unchanged'])
        for word in ('NVS', 'Bluetooth bonds', 'app-data', '0x0'):
            self.assertIn(word, files['FLASHING.md'].decode())

    def test_original_source_bundles_and_licenses_preserved(self):
        files = self.payloads[complete.TAG]
        self.assertEqual(files['source-custody.zip'], self.inputs['source-custody.zip'])
        self.assertEqual(files['reconstruction-inputs.zip'], self.inputs['reconstruction-inputs.zip'])
        mapping = complete.parse(complete.zip_files(files['source-custody.zip'])['source-equivalence.json'])
        self.assertEqual(len(mapping['sources']), 5)
        self.assertEqual(files['reconstruct_watch_112_sources.py'], (ROOT / 'scripts/reconstruct_watch_112_sources.py').read_bytes())
        for assets in self.payloads.values():
            self.assertEqual(assets['LICENSES.zip'], self.inputs['LICENSES.zip'])

    def test_previously_published_packages_and_sources_are_immutable(self):
        old = {r['id']: r for r in self.plan['baseline_index']['drivers']}
        originals = complete.parse(self.inputs['existing-new-driver-records.json'])
        for identity, record in self.plan['product']['reused_driver_records'].items():
            self.assertNotIn(record['tag'], self.payloads)
            if identity in originals:
                self.assertEqual(record['source_sha'], originals[identity]['source_sha'])
                self.assertEqual(record['sha256'], originals[identity]['sha256'])
            else:
                self.assertEqual(record, old[identity])
        self.assertEqual(self.plan['baseline_index']['firmware']['version'], '1.0.7')
        self.assertNotIn('firmware-v1.0.7', self.payloads)

    def test_reused_providers_validate_both_historical_release_schemas(self):
        def standalone(plan, output):
            self.assertTrue(all('accepted_source_sha' not in r for r in plan['driver_records']))
            self.assertGreaterEqual(len(plan['driver_records']), 9)
        captured = []
        def product(releases, output):
            captured.extend(releases)
            for release in releases:
                self.assertEqual(len(release['assets']), 6)
                self.assertTrue((output / release['tag'] / 'accepted-manifest.json').is_file())
        with patch.object(pub, 'verify_driver_releases', side_effect=standalone), \
             patch.object(pub, 'release_by_tag', return_value={'draft': False}), \
             patch.object(pub, 'release_preflight', side_effect=product):
            complete.verify_reused_releases(self.plan, self.output)
        self.assertEqual(len(captured), 8)

    def test_any_changed_or_missing_custody_input_is_rejected(self):
        for name in self.inputs:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Accepted input changed'):
                complete.derive({**self.inputs, name: self.inputs[name] + b'changed'}, self.source)
        with self.assertRaisesRegex(ValueError, 'input inventory'):
            complete.derive({k: v for k, v in self.inputs.items() if k != 'owner-acceptance.json'}, self.source)

    def test_self_consistent_but_replaced_image_rejected(self):
        import gzip
        image = gzip.decompress(self.inputs['accepted.bin.gz'])
        bad = gzip.compress(b'\x00' + image[1:], mtime=0)
        # Even changing the outer input digest cannot relabel the accepted image.
        with patch.dict(complete.INPUT_HASHES, {'accepted.bin.gz': pub.sha(bad)}), \
             self.assertRaisesRegex(ValueError, 'full image hash'):
            complete.derive({**self.inputs, 'accepted.bin.gz': bad}, self.source)

    def test_invalid_and_duplicate_json_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            complete.parse(b'{"x":1,"x":2}')
        with self.assertRaisesRegex(ValueError, 'Exact release source'):
            complete.derive(self.inputs, 'main')
        with self.assertRaisesRegex(ValueError, 'Unsafe ZIP'):
            complete.zip_files(pub.archive({'../escape': b'bad'}))

    def test_staged_plan_rewrite_is_rejected(self):
        path = self.output / 'publication-plan.json'
        original = path.read_bytes()
        changed = copy.deepcopy(self.plan)
        changed['app_records'][0]['sha256'] = '0' * 64
        try:
            path.write_bytes(pub.encoded(changed))
            with self.assertRaisesRegex(ValueError, 'plan differs from accepted bytes'):
                complete.verify_stage(self.output)
        finally:
            path.write_bytes(original)

    def test_staged_asset_change_and_extra_asset_are_rejected(self):
        folder = self.output / self.plan['app_records'][0]['tag']
        path = folder / self.plan['app_records'][0]['asset']
        original = path.read_bytes()
        try:
            path.write_bytes(original + b'changed')
            with self.assertRaisesRegex(ValueError, 'Staged release assets changed'):
                complete.verify_stage(self.output)
        finally:
            path.write_bytes(original)
        extra = folder / 'unapproved.txt'
        try:
            extra.write_bytes(b'unapproved')
            with self.assertRaisesRegex(ValueError, 'Staged release assets changed'):
                complete.verify_stage(self.output)
        finally:
            extra.unlink()

    def test_changed_predecessor_and_partial_index_rejected(self):
        baseline = self.plan['baseline_index']
        for parent, current in [('f' * 40, baseline), (complete.BASE_COMMIT, {**baseline, 'apps': []})]:
            with self.assertRaisesRegex(ValueError, 'predecessor changed'):
                complete.verify_predecessor(self.plan, parent, current)
        partial = copy.deepcopy(self.plan['index'])
        partial['apps'] = baseline['apps']
        with self.assertRaisesRegex(ValueError, 'predecessor changed'):
            complete.verify_predecessor(self.plan, 'f' * 40, partial)

    def test_exact_completed_index_is_idempotent(self):
        complete.verify_predecessor(self.plan, 'f' * 40, self.plan['index'])

    def test_same_version_component_overwrites_rejected(self):
        for kind in ('apps', 'drivers'):
            changed = copy.deepcopy(self.plan['index'][kind][0])
            changed['sha256'] = '0' * 64
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'Immutable version collision'):
                complete.update_index(self.plan['index'], kind, changed)

    def test_staging_refuses_existing_output(self):
        with self.assertRaisesRegex(ValueError, 'Refusing to replace'):
            complete.stage(self.output, self.source)

    def publication_context(self):
        return patch.dict(os.environ, {'GITHUB_REPOSITORY': pub.REPOSITORY,
                                      'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main'})

    def command(self, *args):
        return b'' if args[1] == 'status' else self.source.encode()

    def test_last_index_race_refuses_before_any_mutation(self):
        with self.publication_context(), patch.object(pub, 'command', side_effect=self.command), \
             patch.object(pub, 'api', side_effect=[{'default_branch': 'main'}, {'sha': self.source}]), \
             patch.object(complete, 'preflight', return_value=self.plan), \
             patch.object(pub, 'current_release_index', return_value=('f' * 40, self.plan['baseline_index'])), \
             patch.object(pub, 'publish_one') as one, patch.object(pub, 'publish_index') as index:
            with self.assertRaisesRegex(ValueError, 'predecessor changed'):
                complete.publish(self.output)
            one.assert_not_called()
            index.assert_not_called()

    def test_all_releases_precede_compare_and_swap_index(self):
        calls = []
        def one(release, output, **kwargs):
            calls.append(('release', release['tag'], release['latest']))
        def index(value, **kwargs):
            self.assertEqual(kwargs, {'expected_parent': complete.BASE_COMMIT, 'expected_current': self.plan['baseline_index']})
            self.assertEqual(value, self.plan['index'])
            calls.append(('index', value['firmware']['version']))
        with self.publication_context(), patch.object(pub, 'command', side_effect=self.command), \
             patch.object(pub, 'api', side_effect=[{'default_branch': 'main'}, {'sha': self.source}]), \
             patch.object(complete, 'preflight', return_value=self.plan), \
             patch.object(pub, 'current_release_index', return_value=(complete.BASE_COMMIT, self.plan['baseline_index'])), \
             patch.object(pub, 'publish_one', side_effect=one), patch.object(pub, 'publish_index', side_effect=index):
            complete.publish(self.output)
        self.assertEqual(calls[-2:], [('release', complete.TAG, True), ('index', '1.0.12')])
        self.assertTrue(all(not call[2] for call in calls[:-2]))


if __name__ == '__main__':
    unittest.main()

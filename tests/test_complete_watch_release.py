"""Exercise exact accepted binary packaging and publication's fail-closed gates.

No compiler, physical device, GitHub writes, or network calls are used. The small
committed image/evidence inputs are the real production inputs, not a recompiled
fixture. Remote coordination tests mock transport while retaining the real index
and immutable-release validation functions.
"""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import publish_complete_watch as complete
import publish_watch_product as pub


class CompleteReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inputs = ROOT / 'release/complete-1.0.7'
        evidence_inputs = Path(os.environ.get('COMPLETE_WATCH_EVIDENCE_INPUTS', inputs))
        cls.image = gzip.decompress((inputs / 'accepted.bin.gz').read_bytes())
        cls.evidence = (evidence_inputs / 'accepted-app-evidence.zip').read_bytes()
        cls.drivers = complete.zip_files((evidence_inputs / 'immutable-driver-inputs.zip').read_bytes())
        cls.baseline = complete.parse((inputs / 'predecessor-index.json').read_bytes())
        cls.custody = {name: (complete.CUSTODY / name).read_bytes() for name in complete.CUSTODY_HASHES}
        cls.supplement = complete.read_tree(inputs / 'licenses/supplemental')
        cls.existing_new = (inputs / 'existing-new-driver-records.json').read_bytes()
        cls.source = complete.PUBLISHED_SOURCE
        cls.plan, cls.payloads = complete.derive(cls.image, cls.evidence, cls.custody,
                                                cls.drivers, cls.baseline, cls.source,
                                                supplement=cls.supplement, existing_new_raw=cls.existing_new)
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name) / 'stage'
        cls.output.mkdir()
        for tag, files in cls.payloads.items():
            directory = cls.output / tag
            directory.mkdir()
            for name, raw in files.items():
                (directory / name).write_bytes(raw)
        for name, raw in {'publication-plan.json': pub.encoded(cls.plan),
                          'baseline-index.json': complete.serialize_index(cls.baseline).encode(),
                          'immutable-driver-inputs.zip': pub.archive(cls.drivers),
                          'supplemental-licenses.zip': pub.archive(cls.supplement)}.items():
            (cls.output / name).write_bytes(raw)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def derive(self, **changes):
        args = dict(image=self.image, current_raw=self.evidence, custody=self.custody,
                    driver_inputs=self.drivers, baseline=self.baseline, source_sha=self.source,
                    supplement=self.supplement, existing_new_raw=self.existing_new)
        args.update(changes)
        return complete.derive(**args)

    def test_stage_independently_regenerates_all_expected_assets(self):
        self.assertEqual(complete.verify_stage(self.output), self.plan)
        self.assertEqual(len(self.plan['releases']), 32)
        self.assertEqual(len(self.plan['app_records']), 22)
        self.assertEqual(len(self.plan['installed_providers']), 21)
        self.assertEqual(len(self.plan['product']['reused_driver_records']), 12)

    def test_exact_image_native_apps_manifests_and_every_provider_preserved(self):
        files = self.payloads[complete.TAG]
        self.assertEqual(files[complete.ASSET], self.image)
        store = complete.read_image(self.image[0x2f0000:0x800000], 0x510000)
        self.assertEqual(complete.zip_files(files['accepted-store.zip']), store)
        self.assertEqual(len(store), 89)
        cohort = complete.parse(store['cohort.json'])
        self.assertEqual(cohort['runtime_version'], '0.1.41')
        self.assertEqual(pub.sha(self.image[0x10000:0x10000 + cohort['firmware_size']]),
                         cohort['firmware_sha256'])
        for record in self.plan['app_records']:
            app = self.payloads[record['tag']]
            for suffix in ('.elf', '.json'):
                self.assertEqual(app[record['id'] + suffix], store[record['id'] + suffix])
        packages = complete.zip_files(files['provider-packages.zip'])
        for provider in self.plan['installed_providers']:
            package = complete.zip_files(packages[provider['package']['asset']])
            directory = provider['directory']
            self.assertEqual(package['driver.elf'], store[directory + '/driver.elf'])
            self.assertEqual(complete.parse(package['source-manifest.json']),
                             complete.parse(store[directory + '/manifest.json']))
        self.assertNotIn('ota', self.plan['index']['firmware'])
        self.assertEqual({n for n in files if n.endswith('.bin')}, {complete.ASSET})

    def test_all_sources_and_license_bytes_are_retained(self):
        expected = {n: raw for n, raw in complete.zip_files(self.evidence).items()
                    if n.startswith('licenses/')}
        expected.update({'supplemental/' + n: raw for n, raw in self.supplement.items()})
        for tag, files in self.payloads.items():
            self.assertEqual(complete.zip_files(files['LICENSES.zip']), expected, tag)
        provenance = complete.parse(self.payloads[complete.TAG]['product-provenance.json'])
        self.assertFalse(provenance['binary_rebuilt'])
        self.assertEqual(provenance['source_and_acceptance']['source_commit_in_delivered_image'],
                         complete.ACCEPTED_SOURCE)
        self.assertIn('NVS', self.payloads[complete.TAG]['FLASHING.md'].decode())
        self.assertIn('Bluetooth bonds', self.payloads[complete.TAG]['FLASHING.md'].decode())

    def test_published_history_and_original_driver_records_unchanged(self):
        self.assertEqual(self.plan['baseline_index'], self.baseline)
        self.assertEqual(self.baseline['firmware']['version'], '1.0.3')
        self.assertNotIn('firmware-v1.0.3', self.payloads)
        self.assertNotIn('firmware-v1.0.6', self.payloads)
        final = {record['id']: record for record in self.plan['index']['drivers']}
        changed = {record['id'] for record in self.plan['driver_records']
                   if record['id'] not in self.plan['product']['reused_driver_records']}
        for record in self.baseline['drivers']:
            if record['id'] not in changed and record['id'] not in ('twatch-imu', 'twatch-pmu'):
                self.assertEqual(final[record['id']], record)
        for record in self.plan['product']['reused_driver_records'].values():
            self.assertNotIn(record['tag'], self.payloads)

    def test_previously_published_new_driver_versions_keep_their_source_and_bytes(self):
        originals = complete.parse(self.existing_new)
        for identity, original in originals.items():
            record = self.plan['product']['reused_driver_records'][identity]
            self.assertEqual(record['source_sha'], original['source_sha'])
            self.assertEqual(record['sha256'], original['sha256'])
            self.assertEqual(record['size'], original['size_bytes'])
            self.assertNotIn(record['tag'], self.payloads)
        self.assertEqual(self.payloads[complete.TAG]['existing-driver-releases.json'], self.existing_new)
        with self.assertRaisesRegex(ValueError, 'published driver record custody differs'):
            self.derive(existing_new_raw=self.existing_new + b' ')

    def test_corrupted_or_replacement_image_rejected(self):
        for raw in (self.image[:-1], b'\x00' + self.image[1:]):
            with self.subTest(size=len(raw)), self.assertRaisesRegex(ValueError, 'image hash differs'):
                self.derive(image=raw)

    def test_corrupted_or_missing_app_build_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError, 'evidence ZIP hash differs'):
            self.derive(current_raw=self.evidence + b'extra')

    def test_modified_source_custody_rejected(self):
        for name in self.custody:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'source custody changed'):
                self.derive(custody={**self.custody, name: self.custody[name] + b' '})

    def test_corrupted_reused_driver_rejected(self):
        name = next(iter(self.drivers))
        with self.assertRaisesRegex(ValueError, 'driver input hash differs'):
            self.derive(driver_inputs={**self.drivers, name: self.drivers[name] + b'changed'})

    def test_self_consistent_but_changed_provider_package_is_rejected(self):
        name = next(iter(self.drivers))
        files = complete.zip_files(self.drivers[name])
        source = files['source-manifest.json']
        files['driver.elf'] += b'changed'
        manifest = complete.parse(files['.package.json'])
        for entry in manifest['entries']:
            if entry['name'] == 'driver.elf':
                entry.update(complete.metadata(files['driver.elf']))
        files['.package.json'] = pub.encoded(manifest)
        with self.assertRaisesRegex(ValueError, 'driver payload/manifest collision'):
            complete.verify_driver_package(pub.archive(files), files['driver.elf'][:-7], source)

    def test_self_consistent_supplement_rewrite_rejected(self):
        changed = dict(self.supplement)
        name = next(n for n in changed if n != 'SOURCES.json')
        changed[name] += b'change'
        sources = complete.parse(changed['SOURCES.json'])
        sources['files'][name] = complete.metadata(changed[name])
        changed['SOURCES.json'] = pub.encoded(sources)
        with self.assertRaisesRegex(ValueError, 'license source custody differs'):
            self.derive(supplement=changed)

    def test_duplicate_json_and_unsafe_archive_names_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            complete.parse(b'{"version":"1.0.7","version":"1.0.8"}')
        with self.assertRaisesRegex(ValueError, 'Unsafe ZIP path'):
            complete.zip_files(pub.archive({'../escape': b'x'}))

    def test_self_consistent_plan_rewrite_cannot_change_an_accepted_app(self):
        path = self.output / 'publication-plan.json'
        changed = copy.deepcopy(self.plan)
        changed['app_records'][0]['sha256'] = '0' * 64
        original = path.read_bytes()
        try:
            path.write_bytes(pub.encoded(changed))
            with self.assertRaisesRegex(ValueError, 'plan differs from accepted bytes'):
                complete.verify_stage(self.output)
        finally:
            path.write_bytes(original)

    def test_changed_asset_and_added_asset_rejected(self):
        tag = self.plan['app_records'][0]['tag']
        path = self.output / tag / self.plan['app_records'][0]['asset']
        original = path.read_bytes()
        try:
            path.write_bytes(original + b'changed')
            with self.assertRaisesRegex(ValueError, 'Staged release assets changed'):
                complete.verify_stage(self.output)
        finally:
            path.write_bytes(original)
        extra = self.output / tag / 'unapproved.txt'
        try:
            extra.write_bytes(b'unapproved')
            with self.assertRaisesRegex(ValueError, 'Staged release assets changed'):
                complete.verify_stage(self.output)
        finally:
            extra.unlink()

    def test_stale_index_commit_or_content_rejected(self):
        changed = copy.deepcopy(self.baseline)
        changed['providers'] = []
        for parent, index in [(('e' * 40), self.baseline), (complete.BASE_COMMIT, changed)]:
            with self.subTest(parent=parent), self.assertRaisesRegex(ValueError, 'predecessor changed'):
                complete.verify_predecessor(self.plan, parent, index)
        with self.assertRaisesRegex(ValueError, 'predecessor bytes'):
            self.derive(baseline=changed)

    def test_same_version_app_or_driver_overwrite_is_refused(self):
        for kind in ('apps', 'drivers'):
            record = copy.deepcopy(self.plan['index'][kind][0])
            record['sha256'] = '0' * 64
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'Immutable version collision'):
                complete.update_index(self.plan['index'], kind, record)

    def test_existing_release_collision_is_detected_before_any_write(self):
        release = self.plan['releases'][0]
        name = next(iter(release['assets']))
        existing = {'tag_name': release['tag'], 'target_commitish': self.source,
                    'draft': True, 'prerelease': False, 'assets': [{'name': name, 'id': 123}]}
        with patch.object(pub, 'release_by_tag', return_value=existing), \
             patch.object(pub.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, stderr=b'HTTP 404')), \
             patch.object(pub, 'gh', return_value=b'wrong immutable bytes') as transport:
            with self.assertRaisesRegex(ValueError, 'Immutable uploaded asset collision'):
                pub.release_preflight([release], self.output)
            self.assertEqual(transport.call_count, 1)
            self.assertNotIn('POST', transport.call_args.args)

    def test_publication_late_index_race_refuses_before_asset_creation(self):
        environment = {'GITHUB_REPOSITORY': pub.REPOSITORY, 'GITHUB_EVENT_NAME': 'push',
                       'GITHUB_REF': 'refs/heads/main'}
        def command(*args):
            return b'' if args[1] == 'status' else self.source.encode()
        with patch.dict(os.environ, environment), patch.object(pub, 'command', side_effect=command), \
             patch.object(pub, 'api', side_effect=[{'default_branch': 'main'}, {'sha': self.source}]), \
             patch.object(complete, 'preflight', return_value=self.plan), \
             patch.object(pub, 'current_release_index', return_value=('e' * 40, self.baseline)), \
             patch.object(pub, 'publish_one') as publish_one, patch.object(pub, 'publish_index') as publish_index:
            with self.assertRaisesRegex(ValueError, 'predecessor changed'):
                complete.publish(self.output)
            publish_one.assert_not_called()
            publish_index.assert_not_called()

    def test_staging_refuses_existing_output_before_writing(self):
        with self.assertRaisesRegex(ValueError, 'Refusing to replace'):
            complete.stage(None, None, None, None, None, self.output, self.source)

    def test_final_index_compare_and_swap_rejects_an_intervening_update(self):
        with patch.object(pub, 'current_release_index', return_value=('f' * 40, self.baseline)), \
             patch.object(pub.subprocess, 'check_output') as git_write:
            with self.assertRaisesRegex(ValueError, 'predecessor changed'):
                pub.publish_index(self.plan['index'], expected_parent=complete.BASE_COMMIT,
                                  expected_current=self.baseline)
            git_write.assert_not_called()

    def test_publication_orders_all_verified_releases_before_the_index(self):
        environment = {'GITHUB_REPOSITORY': pub.REPOSITORY, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                       'GITHUB_REF': 'refs/heads/main'}
        calls = []
        def command(*args):
            return b'' if args[1] == 'status' else self.source.encode()
        def publish_one(release, output, **kwargs):
            calls.append(('release', release['tag'], release['latest']))
        def publish_index(index, **kwargs):
            self.assertEqual(kwargs, {'expected_parent': complete.BASE_COMMIT,
                                     'expected_current': self.baseline})
            self.assertEqual(index, self.plan['index'])
            calls.append(('index', index['firmware']['version']))
        with patch.dict(os.environ, environment), patch.object(pub, 'command', side_effect=command), \
             patch.object(pub, 'api', side_effect=[{'default_branch': 'main'}, {'sha': self.source}]), \
             patch.object(complete, 'preflight', return_value=self.plan), \
             patch.object(pub, 'current_release_index', return_value=(complete.BASE_COMMIT, self.baseline)), \
             patch.object(pub, 'publish_one', side_effect=publish_one), \
             patch.object(pub, 'publish_index', side_effect=publish_index):
            self.assertEqual(complete.publish(self.output), self.plan)
        self.assertEqual(calls[-2:], [('release', complete.TAG, True), ('index', '1.0.7')])
        self.assertEqual(len(calls), len(self.plan['releases']) + 1)
        self.assertTrue(all(not call[2] for call in calls[:-2]))


if __name__ == '__main__':
    unittest.main()

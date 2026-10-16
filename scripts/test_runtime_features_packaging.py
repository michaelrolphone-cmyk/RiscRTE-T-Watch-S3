#!/usr/bin/env python3
"""Focused policy and artifact-safety regressions for the opt-in 1.0.12 lane."""
import argparse
import io
import json
from pathlib import Path
import unittest
import zipfile

from current_apps_overlay import APPS, ROOT, config, encoded
from current_cohort import encode
from runtime_features_profile import VERSION, RUNTIME_VERSION, FEATURE_CAPS, upgrade_boot
from runtime_features_watch_candidate import check_policy
from runtime_features_watch_origins import read_origin
from build_runtime_features_watch_candidate import safe_archive


class PolicyTests(unittest.TestCase):
    origin = None

    def setUp(self):
        self.previous = self.origin['store']
        self.configuration = config(ROOT, profile='runtime-features')
        self.following = dict(self.previous)
        self.following['boot.json'] = encoded(upgrade_boot(json.loads(self.previous['boot.json'])))
        self.following['cohort.json'] = encode({**self.origin['identity'], 'version': VERSION, 'runtime_version': RUNTIME_VERSION, 'source_revision': 'a' * 40})
        for name in APPS:
            manifest = json.loads(self.previous[name + '.json'])
            manifest['version'] = self.configuration['app_versions'][name]
            manifest['requires'] += [{'capability': cap, 'api': 1}
                                     for cap in (*FEATURE_CAPS.get(name, ()), 'telemetry.broadcast')]
            self.following[name + '.json'] = encoded(manifest)
            self.following[name + '.elf'] = b'policy-only:' + name.encode()
        self.following['broadcast/driver.elf'] = b'policy-only-broadcast'
        self.following['broadcast/manifest.json'] = b'{}'

    def reject(self, change):
        change(self.following)
        with self.assertRaises(ValueError):
            check_policy(self.previous, self.following, self.configuration)

    def test_explicit_feature_policy(self):
        result = check_policy(self.previous, self.following, self.configuration)
        self.assertEqual(result['prior_app_count'], 22)
        self.assertEqual(result['candidate_app_count'], 22)
        self.assertTrue(result['all_prior_provider_bytes_preserved'])

    def test_inventory_removal(self):
        self.reject(lambda files: files.pop('waterfall.elf'))

    def test_inventory_addition(self):
        self.reject(lambda files: files.update({'extra.elf': b'bad'}))

    def test_board_change(self):
        self.reject(lambda files: files.update({'board.json': b'{}'}))

    def test_existing_provider_change(self):
        self.reject(lambda files: files.update({'pmu/driver.elf': b'changed'}))

    def test_app_not_rebuilt(self):
        self.reject(lambda files: files.update({'waterfall.elf': self.previous['waterfall.elf']}))

    def test_manifest_authority_change(self):
        def change(files):
            manifest = json.loads(files['waterfall.json'])
            manifest['requires'].append({'capability': 'unexpected.authority', 'api': 1})
            files['waterfall.json'] = encoded(manifest)
        self.reject(change)

    def test_boot_ownership_change(self):
        def change(files):
            boot = json.loads(files['boot.json'])
            row = next(r for r in boot['app_capabilities'] if r['manifest'] == 'waterfall.json')
            next(g for g in row['grants'] if g['capability'] == 'storage.app-data')['instance_id'] = 1
            files['boot.json'] = encoded(boot)
        self.reject(change)

    def test_demand_policy_required(self):
        def change(files):
            boot = json.loads(files['boot.json'])
            boot.pop('provider_activation')
            files['boot.json'] = encoded(boot)
        self.reject(change)

    def test_unversioned_app_rejected(self):
        self.reject(lambda files: files.update({'waterfall.json': self.previous['waterfall.json']}))


class ArchiveTests(unittest.TestCase):
    def archive(self, names):
        result = io.BytesIO()
        with zipfile.ZipFile(result, 'w') as archive:
            for name in names:
                archive.writestr(name, b'test')
        return result.getvalue()

    def test_nested_file(self):
        self.assertEqual(safe_archive(self.archive(['files/clock.json'])), {'files/clock.json': b'test'})

    def test_unsafe_paths(self):
        for name in ('../escape', '/absolute', 'files/../../escape', 'files\\escape', 'files/./x'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_archive(self.archive([name]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-bundle', type=Path, required=True)
    args = parser.parse_args()
    PolicyTests.origin = read_origin(source_bundle=args.source_bundle)
    unittest.main(argv=[__file__], verbosity=2)

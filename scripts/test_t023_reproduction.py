#!/usr/bin/env python3
"""Portable T023 recipe/manifest regressions; optional real component replay checks."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import unittest

from build_t023_springboard import compose_manifest, build_command

ROOT = Path(__file__).resolve().parents[1]
RECIPE = json.loads((ROOT / 'profiles/t023-reproduction.json').read_text())


class ReproductionTests(unittest.TestCase):
    def test_public_component_pins_are_exact(self):
        for name in ['shared', 'system', 'rgb_system', 'utilities', 'bridges']:
            self.assertRegex(RECIPE['source_pins'][name]['commit'], r'^[a-f0-9]{40}$')
        self.assertEqual(RECIPE['source_pins']['system']['commit'], 'e6321624e166a972745572d48354c96e67a5fb10')
        self.assertEqual(RECIPE['source_pins']['shared']['commit'], '063a45ae733cc3c4b5f77b22ff78dc69bff2f6c0')

    def test_complete_baseline_inventory(self):
        expected = 128 if RECIPE['home']['preferences'] == 'atomic' else 121
        self.assertEqual(RECIPE['baseline']['file_count'], expected)
        self.assertEqual(len(RECIPE['baseline']['files']), expected)
        self.assertTrue({'boot.json', 'board.json', 'cohort.json', 'default.elf', 'springboard.elf'} <= set(RECIPE['baseline']['files']))
        self.assertTrue(all(re.fullmatch('[a-f0-9]{64}', value) for value in RECIPE['baseline']['files'].values()))
        self.assertRegex(RECIPE['baseline']['factory_sha256'], r'^[a-f0-9]{64}$')

    def test_manifest_preserves_every_original_field(self):
        old = {'id': 'springboard', 'file_name': 'springboard.elf', 'version': '1.7.15',
               'requires': [{'capability': 'storage.key-value.atomic', 'api': 1}],
               'optional': [{'capability': 'motion.accel', 'api': 1}], 'other': {'nested': [1, 2]}}
        snapshot = copy.deepcopy(old)
        result = compose_manifest(old)
        self.assertEqual(old, snapshot)
        self.assertEqual(result['requires'], old['requires'])
        self.assertEqual(result['other'], old['other'])
        self.assertEqual(result['optional'][:1], old['optional'])
        self.assertIn({'capability': 'software.installed-apps', 'api': 1}, result['optional'])
        self.assertIn({'capability': 'storage.volume', 'api': 1}, result['optional'])
        self.assertEqual(compose_manifest(result), result)

    def test_atomic_and_discovery_flags_are_independent(self):
        profile = {'arguments': ['-DKEEP_FEATURE', '-I{system}/include', '{system}/app.c']}
        args = dict(profile=profile, compiler=Path('/tools/gcc'), system=Path('/src'),
                    output=Path('/out'), bridge=Path('/bridge'))
        ordinary = build_command(**args, atomic=False)
        atomic = build_command(**args, atomic=True)
        self.assertIn('-DPORTABLE_PACKAGE_DISCOVERY', ordinary)
        self.assertIn('-DPORTABLE_PACKAGE_VOLUME=12', ordinary)
        self.assertNotIn('-DPORTABLE_QUICK_ATOMIC_PREFERENCES', ordinary)
        self.assertIn('-DPORTABLE_QUICK_ATOMIC_PREFERENCES', atomic)
        self.assertIn('-DKEEP_FEATURE', atomic)

    def test_commands_are_portable_and_complete(self):
        for command in RECIPE['commands'].values():
            self.assertFalse(any('/workspace/' in item or '/Users/' in item for item in command))
        command = RECIPE['commands']['compose']
        for value in ['--runtime-version', '--source-revision', '{published_recipe_commit}',
                      '--native-provider-manifests', '{verified_native_manifest_list}', '--composition-report']:
            self.assertIn(value, command)
        self.assertEqual('--compact-new-providers' in command, RECIPE['home']['preferences'] == 'atomic')
        self.assertEqual(RECIPE['catalog']['feed_product'], RECIPE['product'])
        self.assertEqual(RECIPE['time_profile']['time_servers'], ['time.cloudflare.com'])

    def test_full_feature_flags_preserve_product_policy(self):
        atomic = RECIPE['home']['preferences'] == 'atomic'
        self.assertEqual('-DWATCH_ATOMIC_PREFERENCES' in RECIPE['home']['all_feature_flags'], atomic)
        self.assertEqual('-DPORTABLE_QUICK_ATOMIC_PREFERENCES' in RECIPE['springboard']['all_feature_flags'], atomic)
        self.assertIn('-DWATCH_AUTOMATIC_PROVISION', RECIPE['home']['all_feature_flags'])
        self.assertIn('-DPORTABLE_PACKAGE_DISCOVERY', RECIPE['springboard']['all_feature_flags'])
        if not atomic:
            self.assertIsNone(RECIPE['home']['provision_volume'])
            self.assertIsNone(RECIPE['home']['crash_volume'])

    def test_exact_replayed_springboard_when_supplied(self):
        path = os.environ.get('T023_SPRINGBOARD_REPLAY')
        if path is None:
            self.skipTest('Set T023_SPRINGBOARD_REPLAY to verify a real pinned target rebuild')
        for name, key in [('springboard.elf', 'elf_sha256'), ('springboard.json', 'manifest_sha256')]:
            self.assertEqual(hashlib.sha256((Path(path) / name).read_bytes()).hexdigest(), RECIPE['springboard'][key])

    def test_exact_replayed_home_when_supplied(self):
        path = os.environ.get('T023_HOME_REPLAY')
        if path is None:
            self.skipTest('Set T023_HOME_REPLAY to verify the real shared target build')
        for name, key in [('default.elf', 'elf_sha256'), ('default.json', 'manifest_sha256')]:
            self.assertEqual(hashlib.sha256((Path(path) / name).read_bytes()).hexdigest(), RECIPE['home'][key])


if __name__ == '__main__':
    unittest.main()

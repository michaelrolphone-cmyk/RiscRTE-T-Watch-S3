#!/usr/bin/env python3
"""Contexts-only policy regressions against the exact published 1.0.12 store."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest

from current_apps_overlay import ROOT, APPS as HISTORICAL_APPS, encoded
from current_cohort import encode
from contexts_profile import (APPS, CAPABILITY, GRANT, SERVICE_MANIFEST, VERSION,
    app_manifest, baseline_inputs, baseline_contract, catalog, check_policy, configuration, upgrade_boot)
from build_contexts_cohort import definitions, LTO_APPS, COMPILER_HELPERS, optimization_policy

class ContextsPolicyTests(unittest.TestCase):
    baseline = None
    def setUp(self):
        self.previous = self.baseline
        self.c = configuration(allow_pending=True)
        self.identity = json.loads(self.previous['cohort.json'])
        self.boot = upgrade_boot(json.loads(self.previous['boot.json']), self.identity)
        self.following = dict(self.previous)
        self.following['boot.json'] = encoded(self.boot)
        self.following['cohort.json'] = encode({**self.identity, 'version': VERSION, 'source_revision': 'a' * 40})
        for name in APPS:
            old = json.loads(self.previous[name + '.json']) if name in HISTORICAL_APPS else None
            self.following[name + '.json'] = encoded(app_manifest(name, old, self.c, self.boot))
            self.following[name + '.elf'] = ('explicitly-rebuilt-test:' + name).encode()
        self.following['contexts/driver.elf'] = b'explicit-new-contexts-service'
        self.following[SERVICE_MANIFEST] = encoded({'type': 'driver', 'id': 'contexts-service', 'version': '0.1.1',
            'driver_abi': 2, 'architecture': 'xtensa-esp32s3', 'file_name': 'driver.elf',
            'provides': [CAPABILITY], 'requires': [{'capability': 'platform.clock', 'api': 1},
                {'capability': 'audio.input', 'api': 1}, {'capability': 'radio.iq', 'api': 1}]})

    def reject(self, mutation):
        mutation(self.following)
        with self.assertRaises(ValueError):
            check_policy(self.previous, self.following, self.c)

    def mutate_boot(self, mutation):
        value = json.loads(self.following['boot.json']);mutation(value);self.following['boot.json'] = encoded(value)

    def test_complete_isolated_contract(self):
        report = check_policy(self.previous, self.following, self.c)
        self.assertEqual((report['candidate_app_count'], report['provider_selections'], report['max_app_grants']), (23, 24, 15))
        self.assertTrue(report['all_prior_provider_bytes_preserved'])
        self.assertFalse(report['runtime_changed'])
        self.assertEqual(len(HISTORICAL_APPS), 22)
        self.assertNotIn('contexts', HISTORICAL_APPS)

    def test_one_explicit_new_shared_namespace(self):
        self.assertNotIn('cohort_migration',self.boot)
        before = json.loads(self.previous['boot.json'])
        for old, new in zip(before['app_capabilities'], self.boot['app_capabilities']):
            self.assertEqual(new['grants'], old['grants'] + [GRANT])
        context = self.boot['app_capabilities'][-1]
        self.assertEqual([g for g in context['grants'] if g['capability'].startswith('storage.')],
            [{'capability': 'storage.key-value', 'api': 1, 'instance_id': 1}])

    def test_lto_is_limited_to_model_apps(self):
        self.assertEqual(set(LTO_APPS), {'default','clock','audio_spectrum','waterfall','contexts'})
        for name in APPS:
            flags=definitions(name,self.c['app_versions'][name])
            self.assertEqual('-flto' in flags,name in LTO_APPS)
            roots=[x.removeprefix('-Wl,--undefined=') for x in flags if x.startswith('-Wl,--undefined=')]
            self.assertEqual(roots,list(COMPILER_HELPERS.get(name,())))
        self.assertFalse(optimization_policy()['boot_effect_lto'])

    def test_no_missing_app(self):
        self.reject(lambda f: f.pop('audio_spectrum.elf'))

    def test_no_extra_app(self):
        self.reject(lambda f: f.update({'other.elf': b'bad'}))

    def test_existing_provider_bytes_frozen(self):
        self.reject(lambda f: f.update({'alarm-service/driver.elf': b'changed'}))

    def test_existing_provider_manifest_frozen(self):
        self.reject(lambda f: f.update({'broadcast/manifest.json': b'{}'}))

    def test_board_frozen(self):
        self.reject(lambda f: f.update({'board.json': b'{}'}))

    def test_native_hash_frozen(self):
        def mutate(f):
            value = json.loads(f['cohort.json']);value['firmware_sha256'] = '0' * 64;f['cohort.json'] = encode(value)
        self.reject(mutate)

    def test_app_must_be_rebuilt(self):
        self.reject(lambda f: f.update({'waterfall.elf': self.previous['waterfall.elf']}))

    def test_every_rebuild_is_versioned(self):
        self.reject(lambda f: f.update({'clock.json': self.previous['clock.json']}))

    def test_no_model_namespace_alias(self):
        self.mutate_boot(lambda b: b['app_capabilities'][-1]['grants'].append({'capability': 'storage.app-data', 'api': 1, 'instance_id': 2}))
        self.reject(lambda f: None)

    def test_no_provider_storage_shortcut(self):
        self.mutate_boot(lambda b: b['drivers'][-1].update({'key_value': [{'key': 'spectrum_s0', 'namespace': 7, 'access': 'read'}]}))
        self.reject(lambda f: None)

    def test_consumed_migration_forbidden(self):
        self.mutate_boot(lambda b: b.update({'cohort_migration': {'schema':1,
            'from':{k:self.identity[k] for k in ('product','version','source_revision')},
            'to':{'product':'twatch-s3','version':VERSION},
            'shared_key_value':[{'application_id':'contexts','api':1,'namespace':1}]}}))
        self.reject(lambda f: None)

    def test_contexts_service_has_no_settings_authority(self):
        value = json.loads(self.following[SERVICE_MANIFEST]);value['requires'].append({'capability': 'storage.key-value.bound', 'api': 2})
        self.reject(lambda f: f.update({SERVICE_MANIFEST: encoded(value)}))

    def test_manifest_cannot_add_hidden_authority(self):
        value = json.loads(self.following['contexts.json']);value['requires'].append({'capability': 'storage.installed-files', 'api': 1})
        self.reject(lambda f: f.update({'contexts.json': encoded(value)}))

    def test_pending_source_cannot_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);(root / 'apps').mkdir()
            for name in ('contexts-baseline.json', 'runtime-features-sources.json'):
                (root / 'apps' / name).write_bytes((ROOT / 'apps' / name).read_bytes())
            c = copy.deepcopy(self.c);c['sources']['utilities']['commit'] = None
            (root / 'apps/contexts-sources.json').write_bytes(encoded(c))
            configuration(root, allow_pending=True)
            with self.assertRaises(ValueError):configuration(root)

    def test_new_flags_preserve_accepted_features(self):
        for name in APPS:
            flags = definitions(name, self.c['app_versions'][name])
            if name in ('default', 'clock'):
                self.assertIn('-DWATCH_CONTEXTS_CLIENT', flags);self.assertIn('-DWATCH_RUNTIME_FEATURES', flags)
            else:
                self.assertIn('-DPORTABLE_CONTEXTS_CLIENT', flags);self.assertIn('-DPORTABLE_BLE_BROADCAST', flags)
                self.assertIn('-include', flags)
            self.assertIn('-DPORTABLE_LOW_BATTERY', flags)
        self.assertIn('-DPORTABLE_CONTEXTS_EDITOR', definitions('contexts', '0.1.1'))
        self.assertIn('-DPORTABLE_CATALOG_LIMIT=21', definitions('springboard', '1.7.8'))
        self.assertNotIn('-DPORTABLE_CATALOG_LIMIT=20', definitions('springboard', '1.7.8'))

    def test_catalog_adds_only_contexts(self):
        before = baseline_contract()['catalog'];after = catalog()
        self.assertEqual(after[:-1], before);self.assertEqual(len(after), 21)
        self.assertEqual(after[-1]['file_name'], 'contexts.elf')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--baseline', required=True, type=Path)
    a = p.parse_args()
    ContextsPolicyTests.baseline = baseline_inputs(a.baseline)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContextsPolicyTests))
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__ == '__main__':main()

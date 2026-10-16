#!/usr/bin/env python3
"""Default packaging contracts and rejection tests; no hardware assertions."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import package_shared_default as package


class Contracts(unittest.TestCase):
    def test_historical_contracts_and_publication_gates(self):
        p = package.pins()
        c = package.baseline_contract(p)
        self.assertEqual(c['files']['alarm-service/driver.elf']['sha256'], package.ALARM_SHA)
        self.assertEqual(c['elf_count'], 59 if p['product'] == 'twatch' else 62)
        if p['publication_enabled']:
            self.assertTrue(p['finalized'])
            self.assertRegex(p['runtime_revision'], r'^[0-9a-f]{40}$')
        profile = (package.ROOT / 'profiles/native-idf61.cmake').read_text()
        self.assertIn('RISC_RUNTIME_PREFERENCE_STORE=1', profile)
        self.assertIn('RISC_RUNTIME_STORAGE_FILES=1', profile)

    def fixtures(self, product):
        app = {'id': 'twatch-clock', 'file_name': 'default.elf', 'requires': [
            {'capability': 'storage.key-value', 'api': 1}, {'capability': 'storage.preferences', 'api': 1},
            {'capability': 'display.output', 'api': 1}], 'optional': [{'capability': 'storage.files', 'api': 1}]}
        grants = [{'capability': 'storage.key-value', 'api': 1, 'instance_id': 1},
                  {'capability': 'display.output', 'api': 1, 'instance_id': 5},
                  {'capability': 'storage.shared-data', 'api': 1, 'instance_id': 2, 'file': 'unchanged.bin'}]
        if product == 'waveshare':
            grants += [{'capability': 'storage.volume', 'api': 1, 'instance_id': 12},
                       {'capability': 'storage.key-value.atomic', 'api': 1, 'instance_id': 1}]
        boot = {'board': 'board.json', 'drivers': [{'manifest': 'driver/manifest.json'}], 'default_app': 'default.elf',
                'app_capabilities': [{'manifest': 'other.json', 'grants': [{'capability': 'storage.key-value', 'api': 1, 'instance_id': 6}]},
                                     {'manifest': 'default.json', 'grants': grants}]}
        before = {'boot.json': package.encoded(boot), 'cohort.json': package.encoded({'version': '1.0.0', 'product': product}),
                  'default.elf': b'old-default', 'default.json': package.encoded({'id': 'twatch-clock'}),
                  'alarm-service/driver.elf': b'synthetic-alarm', 'driver/driver.elf': b'untouched-driver',
                  'other.elf': b'untouched-app', 'board.json': b'untouched-board'}
        default, manifest = b'canonical-default', package.encoded(app)
        p = {'version': '1.0.1', 'product': product, 'default_bytes': len(default), 'default_sha256': package.sha(default),
             'default_manifest_sha256': package.sha(manifest)}
        return before, default, manifest, p, '1' * 40

    def test_composition_and_every_payload_mutation(self):
        with patch.object(package, 'ALARM_SHA', package.sha(b'synthetic-alarm')):
            for product in ('twatch', 'waveshare'):
                args = self.fixtures(product)
                before, default, manifest, p, revision = args
                after = package.compose(*args)
                proof = package.verify_store(before, after, default, manifest, p, revision)
                self.assertEqual(proof['unchanged_elf_count'], 3)
                for name in after:
                    changed = dict(after); changed[name] += b'!'
                    with self.subTest(product=product, payload=name), self.assertRaises((ValueError, json.JSONDecodeError)):
                        package.verify_store(before, changed, default, manifest, p, revision)
                changed = dict(after); changed['unexpected.bin'] = b'new'
                with self.assertRaises(ValueError): package.verify_store(before, changed, default, manifest, p, revision)
                changed = dict(after); del changed['other.elf']
                with self.assertRaises(ValueError): package.verify_store(before, changed, default, manifest, p, revision)
                changed = dict(after); boot = json.loads(changed['boot.json'])
                boot['app_capabilities'][0]['grants'][0]['instance_id'] = 7
                changed['boot.json'] = package.encoded(boot)
                with self.assertRaises(ValueError): package.verify_store(before, changed, default, manifest, p, revision)

    def test_only_default_policy_changed(self):
        for product in ('twatch', 'waveshare'):
            before, _, manifest, _, _ = self.fixtures(product)
            boot = json.loads(before['boot.json']); app = json.loads(manifest)
            after = package.provision(boot, app, product)
            self.assertEqual(after['app_capabilities'][0], boot['app_capabilities'][0])
            self.assertEqual(after['drivers'], boot['drivers'])
            route = [x for x in after['app_capabilities'][1]['grants'] if x['capability'] == 'storage.files']
            self.assertEqual(len(route), 1 if product == 'waveshare' else 0)
            if route: self.assertEqual((route[0]['instance_id'], route[0]['backend_instance'], route[0]['backend_provider']), (12, 12, 'sdmmc-fatfs'))
            broken = copy.deepcopy(boot); broken['app_capabilities'].append(broken['app_capabilities'][1])
            with self.assertRaises(ValueError): package.provision(broken, app, product)

    def test_runtime_cohort_binding(self):
        before, _, _, p, revision = self.fixtures('twatch')
        firmware = b'new-runtime\0RISC_RUNTIME_VERSION:0.4.4\0'
        result = package.expected_cohort(before, p, revision, firmware)
        self.assertEqual(result['firmware_sha256'], package.sha(firmware))
        self.assertEqual(result['runtime_version'], '0.4.4')
        for invalid in (b'no marker', firmware * 2):
            with self.assertRaises(ValueError): package.expected_cohort(before, p, revision, invalid)


if __name__ == '__main__':
    unittest.main(verbosity=2)

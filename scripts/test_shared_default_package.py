#!/usr/bin/env python3
"""Default packaging contracts and rejection tests; no hardware assertions."""
import copy
import json
import tempfile
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

    def test_explicit_serial_namespace_selection(self):
        p = package.pins()
        profile = (package.ROOT / 'profiles/native-idf61.cmake').read_text()
        expected = package.serial_files.contract(p['product'])
        self.assertEqual(package.serial_files.check_profile(profile, p['product']), expected)
        self.assertEqual([n['id'] for n in expected['namespaces']], [2, 12] if p['product'] == 'waveshare' else [2])
        self.assertFalse(expected['active_boot_bank_writable'])
        self.assertFalse(expected['application_grants_reused'])
        previous = (package.ROOT / p['previous_release_profile']).read_text()
        package.serial_files.check_profile(profile, p['product'], previous)
        for old, new in (('RISC_PROVIDER_CAPACITY=40', 'RISC_PROVIDER_CAPACITY=39'), ('RISC_NATIVE_IQ ON', 'RISC_NATIVE_IQ OFF')):
            with self.subTest(unrelated=old), self.assertRaises(ValueError):
                package.serial_files.check_profile(profile.replace(old, new), p['product'], previous)
        for flag in expected['flags']:
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                package.serial_files.check_profile(profile.replace(flag + '=1', flag + '=0'), p['product'])
        for flag in ('RISC_NATIVE_SERIAL_BOOT_FILES=1', 'RISC_NATIVE_SERIAL_FILES=1', 'RISC_NATIVE_SERIAL_UNKNOWN=1'):
            with self.subTest(extra=flag), self.assertRaises(ValueError):
                package.serial_files.check_profile(profile.replace('set(RISC_NATIVE_DEFINITIONS', 'set(RISC_NATIVE_DEFINITIONS ' + flag), p['product'])
        if p['product'] == 'twatch':
            with self.assertRaises(ValueError):
                package.serial_files.check_profile(profile.replace('set(RISC_NATIVE_DEFINITIONS', 'set(RISC_NATIVE_DEFINITIONS RISC_NATIVE_SERIAL_SD=1'), p['product'])

    def test_native_serial_source_and_link_gate(self):
        p = package.pins()
        profile = (package.ROOT / 'profiles/native-idf61.cmake').read_text()
        symbols = ['NativeSerialStorage_prepare', 'NativeSerialStorage_sdFiles', 'NativeSerialFiles_prepare', 'ReopenedFiles_open']
        blobs = {'firmware_elf': b'synthetic', 'firmware_bin': b'/appdata/.serial-files\0'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = {}
            for name in package.serial_files.RUNTIME_SOURCES:
                source = root / name; source.parent.mkdir(parents=True, exist_ok=True); source.write_bytes(b'source')
                inputs['runtime/' + name] = package.sha(b'source')
            proof = {'source_files': inputs}
            with patch.object(package.serial_files, 'linked_symbols', return_value=symbols):
                self.assertEqual(package.serial_files.check_native(blobs, proof, p['product'], root, profile), p['serial_files'])
                for name in inputs:
                    bad = dict(inputs); del bad[name]
                    with self.subTest(missing=name), self.assertRaises(ValueError):
                        package.serial_files.check_native(blobs, {'source_files': bad}, p['product'], root, profile)
                with self.assertRaises(ValueError):
                    package.serial_files.check_native(dict(blobs, firmware_bin=b'wrong-root'), proof, p['product'], root, profile)
            for fragment in ('NativeSerialStorage', 'NativeSerialFiles', 'ReopenedFiles'):
                with patch.object(package.serial_files, 'linked_symbols', return_value=[s for s in symbols if fragment not in s]), self.assertRaises(ValueError):
                    package.serial_files.check_native(blobs, proof, p['product'], root, profile)
            if p['product'] == 'waveshare':
                with patch.object(package.serial_files, 'linked_symbols', return_value=[s for s in symbols if 'sdFiles' not in s]), self.assertRaises(ValueError):
                    package.serial_files.check_native(blobs, proof, p['product'], root, profile)

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

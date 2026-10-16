#!/usr/bin/env python3
"""Exact-input tests for T-Watch payload preparation; no device or network use."""
import argparse
import copy
import json
from pathlib import Path
import unittest
import audit_catalog_payload as a


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(a.BASELINE.read_text())
        cls.assets = {p.name: p.read_bytes() for p in ARGS.assets.iterdir() if p.is_file()}
        cls.source = a.git_sources(cls.contract, {'product': a.ROOT, 'runtime': ARGS.runtime, 'schema': ARGS.runtime})
        cls.files = a.module(cls.source['product', 'scripts/read_only_spiffs.py'], 'decoder')['read_image'](
            cls.assets['store.bin'], 0x550000)
        cls.proof = json.loads(cls.assets['qualification.json'])
        cls.report = a.audit(cls.contract, cls.assets, cls.source)

    def reject_boot(self, change):
        files, contract = dict(self.files), copy.deepcopy(self.contract)
        boot = json.loads(files['boot.json'])
        change(boot)
        files['boot.json'] = a.encoded(boot)
        contract['store_files']['boot.json'] = a.record(files['boot.json'])
        with self.assertRaises(ValueError):
            a.classify(files, contract)

    def test_complete_exact_audit(self):
        self.assertEqual(self.report['audit_status'], 'passed')
        self.assertEqual(self.report['firmware_store']['file_count'], 121)
        self.assertEqual(self.report['firmware_store']['elf_count'], 59)
        self.assertEqual(self.report['factory_appdata']['contents'], 'empty')

    def test_no_pair_from_private_workspace(self):
        self.assertFalse(self.report['paired_candidate_available'])
        self.assertEqual(self.report['associated_serial_payload']['files'], [])
        self.assertEqual([r['id'] for r in self.report['serial_admission']['namespaces']], [2])
        with self.assertRaises(ValueError):
            a.require_paired_candidate(self.report)

    def test_every_asset_is_exact(self):
        for name, raw in self.assets.items():
            with self.subTest(asset=name):
                changed = dict(self.assets)
                changed[name] = bytes([raw[0] ^ 1]) + raw[1:]
                with self.assertRaisesRegex(ValueError, 'Exact bytes differ'):
                    a.audit(self.contract, changed, self.source)

    def test_missing_public_asset(self):
        changed = dict(self.assets)
        del changed['ci-provenance.zip']
        with self.assertRaises(ValueError):
            a.audit(self.contract, changed, self.source)

    def test_unaccounted_public_asset(self):
        with self.assertRaises(ValueError):
            a.audit(self.contract, {**self.assets, 'companion.zip': b'fake'}, self.source)

    def test_duplicate_checksum_row(self):
        assets, contract = dict(self.assets), copy.deepcopy(self.contract)
        assets['SHA256SUMS'] += assets['SHA256SUMS'].splitlines(keepends=True)[0]
        contract['assets']['SHA256SUMS'] = a.record(assets['SHA256SUMS'])
        with self.assertRaisesRegex(ValueError, 'Checksum inventory differs'):
            a.audit(contract, assets, self.source)

    def test_wrong_release_source(self):
        assets, contract = dict(self.assets), copy.deepcopy(self.contract)
        release = json.loads(assets['release.json'])
        release['source_revision'] = '0' * 40
        assets['release.json'] = a.encoded(release)
        contract['assets']['release.json'] = a.record(assets['release.json'])
        with self.assertRaisesRegex(ValueError, 'Release identity differs'):
            a.audit(contract, assets, self.source)

    def test_wrong_runtime_pin(self):
        assets, contract = dict(self.assets), copy.deepcopy(self.contract)
        pins = json.loads(assets['source-pins.json'])
        pins['runtime_revision'] = '0' * 40
        assets['source-pins.json'] = a.encoded(pins)
        contract['assets']['source-pins.json'] = a.record(assets['source-pins.json'])
        with self.assertRaisesRegex(ValueError, 'Runtime/admission lineage differs'):
            a.audit(contract, assets, self.source)

    def test_external_application_route_rejected(self):
        self.reject_boot(lambda b: b['app_capabilities'][0].update(image_source={'volume_instance': 2, 'path': 'alarms.elf'}))

    def test_external_driver_route_rejected(self):
        self.reject_boot(lambda b: b['drivers'][0].update(image_source={'volume_instance': 2, 'path': 'driver.elf'}))

    def test_invented_installation_rejected(self):
        self.reject_boot(lambda b: b.update(installation={'volume_instance': 2, 'grants': []}))

    def test_invented_storage_files_grant_rejected(self):
        self.reject_boot(lambda b: b['app_capabilities'][0]['grants'].append({'capability': 'storage.files', 'instance_id': 2}))

    def test_invented_storage_volume_grant_rejected(self):
        self.reject_boot(lambda b: b['app_capabilities'][0]['grants'].append({'capability': 'storage.volume', 'instance_id': 2}))

    def test_missing_internal_elf(self):
        files, contract = dict(self.files), copy.deepcopy(self.contract)
        del files['alarms.elf']
        del contract['store_files']['alarms.elf']
        with self.assertRaisesRegex(ValueError, 'Missing internal executable'):
            a.classify(files, contract)

    def test_orphan_elf(self):
        files, contract = dict(self.files), copy.deepcopy(self.contract)
        files['unowned.elf'] = b'fake'
        contract['store_files']['unowned.elf'] = a.record(b'fake')
        with self.assertRaisesRegex(ValueError, 'Orphan or unaccounted'):
            a.classify(files, contract)

    def test_manifest_traversal(self):
        files, contract = dict(self.files), copy.deepcopy(self.contract)
        manifest = json.loads(files['alarms.json'])
        manifest['file_name'] = '../alarms.elf'
        files['alarms.json'] = a.encoded(manifest)
        contract['store_files']['alarms.json'] = a.record(files['alarms.json'])
        with self.assertRaisesRegex(ValueError, 'executable path'):
            a.classify(files, contract)

    def test_missing_driver_policy(self):
        self.reject_boot(lambda b: b['drivers'][-1].update(manifest='not-present/manifest.json'))

    def test_missing_application_policy(self):
        self.reject_boot(lambda b: b['app_capabilities'][-1].update(manifest='not-present.json'))

    def test_changed_default(self):
        self.reject_boot(lambda b: b.update(default_app='other.elf'))

    def test_no_empty_schema(self):
        schema = json.loads(self.source['schema', 'docs/catalog-payload/1.0.0/manifest.schema.json'])
        for key in ('files', 'volumes'):
            with self.subTest(key=key):
                changed = copy.deepcopy(schema)
                changed['properties']['payload']['properties'][key]['minItems'] = 0
                with self.assertRaises(ValueError):
                    a.verify_schema(changed)

    def test_no_zero_file_total(self):
        schema = json.loads(self.source['schema', 'docs/catalog-payload/1.0.0/manifest.schema.json'])
        schema['properties']['payload']['properties']['totals']['properties']['file_count']['minimum'] = 0
        with self.assertRaises(ValueError):
            a.verify_schema(schema)

    def test_no_publication_switch(self):
        contract = copy.deepcopy(self.contract)
        contract['publication_enabled'] = True
        with self.assertRaisesRegex(ValueError, 'cannot reserve or publish'):
            a.audit(contract, self.assets, self.source)

    def test_no_candidate_version_reservation(self):
        contract = copy.deepcopy(self.contract)
        contract['candidate_version'] = '1.1.44'
        with self.assertRaisesRegex(ValueError, 'cannot reserve or publish'):
            a.audit(contract, self.assets, self.source)

    def test_no_false_hardware_claim(self):
        proof = copy.deepcopy(self.proof)
        proof['hardware_tested'] = True
        with self.assertRaisesRegex(ValueError, 'hardware evidence claim'):
            a.verify_native(self.assets, proof, self.source, self.contract)

    def test_no_unbound_native_source(self):
        source = dict(self.source)
        source['runtime', 'src/ports/esp32s3/NativeSerialStorage.cpp'] += b'\n'
        with self.assertRaisesRegex(ValueError, 'not bound to native receipt'):
            a.verify_native(self.assets, self.proof, source, self.contract)

    def test_no_retargeting_private_namespace(self):
        profile = self.source['product', 'profiles/native-idf61.cmake'].decode()
        module = a.module(self.source['product', 'scripts/serial_files_product.py'], 'serial_contract')
        profile = profile.replace('RISC_NATIVE_SERIAL_FILES=1', 'RISC_NATIVE_SERIAL_FILES=1\n    RISC_NATIVE_SERIAL_SD=1')
        with self.assertRaisesRegex(ValueError, 'Unexpected serial namespace'):
            module['check_profile'](profile, 'twatch')

    def test_factory_internal_data_erasure(self):
        self.assertEqual(self.report['flash']['saved_settings_and_internal_data'], 'erased')
        self.assertFalse(self.report['flash']['preserving_update_kit'])
        rows = {r['name']: r for r in self.report['factory_partitions']}
        self.assertTrue(rows['nvs']['erased'])
        self.assertTrue(rows['app1']['erased'])
        self.assertTrue(rows['bootfs1']['erased'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    ARGS, remaining = parser.parse_known_args()
    unittest.main(argv=[__file__, *remaining])

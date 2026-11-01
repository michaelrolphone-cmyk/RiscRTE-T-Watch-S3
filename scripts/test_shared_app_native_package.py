#!/usr/bin/env python3
"""Pure composition invariants; actual release decode is checked by the builder."""
import copy
import json
import unittest
from unittest.mock import patch
import package_shared_app_native as p

class Composition(unittest.TestCase):
    def setUp(self):
        self.before = {f'app{i}.elf': b'old' + bytes([i]) for i in range(60)}
        self.before.update({f'data{i}.json': b'{}' for i in range(61)})
        self.before.update({'default.elf': b'old-home', 'default.json': p.encoded({'id': 'default', 'version': '0.20.4', 'requires': [{'capability': 'old.authority'}]}),
                            'boot.json': p.encoded({'drivers': [{}] * 36, 'app_capabilities': [{}] * 26}),
                            'cohort.json': p.encoded({'version': '1.1.46', 'runtime_version': '0.4.17', 'source_revision': 'b' * 40, 'extra': 'preserve'})})
        assert len(self.before) == 125
        self.contract = {'source_revision': 'b' * 40, 'version': '1.1.46',
                         'files': {n: p.record(b) for n, b in self.before.items()}}
        self.elf = b'\x7fELFtarget';self.manifest = p.encoded(dict(json.loads(self.before['default.json']), version='0.23.1'))
        self.firmware = b'\xe9RISC_RUNTIME_VERSION:0.4.18\0native'
        self.pins = {'home': {'elf': p.record(self.elf), 'manifest': p.record(self.manifest), 'version': '0.23.1'},
                     'firmware': dict(p.record(self.firmware), runtime_version='0.4.18', runtime_revision='c' * 40)}
        self.mock = patch.object(p, 'baseline_contract', return_value=self.contract);self.mock.start();self.addCleanup(self.mock.stop)
    def compose(self, **kw):
        args = dict(before=self.before, home_elf=self.elf, home_manifest=self.manifest,
                    firmware=self.firmware, product_version='1.1.47', product_revision='d' * 40, expected_inputs=self.pins)
        args.update(kw);return p.compose(**args)
    def test_only_three_changes(self):
        old=copy.deepcopy(self.before);a,r=self.compose()
        self.assertEqual(set(r['changed_store_files']),p.REPLACEMENTS);self.assertEqual(r['retained_internal_files'],122)
        self.assertEqual(self.before,old);self.assertFalse(r['feed_updated'])
        for n in old.keys()-p.REPLACEMENTS:self.assertEqual(a[n],old[n])
        self.assertEqual(json.loads(a['cohort.json'])['extra'],'preserve')
        self.assertFalse(r['publication_enabled']);self.assertFalse(r['hardware_tested'])
    def test_corrupt_internal(self):
        self.before['data0.json']=b'changed'
        with self.assertRaises(ValueError):self.compose()
    def test_missing_internal(self):
        self.before.pop('data0.json')
        with self.assertRaises(ValueError):self.compose()
    def test_extra_internal(self):
        self.before['extra']=b'x'
        with self.assertRaises(ValueError):self.compose()
    def test_manifest_authority_change(self):
        m=p.encoded(dict(json.loads(self.manifest),requires=[]));self.pins['home']['manifest']=p.record(m)
        with self.assertRaises(ValueError):self.compose(home_manifest=m)
    def test_home_metadata_change(self):
        m=p.encoded(dict(json.loads(self.manifest),icon='other'));self.pins['home']['manifest']=p.record(m)
        with self.assertRaises(ValueError):self.compose(home_manifest=m)
    def test_home_wrong_bytes(self):
        with self.assertRaises(ValueError):self.compose(home_elf=b'other')
    def test_native_wrong_bytes(self):
        with self.assertRaises(ValueError):self.compose(firmware=b'other')
    def test_native_ambiguous_identity(self):
        f=self.firmware+b'RISC_RUNTIME_VERSION:0.4.19\0';self.pins['firmware'].update(p.record(f))
        with self.assertRaises(ValueError):self.compose(firmware=f)
    def test_runtime_rollback(self):
        f=self.firmware.replace(b'0.4.18',b'0.4.17');self.pins['firmware'].update(p.record(f),runtime_version='0.4.17')
        with self.assertRaises(ValueError):self.compose(firmware=f)
    def test_product_identity(self):
        for v in ('1.1.46','1.1.45','01.1.65','bad'):
            with self.subTest(v=v),self.assertRaises(ValueError):self.compose(product_version=v)
        with self.assertRaises(ValueError):self.compose(product_revision='branch')
    def test_runtime_source_pin(self):
        self.pins['firmware']['runtime_revision']='branch'
        with self.assertRaises(ValueError):self.compose()
    def test_no_unpinned_category(self):
        self.pins['apps']={}
        with self.assertRaises(ValueError):self.compose()
    def test_size_type_not_boolean(self):
        self.pins['home']['elf']['bytes']=True
        with self.assertRaises(ValueError):self.compose()
    def test_partition_overflow(self):
        f=self.firmware+b'x'*0x260000;self.pins['firmware'].update(p.record(f))
        with self.assertRaises(ValueError):self.compose(firmware=f)

class ReleasedContract(unittest.TestCase):
    def test_actual_selected_contract(self):
        c=p.baseline_contract()
        self.assertEqual(c['repo'],'michaelrolphone-cmyk/RiscRTE-T-Watch-S3')
        self.assertEqual(c['release_tag'],'test-provisioning-1.1.46')
        self.assertEqual(len(c['files']),125)
        self.assertEqual(sum(n.endswith('.elf') for n in c['files']),61)
        self.assertEqual((c['driver_count'],c['app_policy_count']),(36,26))
        self.assertIn('feed',c)

if __name__ == '__main__':unittest.main()

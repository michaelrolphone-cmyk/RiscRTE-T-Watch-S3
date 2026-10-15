#!/usr/bin/env python3
"""Offline rejection contracts for the official 1.1.35 successor."""
import copy, json, tempfile, unittest
from pathlib import Path
import watch_app_repair as p


class RepairTests(unittest.TestCase):
    def fixture(self):
        before = {n: b'preserved' for n in p.PINS['baseline_files']}
        before['cohort.json'] = p.encoded({'version': '1.1.35', 'apps': ['keep'], 'source_revision': p.PINS['baseline_source']})
        after = copy.deepcopy(before)
        for name in p.PINS['expected_repaired_apps']:
            before[name+'.json'] = p.encoded({'id': name, 'version': '1.2.3', 'requires': [{'capability': 'existing', 'api': 1}]})
            after[name+'.elf'] = b'repaired'
            after[name+'.json'] = p.encoded(p.next_manifest(before[name+'.json']))
        cohort = json.loads(before['cohort.json'])
        cohort.update(version=p.PINS['version'], source_revision='a'*40, runtime_version=p.PINS['runtime_version'], firmware_sha256=p.sha(b'firmware'), firmware_size=8)
        after['cohort.json'] = p.encoded(cohort)
        return before, after

    def check(self, before, after):
        return p.verify_metadata(before, after, b'firmware', 'a'*40)

    def test_exact_manifest_and_cohort_delta(self):
        self.assertEqual(len(self.check(*self.fixture())), 35)

    def test_added_capability_refused(self):
        before, after = self.fixture()
        value = json.loads(after['calculator.json']); value['requires'].append({'capability':'extra','api':1})
        after['calculator.json'] = p.encoded(value)
        with self.assertRaisesRegex(ValueError, 'authority'): self.check(before, after)

    def test_removed_capability_refused(self):
        before, after = self.fixture(); value=json.loads(after['calculator.json']); value['requires']=[]; after['calculator.json']=p.encoded(value)
        with self.assertRaisesRegex(ValueError, 'authority'): self.check(before, after)

    def test_wrong_version_refused(self):
        before, after = self.fixture(); value=json.loads(after['calculator.json']); value['version']='2.0.0'; after['calculator.json']=p.encoded(value)
        with self.assertRaisesRegex(ValueError, 'authority'): self.check(before, after)

    def test_springboard_change_refused(self):
        for name in ('springboard.elf', 'springboard.json', 'default.elf', 'default.json', 'boot.json'):
            with self.subTest(name=name):
                before, after = self.fixture(); after[name]=b'changed'
                with self.assertRaisesRegex(ValueError, 'changed store'): self.check(before, after)

    def test_file_added_or_removed_refused(self):
        for addition in (False, True):
            before, after = self.fixture()
            if addition: after['extra.elf']=b'extra'
            else: del after['springboard.elf']
            with self.assertRaisesRegex(ValueError, 'inventory'): self.check(before, after)

    def test_missing_repaired_app_refused(self):
        before, after = self.fixture(); after['calculator.elf']=before['calculator.elf']
        with self.assertRaisesRegex(ValueError, 'changed store'): self.check(before, after)

    def test_cohort_inventory_changed_refused(self):
        before, after = self.fixture(); value=json.loads(after['cohort.json']); value['apps']=[]; after['cohort.json']=p.encoded(value)
        with self.assertRaisesRegex(ValueError, 'Cohort'): self.check(before, after)

    def test_baseline_hashes_are_complete_and_springboard_bound(self):
        pins=p.PINS
        self.assertEqual(len(pins['baseline_files']),121)
        self.assertEqual(sum(n.endswith('.elf') for n in pins['baseline_files']),59)
        self.assertEqual(pins['baseline_files']['springboard.elf'],pins['preserved_springboard_sha256'])
        self.assertEqual(len(pins['expected_repaired_apps']),17)

    def test_bad_baseline_refused(self):
        with self.assertRaisesRegex(ValueError, 'official'): p.verify_baseline({})

    def test_reserved_provisioning_version_remains_distinct(self):
        self.assertEqual(p.PINS['provisioning_version_reserved'],'1.1.34')
        self.assertEqual(p.PINS['version'],'1.1.36')


if __name__ == '__main__': unittest.main()

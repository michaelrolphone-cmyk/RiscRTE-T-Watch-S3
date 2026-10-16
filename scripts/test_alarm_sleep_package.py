#!/usr/bin/env python3
"""Reject overbroad store, manifest, release, and publication mutations."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import package_alarm_sleep as p


class PackageContract(unittest.TestCase):
    def setUp(self):
        self.revision = 'a' * 40
        self.alarm = b'new ordinary ELF'
        self.manifest = {'id': 'alarm-service', 'version': '0.4.12', 'file_name': 'driver.elf',
                         'requires': [{'capability': 'storage.key-value.bound', 'api': 1}],
                         'provides': [{'capability': 'alarm.service', 'api': 1}]}
        self.manifest_bytes = p.encoded(self.manifest)
        self.before = {'alarm-service/driver.elf': b'old ordinary ELF',
                       'alarm-service/manifest.json': p.encoded(dict(self.manifest, version='0.4.11')),
                       'cohort.json': p.encoded({'version': '0.1.49', 'source_revision': 'b' * 40, 'firmware_sha256': 'c' * 64}),
                       'settings.elf': b'preserved settings', 'settings.json': b'preserved settings identity'}
        self.pins = {'alarm_bytes': len(self.alarm), 'alarm_sha256': p.sha(self.alarm),
                     'alarm_manifest_sha256': p.sha(self.manifest_bytes), 'alarm_version': '0.4.12',
                     'baseline_alarm_version': '0.4.11', 'baseline_version': '0.1.49', 'version': '0.1.50', 'elf_count': 2}
        self.after = p.compose(self.before, self.alarm, self.manifest_bytes, self.revision, self.pins)

    def test_exact_service_only_diff(self):
        self.assertEqual(p.verify_store(self.before, self.after, self.pins, self.revision), p.CHANGED)
        self.assertEqual(self.after['alarm-service/manifest.json'], self.manifest_bytes)
        self.assertEqual(self.after['settings.elf'], self.before['settings.elf'])

    def test_reject_other_elf_mutation(self):
        self.after['settings.elf'] += b'changed'
        with self.assertRaises(ValueError): p.verify_store(self.before, self.after, self.pins, self.revision)

    def test_reject_missing_elf(self):
        del self.after['settings.elf']
        with self.assertRaises(ValueError): p.verify_store(self.before, self.after, self.pins, self.revision)

    def test_reject_added_payload(self):
        self.after['rogue.elf'] = b'x'
        with self.assertRaises(ValueError): p.verify_store(self.before, self.after, self.pins, self.revision)

    def test_reject_settings_identity_mutation(self):
        self.after['settings.json'] = b'changed'
        with self.assertRaises(ValueError): p.verify_store(self.before, self.after, self.pins, self.revision)

    def test_reject_alarm_manifest_authority(self):
        for key, value in [('id', 'other'), ('requires', []), ('provides', []), ('file_name', 'other.elf')]:
            with self.subTest(key=key):
                data = p.encoded(dict(self.manifest, **{key: value}))
                pins = dict(self.pins, alarm_manifest_sha256=p.sha(data))
                with self.assertRaises(ValueError): p.compose(self.before, self.alarm, data, self.revision, pins)

    def test_reject_cohort_native_identity(self):
        self.after['cohort.json'] = p.encoded({'version': '0.1.50', 'source_revision': self.revision, 'firmware_sha256': 'd' * 64})
        with self.assertRaises(ValueError): p.verify_store(self.before, self.after, self.pins, self.revision)

    def test_reject_wrong_service_bytes(self):
        with self.assertRaises(ValueError): p.compose(self.before, self.alarm + b'bad', self.manifest_bytes, self.revision, self.pins)

    def test_reject_wrong_service_manifest_digest(self):
        with self.assertRaises(ValueError): p.compose(self.before, self.alarm, self.manifest_bytes + b' ', self.revision, self.pins)

    def test_reject_wrong_predecessor(self):
        with self.assertRaises(ValueError): p.compose(self.before, self.alarm, self.manifest_bytes, self.revision, dict(self.pins, baseline_alarm_version='0.0.0'))

    def test_reject_wrong_elf_count(self):
        with self.assertRaises(ValueError): p.verify_store(self.before, self.after, dict(self.pins, elf_count=1), self.revision)

    def test_manifest_semantics_preserved_for_watch(self):
        before = dict(self.before, **{'alarm-service/manifest.json': p.encoded(dict(self.manifest, version='0.4.9')),
                                    'cohort.json': p.encoded({'version': '1.1.40', 'source_revision': 'b' * 40})})
        pins = dict(self.pins, baseline_alarm_version='0.4.9', baseline_version='1.1.40', version='1.1.41')
        result = p.compose(before, self.alarm, self.manifest_bytes, self.revision, pins)
        self.assertEqual(result['alarm-service/driver.elf'], self.alarm)

    def test_archive_is_reproducible(self):
        self.assertEqual(p.make_archive({'b': b'2', 'a': b'1'}), p.make_archive({'a': b'1', 'b': b'2'}))

    def test_publication_source_hash_and_complete_asset_set(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)
            assets = {'factory.bin': b'factory'}
            release = dict(source_revision=self.revision, native_rebuilt=False, hardware_tested=False, device_accessed=False,
                           changed_store_files=p.CHANGED, alarm_version='0.4.12', artifacts={name:p.record(data) for name,data in assets.items()})
            assets['release.json'] = p.encoded(release)
            for name,data in assets.items(): (output/name).write_bytes(data)
            sums = ''.join(p.sha(data)+'  '+name+'\n' for name,data in sorted(assets.items())).encode()
            (output/'SHA256SUMS').write_bytes(sums)
            p.verify_output(output,p.sha(sums),self.revision)
            with self.assertRaises(ValueError): p.verify_output(output,p.sha(sums),'d'*40)
            (output/'rogue').write_bytes(b'unverified')
            with self.assertRaises(ValueError): p.verify_output(output,p.sha(sums),self.revision)

    def test_release_workflow_is_source_pinned(self):
        text = (p.ROOT/'.github/workflows/alarm-sleep-release.yml').read_text()
        self.assertIn('ref: ${{ github.sha }}', text)
        self.assertIn('persist-credentials: false', text)
        self.assertNotIn('--clobber', text)
        self.assertNotIn('workflow_dispatch:', text)
        self.assertIn('--verify-tag', text)
        self.assertIn('verify_output', text)
        self.assertIn("'source_revision'", (p.ROOT/'scripts/package_alarm_sleep.py').read_text())


if __name__ == '__main__':
    unittest.main()

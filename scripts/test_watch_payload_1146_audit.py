#!/usr/bin/env python3
"""Bounded positive/adversarial source-audit tests; no device or release writes."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import watch_payload_1146_audit as audit

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--source-cache', type=Path, required=True)
args, remaining = parser.parse_known_args()


class SourceAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = audit.decode((audit.DOCS / 'source-lock.json').read_bytes())
        cls.feed = audit.decode((audit.DOCS / 'core-feed.json').read_bytes())
        cls.release = audit.decode((audit.DOCS / 'release-metadata.json').read_bytes())
        cls.sources = audit.read_sources(cls.lock, args.source_cache)

    def changed_feed(self, mutate):
        feed = copy.deepcopy(self.feed)
        mutate(feed)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            audit.check_feed(feed)

    def test_complete_positive_audit(self):
        result = audit.audit(cache=args.source_cache)
        self.assertEqual(result['inventory'], {'files': 125, 'elf': 61, 'json': 64, 'bytes': 4958853})
        self.assertEqual(result['source_files_verified'], 20)
        self.assertEqual(result['release_binary_bytes_downloaded'], 0)
        self.assertEqual(result['generic_pair_status'], 'rejected')

    def test_every_file_has_only_evidenced_classification(self):
        matrix = audit.make_matrix(audit.check_feed(self.feed))
        self.assertTrue(matrix['not_an_installable_payload'])
        self.assertEqual(len(matrix['rows']), 125)
        for row in matrix['rows']:
            self.assertEqual(row['classification'], 'firmware-owned-internal-store')
            self.assertIsNone(row['rtef1_destination'])
            self.assertFalse(row['execution_verified'])
            self.assertIn('store_files', row['evidence'])

    def test_every_declared_file_hash_is_bound_by_exact_feed(self):
        for index in range(125):
            with self.subTest(index=index):
                changed = copy.deepcopy(self.feed)
                changed['boot_profiles']['core']['profile']['files'][index][2] = '0' * 64
                with self.assertRaises(ValueError):
                    audit.exact(audit.encoded(changed), self.lock['snapshots']['core-feed.json'], 'feed')

    def test_missing_extra_and_empty_inventory(self):
        for replacement in ([], self.feed['boot_profiles']['core']['profile']['files'][:-1],
                            self.feed['boot_profiles']['core']['profile']['files'] + [['extra.json', 1, '0' * 64]]):
            self.changed_feed(lambda f: f['boot_profiles']['core']['profile'].update(files=replacement))

    def test_duplicate_and_overlapping_paths(self):
        for value in ('alarm-service/driver.elf', 'alarm-service'):
            self.changed_feed(lambda f: f['boot_profiles']['core']['profile']['files'][1].__setitem__(0, value))

    def test_path_adversaries(self):
        for value in ('/bootfs/x.elf', '../x.elf', 'a/../x.elf', 'a//x.elf', 'a/./x.elf',
                      'a\\b.elf', 'a\n.elf', 'a\x7f.elf', 'a/.elf/', '.provision-sha256',
                      'é.elf', 'a' * 31 + '.elf', '/appdata/.serial-files/a.elf'):
            with self.subTest(path=value):
                self.changed_feed(lambda f: f['boot_profiles']['core']['profile']['files'][0].__setitem__(0, value))

    def test_size_adversaries(self):
        for value in (True, False, 0, -1, 1.5, '20684', 8 * 1024 * 1024 + 1):
            self.changed_feed(lambda f: f['boot_profiles']['core']['profile']['files'][0].__setitem__(1, value))

    def test_digest_adversaries(self):
        for value in ('', 'a' * 63, 'g' * 64, 'A' * 64, 123, None):
            self.changed_feed(lambda f: f['boot_profiles']['core']['profile']['files'][0].__setitem__(2, value))

    def test_row_shape_unknown_fields_and_sort(self):
        self.changed_feed(lambda f: f['boot_profiles']['core']['profile']['files'][0].append('2'))
        self.changed_feed(lambda f: f['boot_profiles']['core']['profile'].update(namespace='2'))
        self.changed_feed(lambda f: f['boot_profiles']['core']['profile']['files'].reverse())

    def test_catalog_is_not_core(self):
        audit.check_feed(self.feed)
        self.assertEqual(self.feed['apps'], [])
        self.assertEqual(len(self.feed['boot_profiles']['core']['profile']['files']), 125)
        self.changed_feed(lambda f: f.update(boot_profiles={}))
        self.changed_feed(lambda f: f.update(apps=[{'invented': True}]))

    def test_invented_mirror_or_serial_route_rejected(self):
        self.changed_feed(lambda f: f['boot_profiles']['core'].update(mirrors=[{'namespace': '2'}]))
        self.changed_feed(lambda f: f['boot_profiles']['core']['profile'].update(image_source={'volume_instance': 2}))

    def test_native_identity_and_image_url(self):
        for key, value in (('firmware_sha256', '0' * 64), ('runtime_version', '0.4.5'),
                           ('layout', 'littlefs'), ('store_abi', 2)):
            self.changed_feed(lambda f: f['boot_profiles']['core']['native'].update({key: value}))
        for key, value in (('bytes', 524288), ('sha256', '0' * 64), ('url', 'https://example.org/store.bin')):
            self.changed_feed(lambda f: f['boot_profiles']['core']['profile']['image'].update({key: value}))

    def test_json_duplicate_nonfinite_and_bad_utf8(self):
        for raw in (b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff'):
            with self.assertRaises((ValueError, UnicodeDecodeError)):
                audit.decode(raw)

    def test_no_budget_or_namespace_inferred(self):
        for key, value in (('accepted_write_budget', 524288 - 139264 - 4096),
                           ('rtef1_core_destination', '2'), ('accepted_generic_consumer', '.packages'),
                           ('accepted_hardware_revisions', ['*']), ('trusted_release_context', {})):
            lock = copy.deepcopy(self.lock)
            lock['admission'][key] = value
            with self.assertRaises(ValueError):
                audit.check_lock(lock)

    def test_no_pair_payload_or_hardware_claim(self):
        for key in ('generic_pair_available', 'payload_manifest_emitted', 'hardware_qualified'):
            lock = copy.deepcopy(self.lock)
            lock['admission'][key] = True
            with self.assertRaises(ValueError):
                audit.check_lock(lock)
        with self.assertRaisesRegex(ValueError, 'generic pair rejected'):
            audit.require_pair()

    def test_source_closure_and_revisions(self):
        for mutate in (lambda x: x['sources'].pop(),
                       lambda x: x['sources'].append(x['sources'][0]),
                       lambda x: x['sources'][0].update(commit='0' * 40),
                       lambda x: x['sources'][0].update(url='https://example.org/feed')):
            lock = copy.deepcopy(self.lock)
            mutate(lock)
            with self.assertRaises(ValueError):
                audit.check_lock(lock)

    def test_every_source_byte_identity(self):
        for row in self.lock['sources']:
            with self.subTest(source=row['id']):
                with self.assertRaises(ValueError):
                    audit.exact(self.sources[row['id']] + b'\n', row, row['id'])

    def test_source_namespace_alias_and_reserve_regressions(self):
        for key, old, new in (
                ('serial_storage', b'/appdata/.serial-files', b'/appdata/.packages'),
                ('package_volume', b'/appdata/.packages', b'/appdata/.serial-files'),
                ('appdata_files', b'%s/n%08lx', b'%s/.serial-files'),
                ('serial_reserve', b'ReservedBytes=139264', b'ReservedBytes=0'),
                ('producer_package', b'T-Watch must remain internal-only', b'allow external'),
                ('native_profile', b'RISC_NATIVE_SERIAL_FILES=1', b'RISC_NATIVE_SERIAL_FILES=0')):
            changed = dict(self.sources)
            changed[key] = changed[key].replace(old, new)
            with self.assertRaises(ValueError):
                audit.check_sources(changed)

    def test_empty_payload_schema_refused(self):
        value = audit.decode(self.sources['payload_schema'])
        value['properties']['payload']['properties']['files']['minItems'] = 0
        changed = dict(self.sources, payload_schema=audit.encoded(value))
        with self.assertRaises(ValueError):
            audit.check_sources(changed)

    def test_release_identity_changes(self):
        for key, value in (('id', 1), ('tag_name', 'test-shared-default-1.1.43'),
                           ('target_commitish', '0' * 40), ('draft', True)):
            release = copy.deepcopy(self.release)
            release[key] = value
            with self.assertRaises(ValueError):
                audit.check_metadata(release)

    def test_release_metadata_corrupt_missing_duplicate(self):
        for mutate in (lambda x: x['assets'].pop(),
                       lambda x: x['assets'].append(x['assets'][0]),
                       lambda x: x['assets'][0].update(size=True),
                       lambda x: next(r for r in x['assets'] if r['name'] == 'store.bin').update(digest='sha256:' + '0' * 64),
                       lambda x: x['assets'][0].update(browser_download_url='https://example.org/a')):
            release = copy.deepcopy(self.release)
            mutate(release)
            with self.assertRaises(ValueError):
                audit.check_metadata(release)

    def test_exact_snapshot_corruption(self):
        for name, pin in self.lock['snapshots'].items():
            with self.assertRaises(ValueError):
                audit.exact((audit.DOCS / name).read_bytes() + b' ', pin, name)

    def test_tampered_matrix_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('source-lock.json', 'core-feed.json', 'release-metadata.json',
                         'inventory-consumers.json', 'inventory-consumers.md'):
                (root / name).write_bytes((audit.DOCS / name).read_bytes())
            value = audit.decode((root / 'inventory-consumers.json').read_bytes())
            value['rows'][0]['rtef1_destination'] = '2'
            (root / 'inventory-consumers.json').write_bytes(audit.encoded(value))
            with self.assertRaisesRegex(ValueError, 'derived matrix differs'):
                audit.audit(docs=root, cache=args.source_cache)
            (root / 'link').symlink_to(root / 'core-feed.json')
            with self.assertRaises(ValueError):
                audit.bounded_read(root / 'link')

    def test_fetch_never_accepts_binary_asset_or_non_github_endpoint(self):
        for url in ('https://example.org/a', 'file:///etc/passwd',
                    f'https://github.com/{audit.REPOSITORY}/releases/download/{audit.TAG}/firmware.bin'):
            with self.assertRaises(ValueError):
                audit.fetch(url)

    def test_online_metadata_mismatch_fails_closed(self):
        changed = copy.deepcopy(self.release)
        changed['assets'][0]['size'] += 1
        with patch.object(audit, 'read_sources', return_value=self.sources), \
                patch.object(audit, 'fetch', return_value=audit.encoded(changed)):
            with self.assertRaisesRegex(ValueError, 'live public release metadata differs'):
                audit.audit(cache=args.source_cache, online=True)


if __name__ == '__main__':
    unittest.main(argv=[__file__, *remaining])

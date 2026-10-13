"""Source contracts plus opt-in exact, in-memory all-app staging mutations.

Set WATCH_EXPANDED_INPUTS to a JSON object containing the nine compose path
arguments (underscored CLI names, excluding output). Set
WATCH_EXPANDED_REFERENCE to the qualified staging.json to enable exact tests.
These tests never build firmware, emit a store image, or duplicate a staged store.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import current_bootfs as bootfs
import shared_watch_expanded_store as recipe


class SourceContracts(unittest.TestCase):
    def test_raw_generic_manifest_pins(self):
        self.assertEqual(recipe.ADAPTER_MANIFESTS, {
            'power_sleep': (236, '03b51f515bb72efb701976aa81de78f69bd590761d3671f41877cebfa5105e30'),
            'power_key': (238, 'e7278f18a506c29e94936358fac18cf2b3710ad008aed09a96eb8290257bc6b2'),
            'display_power': (241, '6d9fe86bdd8da3a6c20d798a06e875a1c392fce7c32ed176d69d436961032fcb'),
        })
        self.assertEqual(set(recipe.ADAPTERS), set(recipe.ADAPTER_MANIFESTS))

    def test_inventory_hash_binds_path_size_and_bytes(self):
        original = {'a.elf': b'elf', 'a.json': b'{}'}
        digest = recipe.sha(recipe.encode(recipe.inventory(original)))
        self.assertEqual(digest, recipe.sha(recipe.encode(recipe.inventory(dict(reversed(list(original.items())))))))
        for changed in ({'b.elf': b'elf', 'a.json': b'{}'},
                        {**original, 'a.elf': b'ELF'}, {**original, 'a.json': b'{}\n'}):
            with self.subTest(changed=changed):
                self.assertNotEqual(digest, recipe.sha(recipe.encode(recipe.inventory(changed))))

    def test_exact_file_custody_rejects_size_and_same_size_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'payload'
            path.write_bytes(b'original')
            digest = recipe.sha(b'original')
            self.assertEqual(recipe.checked(path, 8, digest), b'original')
            for changed in (b'Original', b'original\n'):
                path.write_bytes(changed)
                with self.assertRaisesRegex(ValueError, 'Artifact custody mismatch'):
                    recipe.checked(path, 8, digest)

    def test_strict_json_rejects_duplicates_and_nonfinite_values(self):
        for raw in (b'{"api":1,"api":2}', b'{"nested":{"x":1,"x":2}}',
                    b'{"api":NaN}', b'{"api":Infinity}', b'{"api":-Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                recipe.document(raw)
        with self.assertRaises(ValueError):
            recipe.encode({'api': float('nan')})

    def test_capacity_data_and_index_boundaries(self):
        for size, pages in ((0, 1), (1, 2), (251, 2), (252, 3),
                            (103 * 251, 104), (103 * 251 + 1, 106),
                            (227 * 251, 229), (227 * 251 + 1, 231)):
            with self.subTest(size=size):
                self.assertEqual(recipe.capacity({'object': b'x' * size}),
                                 (pages, (pages + 14) // 15, 1360 - (pages + 14) // 15))
        self.assertEqual(recipe.capacity({'object': b'x' * (14 * 251)})[:2], (15, 1))
        self.assertEqual(recipe.capacity({'object': b'x' * (15 * 251)})[:2], (16, 2))

    def test_capacity_two_free_blocks_boundary_and_overflow(self):
        # Empty objects each occupy one index page. No output or image is created.
        store = {str(i): b'' for i in range(1358 * 15)}
        self.assertEqual(recipe.capacity(store), (20370, 1358, 2))
        for count in (1358 * 15 + 1, 1360 * 15 + 1):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'free-block reserve'):
                recipe.capacity({str(i): b'' for i in range(count)})
        with self.assertRaisesRegex(ValueError, 'exact bytes'):
            recipe.capacity({'object': bytearray(b'x')})

    def test_capacity_matches_pinned_generator_without_serialization(self):
        self.assertEqual(recipe.sha(bootfs.GENERATOR.read_bytes()), bootfs.GENERATOR_SHA)
        spec = importlib.util.spec_from_file_location('count_expanded_test', bootfs.GENERATOR)
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        config = generator.SpiffsBuildConfig(**bootfs.CONFIG)
        self.assertEqual((config.OBJ_DATA_PAGE_CONTENT_LEN, config.OBJ_USABLE_PAGES_PER_BLOCK,
                          config.OBJ_INDEX_PAGES_OBJ_IDS_HEAD_LIM, config.OBJ_INDEX_PAGES_OBJ_IDS_LIM),
                         (251, 15, 103, 124))
        store = {str(i): b'x' * size for i, size in enumerate(
            (0, 1, 251, 252, 14 * 251, 15 * 251, 103 * 251, 103 * 251 + 1,
             227 * 251, 227 * 251 + 1))}
        fs = generator.SpiffsFS(0x40000, config)
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(fs, 'to_binary') as emit:
            path = Path(temporary) / 'object'
            for name, raw in sorted(store.items()):
                path.write_bytes(raw)
                fs.create_file('/' + name, str(path))
            self.assertEqual(recipe.capacity(store)[1], len(fs.blocks))
            emit.assert_not_called()

    def test_existing_output_is_refused_before_composition(self):
        with tempfile.TemporaryDirectory() as temporary:
            arguments = ['stage']
            for name in ('baseline-bin', 'shared-watch', 'home-build', 'ui-build', 'generic-components',
                         'contexts-build', 'scene-component', 'system-ui', 'compiler', 'output'):
                arguments += ['--' + name, temporary]
            with mock.patch.object(sys, 'argv', arguments), mock.patch.object(recipe, 'compose') as compose:
                with self.assertRaisesRegex(ValueError, 'fresh staging output'):
                    recipe.main()
                compose.assert_not_called()


class SyntheticStoreMutations(unittest.TestCase):
    """Exercise composition guards in CI without downloading private artifacts."""
    def setUp(self):
        applications = ['default', 'clock', 'settings', 'springboard', 'contexts']
        applications += ['app' + str(i) for i in range(20)]
        providers = ['ui-scene'] + ['provider' + str(i) for i in range(29)]
        self.old = {'board.json': b'{}\n', 'cohort.json': b'old-unsealed-cohort'}
        for app in applications:
            self.old[app + '.elf'] = ('old-' + app).encode()
            self.old[app + '.json'] = recipe.encode({'id': app, 'type': 'application',
                                                     'file_name': app + '.elf', 'requires': []})
        for provider in providers:
            self.old[provider + '/driver.elf'] = ('old-' + provider).encode()
            self.old[provider + '/manifest.json'] = recipe.encode({'type': 'driver'})
        before = {'board': 'board.json', 'default_app': 'default.elf',
                  'app_capabilities': [{'manifest': app + '.json', 'grants': []} for app in applications],
                  'drivers': [{'manifest': provider + '/manifest.json'} for provider in providers]}
        before['drivers'].append({'manifest': providers[1] + '/manifest.json', 'instance_id': 1})
        self.old['boot.json'] = recipe.encode(before)
        self.store = dict(self.old)
        for name in recipe.REPLACED:
            self.store[name] = ('new-' + name).encode()
        boot = recipe.document(self.old['boot.json'])
        for directory, _, _ in recipe.ADAPTERS.values():
            self.store[directory + '/driver.elf'] = b'new-generic-elf'
            self.store[directory + '/manifest.json'] = b'{"type":"driver"}\n'
            boot['drivers'].append({'manifest': directory + '/manifest.json'})
        rows = {row['manifest']: row for row in boot['app_capabilities']}
        for app in ('default', 'settings', 'springboard'):
            rows[app + '.json']['grants'] += [{'capability': cap, 'api': 1, 'instance_id': 0}
                                             for cap in recipe.GENERIC_CAPABILITIES]
        for app in ('settings', 'springboard', 'contexts'):
            rows[app + '.json']['grants'].append({'capability': 'app.catalog', 'api': 1, 'instance_id': 0})
        contexts = recipe.document(self.store['contexts.json'])
        contexts['optional'] = [{'capability': 'app.catalog', 'api': 1}]
        self.store['contexts.json'] = recipe.encode(contexts)
        self.store['boot.json'] = recipe.encode(boot)
        # Only the synthetic byte inventory differs from the real qualified fixture.
        patch = mock.patch.object(recipe, 'TARGET_INVENTORY_SHA',
                                  recipe.sha(recipe.encode(recipe.inventory(self.store))))
        patch.start()
        self.addCleanup(patch.stop)
        self.assertEqual(len(self.old), 113)
        self.assertEqual(recipe.verify_store(self.old, self.store), recipe.capacity(self.store))

    def mutate(self, name, change):
        value = recipe.document(self.store[name])
        change(value)
        return {**self.store, name: recipe.encode(value)}

    def test_store_membership_and_retained_custody(self):
        removed = dict(self.store)
        removed.pop('clock.elf')
        for store, message in ((removed, 'membership'),
                               ({**self.store, 'extra.elf': b'x'}, 'membership'),
                               ({**self.store, 'clock.elf': b'changed'}, 'Retained'),
                               ({**self.store, 'cohort.json': b'changed'}, 'cohort changed')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                recipe.verify_store(self.old, store)

    def test_boot_membership_and_authority_mutations(self):
        for change, message in (
            (lambda b: b['app_capabilities'].__setitem__(-1, b['app_capabilities'][0]), 'application membership'),
            (lambda b: b['drivers'][0].update(instance_id=99), 'provider membership'),
            (lambda b: b['app_capabilities'][0]['grants'].pop(), 'boot authority'),
            (lambda b: b['app_capabilities'][0]['grants'].append(b['app_capabilities'][0]['grants'][0]),
             'Duplicate application authority')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                recipe.verify_store(self.old, self.mutate('boot.json', change))

    def test_metadata_and_optional_catalog_mutations(self):
        for name, change, message in (
            ('board.json', lambda m: m.update(changed=True), 'inventory differs'),
            ('contexts.json', lambda m: m.update(id='settings'), 'identity'),
            ('contexts.json', lambda m: m.update(optional=[]), 'must remain optional')):
            with self.subTest(name=name, message=message), self.assertRaisesRegex(ValueError, message):
                recipe.verify_store(self.old, self.mutate(name, change))

    def test_required_optional_and_grant_capacity_mutations(self):
        for field in ('requires', 'optional'):
            changed = self.mutate('contexts.json', lambda m: m.update({field: [
                {'capability': 'test.' + str(i), 'api': 1} for i in range(recipe.AUTHORITY_CAPACITY+1)]}))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'capacity exceeded'):
                recipe.verify_store(self.old, changed)
        changed = self.mutate('boot.json', lambda b: b['app_capabilities'][0].update(grants=[
            {'capability': 'test.' + str(i), 'api': 1, 'instance_id': 0} for i in range(recipe.AUTHORITY_CAPACITY+1)]))
        with self.assertRaisesRegex(ValueError, 'capacity exceeded'):
            recipe.verify_store(self.old, changed)

    def test_frozen_new_payload_and_generic_metadata_mutations(self):
        for name in ('default.elf', 'powerkey/driver.elf', 'powerkey/manifest.json'):
            changed = {**self.store, name: self.store[name] + b' '}
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'inventory differs'):
                recipe.verify_store(self.old, changed)


@unittest.skipUnless(os.environ.get('WATCH_EXPANDED_INPUTS') and os.environ.get('WATCH_EXPANDED_REFERENCE'),
                     'Set explicit compose input paths and qualified staging.json reference')
class ExactArtifactMutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.args = types.SimpleNamespace(**{name: Path(value) for name, value in
                                          json.loads(os.environ['WATCH_EXPANDED_INPUTS']).items()})
        cls.old = recipe.exact_baseline(cls.args.baseline_bin)
        cls.store, cls.record = recipe.compose(cls.args)
        cls.reference = recipe.document(Path(os.environ['WATCH_EXPANDED_REFERENCE']).read_bytes())

    def mutated_json(self, name, change):
        store = dict(self.store)
        value = recipe.document(store[name])
        change(value)
        store[name] = recipe.encode(value)
        return store

    def test_exact_receipt_and_all_target_hashes_are_unchanged(self):
        self.assertEqual(self.record, self.reference)
        self.assertEqual(recipe.sha(recipe.encode(recipe.inventory(self.store))), recipe.TARGET_INVENTORY_SHA)
        self.assertEqual(recipe.verify_store(self.old, self.store), (20244, 1350, 10))
        self.assertEqual((self.record['files'], self.record['elfs'], self.record['apps'], self.record['providers']),
                         (119, 58, 25, 34))
        self.assertFalse(self.record['flashable'])
        self.assertFalse(self.record['native_cohort_admitted'])
        self.assertEqual(self.record['status'], 'unsealed component staging only')

    def test_fifty_retained_elfs_and_unsealed_cohort_are_identical(self):
        retained = [n for n in self.old if n.endswith('.elf') and n not in recipe.REPLACED]
        self.assertEqual(len(retained), 50)
        for name in retained + ['cohort.json']:
            with self.subTest(name=name):
                self.assertEqual(self.old[name], self.store[name])
        self.assertEqual(self.old, recipe.exact_baseline(self.args.baseline_bin))

    def test_raw_generic_manifest_and_elf_mutations_fail_custody(self):
        read_bytes = Path.read_bytes
        for role in recipe.ADAPTERS:
            for name in ('driver.elf', 'manifest.json'):
                target = self.args.generic_components / role / name
                raw = target.read_bytes()
                for altered in (raw + b'\n', bytes([raw[0] ^ 1]) + raw[1:]):
                    def read(path, target=target, altered=altered):
                        return altered if path == target else read_bytes(path)
                    with self.subTest(role=role, name=name, size=len(altered)), \
                            mock.patch.object(Path, 'read_bytes', read), \
                            self.assertRaisesRegex(ValueError, 'Artifact custody mismatch'):
                        recipe.load_adapter(self.args.generic_components, role)

    def test_generic_capability_identity_and_dependency_mutations_fail_custody(self):
        read_bytes = Path.read_bytes
        for role in recipe.ADAPTERS:
            target = self.args.generic_components / role / 'manifest.json'
            for change in (lambda m: m['provides'][0].update(capability='other.service'),
                           lambda m: m['requires'][0].update(api=2),
                           lambda m: m.update(id='wrong-provider')):
                manifest = recipe.document(target.read_bytes())
                change(manifest)
                altered = recipe.encode(manifest)
                def read(path, target=target, altered=altered):
                    return altered if path == target else read_bytes(path)
                with self.subTest(role=role, mutation=altered), mock.patch.object(Path, 'read_bytes', read), \
                        self.assertRaisesRegex(ValueError, 'Artifact custody mismatch'):
                    recipe.load_adapter(self.args.generic_components, role)

    def test_bad_baseline_and_selection_fail_before_staging(self):
        read_bytes = Path.read_bytes
        for target in (self.args.baseline_bin, recipe.ROOT / 'docs/watch-recovery/selection.json'):
            raw = target.read_bytes()
            altered = bytes([raw[0] ^ 1]) + raw[1:]
            def read(path):
                return altered if path == target else read_bytes(path)
            with self.subTest(path=target), mock.patch.object(Path, 'read_bytes', read), \
                    self.assertRaisesRegex(ValueError, 'custody mismatch|selection changed'):
                recipe.exact_baseline(self.args.baseline_bin)

    def test_metadata_helper_mutation_fails_before_execution(self):
        original = recipe.git_blob
        def changed(repo, revision, path):
            raw = original(repo, revision, path)
            return raw + b'\n' if path.endswith('stage_app_catalog_metadata.py') else raw
        with mock.patch.object(recipe, 'git_blob', side_effect=changed), \
                self.assertRaisesRegex(ValueError, 'Metadata helper differs'):
            recipe.compose(self.args)

    def test_launcher_fixture_duplicate_member_is_rejected(self):
        original = recipe.git_blob
        def changed(repo, revision, path):
            raw = original(repo, revision, path)
            if path.endswith('watch_springboard_catalog_23.c'):
                raw = raw.replace(b'.file_name="settings.elf"', b'.file_name="battery.elf"')
            return raw
        with mock.patch.object(recipe, 'git_blob', side_effect=changed), \
                self.assertRaisesRegex(ValueError, 'retained launcher'):
            recipe.compose(self.args)

    def test_retained_elf_and_cohort_mutations_are_rejected(self):
        for name in [n for n in self.old if n.endswith('.elf') and n not in recipe.REPLACED] + ['cohort.json']:
            changed = {**self.store, name: self.store[name] + b'x'}
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Retained|cohort changed'):
                recipe.verify_store(self.old, changed)

    def test_each_new_or_replaced_payload_mutation_is_rejected(self):
        names = recipe.REPLACED | {d + '/driver.elf' for d, _, _ in recipe.ADAPTERS.values()}
        for name in names:
            raw = self.store[name]
            changed = {**self.store, name: bytes([raw[0] ^ 1]) + raw[1:]}
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'inventory differs'):
                recipe.verify_store(self.old, changed)

    def test_every_json_metadata_mutation_is_rejected(self):
        for name in (n for n in self.store if n.endswith('.json') and n != 'cohort.json'):
            changed = self.mutated_json(name, lambda m: m.update(unselected_field=True))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'metadata|inventory'):
                recipe.verify_store(self.old, changed)

    def test_removed_added_and_renamed_store_members_are_rejected(self):
        for name in ('settings.elf', 'clock.json', 'powerkey/manifest.json'):
            removed = dict(self.store)
            removed.pop(name)
            renamed = {**removed, 'other-member': self.store[name]}
            for changed in (removed, renamed, {**self.store, 'extra': b'x'}):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'store membership'):
                    recipe.verify_store(self.old, changed)

    def test_duplicate_and_removed_app_rows_are_rejected(self):
        for change in (lambda b: b['app_capabilities'].__setitem__(-1, b['app_capabilities'][0]),
                       lambda b: b['app_capabilities'].pop(),
                       lambda b: b['app_capabilities'].reverse()):
            with self.assertRaisesRegex(ValueError, 'application membership'):
                recipe.verify_store(self.old, self.mutated_json('boot.json', change))

    def test_provider_removal_duplicates_instance_and_policy_changes_are_rejected(self):
        for change in (lambda b: b['drivers'].pop(),
                       lambda b: b['drivers'].__setitem__(-1, b['drivers'][0]),
                       lambda b: b['drivers'][0].update(instance_id=999),
                       lambda b: b['drivers'][10]['key_value'][0].update(access='read-write')):
            with self.assertRaisesRegex(ValueError, 'provider membership or policy'):
                recipe.verify_store(self.old, self.mutated_json('boot.json', change))

    def test_application_identity_and_duplicate_authority_are_rejected(self):
        for change, message in (
            (lambda m: m.update(id='settings'), 'identity'),
            (lambda m: m.update(file_name='settings.elf'), 'identity'),
            (lambda m: m['requires'].append(m['requires'][0]), 'Duplicate application authority')):
            with self.assertRaisesRegex(ValueError, message):
                recipe.verify_store(self.old, self.mutated_json('contexts.json', change))

    def test_optional_contexts_catalog_cannot_become_required(self):
        def change(manifest):
            manifest['requires'] += manifest['optional']
            manifest['optional'] = []
        with self.assertRaisesRegex(ValueError, 'catalog must remain optional'):
            recipe.verify_store(self.old, self.mutated_json('contexts.json', change))

    def test_grant_removal_instance_change_and_unrelated_policy_are_rejected(self):
        for change in (lambda b: b['app_capabilities'][0]['grants'].pop(),
                       lambda b: b['app_capabilities'][0]['grants'][-1].update(instance_id=1),
                       lambda b: b.update(default_app='settings.elf')):
            with self.assertRaisesRegex(ValueError, 'Unrelated boot authority or metadata'):
                recipe.verify_store(self.old, self.mutated_json('boot.json', change))

    def test_requirements_optional_and_grants_capacity_are_rejected(self):
        for field in ('requires', 'optional'):
            def change(manifest):
                manifest[field] = [{'capability': 'test.' + str(i), 'api': 1} for i in range(recipe.AUTHORITY_CAPACITY+1)]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'capacity exceeded'):
                recipe.verify_store(self.old, self.mutated_json('contexts.json', change))
        def change(boot):
            row = next(r for r in boot['app_capabilities'] if r['manifest'] == 'file_browser.json')
            self.assertEqual(len(row['grants']), 24)
            row['grants'] += [{'capability': 'extra'+str(i), 'api': 1, 'instance_id': 0} for i in range(recipe.AUTHORITY_CAPACITY-len(row['grants'])+1)]
        with self.assertRaisesRegex(ValueError, 'capacity exceeded'):
            recipe.verify_store(self.old, self.mutated_json('boot.json', change))

    def test_store_capacity_fails_before_final_inventory(self):
        changed = {**self.store, 'default.elf': self.store['default.elf'] + b'x' * 100000}
        with self.assertRaisesRegex(ValueError, 'free-block reserve'):
            recipe.verify_store(self.old, changed)


if __name__ == '__main__':
    unittest.main()

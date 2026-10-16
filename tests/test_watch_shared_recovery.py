"""Bounded source/staging tests. Exact artifact tests use explicit external inputs."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import stage_watch_shared_recovery as recipe


class SourceContract(unittest.TestCase):
    def test_recovery_and_home_source_pins(self):
        selected = recipe.SELECTION
        self.assertEqual(selected['baseline_source'], 'b5ed35f93792cd34a0c6df30895767a708a98658')
        self.assertEqual(selected['home']['source'], 'ec768c7fae6fdb484fef28c6ec87f129b0a7f585')
        self.assertEqual(selected['native']['retained_source'], '06da76aa7f074220b74a282badca0ed0061f1643')
        self.assertIsNone(selected['native']['selected_successor'])
        self.assertEqual(recipe.sha((ROOT / 'docs/watch-recovery/selection.json').read_bytes()),
                         selected['baseline_selection_sha256'])
        self.assertEqual(selected['home']['system_source'], '076f8da38f7dfebdfde6dd5d46e06446470fb828')
        self.assertEqual(selected['home']['utilities_source'], 'fc0bdbbbc600ce891e60c44d091fce0586ade7d8')

    def test_optional_ui_is_not_blanket_selected(self):
        ui = recipe.SELECTION['optional_ui_sources']
        self.assertFalse(ui['selected'])
        self.assertEqual(ui['allowed_apps'], ['settings', 'springboard'])

    def test_duplicate_json_and_nonfinite_refused(self):
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                recipe.document(raw)

    def test_unsigned_compaction_semantic_equality(self):
        old = {'x.json': b'{\n  "x": [1, "two"], "a": {"b": true}\n}',
               'payload.elf': b'unchanged payload'}
        new, changed = recipe.compact_metadata(old)
        self.assertEqual(changed, ['x.json'])
        self.assertEqual(recipe.document(old['x.json']), recipe.document(new['x.json']))
        self.assertEqual(old['payload.elf'], new['payload.elf'])
        self.assertEqual(recipe.compact_metadata(new)[1], [])

    def test_signed_nested_metadata_and_cohort_preserved(self):
        old = {'signed.json': b'{ "meta": { "signature": "opaque" }, "x": 1 }',
               'cohort.json': b'{ "x": 1 }'}
        new, changed = recipe.compact_metadata(old)
        self.assertEqual(old, new)
        self.assertEqual(changed, [])

    def test_generic_grants_are_independent_instance_zero(self):
        self.assertEqual(recipe.SELECTION['generic_services'], [
            {'capability': c, 'api': 1, 'instance_id': 0}
            for c in ['power.sleep', 'input.power-key', 'display.power']])


REQUIRED_ENV = ['WATCH_SHARED_RECOVERY_BASELINE', 'WATCH_SHARED_SOURCE', 'WATCH_SHARED_BUILD']


@unittest.skipUnless(all(os.environ.get(k) for k in REQUIRED_ENV),
                     'Set explicit recovered-image, shared-source and shared-build test inputs')
class ExactArtifactStaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline, cls.source, cls.build = [Path(os.environ[k]) for k in REQUIRED_ENV]
        cls.raw = cls.baseline.read_bytes()
        cls.recovery = recipe.audit(cls.raw)
        cls.old = recipe.read_image(cls.raw[0x2f0000:0x800000], recipe.IMAGE_SIZE)
        cls.stager, cls.apps, cls.record = recipe.load_home(cls.source, cls.build)
        cls.new, cls.staging, cls.compacted = recipe.stage_pair(cls.old, cls.apps, cls.stager)

    def test_exact_binary_pair_and_return_preservation(self):
        self.assertEqual(len(self.new['default.elf']), 871088)
        self.assertEqual(recipe.sha(self.new['default.elf']),
                         '7397f8ba6a036299a71bf7c62ba7882065e9ffca0ea87f0175a7eb35908cfbc1')
        self.assertEqual(recipe.sha(self.new['clock.elf']),
                         'cfd7de71d1949e415ba6662862feba4733e384258670ec73760425436d3fcde1')
        self.assertEqual(self.old['clock.elf'], self.new['clock.elf'])

    def test_all_unrelated_payloads_and_cohort_unchanged(self):
        changed = {n for n in self.old if self.old[n] != self.new[n]}
        self.assertEqual(changed, {'boot.json', 'clock.json', 'default.elf', 'default.json'})
        self.assertEqual(len(self.new), 113)
        self.assertEqual(sum(n.endswith('.elf') and self.old[n] == self.new[n] for n in self.old), 54)
        self.assertEqual(self.old['cohort.json'], self.new['cohort.json'])
        self.assertEqual(len(recipe.document(self.new['boot.json'])['app_capabilities']), 25)
        self.assertEqual(len(recipe.document(self.new['boot.json'])['drivers']), 31)

    def test_input_objects_remain_unmodified(self):
        self.assertEqual(self.old, recipe.read_image(self.raw[0x2f0000:0x800000], recipe.IMAGE_SIZE))
        self.assertEqual(recipe.sha(self.raw), recipe.RECOVERY['full_image_sha256'])

    def test_generic_requirements_and_namespaced_grants_preserved(self):
        before = next(r for r in recipe.document(self.old['boot.json'])['app_capabilities'] if r['manifest'] == 'default.json')
        after = next(r for r in recipe.document(self.new['boot.json'])['app_capabilities'] if r['manifest'] == 'default.json')
        self.assertEqual(after['grants'], before['grants'] + recipe.SELECTION['generic_services'])
        required = {(r['capability'], r['api']) for r in recipe.document(self.apps['default.json'])['requires']}
        declared = {(r['capability'], r['api']) for r in recipe.document(self.new['default.json'])['requires']}
        self.assertTrue(required <= declared)
        self.assertEqual(recipe.closure_gaps(self.new), recipe.SELECTION['generic_services'])

    def test_feature_and_dependency_receipt_refusals(self):
        for name, mutation in [
            ('font/native-height feature', lambda r: r['artifacts']['default']['defines'].remove('-DPORTABLE_WATCH_NATIVE_HEIGHT')),
            ('motion feature', lambda r: r['artifacts']['default']['defines'].remove('-DWATCH_MOTION_WAKE')),
            ('board define', lambda r: r['artifacts']['default']['defines'].append('-DTWATCH')),
            ('System source', lambda r: r['dependency_lock']['system'].__setitem__('commit', '0' * 40)),
            ('Utilities source', lambda r: r['verified_dependencies']['utilities'].__setitem__('commit', '0' * 40)),
            ('return role', lambda r: r['artifacts']['clock'].__setitem__('role', 'home')),
            ('loader sections', lambda r: r['artifacts']['default']['compaction'].__setitem__('retained_loader_sections_symbols_relocations_unchanged', False)),
        ]:
            with self.subTest(name=name):
                record = copy.deepcopy(self.record)
                mutation(record)
                with self.assertRaises(ValueError):
                    recipe.verify_record(record)

    def test_wrong_pair_bytes_refused(self):
        for name in ['default.elf', 'clock.elf', 'build.json', 'default.json']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                for member in ['default.elf', 'clock.elf', 'default.json', 'clock.json', 'build.json']:
                    raw = (self.build / member).read_bytes()
                    if member == name:
                        raw += b'\n'
                    (folder / member).write_bytes(raw)
                with self.assertRaises(ValueError):
                    recipe.load_home(self.source, folder)

    def test_source_blob_mutation_refused(self):
        original = recipe.source_blob
        def mutated(repository, commit, path):
            raw = original(repository, commit, path)
            return raw + b'\n' if path == 'scripts/build.py' else raw
        with mock.patch.object(recipe, 'source_blob', side_effect=mutated), self.assertRaises(ValueError):
            recipe.load_home(self.source, self.build)

    def test_unrelated_payload_mutations_refused(self):
        for name in ['settings.elf', 'springboard.elf', 'alarm-service/driver.elf', 'file_browser.elf', 'cohort.json']:
            with self.subTest(name=name):
                changed = dict(self.new)
                changed[name] += b'x'
                with self.assertRaises(ValueError):
                    recipe.verify_preservation(self.old, changed)

    def test_unrelated_authority_mutation_refused(self):
        changed = dict(self.new)
        boot = recipe.document(changed['boot.json'])
        boot['drivers'][0]['instance_id'] = 999
        changed['boot.json'] = recipe.encoded(boot)
        with self.assertRaisesRegex(ValueError, 'authority'):
            recipe.verify_preservation(self.old, changed)

    def test_removal_or_addition_refused(self):
        for remove in [True, False]:
            changed = dict(self.new)
            if remove:
                del changed['settings.elf']
            else:
                changed['new-driver.elf'] = b'x'
            with self.assertRaises(ValueError):
                recipe.verify_preservation(self.old, changed)

    def test_recovered_formatted_appdata_native_and_other_regions(self):
        recipe.provision_guards(self.raw, self.raw)
        for offset in [0x8000, 0x10000, 0x270100, 0x800010, 0xff5000]:
            with self.subTest(offset=hex(offset)):
                modified = bytearray(self.raw)
                modified[offset] ^= 1
                with self.assertRaises(ValueError):
                    recipe.provision_guards(self.raw, modified)

    def test_wrong_recovery_input_refused(self):
        modified = bytearray(self.raw)
        modified[0x270100] ^= 1
        with self.assertRaises(ValueError):
            recipe.audit(modified)

    def test_physical_capacity_fails_closed(self):
        before, after = recipe.capacity(self.old), recipe.capacity(self.new)
        self.assertEqual((before['occupied_blocks'], before['free_blocks']), (1294, 2))
        self.assertEqual((after['occupied_blocks'], after['free_blocks']), (1297, -1))
        self.assertEqual(after['missing_blocks'], 3)
        self.assertFalse(after['admitted'])
        self.assertFalse(after['image_generated'])

    def test_optional_compaction_still_fails_capacity(self):
        new, _, compacted = recipe.stage_pair(self.old, self.apps, self.stager, True)
        recipe.verify_preservation(self.old, new, compacted)
        self.assertEqual(recipe.capacity(new)['free_blocks'], 0)
        self.assertFalse(recipe.capacity(new)['admitted'])
        self.assertEqual(new['cohort.json'], self.old['cohort.json'])
        for name in compacted:
            self.assertEqual(recipe.document(new[name]), recipe.document(self.old[name]))

    def test_staging_outputs_only_unsealed_overlay_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            report = recipe.run(self.baseline, self.source, self.build, out)
            self.assertFalse(report['flashable'])
            self.assertFalse(report['firmware_built'])
            self.assertFalse(report['image_generated'])
            self.assertTrue(report['blockers'])
            self.assertTrue((out / 'NOT-FLASHABLE.txt').exists())
            self.assertEqual([p.name for p in out.rglob('*.bin')], [])
            self.assertEqual([p.name for p in out.rglob('*') if p.name == 'driver.elf'], [])
            for name, record in report['overlay_inventory'].items():
                raw = (out / 'UNSEALED-OVERLAY' / name).read_bytes()
                self.assertEqual(recipe.sha(raw), record['sha256'])
            with self.assertRaises(ValueError):
                recipe.run(self.baseline, self.source, self.build, out)


if __name__ == '__main__':
    unittest.main()

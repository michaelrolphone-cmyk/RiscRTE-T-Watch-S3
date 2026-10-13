import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import assemble_watch_scanner_policy as assembly
import build_scanner_policy as builder


class RecipeTest(unittest.TestCase):
    def prior(self):
        return {
            'ble_scanner.elf': b'old',
            'ble_scanner.json': assembly.encoded({'version': '0.2.18', 'requires': [
                {'capability': 'ui.text-input', 'api': 1}, {'capability': 'storage.volume', 'api': 2}]}),
            'waterfall.elf': b'unchanged-rf', 'timecard.elf': b'unchanged-timecard',
            'text-input/driver.elf': b'unchanged-text', 'ui-scene/driver.elf': b'unchanged-scene',
            'board.json': b'{ "board_id": "watch", "pins": [1, 2, 3] }\n',
            'audio_spectrum.json': b'{ "id": "ble_scanner", "type": "application", "version": "1" }\n',
            'boot.json': b' { "app_capabilities": [{"manifest":"ble_scanner.json","grants":[{"capability":"ui.text-input","api":1,"instance_id":0}]}] }\n',
            'cohort.json': assembly.encoded({'version': '1.1.18', 'source_revision': assembly.BASE}),
        }

    def component(self, old):
        return {'ble_scanner.elf': b'new', 'ble_scanner.json': assembly.encoded(
            dict(json.loads(old['ble_scanner.json']), version=builder.VERSION))}

    def test_exact_delta_preserves_input_and_other_bytes(self):
        old = self.prior()
        frozen = copy.deepcopy(old)
        new = assembly.payload(old, self.component(old), 'new')
        self.assertEqual(old, frozen)
        self.assertEqual({name for name in new if old[name] != new[name]}, assembly.CHANGED)
        assembly.verify_preservation(old, new)
        self.assertEqual(json.loads(new['ble_scanner.json']),
                         dict(json.loads(old['ble_scanner.json']), version='0.2.19'))

    def test_excess_and_removed_manifest_authority_rejected(self):
        for addition in (True, False):
            old = self.prior()
            components = self.component(old)
            manifest = json.loads(components['ble_scanner.json'])
            if addition:
                manifest['requires'].append({'capability': 'net.http', 'api': 1})
            else:
                manifest['requires'].pop()
            components['ble_scanner.json'] = assembly.encoded(manifest)
            with self.assertRaises(ValueError):
                assembly.payload(old, components, 'new')

    def test_wrong_source_and_version_rejected(self):
        for name, field in [('cohort.json', 'source_revision'), ('ble_scanner.json', 'version')]:
            old = self.prior()
            value = json.loads(old[name])
            value[field] = 'wrong'
            old[name] = assembly.encoded(value)
            with self.assertRaises(ValueError):
                assembly.payload(old, self.component(old), 'new')

    def test_duplicate_grant_rejected(self):
        old = self.prior()
        boot = json.loads(old['boot.json'])
        boot['app_capabilities'][0]['grants'].append(assembly.GRANT)
        old['boot.json'] = assembly.encoded(boot)
        with self.assertRaises(ValueError):
            assembly.payload(old, self.component(old), 'new')

    def test_unrelated_binary_and_decoded_metadata_rejected(self):
        for name, raw in [('waterfall.elf', b'changed'), ('board.json', b'{}'), ('boot.json', b'{}')]:
            old = self.prior()
            new = dict(old, **{name: raw})
            with self.assertRaises(ValueError):
                assembly.verify_preservation(old, new)

    def test_reserve_does_not_compact_when_sufficient(self):
        old = self.prior()
        with patch.object(assembly, 'ordered_build', return_value=(b'packed', {'empty_blocks': 2})):
            new, _, _, changes = assembly.compact_to_floor(old)
        self.assertEqual(old, new)
        self.assertEqual(changes, [])

    def test_lossless_reserve_compaction_preserves_boot_bytes(self):
        old = self.prior()
        calls = []
        def pack(files, _):
            calls.append(copy.deepcopy(files))
            if len(calls) == 1:
                raise ValueError('Current bootfs lacks SPIFFS free-block reserve')
            return b'packed', {'empty_blocks': 2}
        with patch.object(assembly, 'ordered_build', side_effect=pack):
            new, _, _, changes = assembly.compact_to_floor(old)
        self.assertEqual([row['path'] for row in changes], ['audio_spectrum.json'])
        self.assertEqual(old['boot.json'], new['boot.json'])
        self.assertEqual(json.loads(old['audio_spectrum.json']), json.loads(new['audio_spectrum.json']))
        assembly.verify_preservation(old, new)

    def test_irrecoverable_reserve_and_other_packing_errors_propagate(self):
        for message in ['Current bootfs lacks SPIFFS free-block reserve', 'Unexpected bad input']:
            with patch.object(assembly, 'ordered_build', side_effect=ValueError(message)):
                with self.assertRaises(ValueError):
                    assembly.compact_to_floor(self.prior())

    def test_duplicate_json_keys_are_rejected_at_all_depths(self):
        for raw in (b'{"type":"application","type":"driver"}',
                    b'{"type":"application","requires":[{"api":1,"api":2}]}'):
            with self.assertRaises(ValueError):
                assembly.strict_json(raw)
            old = self.prior()
            old['audio_spectrum.json'] = raw
            with patch.object(assembly, 'ordered_build', return_value=(b'packed', {'empty_blocks': 2})):
                with self.assertRaises(ValueError):
                    assembly.compact_to_floor(old)
            with self.assertRaises(ValueError):
                assembly.verify_preservation(old, dict(old))

    def test_signed_and_unlisted_metadata_never_compact(self):
        old = self.prior()
        old['audio_spectrum.json'] = b'{ "type": "application", "signature": "keep" }\n'
        with patch.object(assembly, 'ordered_build', side_effect=ValueError(
                'Current bootfs lacks SPIFFS free-block reserve')) as pack:
            with self.assertRaises(ValueError):
                assembly.compact_to_floor(old)
            self.assertEqual(pack.call_count, 1)
        new = dict(old, **{'audio_spectrum.json': b'{"type":"application","signature":"keep"}\n'})
        with self.assertRaises(ValueError):
            assembly.verify_preservation(old, new)
        new = dict(old, **{'board.json': b'{"board_id":"watch","pins":[1,2,3]}\n'})
        with self.assertRaises(ValueError):
            assembly.verify_preservation(old, new)

    def test_known_linker_abort_retries_identical_command_and_rejects_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            elf = root / 'app.elf'
            command = ['compiler', 'same-flags', '-o', str(elf)]
            calls = []
            def invoke(actual, **kwargs):
                calls.append(list(actual))
                elf.write_bytes(b'rejected' if len(calls) == 1 else b'accepted')
                return subprocess.CompletedProcess(actual, 1 if len(calls) == 1 else 0,
                    'ld terminated with signal 6\ndouble free or corruption (out)' if len(calls) == 1 else '')
            with patch.object(builder.subprocess, 'run', side_effect=invoke):
                history = builder.compile_exact(command, elf, root / 'logs')
            self.assertEqual(calls, [command, command])
            self.assertEqual(elf.read_bytes(), b'accepted')
            self.assertEqual((root / 'logs/rejected-link-attempt-1.elf').read_bytes(), b'rejected')
            self.assertEqual([row['returncode'] for row in history], [1, 0])

    def test_other_linker_errors_are_not_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(builder.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    ['compiler'], 1, 'unexpected linker error')) as run:
                with self.assertRaises(RuntimeError):
                    builder.compile_exact(['compiler'], root / 'app.elf', root / 'logs')
                self.assertEqual(run.call_count, 1)

    def test_persistent_known_linker_abort_remains_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(builder.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    ['compiler'], 1, 'ld terminated with signal 6\ndouble free or corruption (out)')) as run:
                with self.assertRaises(RuntimeError):
                    builder.compile_exact(['compiler'], root / 'app.elf', root / 'logs', attempts=2)
                self.assertEqual(run.call_count, 2)

    def test_only_feature_addition_is_optional_policy(self):
        self.assertEqual(builder.FEATURE_ADDITIONS, ['-DPORTABLE_TEXT_INPUT_POLICY'])
        self.assertEqual(builder.VERSION, '0.2.19')


    def test_json_scalar_types_and_nonfinite_numbers_are_not_equivalent(self):
        self.assertFalse(assembly.same_json({'api': 1}, {'api': True}))
        self.assertFalse(assembly.same_json({'api': 1}, {'api': 1.0}))
        for raw in ('{"api":NaN}', '{"api":Infinity}', '{"api":-Infinity}'):
            with self.assertRaises(ValueError):
                assembly.strict_json(raw)

    def test_exact_watch_command_only_adds_policy(self):
        prior = {'defines': ['-DKEEP_FEATURE', '-flto'],
                 'command': ['compiler', '-DKEEP_FEATURE', '-flto', '/old/source.c', '-o', '/old/app.elf'], 'source_roots': {'generated':'/old'}}
        from pathlib import Path
        on, inherited = builder.command_for(prior, {'generated':Path('/out')})
        off, _ = builder.command_for(prior, {'generated':Path('/out')}, False)
        self.assertEqual([v for v in on if v not in builder.FEATURE_ADDITIONS], off)
        self.assertEqual(inherited, prior['defines'])

    def test_driver_metadata_can_compact_but_cannot_change_authority(self):
        old = self.prior()
        old['panel/manifest.json'] = b'{ "type": "driver", "requires": [{"api": 1}] }\n'
        new = dict(old)
        new['panel/manifest.json'] = b'{"type":"driver","requires":[{"api":1}]}\n'
        assembly.verify_preservation(old, new)
        new['panel/manifest.json'] = b'{"type":"driver","requires":[{"api":true}]}\n'
        with self.assertRaises(ValueError):
            assembly.verify_preservation(old, new)

    def test_public_source_gate_rejects_unfinalized_selection(self):
        with patch.object(builder, 'git', return_value='exact'), patch.object(builder, 'load_selection', return_value={'finalized':False}):
            with self.assertRaises(ValueError):
                builder.source_guard({'utilities':Path('/source')}, {'utilities':'exact'}, False)
            builder.source_guard({'utilities':Path('/source')}, {'utilities':'exact'}, True)

    def test_public_source_gate_rejects_dirty_source(self):
        selection={'finalized':True,'source_publication':'public-exact-commit','sources':{'utilities':'exact'}}
        with patch.object(builder, 'git', side_effect=['exact',' M Apps/ble_scanner.c']), patch.object(builder, 'load_selection', return_value=selection):
            with self.assertRaises(ValueError):
                builder.source_guard({'utilities':Path('/source')}, {'utilities':'exact'}, False)

    def test_policy_cannot_already_exist_in_predecessor(self):
        prior={'defines':builder.FEATURE_ADDITIONS,'source_roots':{}}
        with self.assertRaises(ValueError):
            builder.command_for(prior, {'generated':Path('/out')})

    def test_manifest_custody_is_pinned_watch_only(self):
        for name in ('manifest_sha256','record_sha256','elf_sha256'):
            self.assertEqual(len(builder.PINNED[name]),64)
        self.assertTrue(builder.SELECTION['scope']['watch_only'])
        self.assertTrue(builder.SELECTION['scope']['x4_scanner_0_2_24_provenance_unresolved'])
        self.assertTrue(builder.SELECTION['scope']['tonight_sealed_at_files'])

    def test_provisional_source_rejects_changed_system(self):
        with patch.object(builder, 'git', side_effect=['exact',' M source.c']):
            with self.assertRaises(ValueError):
                builder.source_guard({'system-apps':Path('/source')}, {'system-apps':'exact'}, True)

    def test_public_source_rejects_different_selection(self):
        selection={'finalized':True,'source_publication':'public-exact-commit','sources':{'utilities':'other'}}
        with patch.object(builder,'load_selection',return_value=selection):
            with self.assertRaises(ValueError):
                builder.source_guard({'utilities':Path('/source')}, {'utilities':'exact'}, False)

    def test_capacity_page_boundaries(self):
        self.assertEqual(assembly.page_demand({'empty':b''})['used_object_pages'],1)
        self.assertEqual(assembly.page_demand({'a':b'x'*251})['used_object_pages'],2)
        self.assertEqual(assembly.page_demand({'a':b'x'*(251*103)})['index_pages'],1)
        self.assertEqual(assembly.page_demand({'a':b'x'*(251*103+1)})['index_pages'],2)
        self.assertEqual(assembly.page_demand({'a':b'x'*(251*(103+124)+1)})['index_pages'],3)

    def test_capacity_failure_reports_exact_delta_without_mutation(self):
        old=self.prior()
        new=assembly.payload(old,self.component(old),'new')
        new['ble_scanner.elf'] = b'x'*1000
        before=copy.deepcopy(new)
        result=assembly.capacity_failure(old,new)
        self.assertEqual(new,before)
        self.assertEqual(result['scanner_elf_delta_bytes'],997)
        self.assertEqual(result['required_free_spiffs_blocks'],2)
        self.assertTrue(result['no_code_size_workaround_applied'])

class PackingOnlyTest(unittest.TestCase):
    def test_selection_is_exactly_two_named_artifacts(self):
        self.assertEqual(set(assembly.PACKING_ONLY), {'calculator.elf', 'model_viewer.elf'})
        for name, row in assembly.PACKING_ONLY.items():
            self.assertEqual(len(row['original_sha256']), 64)
            self.assertEqual(len(row['packed_sha256']), 64)
            self.assertGreater(row['original_bytes'], row['packed_bytes'])
            self.assertEqual(row['pages_saved'], 7)

    def test_packing_source_identity_is_pinned(self):
        import hashlib
        for name, row in assembly.PACKING_ONLY.items():
            raw = (assembly.ROOT / row['source_receipt']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['source_receipt_sha256'])
            receipt = json.loads(raw)
            self.assertEqual(receipt['selected_elf_sha256'], row['original_sha256'])
            self.assertFalse(receipt['rebuild'])

    def test_unselected_original_rejected_before_packing(self):
        for name in assembly.PACKING_ONLY:
            with self.assertRaisesRegex(ValueError, 'Wrong packing-only predecessor'):
                assembly.packed_companion(name, b'unselected')

    def test_companion_input_must_exist_and_remain_original(self):
        for old, new in [({}, {}), ({'calculator.elf': b'original'}, {'calculator.elf': b'changed'})]:
            with self.assertRaisesRegex(ValueError, 'Packing-only input changed'):
                assembly.pack_companions(old, new)

    def test_packing_does_not_mutate_original_or_manifest(self):
        old = {'calculator.elf': b'calc', 'model_viewer.elf': b'model',
               'calculator.json': b'calc manifest', 'model_viewer.json': b'model manifest'}
        frozen = copy.deepcopy(old)
        def packed(name, raw):
            return raw + b'-packed', {'path': name}
        with patch.object(assembly, 'packed_companion', side_effect=packed):
            new, proofs = assembly.pack_companions(old, old)
        self.assertEqual(old, frozen)
        self.assertEqual({n for n in new if new[n] != old[n]}, set(assembly.PACKING_ONLY))
        self.assertEqual({r['path'] for r in proofs}, set(assembly.PACKING_ONLY))

if __name__ == '__main__':
    unittest.main()

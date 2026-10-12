import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import assemble_watch_spectrum_policy as assembly
import build_spectrum_policy as builder


class RecipeTest(unittest.TestCase):
    def prior(self):
        return {
            'audio_spectrum.elf': b'old',
            'audio_spectrum.json': assembly.encoded({'version': '0.5.4', 'requires': [
                {'capability': 'ui.text-input', 'api': 1}, {'capability': 'audio.input', 'api': 1}]}),
            'waterfall.elf': b'unchanged-rf', 'timecard.elf': b'unchanged-timecard',
            'text-input/driver.elf': b'unchanged-text', 'ui-scene/driver.elf': b'unchanged-scene',
            'board.json': b'{ "board_id": "watch", "pins": [1, 2, 3] }\n',
            'file_browser.json': b'{ "id": "file_browser", "type": "application", "version": "1" }\n',
            'boot.json': b' { "app_capabilities": [{"manifest":"audio_spectrum.json","grants":[{"capability":"ui.text-input","api":1,"instance_id":0}]}] }\n',
            'cohort.json': assembly.encoded({'version': '1.1.18', 'source_revision': assembly.BASE}),
        }

    def component(self, old):
        return {'audio_spectrum.elf': b'new', 'audio_spectrum.json': assembly.encoded(
            dict(json.loads(old['audio_spectrum.json']), version=builder.VERSION))}

    def test_exact_delta_preserves_input_and_other_bytes(self):
        old = self.prior()
        frozen = copy.deepcopy(old)
        new = assembly.payload(old, self.component(old), 'new')
        self.assertEqual(old, frozen)
        self.assertEqual({name for name in new if old[name] != new[name]}, assembly.CHANGED)
        assembly.verify_preservation(old, new)
        self.assertEqual(json.loads(new['audio_spectrum.json']),
                         dict(json.loads(old['audio_spectrum.json']), version='0.5.5'))

    def test_excess_and_removed_manifest_authority_rejected(self):
        for addition in (True, False):
            old = self.prior()
            components = self.component(old)
            manifest = json.loads(components['audio_spectrum.json'])
            if addition:
                manifest['requires'].append({'capability': 'net.http', 'api': 1})
            else:
                manifest['requires'].pop()
            components['audio_spectrum.json'] = assembly.encoded(manifest)
            with self.assertRaises(ValueError):
                assembly.payload(old, components, 'new')

    def test_wrong_source_and_version_rejected(self):
        for name, field in [('cohort.json', 'source_revision'), ('audio_spectrum.json', 'version')]:
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
        self.assertEqual([row['path'] for row in changes], ['file_browser.json'])
        self.assertEqual(old['boot.json'], new['boot.json'])
        self.assertEqual(json.loads(old['file_browser.json']), json.loads(new['file_browser.json']))
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
            old['file_browser.json'] = raw
            with patch.object(assembly, 'ordered_build', return_value=(b'packed', {'empty_blocks': 2})):
                with self.assertRaises(ValueError):
                    assembly.compact_to_floor(old)
            with self.assertRaises(ValueError):
                assembly.verify_preservation(old, dict(old))

    def test_signed_and_unlisted_metadata_never_compact(self):
        old = self.prior()
        old['file_browser.json'] = b'{ "type": "application", "signature": "keep" }\n'
        with patch.object(assembly, 'ordered_build', side_effect=ValueError(
                'Current bootfs lacks SPIFFS free-block reserve')) as pack:
            with self.assertRaises(ValueError):
                assembly.compact_to_floor(old)
            self.assertEqual(pack.call_count, 1)
        new = dict(old, **{'file_browser.json': b'{"type":"application","signature":"keep"}\n'})
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
        self.assertEqual(builder.VERSION, '0.5.5')
        self.assertEqual(builder.COMPONENT_BUDGET_BYTES, 238000)


if __name__ == '__main__':
    unittest.main()

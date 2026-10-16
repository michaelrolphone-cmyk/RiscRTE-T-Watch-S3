import copy, json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import assemble_watch_spectrum_shared_input as union

class SpectrumUnionTests(unittest.TestCase):
    def fixture(self):
        manifest = {'id': 'audio_spectrum', 'version': '0.5.3', 'requires': [{'capability': 'storage.key-value', 'api': 1}]}
        boot = {'app_capabilities': [{'manifest': n + '.json', 'grants': [{'capability': 'kept-' + n, 'api': 1, 'instance_id': 3}]} for n in ['file_browser', 'model_viewer', 'ble_scanner', 'audio_spectrum']], 'unrelated': {'preserve': True}}
        old = {'audio_spectrum.elf': b'old', 'audio_spectrum.json': union.encoded(manifest), 'boot.json': union.encoded(boot), 'cohort.json': union.encoded({'version': '1.1.18', 'source_revision': union.BASE, 'firmware_sha256': 'kept'}), 'untouched.elf': b'unchanged'}
        manifest['version'] = '0.5.4'; manifest['requires'].append({'capability': 'ui.text-input', 'api': 1})
        return old, {'audio_spectrum.elf': b'new', 'audio_spectrum.json': union.encoded(manifest)}

    def test_only_spectrum_authority_and_cohort_identity_change(self):
        old, component = self.fixture(); frozen = copy.deepcopy(old)
        result = union.payload(old, component, 'new-source')
        self.assertEqual(old, frozen)
        self.assertEqual({n for n in old if old[n] != result[n]}, union.CHANGED)
        before = json.loads(old['boot.json']); after = json.loads(result['boot.json'])
        before['app_capabilities'][-1]['grants'].append(union.GRANT)
        self.assertEqual(after, before)
        cohort = json.loads(old['cohort.json']); cohort['source_revision'] = 'new-source'
        self.assertEqual(json.loads(result['cohort.json']), cohort)

    def test_rejects_manifest_removal_or_expansion(self):
        old, component = self.fixture(); manifest = json.loads(component['audio_spectrum.json'])
        manifest['requires'].pop(0); component['audio_spectrum.json'] = union.encoded(manifest)
        with self.assertRaisesRegex(ValueError, 'additive delta'): union.payload(old, component, 'new')

    def test_rejects_other_component_and_wrong_predecessor(self):
        old, component = self.fixture(); component['settings.elf'] = b'bad'
        with self.assertRaisesRegex(ValueError, 'Unexpected Spectrum'): union.payload(old, component, 'new')
        old, component = self.fixture(); cohort = json.loads(old['cohort.json']); cohort['source_revision'] = 'unknown'; old['cohort.json'] = union.encoded(cohort)
        with self.assertRaisesRegex(ValueError, 'Wrong LoRa'): union.payload(old, component, 'new')

if __name__ == '__main__': unittest.main()

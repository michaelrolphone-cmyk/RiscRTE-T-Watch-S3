import copy, json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import assemble_watch_points_union as union

class PointsUnionTests(unittest.TestCase):
    def fixture(self):
        manifest = {'id': 'points_in_time', 'version': '0.6.12', 'requires': [{'capability': 'storage.key-value', 'api': 1}]}
        boot = {'app_capabilities': [{'manifest': n + '.json', 'grants': [{'capability': 'kept-' + n, 'api': 1, 'instance_id': 3}]} for n in ['file_browser', 'model_viewer', 'ble_scanner', 'points_in_time']], 'unrelated': {'preserve': True}}
        old = {'points_in_time.elf': b'old', 'points_in_time.json': union.encoded(manifest), 'boot.json': union.encoded(boot), 'cohort.json': union.encoded({'version': '1.1.18', 'source_revision': union.FILES_SOURCE, 'firmware_sha256': 'kept'}), 'untouched.elf': b'unchanged'}
        manifest['version'] = '0.6.13'; manifest['requires'].append({'capability': 'ui.text-input', 'api': 1})
        return old, {'points_in_time.elf': b'new', 'points_in_time.json': union.encoded(manifest)}

    def test_only_points_authority_and_cohort_identity_change(self):
        old, component = self.fixture(); frozen = copy.deepcopy(old)
        result = union.points_union(old, component, 'new-source')
        self.assertEqual(old, frozen)
        self.assertEqual({n for n in old if old[n] != result[n]}, union.CHANGED)
        before = json.loads(old['boot.json']); after = json.loads(result['boot.json'])
        before['app_capabilities'][-1]['grants'].append(union.TEXT_GRANT)
        self.assertEqual(after, before)
        cohort = json.loads(old['cohort.json']); cohort['source_revision'] = 'new-source'
        self.assertEqual(json.loads(result['cohort.json']), cohort)

    def test_rejects_manifest_removal_or_expansion(self):
        old, component = self.fixture(); manifest = json.loads(component['points_in_time.json'])
        manifest['requires'].pop(0); component['points_in_time.json'] = union.encoded(manifest)
        with self.assertRaisesRegex(ValueError, 'additive delta'): union.points_union(old, component, 'new')

    def test_rejects_other_component_and_wrong_predecessor(self):
        old, component = self.fixture(); component['settings.elf'] = b'bad'
        with self.assertRaisesRegex(ValueError, 'Unexpected Points'): union.points_union(old, component, 'new')
        old, component = self.fixture(); cohort = json.loads(old['cohort.json']); cohort['source_revision'] = 'unknown'; old['cohort.json'] = union.encoded(cohort)
        with self.assertRaisesRegex(ValueError, 'Wrong Files'): union.points_union(old, component, 'new')

if __name__ == '__main__': unittest.main()

"""Historical derivation imports and metadata cannot fall back to live sources."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import current_cohort as live_cohort
import midpoint_source_custody as custody
import publish_midpoint_test as publisher


class MidpointSourceCustody(unittest.TestCase):
    def copy(self, directory):
        target = Path(directory) / 'frozen'
        shutil.copytree(custody.FROZEN, target)
        return target

    def test_complete_source_inventory_and_original_acceptance_are_unchanged(self):
        record = custody.verify()
        self.assertEqual(len(record['files']), 38)
        self.assertEqual(len(record['modules']), 28)
        acceptance = json.loads(publisher.ACCEPTANCE.read_bytes())
        self.assertEqual(publisher.source_guards(), acceptance['derivation_sources'])
        self.assertEqual(record['commit'], acceptance['source_sha'])
        for name in record['modules']:
            self.assertIn('scripts/' + name + '.py', record['files'])

    def test_live_import_cache_cannot_enter_frozen_graph(self):
        record = custody.verify()
        poison = {name: ModuleType('must_not_be_used') for name in record['modules']}
        paths = list(sys.path)
        with patch.dict(sys.modules, poison):
            graph = custody.FrozenModules()
            midpoint = graph.load('midpoint_upgrade')
            self.assertEqual(midpoint.baseline()['source_revision'], midpoint.MIDPOINT_SOURCE)
            self.assertIs(midpoint.create, graph.load('current_cohort').create)
            self.assertIs(midpoint.base.build_store, graph.load('current_bootfs').build)
            # The import inside read_config must also stay in the frozen graph.
            self.assertEqual(graph.load('publish_watch_product').read_config()['version'], '1.0.2')
            for name, module in poison.items():
                self.assertIs(sys.modules[name], module)
        self.assertEqual(sys.path, paths)
        self.assertIs(sys.modules['current_cohort'], live_cohort)
        self.assertIsNot(publisher.cohort, live_cohort)

    def test_frozen_helper_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy(directory)
            path = root / 'scripts/current_cohort.py'
            path.write_bytes(path.read_bytes() + b'\n# altered\n')
            with self.assertRaisesRegex(ValueError, 'Frozen derivation source changed'):
                custody.FrozenModules(root)

    def test_mutation_between_verification_and_import_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy(directory)
            graph = custody.FrozenModules(root)
            path = root / 'scripts/current_cohort.py'
            path.write_bytes(path.read_bytes() + b'\n# altered after verification\n')
            with self.assertRaisesRegex(ValueError, 'Frozen derivation source changed'):
                graph.load('current_cohort')

    def test_rehashing_changed_source_does_not_authorize_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy(directory)
            path = root / 'scripts/current_cohort.py'
            path.write_bytes(path.read_bytes() + b'\n# altered\n')
            record = json.loads((root / 'PROVENANCE.json').read_bytes())
            record['files']['scripts/current_cohort.py']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            (root / 'PROVENANCE.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
            with self.assertRaisesRegex(ValueError, 'Frozen midpoint provenance changed'):
                custody.verify(root)

    def test_added_or_missing_frozen_input_is_rejected(self):
        for extra in (True, False):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                root = self.copy(directory)
                if extra:
                    (root / 'scripts/injected.py').write_text('raise AssertionError()\n')
                else:
                    (root / 'apps/current-runtime-requirements.json').unlink()
                with self.assertRaisesRegex(ValueError, 'Frozen midpoint inventory changed'):
                    custody.verify(root)

    def test_undeclared_module_cannot_be_loaded(self):
        with self.assertRaisesRegex(ImportError, 'Undeclared frozen midpoint module'):
            custody.FrozenModules().load('current_apps_overlay')

    def test_generator_loads_do_not_change_frozen_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy(directory)
            graph = custody.FrozenModules(root)
            store = {'cohort-test': b'exact frozen generator input'}
            image, proof = graph.load('current_bootfs').build(store)
            self.assertEqual(graph.load('read_only_spiffs').read_image(image, len(image)), store)
            self.assertTrue(proof['independent_round_trip_verified'])
            self.assertEqual(custody.verify(root), graph.record)
            self.assertFalse(list(root.rglob('*.pyc')))


if __name__ == '__main__':
    unittest.main()

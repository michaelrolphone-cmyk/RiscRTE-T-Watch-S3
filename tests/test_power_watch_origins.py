"""Source routes preserve authority and never infer installation of a candidate."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from current_apps_overlay import APPS, config, encoded
from current_cohort import create, encode
from power_watch_candidate import check_policy
from power_watch_origins import read_origin
from rf_spectrum_profile import upgrade_boot, PRIVATE_GRANTS
from rf_watch_candidate import accepted


class PowerOrigins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.origin = accepted()

    def delivered_policy_fixture(self):
        store = dict(self.origin['store'])
        store['boot.json'] = encoded(upgrade_boot(json.loads(store['boot.json'])))
        m = json.loads(store['waterfall.json']);m['requires'].extend({'capability': g['capability'], 'api': g['api']} for g in PRIVATE_GRANTS)
        store['waterfall.json'] = encoded(m)
        for name, version in {'pmu': '0.6.2', 'panel': '0.4.2', 'imu': '0.4.2'}.items():
            m = json.loads(store[name + '/manifest.json']);m['version'] = version
            store[name + '/manifest.json'] = encoded(m);store[name + '/driver.elf'] = b'policy-only-repaired-fixture'
        store['cohort.json'] = encode(create('1.0.10', '0.1.53', 'a' * 40, b'fixture' * 8))
        return store

    def test_delivered_origin_requires_exact_supplied_bytes(self):
        with self.assertRaisesRegex(ValueError, 'exact delivered'): read_origin('delivered-1.0.10')
        with tempfile.TemporaryDirectory() as tmp:
            descriptor = json.loads((ROOT / 'apps/power-1.0.10-origin.json').read_text())
            for name in descriptor['assets']: (Path(tmp) / name).write_bytes(b'incorrect')
            with self.assertRaisesRegex(ValueError, 'custody differs'): read_origin('delivered-1.0.10', tmp)

    def test_origin_selection_is_explicit(self):
        with self.assertRaisesRegex(ValueError, 'Unqualified'): read_origin('latest')
        origin = read_origin()
        self.assertEqual(origin['kind'], 'accepted-1.0.7')
        self.assertTrue(origin['physical_acceptance_claimed'])

    def test_ten_to_eleven_adds_no_new_grants_or_native_authority(self):
        previous = self.delivered_policy_fixture();following = dict(previous)
        c = config(profile='power-repair')
        for name in APPS:
            m = json.loads(following[name + '.json']);m['version'] = c['app_versions'][name]
            following[name + '.json'] = encoded(m)
        proof = check_policy(previous, following, c)
        self.assertEqual(proof['new_private_grants'], [])
        self.assertTrue(proof['all_prior_persistent_owners_preserved'])
        following['panel/driver.elf'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'version increment'): check_policy(previous, following, c)

    def test_open_selection_cannot_be_packaged_as_final_by_default(self):
        import build_power_watch_candidate as builder
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(builder, 'checked_source', return_value='a' * 40), \
                 patch.object(builder, 'verify_apps', return_value=({}, {'cutoff_selection': {'status': 'open'}})), \
                 patch.object(builder, 'read_origin') as read:
                with self.assertRaisesRegex(ValueError, 'selection remains open'):
                    builder.prepare(root / 'apps', root / 'runtime', root / 'native', root / 'output')
            read.assert_not_called()
            self.assertFalse((root / 'output').exists())

    def test_installer_never_calls_delivered_source_hardware_accepted(self):
        from build_power_watch_candidate import instructions
        text = instructions('paired', 'bma423', {'asset': 'paired.bin'}, None, 'delivered-1.0.10')
        self.assertIn('delivered Watch 1.0.10', text)
        self.assertIn('no device installation or acceptance is inferred', text)
        self.assertIn('exact verified Runtime 0.1.54', text)


if __name__ == '__main__': unittest.main()

"""Power-repair is additive; immutable accepted/RF generations cannot drift."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_clock_app import clock_manifest
from build_current_apps import application_inputs, definitions
from current_apps_overlay import APPS, CLOCK_APPS, config, configure_boot, payloads
from power_repair_profile import (PRIOR_ARCHIVE, POWER_DRIVERS, STORAGE, VERSION,
                                  baseline_inputs, prior_apps, runtime_requirements)
from power_watch_candidate import check_policy
from rf_watch_candidate import accepted


class PowerRepairProfile(unittest.TestCase):
    def copy_profile(self, root):
        for file in ('apps/power-repair-sources.json', 'apps/power-repair-runtime-requirements.json',
                     'apps/rf-spectrum-sources.json', 'apps/rf-spectrum-runtime-requirements.json'):
            path = root / file;path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / file).read_bytes())

    def test_all_apps_increment_and_all_rf_features_remain(self):
        c = config(profile='power-repair', allow_pending=True)
        prior = config(profile='rf-spectrum')
        self.assertEqual(c['product_version'], '1.0.10')
        self.assertEqual(len(c['app_versions']), 22)
        self.assertEqual(c['rf_storage'], STORAGE)
        self.assertEqual(c['power_drivers'], POWER_DRIVERS)
        for name in APPS:
            self.assertGreater(tuple(map(int, c['app_versions'][name].split('.'))),
                               tuple(map(int, prior['app_versions'][name].split('.'))))
            flags = definitions(name, c['app_versions'][name], True, rf_spectrum=True)
            self.assertIn('-DPORTABLE_LOW_BATTERY', flags)
            self.assertIn('-DWATCH_ALARM_SLEEP_RESUME', flags)
            self.assertIn('-DWATCH_MOTION_WAKE' if name in CLOCK_APPS else '-DPORTABLE_MOTION_WAKE', flags)
        self.assertEqual(payloads('power-repair') - payloads('rf-spectrum'),
                         {'panel/driver.elf', 'panel/manifest.json'})
        self.assertEqual(clock_manifest(True, True, True, True, True)['version'], c['app_versions']['clock'])
        self.assertEqual(clock_manifest(True, True, True, True)['version'], '0.10.4')

    def test_runtime_pending_pin_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);self.copy_profile(root)
            for name, key in (('power-repair-sources.json', None), ('power-repair-runtime-requirements.json', 'source_sha')):
                path = root / 'apps' / name;value = json.loads(path.read_text())
                if key: value[key] = None
                else: value['sources']['runtime']['commit'] = None
                path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'pin is pending'): config(root, profile='power-repair')
            self.assertIsNone(config(root, profile='power-repair', allow_pending=True)['sources']['runtime']['commit'])

    def test_source_features_versions_and_driver_drift_rejected(self):
        for mutation in ('clock', 'waterfall', 'features', 'system', 'namespace', 'driver', 'runtime'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp);self.copy_profile(root)
                path = root / 'apps/power-repair-sources.json';value = json.loads(path.read_text())
                if mutation in ('clock', 'waterfall'): value['app_versions'][mutation] = config(profile='rf-spectrum')['app_versions'][mutation]
                elif mutation == 'features': value['features']['rf_spectrum'] = False
                elif mutation == 'system': value['sources']['system-apps']['commit'] = 'f' * 40
                elif mutation == 'namespace': value['rf_storage']['app_data_instance'] = 2
                elif mutation == 'driver': value['power_drivers']['panel'] = '0.4.1'
                else: value['sources']['runtime']['commit'] = 'a' * 40
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError): config(root, profile='power-repair', allow_pending=True)

    def test_partition_and_persistent_bounds_cannot_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);self.copy_profile(root)
            path = root / 'apps/power-repair-runtime-requirements.json'
            value = json.loads(path.read_text());value['deployment']['partitions']['appdata']['offset'] += 4096
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'layout'): runtime_requirements(root, allow_pending=True)

    def test_boot_policy_is_exact_full_rf_policy(self):
        with zipfile.ZipFile(ROOT / 'release/complete-1.0.7/accepted-app-evidence.zip') as z:
            source = json.loads(z.read('current-apps-build.json'))
        self.assertEqual(configure_boot(source['baseline_boot'], 'power-repair'),
                         configure_boot(source['baseline_boot'], 'rf-spectrum'))
        policy = configure_boot(source['baseline_boot'], 'power-repair')
        self.assertEqual(len(policy['app_capabilities']), 22)
        self.assertEqual(len(policy['drivers']), 22)
        self.assertNotIn('cohort_migration', policy)
        self.assertEqual(len(next(row for row in policy['app_capabilities'] if row['manifest'] == 'waterfall.json')['grants']), 12)

    def test_rf_target_dependency_closure_retained(self):
        repos = {name: Path('/' + name) for name in ('system-apps', 'utilities', 'productivity')}
        source = application_inputs('waterfall', Path('/utilities/Apps/waterfall.c'), repos, Path('/watch'), Path('/out'), 'power-repair')[0]
        self.assertIn(Path('/system-apps/lib/NativeApps/src/SingleFloatDivisionCompat.c'), source)
        self.assertIn(Path('/watch/apps/clock/portable_sleep.c'), source)

    def test_rf_evidence_restores_only_original_spectrum_storage_input(self):
        files = {n + e: b'{}' for n in APPS for e in ('.elf', '.json')}
        files['audio_spectrum.json'] = json.dumps({'requires': [
            {'capability': 'storage.key-value', 'api': 2},
            {'capability': 'storage.key-value', 'api': 1},
            {'capability': 'storage.app-data', 'api': 1}]}).encode()
        prior = {'baseline_board': {}, 'baseline_boot': {}, 'catalog': [], 'baseline_sha256': 'a' * 64}
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'prior.zip';archive.write_bytes(b'fixture')
            with patch('power_repair_profile.prior_apps', return_value=(files, prior)):
                raw = baseline_inputs(archive)
        self.assertEqual(json.loads(raw['store/audio_spectrum.json'])['requires'],
                         [{'capability': 'storage.key-value', 'api': 1}])

    def test_historical_archive_cannot_be_substituted(self):
        with self.assertRaisesRegex(ValueError, 'custody differs'): prior_apps(b'wrong archive')

    def test_same_tree_public_repin_requires_exact_previous_identity(self):
        import pin_power_repair_sources
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);self.copy_profile(root)
            original = config(root, profile='power-repair', allow_pending=True)['sources']['runtime']['commit']
            expected = 'f' * 40
            def git(command, **kwargs):
                return 'version = 0.1.53\n' if 'show' in command else 'same-tree\n'
            with patch('power_watch_candidate.checked_source', return_value=expected), \
                 patch.object(pin_power_repair_sources.subprocess, 'check_output', side_effect=git):
                with self.assertRaisesRegex(ValueError, 'already pinned'):
                    pin_power_repair_sources.pin(root / 'runtime', expected, root)
                pin_power_repair_sources.pin(root / 'runtime', expected, root, replace_reviewed_sha=original)
            self.assertEqual(config(root, profile='power-repair')['sources']['runtime']['commit'], expected)

    def test_public_repin_rejects_different_source_tree(self):
        import pin_power_repair_sources
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);self.copy_profile(root)
            original = config(root, profile='power-repair', allow_pending=True)['sources']['runtime']['commit']
            expected = 'e' * 40
            def git(command, **kwargs):
                if 'show' in command: return 'version = 0.1.53\n'
                return 'old-tree\n' if command[-1].startswith(original) else 'new-tree\n'
            with patch('power_watch_candidate.checked_source', return_value=expected), \
                 patch.object(pin_power_repair_sources.subprocess, 'check_output', side_effect=git):
                with self.assertRaisesRegex(ValueError, 'not the reviewed same tree'):
                    pin_power_repair_sources.pin(root / 'runtime', expected, root, replace_reviewed_sha=original)
            self.assertEqual(config(root, profile='power-repair')['sources']['runtime']['commit'], original)

    def test_initial_and_paired_instructions_are_explicit(self):
        from build_power_watch_candidate import instructions
        text = instructions('both', 'bma423', {'asset': 'paired.bin'}, {'asset': 'initial.bin'})
        self.assertIn('Watch 1.0.10', text)
        self.assertIn('Runtime 0.1.53', text)
        self.assertIn('Erases NVS', text)
        self.assertIn('Preserves NVS', text)
        self.assertNotIn('reused from accepted', text)
        self.assertIn('parser grammar only', text)
        self.assertIn('not reachable through the installed updater catalog', text)
        self.assertIn('No release or catalog publication is authorized', text)


if __name__ == '__main__': unittest.main()

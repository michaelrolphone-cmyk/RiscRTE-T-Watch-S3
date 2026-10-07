"""Future RF authority/version checks use real accepted app evidence."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_clock_app
import build_current_apps
from current_apps_overlay import APPS, CLOCK_APPS, config, configure_boot, payloads
from rf_spectrum_profile import PRIVATE_GRANTS, STORAGE, runtime_requirements, upgrade_boot, validate_waterfall_manifest, verify_profile
import pin_rf_spectrum_sources
from test_current_clock_manifest import CompilerCaptured


class RfSpectrumProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(ROOT / 'release/complete-1.0.7/accepted-app-evidence.zip') as archive:
            cls.accepted = json.loads(archive.read('current-apps-build.json'))
        cls.c = config(profile='rf-spectrum', allow_pending=True)

    def copy_profile(self, root):
        for file in ('apps/rf-spectrum-sources.json', 'apps/rf-spectrum-runtime-requirements.json',
                     'apps/apex-runtime-requirements.json', 'release/complete-1.0.7/acceptance.json'):
            path = root / file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / file).read_bytes())

    def waterfall_manifest(self):
        return {'version': '0.2.0', 'min_firmware_version': '0.1.41',
                'requires': [{'capability': cap, 'api': api} for cap, api in (
                    ('display.output', '>=1'), ('input.touch.raw', '>=1'), ('radio.iq', '>=1'),
                    ('storage.key-value', '>=2'), ('alarm.service', '>=1'), ('storage.app-data', '>=1'))],
                'optional': [{'capability': 'board.battery', 'api': '>=1'},
                             {'capability': 'input.navigation', 'api': '>=1'}]}

    def test_full_profile_retains_accepted_sources_and_policy(self):
        self.assertEqual(set(self.c['app_versions']), set(APPS))
        self.assertEqual(len(APPS), 22)
        self.assertEqual(self.c['product_version'], '1.0.8')
        self.assertEqual(self.c['source_app_versions']['waterfall'], '0.2.0')
        self.assertEqual(self.c['rf_storage'], STORAGE)
        self.assertEqual(payloads('rf-spectrum'), payloads('low-battery'))
        for name in APPS:
            flags = build_current_apps.definitions(name, self.c['app_versions'][name], True, rf_spectrum=True)
            self.assertIn('-DPORTABLE_LOW_BATTERY', flags)
            self.assertIn('-DWATCH_ALARM_SLEEP_RESUME', flags)
            self.assertIn('-DWATCH_MOTION_WAKE' if name in CLOCK_APPS else '-DPORTABLE_MOTION_WAKE', flags)
        self.assertEqual(runtime_requirements()['firmware_version'], '0.1.41')

    def test_pending_pin_cannot_build_or_substitute_accepted_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.copy_profile(root)
            c = copy.deepcopy(self.c)
            c['sources']['utilities']['commit'] = None
            (root / 'apps/rf-spectrum-sources.json').write_text(json.dumps(c))
            with self.assertRaisesRegex(ValueError, 'pin is pending'):
                config(root, profile='rf-spectrum')
            self.assertIsNone(config(root, profile='rf-spectrum', allow_pending=True)['sources']['utilities']['commit'])
        self.assertEqual(config(profile='low-battery')['sources']['utilities']['commit'],
                         '5b03792a7ad1ce1610193bc82f2677e1228469f8')

    def test_exact_accepted_boot_plus_two_private_grants(self):
        original = copy.deepcopy(self.accepted['boot'])
        future = configure_boot(self.accepted['baseline_boot'], 'rf-spectrum')
        self.assertEqual(future, upgrade_boot(original))
        self.assertEqual(original, self.accepted['boot'])
        self.assertEqual(future['drivers'], original['drivers'])
        self.assertNotIn('cohort_migration', future)
        self.assertIn('cohort_migration', original)
        for before, after in zip(original['app_capabilities'], future['app_capabilities']):
            expected = copy.deepcopy(before)
            if before['manifest'] == 'waterfall.json':
                expected['grants'] += PRIVATE_GRANTS
                self.assertEqual(len(expected['grants']), 12)
            self.assertEqual(after, expected)
        data = {row['manifest']: [g['instance_id'] for g in row['grants']
                                if g['capability'] == 'storage.app-data']
                for row in future['app_capabilities']}
        self.assertEqual({k: v for k, v in data.items() if v},
                         {'timecard.json': [1], 'audio_spectrum.json': [2], 'waterfall.json': [3]})

    def test_namespace_collision_cannot_expand_authority(self):
        for added in PRIVATE_GRANTS:
            b = copy.deepcopy(self.accepted['boot'])
            b['app_capabilities'][0]['grants'].append(copy.deepcopy(added))
            with self.assertRaisesRegex(ValueError, 'already owned'):
                upgrade_boot(b)
        b = copy.deepcopy(self.accepted['boot'])
        next(d for d in b['drivers'] if 'key_value' in d)['key_value'][0]['namespace'] = 13
        with self.assertRaisesRegex(ValueError, 'already owned by a provider'):
            upgrade_boot(b)

    def test_compiler_namespaces_and_root_return_are_rf_only(self):
        for name in APPS:
            previous = build_current_apps.definitions(name, self.c['app_versions'][name], True)
            following = build_current_apps.definitions(name, self.c['app_versions'][name], True, rf_spectrum=True)
            if name == 'waterfall':
                self.assertIn('-DRF_STORAGE_INSTANCE=13', following)
                self.assertIn('-DRF_APP_DATA_INSTANCE=3', following)
                self.assertIn('-DRF_RETURN_APP="springboard.elf"', following)
                self.assertIn('-DPORTABLE_APP_LAUNCH_GUARD', following)
                self.assertNotIn('-DPORTABLE_RETURN_APP="springboard.elf"', following)
                self.assertIn('-DPORTABLE_RETURN_APP="springboard.elf"', previous)
            else:
                self.assertEqual(previous, following)
                self.assertNotIn('-DPORTABLE_APP_LAUNCH_GUARD', following)
        with self.assertRaisesRegex(ValueError, 'automatic low battery'):
            build_current_apps.definitions('waterfall', '0.2.0', rf_spectrum=True)

    def test_float_helper_is_linked_only_for_rf_and_existing_launcher(self):
        repos = {name: Path('/' + name) for name in ('system-apps', 'utilities', 'productivity')}
        helper = repos['system-apps'] / 'lib/NativeApps/src/SingleFloatDivisionCompat.c'
        for name in APPS:
            if name in CLOCK_APPS: continue
            for profile in ('current', 'low-battery', 'rf-spectrum'):
                sources, includes, allowed = build_current_apps.application_inputs(
                    name, Path('/app.c'), repos, Path('/watch'), Path('/out'), profile)
                self.assertEqual(helper in sources,
                                 name == 'springboard' or (name == 'waterfall' and profile == 'rf-spectrum'))
                self.assertNotIn('__divsf3', allowed)

    def test_candidate_command_defaults_to_rf_and_legacy_command_does_not(self):
        args = ['builder', '--system-apps', '/system', '--utilities', '/utilities',
                '--productivity', '/productivity', '--runtime', '/runtime', '--drivers', '/drivers',
                '--baseline', '/baseline.zip', '--output', '/out', '--motion-model', 'bma423']
        for default in ('current', 'rf-spectrum'):
            with patch.object(sys, 'argv', args), patch.object(build_current_apps, 'build') as build:
                build_current_apps.main(default)
            self.assertEqual(build.call_args.kwargs['profile'], default)

    def test_clock_uses_separate_manifest_and_exact_production_flags(self):
        self.assertEqual(build_clock_app.clock_manifest(True, True, True, True)['version'], '0.10.4')
        self.assertEqual(build_clock_app.clock_manifest(True, True, True)['version'], '0.10.3')
        for returning in (False, True):
            commands = []
            def capture(command, **kwargs):
                commands.append(command)
                if '-shared' in command:
                    raise CompilerCaptured()
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                shutil.copytree(ROOT / 'sdk/app', root / 'sdk/app')
                header = root / 'utilities/lib/Alarm/include/PointsRecords.h'
                header.parent.mkdir(parents=True)
                header.write_text('#define POINTS_DEFAULTS_AVAILABLE 1\n')
                with patch.object(build_clock_app, 'ROOT', root), \
                     patch.object(build_clock_app.subprocess, 'run', side_effect=capture), \
                     patch.dict(os.environ, {'TWATCH_CC': 'mock-gcc'}):
                    with self.assertRaises(CompilerCaptured):
                        build_clock_app.build(launcher=True, returning=returning, alarm_system=root / 'system',
                                              points_utilities=root / 'utilities', paired=True, current=True,
                                              low_battery=True, rf_spectrum=True)
            self.assertCountEqual([x for x in commands[-1] if x.startswith('-D')],
                                  build_current_apps.definitions('clock' if returning else 'default',
                                                                  '0.10.4', True, rf_spectrum=True))

    def test_configuration_rejects_namespace_runtime_version_and_source_drift(self):
        for mutation in ('namespace', 'quota', 'features', 'version', 'source', 'runtime', 'system', 'drivers'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.copy_profile(root)
                c = copy.deepcopy(self.c)
                if mutation == 'namespace': c['rf_storage']['key_value_instance'] = 7
                elif mutation == 'quota': c['rf_storage']['quota_bytes'] = 262144
                elif mutation == 'features': c['features']['low_battery'] = False
                elif mutation == 'version': c['app_versions']['clock'] = '0.10.3'
                elif mutation == 'source': c['source_app_versions']['waterfall'] = '0.1.5'
                elif mutation == 'runtime': c['sources']['runtime']['commit'] = '1' * 40
                elif mutation == 'system': c['sources']['system-apps']['commit'] = '1' * 40
                else: c['sdr']['commit'] = '1' * 40
                (root / 'apps/rf-spectrum-sources.json').write_text(json.dumps(c))
                with self.assertRaises(ValueError): config(root, profile='rf-spectrum', allow_pending=True)

    def test_source_manifest_requires_six_exact_capabilities_and_optional_battery(self):
        original = self.waterfall_manifest()
        validate_waterfall_manifest(original)
        for change in ('old-source', 'old-runtime', 'missing-data', 'duplicate', 'missing-battery'):
            manifest = copy.deepcopy(original)
            if change == 'old-source': manifest['version'] = '0.1.5'
            elif change == 'old-runtime': manifest['min_firmware_version'] = '0.1.37'
            elif change == 'missing-data': manifest['requires'].pop()
            elif change == 'duplicate': manifest['requires'].append(manifest['requires'][0])
            else: manifest['optional'] = []
            with self.assertRaises(ValueError): validate_waterfall_manifest(manifest)

    def test_final_source_pin_uses_clean_exact_checkout_and_cannot_repin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.copy_profile(root)
            c = copy.deepcopy(self.c)
            c['sources']['utilities']['commit'] = None
            profile = root / 'apps/rf-spectrum-sources.json'
            profile.write_text(json.dumps(c))
            utilities = root / 'utilities'
            (utilities / 'Apps').mkdir(parents=True)
            for name in pin_rf_spectrum_sources.UTILITY_APPS:
                manifest = self.waterfall_manifest() if name == 'waterfall' else {'version': c['source_app_versions'][name]}
                (utilities / 'Apps' / (name + '.json')).write_text(json.dumps(manifest))
            def git(path, *args): return 'a' * 40 if args[0] == 'rev-parse' else ''
            with patch.object(pin_rf_spectrum_sources, 'git', side_effect=git), \
                 patch.object(pin_rf_spectrum_sources.subprocess, 'run') as run:
                run.return_value.returncode = 0
                self.assertEqual(pin_rf_spectrum_sources.pin_utilities(utilities, root), 'a' * 40)
            self.assertEqual(config(root, profile='rf-spectrum')['sources']['utilities']['commit'], 'a' * 40)
            before = profile.read_bytes()
            for responses in (['b' * 40, ''], ['a' * 40, ' M Apps/waterfall.c']):
                with patch.object(pin_rf_spectrum_sources, 'git', side_effect=responses):
                    with self.assertRaises(ValueError): pin_rf_spectrum_sources.pin_utilities(utilities, root)
                self.assertEqual(profile.read_bytes(), before)

    def test_artifact_requires_exact_grants_flags_storage_and_float_helper(self):
        record = {'configuration': self.c, 'baseline_boot': self.accepted['baseline_boot'],
                  'boot': configure_boot(self.accepted['baseline_boot'], 'rf-spectrum'),
                  'runtime_requirements': runtime_requirements(), 'rf_storage': dict(STORAGE),
                  'apps': {name: {'defines': build_current_apps.definitions(name, self.c['app_versions'][name],
                                                                           True, rf_spectrum=True)} for name in APPS}}
        record['apps']['waterfall']['target_dependencies'] = {
            name: {} for name in ('system-apps:lib/NativeApps/src/SingleFloatDivisionCompat.c',
                                  'utilities:Apps/waterfall.c', 'utilities:Apps/rf_application.inc')}
        files = {row['manifest']: json.dumps({'requires': [dict(capability=c, api=a) for c, a in
                 dict.fromkeys((g['capability'], g['api']) for g in row['grants'])]}).encode()
                 for row in record['boot']['app_capabilities']}
        verify_profile(files, record)
        for change in ('battery', 'flags', 'helper', 'quota', 'migration'):
            bad_files, bad = copy.deepcopy(files), copy.deepcopy(record)
            if change == 'battery':
                manifest = json.loads(bad_files['waterfall.json'])
                manifest['requires'] = [g for g in manifest['requires'] if g['capability'] != 'board.battery']
                bad_files['waterfall.json'] = json.dumps(manifest).encode()
            elif change == 'flags': bad['apps']['waterfall']['defines'].append('-DPORTABLE_RETURN_APP="springboard.elf"')
            elif change == 'helper': del bad['apps']['waterfall']['target_dependencies']['system-apps:lib/NativeApps/src/SingleFloatDivisionCompat.c']
            elif change == 'quota': bad['rf_storage']['quota_bytes'] = 262144
            else: bad['boot']['cohort_migration'] = self.accepted['boot']['cohort_migration']
            with self.assertRaises(ValueError): verify_profile(bad_files, bad)


if __name__ == '__main__':
    unittest.main()

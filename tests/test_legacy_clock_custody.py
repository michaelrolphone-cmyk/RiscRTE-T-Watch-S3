"""Historical Clock builds must not inherit the current Home touch sampler."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_legacy_sleep import legacy_clock, legacy_inputs
import build_clock_app

SOURCE_COMMIT = '2a4fbae8fb2425bf830c302863a5e195106e77c9'
TOUCH_SHA = '1742842453178836c8d24e0810575ffc3ee4cb47ffffc89296135a45b0891185'
EXPECTED = {
    'clock.elf': {'size_bytes': 832736, 'sha256': '51a6370952d0823e224976b9b59628f0a76f4bd10c8cdf8b531aa636e49bc72a'},
    'default.elf': {'size_bytes': 832352, 'sha256': 'b02820f75f0381ee14eb919630ecdd0a0b1649f6ec671941a80a5df97b018909'},
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(directory):
    root = Path(directory)
    shutil.copytree(ROOT / 'custody/sleep-prefix', root / 'custody/sleep-prefix')
    shutil.copytree(ROOT / 'apps/clock', root / 'apps/clock')
    shutil.copytree(ROOT / 'sdk/app', root / 'sdk/app')
    return root


class LegacyClockCustody(unittest.TestCase):
    def test_touch_input_is_owned_by_original_immutable_source(self):
        source = legacy_inputs(ROOT)
        record = json.loads((source / 'PROVENANCE.json').read_text())
        self.assertEqual(record['commit'], SOURCE_COMMIT)
        self.assertEqual(record['files']['apps/clock/launcher_touch.h'], TOUCH_SHA)
        self.assertEqual(sha(source / 'apps/clock/launcher_touch.h'), TOUCH_SHA)
        self.assertEqual(len(record['files']), 130)

    def test_current_home_changes_cannot_enter_historical_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = fixture(directory)
            live = root / 'apps/clock/launcher_touch.h'
            live.write_text('#error current Home must not enter the historical Clock\n')
            for name in ('effects/boot.cpp', 'points_projection.c', 'faces/assets.inc',
                         'portable_navigation.c', 'clock_alarm.inc'):
                (root / 'apps/clock' / name).write_text('#error live source must stay separate\n')
            before = live.read_bytes()
            output = legacy_clock(root)
            self.assertEqual(sha(output / 'launcher_touch.h'), TOUCH_SHA)
            self.assertEqual(live.read_bytes(), before)
            frozen = root / 'custody/sleep-prefix/apps/clock'
            files = {p.relative_to(frozen) for p in frozen.rglob('*') if p.is_file()}
            self.assertEqual({p.relative_to(output) for p in output.rglob('*') if p.is_file()}, files)
            for name in files:
                self.assertEqual((output / name).read_bytes(), (frozen / name).read_bytes())
            # Repeated builds must also overwrite stale/current generated input.
            (output / 'launcher_touch.h').write_text('#error stale generated source\n')
            (output / 'stale-injected.h').write_text('#error stale generated source\n')
            self.assertEqual(sha(legacy_clock(root) / 'launcher_touch.h'), TOUCH_SHA)
            self.assertFalse((output / 'stale-injected.h').exists())

    def test_compiler_routes_complete_frozen_inputs_and_retains_current_lane(self):
        class StopBeforeCompile(Exception):
            pass
        with tempfile.TemporaryDirectory() as directory:
            root = fixture(directory)
            utilities = root / 'utilities'
            headers = utilities / 'lib/Alarm/include'
            headers.mkdir(parents=True)
            (headers / 'PointsRecords.h').write_text('/* legacy schema */\n')
            for current in (False, True):
                with self.subTest(current=current), mock.patch.object(build_clock_app, 'ROOT', root), \
                     mock.patch.dict('os.environ', {'TWATCH_CC': '/pinned/bin/xtensa-esp32s3-elf-gcc'}), \
                     mock.patch.object(build_clock_app.subprocess, 'run', side_effect=[None, StopBeforeCompile]) as run:
                    with self.assertRaises(StopBeforeCompile):
                        build_clock_app.build(launcher=True, alarm_system=root / 'system',
                                              points_utilities=utilities, paired=True, current=current)
                    clock = root / ('apps/clock' if current else 'dist/legacy-sleep/clock-source')
                    sdk = root if current else root / 'custody/sleep-prefix'
                    effect, target = [call.args[0] for call in run.call_args_list]
                    self.assertIn(str(clock / 'effects/boot.cpp'), effect)
                    for source in ('crown.c', 'nova/nova.c', 'points_projection.c', 'effects/divdi3.c'):
                        self.assertIn(str(clock / source), target)
                    self.assertIn('-I' + str(sdk / 'sdk/app'), target)
                    self.assertIn('-I' + str(sdk / 'sdk/driver'), target)

    def test_undeclared_frozen_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = fixture(directory)
            (root / 'custody/sleep-prefix/apps/clock/injected.h').write_text('/* undeclared */\n')
            with self.assertRaisesRegex(AssertionError, 'source inventory changed'):
                legacy_clock(root)

    def test_changed_frozen_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = fixture(directory)
            path = root / 'custody/sleep-prefix/apps/clock/launcher_touch.h'
            path.write_bytes(path.read_bytes() + b'\n/* changed */\n')
            with self.assertRaisesRegex(AssertionError, 'apps/clock/launcher_touch.h'):
                legacy_clock(root)

    def test_rehashing_changed_source_does_not_legitimize_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = fixture(directory)
            source = root / 'custody/sleep-prefix'
            path = source / 'apps/clock/launcher_touch.h'
            path.write_bytes(path.read_bytes() + b'\n/* changed */\n')
            record = json.loads((source / 'PROVENANCE.json').read_text())
            record['files']['apps/clock/launcher_touch.h'] = sha(path)
            (source / 'PROVENANCE.json').write_text(json.dumps(record, indent=2) + '\n')
            with self.assertRaisesRegex(AssertionError, 'Sleep-prefix custody record changed'):
                legacy_clock(root)

    def test_frozen_target_expectations_are_unchanged(self):
        wifi = json.loads((ROOT / 'apps/wifi-preserved-elf-baseline.json').read_text())['apps']
        update = json.loads((ROOT / 'scripts/update-preservation-baseline.json').read_text())['files']
        for name, expected in EXPECTED.items():
            self.assertEqual(wifi[name], expected)
            self.assertEqual(update[name], expected)


if __name__ == '__main__':
    unittest.main()

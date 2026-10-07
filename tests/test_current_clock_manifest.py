import sys
import json
import unittest
import os
import shutil
import tempfile
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_clock_app import build, clock_manifest
from build_latest_main_flash import installed_clock_version
import build_clock_app
from build_current_apps import definitions

class CompilerCaptured(Exception):
    pass

class CurrentClockManifest(unittest.TestCase):
    def clock_compile_command(self, current, returning):
        commands = []
        def capture(command, **kwargs):
            commands.append(command)
            if '-shared' in command:
                raise CompilerCaptured()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(build_clock_app.ROOT/'sdk/app', root/'sdk/app')
            header = root/'utilities/lib/Alarm/include/PointsRecords.h'
            header.parent.mkdir(parents=True)
            header.write_text('#define POINTS_DEFAULTS_AVAILABLE 1\n')
            with patch.object(build_clock_app, 'ROOT', root), \
                 patch.object(build_clock_app, 'legacy_clock', return_value=root/'apps/clock'), \
                 patch.object(build_clock_app, 'legacy_inputs', return_value=root), \
                 patch.object(build_clock_app.subprocess, 'run', side_effect=capture), \
                 patch.dict(os.environ, {'TWATCH_CC':'mock-gcc'}):
                with self.assertRaises(CompilerCaptured):
                    build(launcher=True, returning=returning, alarm_system=root/'system',
                          points_utilities=root/'utilities', paired=True, current=current)
        return commands[-1]

    def test_actual_current_clock_commands_require_resume(self):
        for returning in (False, True):
            command = self.clock_compile_command(current=True, returning=returning)
            actual = [arg for arg in command if arg.startswith('-D')]
            self.assertIn('-DWATCH_ALARM_SLEEP_RESUME', actual)
            self.assertCountEqual(actual, definitions('clock' if returning else 'default', '0.10.2'))
            self.assertEqual(Path(command[-1]).name, 'clock.elf' if returning else 'default.elf')

    def test_actual_historical_clock_commands_retain_prefix(self):
        for returning in (False, True):
            command = self.clock_compile_command(current=False, returning=returning)
            self.assertNotIn('-DWATCH_ALARM_SLEEP_RESUME', command)

    def test_frozen_lanes_retain_080(self):
        self.assertEqual(clock_manifest()["version"], "0.8.0")
        self.assertEqual(clock_manifest(paired=True)["version"], "0.8.0")

    def test_current_final_pair_is_0101(self):
        self.assertEqual(clock_manifest(paired=True, current=True)["version"], "0.10.2")
        m = clock_manifest(paired=True, current=True)
        m["version"] = "invalid"
        self.assertEqual(clock_manifest(paired=True, current=True)["version"], "0.10.2")

    def test_final_image_identity_follows_installed_pair(self):
        for version in ("0.8.0", "0.10.0", "0.10.1", "0.10.2"):
            store = {name: json.dumps({"version": version}).encode() for name in ("default.json", "clock.json")}
            self.assertEqual(installed_clock_version(store), version)
        store["default.json"] = b'{"version":"0.8.0"}'
        with self.assertRaisesRegex(ValueError, "Final Clock pair version differs"):
            installed_clock_version(store)

    def test_current_builder_checks_the_same_manifest_it_builds(self):
        source = (Path(__file__).resolve().parents[1]/"scripts/build_current_apps.py").read_text()
        self.assertIn("apps/clock/current-manifest.json", source)
        self.assertNotIn("apps/clock/paired-manifest.json", source)
        self.assertIn("paired=True,current=True", source)

    def test_current_profile_cannot_omit_its_cue_dependencies(self):
        with self.assertRaisesRegex(ValueError, "paired final profile"):
            clock_manifest(current=True)
        with self.assertRaisesRegex(ValueError, "complete paired CUE cohort"):
            build(current=True)

if __name__ == "__main__":
    unittest.main()

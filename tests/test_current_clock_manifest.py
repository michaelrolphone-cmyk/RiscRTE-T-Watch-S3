import sys
import json
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_clock_app import build, clock_manifest
from build_latest_main_flash import installed_clock_version

class CurrentClockManifest(unittest.TestCase):
    def test_frozen_lanes_retain_080(self):
        self.assertEqual(clock_manifest()["version"], "0.8.0")
        self.assertEqual(clock_manifest(paired=True)["version"], "0.8.0")

    def test_current_final_pair_is_081(self):
        self.assertEqual(clock_manifest(paired=True, current=True)["version"], "0.8.1")
        m = clock_manifest(paired=True, current=True)
        m["version"] = "invalid"
        self.assertEqual(clock_manifest(paired=True, current=True)["version"], "0.8.1")

    def test_final_image_identity_follows_installed_pair(self):
        for version in ("0.8.0", "0.8.1"):
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

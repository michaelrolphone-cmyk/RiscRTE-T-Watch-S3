import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_clock_app import build, clock_manifest

class CurrentClockManifest(unittest.TestCase):
    def test_frozen_lanes_retain_080(self):
        self.assertEqual(clock_manifest()["version"], "0.8.0")
        self.assertEqual(clock_manifest(paired=True)["version"], "0.8.0")

    def test_current_final_pair_is_081(self):
        self.assertEqual(clock_manifest(paired=True, current=True)["version"], "0.8.1")
        m = clock_manifest(paired=True, current=True)
        m["version"] = "invalid"
        self.assertEqual(clock_manifest(paired=True, current=True)["version"], "0.8.1")

    def test_current_profile_cannot_omit_its_cue_dependencies(self):
        with self.assertRaisesRegex(ValueError, "paired final profile"):
            clock_manifest(current=True)
        with self.assertRaisesRegex(ValueError, "complete paired CUE cohort"):
            build(current=True)

if __name__ == "__main__":
    unittest.main()

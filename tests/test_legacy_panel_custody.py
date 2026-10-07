"""Legacy deployments keep exact panel0.4.1; current builds keep panel0.4.2."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_legacy_sleep import legacy_inputs, legacy_manifests, legacy_panel_inputs
from pmu_sleep_custody import current_driver_packages
from update_test_production_store_runtime import driver_source_manifests

PANEL_PACKAGE_SHA = '6b59a6c443becc77ca8240cbc7624bca0865e408e45f46973cf0639f8fd6b90d'
PANEL_ELF_SHA = 'a7cddc560dc83e9a7ea8f408ed17637098bdc64fb9b02b028749f49c9d782aad'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class LegacyPanelCustody(unittest.TestCase):
    def test_execution_selects_frozen_panel_with_each_overlay_generation(self):
        baseline = json.loads((ROOT / 'scripts/update-preservation-baseline.json').read_text())
        expected = baseline['files']['panel/manifest.json']
        for current in (False, True):
            with self.subTest(current_profile=current):
                manifests, frozen = driver_source_manifests(current, Path('/external-drivers'))
                self.assertEqual(set(frozen), {'twatch-panel'} if current else {'twatch-gpio', 'twatch-pmu', 'twatch-panel'})
                deployed = (json.dumps(json.loads(manifests['twatch-panel'].read_text()), indent=2, sort_keys=True) + '\n').encode()
                self.assertEqual({'size_bytes': len(deployed), 'sha256': sha(deployed)}, expected)
                source_root = manifests['twatch-panel'].parents[2]
                self.assertEqual(source_root, legacy_panel_inputs(ROOT))
                self.assertTrue((source_root / 'sdk/driver/RiscDisplayOutputV1.h').is_file())
                if current:
                    self.assertEqual(manifests['twatch-pmu'], ROOT / 'drivers/twatch_pmu/manifest.json')
                    self.assertEqual(manifests['twatch-gpio'], ROOT / 'drivers/twatch_gpio/manifest.json')

    def test_separate_source_closure_preserves_older_sleep_snapshot(self):
        old = legacy_inputs(ROOT)
        panel = legacy_panel_inputs(ROOT)
        self.assertNotEqual(old, panel)
        record = json.loads((panel / 'PROVENANCE.json').read_text())
        self.assertEqual(record['commit'], '273b58d64ccc9a7dd66f0659271a942f244edcdf')
        self.assertEqual(len(record['files']), 26)
        for name, expected in record['files'].items():
            self.assertEqual(sha((panel / name).read_bytes()), expected, name)
        self.assertEqual({json.loads(p.read_text())['id'] for p in legacy_manifests(ROOT)},
                         {'twatch-gpio', 'twatch-pmu', 'twatch-panel'})
        self.assertEqual(json.loads((panel / 'drivers/twatch_panel/manifest.json').read_text())['version'], '0.4.1')
        self.assertEqual(json.loads((ROOT / 'drivers/twatch_panel/manifest.json').read_text())['version'], '0.4.2')

    def test_rehashed_source_cannot_silently_replace_custody(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'custody/panel-0.4.1'
            shutil.copytree(legacy_panel_inputs(ROOT), source)
            path = source / 'drivers/twatch_panel/driver.c'
            path.write_bytes(path.read_bytes() + b'\n/* altered */\n')
            with self.assertRaises(AssertionError):
                legacy_panel_inputs(root)
            record = json.loads((source / 'PROVENANCE.json').read_text())
            record['files']['drivers/twatch_panel/driver.c'] = sha(path.read_bytes())
            (source / 'PROVENANCE.json').write_text(json.dumps(record, indent=2) + '\n')
            with self.assertRaisesRegex(AssertionError, 'custody record changed'):
                legacy_panel_inputs(root)

    def test_historical_package_selectors_still_require_old_panel(self):
        baseline = json.loads((ROOT / 'scripts/update-preservation-baseline.json').read_text())
        before = next(p for p in baseline['driver_packages'] if p['id'] == 'twatch-panel')
        after = next(p for p in current_driver_packages(baseline, ROOT) if p['id'] == 'twatch-panel')
        self.assertEqual(before, after)
        self.assertEqual(after['version'], '0.4.1')
        self.assertEqual(after['sha256'], PANEL_PACKAGE_SHA)
        for name in ('build_alarm_common', 'build_points_common', 'build_wifi_common'):
            module = __import__(name)
            self.assertEqual(module.DRIVER_PACKAGES['twatch-panel'], PANEL_PACKAGE_SHA)

    def test_built_old_and_current_target_bytes_are_distinct(self):
        legacy_catalog = ROOT / 'dist/legacy-sleep/catalog.json'
        current_catalog = ROOT / 'dist/catalog.json'
        if not legacy_catalog.is_file() or not current_catalog.is_file():
            self.skipTest('Build target drivers for actual package/ELF custody checks')
        old = next(p for p in json.loads(legacy_catalog.read_text())['packages'] if p['id'] == 'twatch-panel')
        new = next(p for p in json.loads(current_catalog.read_text())['packages'] if p['id'] == 'twatch-panel')
        self.assertEqual((old['version'], old['sha256'], old['size_bytes']), ('0.4.1', PANEL_PACKAGE_SHA, 15344))
        self.assertEqual(new['version'], '0.4.2')
        self.assertNotEqual(old['archive'], new['archive'])
        self.assertNotEqual(old['sha256'], new['sha256'])
        baseline = json.loads((ROOT / 'scripts/update-preservation-baseline.json').read_text())
        for row in (old, new):
            package = ROOT / 'dist' / row['archive']
            self.assertEqual(sha(package.read_bytes()), row['sha256'])
            self.assertEqual(package.stat().st_size, row['size_bytes'])
            with zipfile.ZipFile(package) as archive:
                manifest = json.loads(archive.read('source-manifest.json'))
                self.assertEqual(manifest['version'], row['version'])
                elf = archive.read('driver.elf')
                if row is old:
                    self.assertEqual(sha(elf), PANEL_ELF_SHA)
                    deployed = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
                    for name, data in [('panel/driver.elf', elf), ('panel/manifest.json', deployed)]:
                        self.assertEqual({'size_bytes': len(data), 'sha256': sha(data)}, baseline['files'][name])
                else:
                    self.assertNotEqual(sha(elf), PANEL_ELF_SHA)


if __name__ == '__main__':
    unittest.main()

"""Versioned PMU target custody must not rewrite a historical delivered store."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from pmu_sleep_custody import (CUSTODY_PATH, SOURCE_PATHS, SOURCE_ROOT, current_driver_packages,
                               current_pmu_custody, verify_current_pmu)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class PmuSleepCustody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.custody = current_pmu_custody(ROOT)
        cls.baseline_bytes = (ROOT / 'scripts/update-preservation-baseline.json').read_bytes()
        cls.baseline = json.loads(cls.baseline_bytes)

    def test_explicit_versions_and_common_package_pins(self):
        import build_alarm_common
        import build_points_common
        import build_wifi_common
        package = self.custody['package']
        self.assertEqual(package['version'], '0.5.3')
        for module in (build_alarm_common, build_points_common, build_wifi_common):
            self.assertEqual(module.DRIVER_PACKAGES['twatch-pmu'], package['sha256'])

    def test_only_one_package_row_changes_and_history_is_untouched(self):
        original = copy.deepcopy(self.baseline)
        current = current_driver_packages(self.baseline, ROOT)
        self.assertEqual(self.baseline, original)
        self.assertEqual(len(current), len(original['driver_packages']))
        for old, new in zip(original['driver_packages'], current):
            if old['id'] == 'twatch-pmu':
                self.assertEqual(old['version'], '0.5.2')
                self.assertEqual(new, self.custody['package'])
            else:
                self.assertEqual(old, new)
        self.assertEqual(self.baseline_bytes, (ROOT / 'scripts/update-preservation-baseline.json').read_bytes())
        self.assertEqual(digest(self.baseline_bytes),
                         'eea78347619cb03420d3ca9a957fa025f4dc09263888b313b1a0aee72fefb39f')
        self.assertEqual(original['watch_source_sha'], '216e2d73b72cca6c3bcf75ad9ef56466b8861144')

    def test_source_and_scope_cannot_be_silently_rehashed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in {SOURCE_ROOT+"/"+n for n in SOURCE_PATHS} | {CUSTODY_PATH}:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / name).read_bytes())
            current_pmu_custody(root)
            source = root / SOURCE_ROOT / 'drivers/twatch_pmu/driver.c'
            source.write_bytes(source.read_bytes() + b'\n/* unbuilt change */\n')
            with self.assertRaisesRegex(ValueError, 'source differs'):
                current_pmu_custody(root)
            source.write_bytes((ROOT / SOURCE_ROOT / 'drivers/twatch_pmu/driver.c').read_bytes())
            custody = copy.deepcopy(self.custody)
            custody['files']['rtc/driver.elf'] = custody['files']['pmu/driver.elf']
            (root / CUSTODY_PATH).write_text(json.dumps(custody))
            with self.assertRaisesRegex(ValueError, 'scope'):
                current_pmu_custody(root)

    def target_files(self):
        package = self.custody['package']
        path = ROOT / 'dist' / package['archive']
        if not path.is_file():
            self.skipTest('Build target drivers before target-byte custody checks')
        data = path.read_bytes()
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read('source-manifest.json'))
            manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
            files = {'store/pmu/driver.elf': archive.read('driver.elf'),
                     'store/pmu/manifest.json': manifest_bytes,
                     'packages/' + package['archive']: data,
                     'shared/pmu-sleep-custody.json': (ROOT / CUSTODY_PATH).read_bytes()}
        return files

    def test_actual_target_package_and_deployed_bytes_match(self):
        verify_current_pmu(self.target_files(), ROOT)

    def test_rehashed_archive_metadata_does_not_authorize_payload_change(self):
        for name in ('store/pmu/driver.elf', 'store/pmu/manifest.json',
                     'packages/' + self.custody['package']['archive']):
            with self.subTest(path=name):
                files = self.target_files()
                files[name] += b'changed'
                with self.assertRaises(ValueError):
                    verify_current_pmu(files, ROOT)
        files = self.target_files()
        files['store/pmu/driver.elf'] += b'changed'
        altered = copy.deepcopy(self.custody)
        changed = files['store/pmu/driver.elf']
        altered['files']['pmu/driver.elf'] = {'sha256': digest(changed), 'size_bytes': len(changed)}
        files['shared/pmu-sleep-custody.json'] = json.dumps(altered).encode()
        with self.assertRaisesRegex(ValueError, 'Archived PMU custody'):
            verify_current_pmu(files, ROOT)

    def test_historical_store_default_and_explicit_pmu_only_overlay(self):
        from check_runtime_store_admission import preserve_store
        files = self.target_files()
        current = {name[6:]: data for name, data in files.items() if name.startswith('store/')}
        current['rtc/driver.elf'] = b'unchanged RTC fixture'
        old = {**current, 'pmu/driver.elf': b'historical PMU fixture',
               'pmu/manifest.json': b'historical PMU manifest fixture'}
        baseline = {'files': {name: {'size_bytes': len(data), 'sha256': digest(data)}
                              for name, data in old.items()}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'historical.json'
            path.write_text(json.dumps(baseline))
            preserved = path.read_bytes()
            preserve_store(old, path)  # Default remains the historical contract.
            with self.assertRaisesRegex(ValueError, 'Delivered store changed'):
                preserve_store(current, path)
            before = dict(current)
            preserve_store(current, path, current_pmu=True, root=ROOT)
            self.assertEqual(current, before)
            self.assertEqual(path.read_bytes(), preserved)
            with self.assertRaisesRegex(ValueError, 'Delivered store changed'):
                preserve_store(old, path, current_pmu=True, root=ROOT)
            for name in current:
                changed = {**current, name: current[name] + b'changed'}
                with self.subTest(path=name), self.assertRaisesRegex(ValueError, 'Delivered store changed'):
                    preserve_store(changed, path, current_pmu=True, root=ROOT)
            baseline['files'].pop('pmu/driver.elf')
            path.write_text(json.dumps(baseline))
            with self.assertRaisesRegex(ValueError, 'complete PMU baseline'):
                preserve_store(current, path, current_pmu=True, root=ROOT)

    def test_missing_or_duplicate_pmu_membership_rejected(self):
        for duplicate in (False, True):
            baseline = copy.deepcopy(self.baseline)
            pmu = next(row for row in baseline['driver_packages'] if row['id'] == 'twatch-pmu')
            if duplicate:
                baseline['driver_packages'].append(pmu)
            else:
                baseline['driver_packages'].remove(pmu)
            with self.assertRaisesRegex(ValueError, 'membership'):
                current_driver_packages(baseline, ROOT)


if __name__ == '__main__':
    unittest.main()

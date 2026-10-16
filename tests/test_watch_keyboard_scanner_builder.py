import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_watch_keyboard_scanner as builder


class WatchKeyboardScannerBuilderTests(unittest.TestCase):
    def test_selected_watch_features_remain(self):
        flags = builder.watch_flags(ROOT, Path('/generated/watch-alarm-profile.h'))
        for name in ('PORTABLE_LOW_BATTERY', 'PORTABLE_BLE_BROADCAST', 'PORTABLE_RTC_UTC8_DENVER',
                     'PORTABLE_FORCE_FULL_FRAMES', 'PORTABLE_INPUT_NAVIGATION_LOCAL', 'PORTABLE_APP_SLEEP_LOCAL',
                     'PORTABLE_ALARM_CLIENT', 'PORTABLE_QUICK_ACTIONS', 'PORTABLE_QUICK_RADIOS',
                     'PORTABLE_MOTION_WAKE', 'WATCH_ALARM_SLEEP_RESUME', 'PORTABLE_CONTEXTS_CLIENT',
                     'PORTABLE_NOVA_UI', 'PORTABLE_ASYNC_RGB565', 'BLE_SCANNER_COMPACT_COLOR_ONLY',
                     'PORTABLE_TEXT_INPUT_CLIENT', 'PORTABLE_CHECKED_STORAGE_RUNTIME',
                     'PORTABLE_NATIVE_CUSTODY_FENCE', 'PORTABLE_ALARM_TERMINAL_RETENTION'):
            self.assertIn('-D' + name, flags)
        self.assertIn('-DPORTABLE_RETURN_APP="springboard.elf"', flags)
        self.assertNotIn('-DPORTABLE_NATIVE_TIME_TOOLBAR', flags)
        self.assertNotIn('-DTEST_IDLE_ELIGIBILITY', flags)

    def test_normalizes_only_profile_paths(self):
        flags = ['-include', '/old/ContextsFaces.h', '-flto']
        self.assertEqual(builder.normalized_flags(flags), ['-include', 'ContextsFaces.h', '-flto'])
        self.assertNotIn('-DPORTABLE_RASTER_SNAPSHOT', builder.watch_flags(ROOT, Path('/generated/watch-alarm-profile.h')))

    def test_manifest_and_authority_are_narrowly_additive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = {'id': 'ble_scanner', 'version': '0.2.17', 'display_name': 'BLE Scanner',
                        'requires': [{'capability': 'bluetooth.sensors', 'api': 1}], 'arbitrary_existing': {'keep': True}}
            grants = [{'capability': 'bluetooth.sensors', 'api': 1, 'instance_id': 0}]
            (root / 'ble_scanner.json').write_text(json.dumps(manifest))
            (root / 'boot.json').write_text(json.dumps({'app_capabilities': [{'manifest': 'ble_scanner.json', 'grants': grants}]}))
            with patch.object(builder, 'sha', return_value=builder.BASELINE_SCANNER_SHA256):
                actual, authority = builder.admission(root)
            expected = copy.deepcopy(manifest);expected['version'] = builder.VERSION
            expected['requires'].append({'capability': 'ui.text-input', 'api': 1})
            self.assertEqual(actual, expected)
            self.assertEqual(authority, [*grants, builder.TEXT_GRANT])
            self.assertEqual(json.loads((root / 'ble_scanner.json').read_text()), manifest)
            with patch.object(builder, 'sha', return_value='wrong'):
                with self.assertRaisesRegex(ValueError, 'bytes differ'):
                    builder.admission(root)


if __name__ == '__main__':
    unittest.main()

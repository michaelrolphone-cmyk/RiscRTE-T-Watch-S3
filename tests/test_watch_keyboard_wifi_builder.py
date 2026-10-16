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
import build_watch_keyboard_wifi as builder


class WatchKeyboardWifiBuilderTests(unittest.TestCase):
    def test_selected_watch_features_remain(self):
        flags = builder.watch_flags(ROOT, Path('/generated/watch-alarm-profile.h'))
        for name in ('PORTABLE_LOW_BATTERY', 'PORTABLE_BLE_BROADCAST', 'PORTABLE_RTC_UTC8_DENVER',
                     'PORTABLE_FORCE_FULL_FRAMES', 'PORTABLE_INPUT_NAVIGATION_LOCAL', 'PORTABLE_APP_SLEEP_LOCAL',
                     'PORTABLE_ALARM_CLIENT', 'PORTABLE_QUICK_ACTIONS', 'PORTABLE_QUICK_RADIOS',
                     'PORTABLE_MOTION_WAKE', 'WATCH_ALARM_SLEEP_RESUME', 'PORTABLE_CONTEXTS_CLIENT',
                     'PORTABLE_NOVA_UI', 'PORTABLE_ASYNC_RGB565', 'PORTABLE_RASTER_SNAPSHOT',
                     'PORTABLE_TEXT_INPUT_CLIENT', 'PORTABLE_CHECKED_STORAGE_RUNTIME',
                     'PORTABLE_NATIVE_CUSTODY_FENCE', 'PORTABLE_ALARM_TERMINAL_RETENTION'):
            self.assertIn('-D' + name, flags)
        self.assertIn('-DPORTABLE_WIFI_VERSION="1.1.28"', flags)
        self.assertIn('-DWIFI_RETURN_APP="springboard.elf"', flags)
        self.assertNotIn('-DPORTABLE_WIFI_PROFILES', flags)
        self.assertNotIn('-DPORTABLE_NATIVE_TIME_TOOLBAR', flags)
        self.assertNotIn('-DTEST_IDLE_ELIGIBILITY', flags)

    def test_normalizes_only_version_and_profile_paths(self):
        flags = ['-DPORTABLE_WIFI_VERSION="1.1.20"', '-include', '/old/ContextsFaces.h', '-flto']
        expected = ['-DPORTABLE_WIFI_VERSION=<version>', '-include', 'ContextsFaces.h', '-flto']
        self.assertEqual(builder.normalized_flags(flags), expected)
        self.assertNotEqual(builder.normalized_flags(flags[:-1]), expected)

    def test_manifest_and_authority_are_narrowly_additive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = {'id': 'wifi_settings', 'version': '1.1.20', 'display_name': 'Wi-Fi',
                        'requires': [{'capability': 'net.wifi', 'api': 1}], 'arbitrary_existing': {'keep': True}}
            grants = [{'capability': 'net.wifi', 'api': 1, 'instance_id': 15}]
            (root / 'wifi_settings.json').write_text(json.dumps(manifest))
            (root / 'boot.json').write_text(json.dumps({'app_capabilities': [{'manifest': 'wifi_settings.json', 'grants': grants}]}))
            with patch.object(builder, 'sha', return_value=builder.BASELINE_WIFI_SHA256):
                actual, authority = builder.admission(root)
            expected = copy.deepcopy(manifest);expected['version'] = builder.VERSION
            expected['requires'].append({'capability': 'ui.text-input', 'api': 1})
            self.assertEqual(actual, expected)
            self.assertEqual(authority, [*grants, builder.TEXT_GRANT])
            self.assertEqual(json.loads((root / 'wifi_settings.json').read_text()), manifest)
            with patch.object(builder, 'sha', return_value='wrong'):
                with self.assertRaisesRegex(ValueError, 'bytes differ'):
                    builder.admission(root)


if __name__ == '__main__':
    unittest.main()

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
import build_watch_keyboard_spectrum as builder


class WatchKeyboardSpectrumBuilderTests(unittest.TestCase):
    def test_selected_watch_features_remain(self):
        flags = builder.watch_flags(ROOT, Path('/generated/watch-alarm-profile.h'))
        for name in ('PORTABLE_LOW_BATTERY', 'PORTABLE_BLE_BROADCAST', 'PORTABLE_RTC_UTC8_DENVER',
                     'PORTABLE_FORCE_FULL_FRAMES', 'PORTABLE_INPUT_NAVIGATION_LOCAL', 'PORTABLE_APP_SLEEP_LOCAL',
                     'PORTABLE_ALARM_CLIENT', 'PORTABLE_QUICK_ACTIONS', 'PORTABLE_QUICK_RADIOS',
                     'PORTABLE_MOTION_WAKE', 'WATCH_ALARM_SLEEP_RESUME', 'PORTABLE_CONTEXTS_CLIENT',
                     'PORTABLE_NOVA_UI', 'PORTABLE_AUDIO_SESSION', 'PORTABLE_AUDIO_CONTINUOUS_CAPTURE', 'PORTABLE_ASYNC_RGB565', 'PORTABLE_SPECTRUM_SHARED_TEXT_INPUT',
                     'PORTABLE_TEXT_INPUT_CLIENT', 'PORTABLE_CHECKED_STORAGE_RUNTIME',
                     'PORTABLE_NATIVE_CUSTODY_FENCE', 'PORTABLE_ALARM_TERMINAL_RETENTION',
                     'PORTABLE_WATCH_COLOR_ONLY', 'PORTABLE_WATCH_FROZEN_ICONS'):
            self.assertIn('-D' + name, flags)
        self.assertIn('-mno-target-align', flags)
        self.assertIn('-flto', flags)
        self.assertIn('-Wl,--undefined=__divsf3', flags)
        self.assertNotIn('-DPORTABLE_NOVA_TEXT_FACES_012', flags)
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
            manifest = {'id': 'audio_spectrum', 'version': '0.5.3', 'display_name': 'Audio Spectrum',
                        'requires': [{'capability': 'storage.key-value', 'api': 1}], 'arbitrary_existing': {'keep': True}}
            grants = [{'capability': 'storage.key-value', 'api': 1, 'instance_id': 0}]
            (root / 'audio_spectrum.json').write_text(json.dumps(manifest))
            (root / 'boot.json').write_text(json.dumps({'app_capabilities': [{'manifest': 'audio_spectrum.json', 'grants': grants}]}))
            with patch.object(builder, 'sha', return_value=builder.BASELINE_SPECTRUM_SHA256):
                actual, authority = builder.admission(root)
            expected = copy.deepcopy(manifest);expected['version'] = builder.VERSION
            expected['requires'].append({'capability': 'ui.text-input', 'api': 1})
            self.assertEqual(actual, expected)
            self.assertEqual(authority, [*grants, builder.TEXT_GRANT])
            self.assertEqual(json.loads((root / 'audio_spectrum.json').read_text()), manifest)
            with patch.object(builder, 'sha', return_value='wrong'):
                with self.assertRaisesRegex(ValueError, 'bytes differ'):
                    builder.admission(root)


if __name__ == '__main__':
    unittest.main()

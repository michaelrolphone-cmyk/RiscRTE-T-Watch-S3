import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('keyboard_recipe', ROOT / 'scripts/assemble_watch_shared_keyboard.py')
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


class RecipeTest(unittest.TestCase):
    def setUp(self):
        self.old = {
            'cohort.json': recipe.encoded({'version': '1.1.16', 'source_revision': recipe.BASE, 'firmware_sha256': 'native'}),
            'wifi_settings.json': recipe.encoded({'id': 'wifi_settings', 'version': '1.1.20', 'requires': [{'api': 1, 'capability': 'net.wifi'}]}),
            'wifi_settings.elf': b'old-wifi', 'ui-scene/driver.elf': b'old-scene',
            'ui-scene/manifest.json': recipe.encoded({'id': 'scene-host', 'version': '0.3.2', 'requires': [
                {'api': 1, 'capability': 'display.output'}, {'api': 1, 'capability': 'input.touch.raw'},
                {'api': 1, 'capability': 'platform.clock'}, {'api': 1, 'capability': 'ui.presentation-profile'}]}),
            'boot.json': recipe.encoded({'provider_activation': 'demand-retained',
                'drivers': [{'manifest': 'provider-%d/manifest.json' % index} for index in range(30)],
                'app_capabilities': [{'manifest': 'wifi_settings.json', 'grants': [{'capability': 'net.wifi', 'api': 1, 'instance_id': 15}]}] +
                                    [{'manifest': 'app-%d.json' % index, 'grants': []} for index in range(24)]}),
            'file_browser.json': recipe.encoded({'version': '1.5.31'}), 'file_browser.elf': b'frozen Files',
            'default.json': recipe.encoded({'version': '0.11.5'}), 'default.elf': b'frozen Clock',
            'ui-profile/driver.elf': b'frozen Watch profile', 'driver.elf': b'frozen provider',
        }
        self.wifi = json.loads(self.old['wifi_settings.json'])
        self.wifi.update(version=recipe.WIFI_VERSION)
        self.wifi['requires'].append(recipe.TEXT_REQUIREMENT)
        self.text = {'architecture': 'xtensa-esp32s3', 'driver_abi': 2, 'file_name': 'driver.elf',
                     'id': 'text-input-host', 'provides': [recipe.TEXT_REQUIREMENT],
                     'requires': [{'api': 1, 'capability': 'ui.scene'}], 'type': 'driver', 'version': '0.1.4'}

    def compose(self):
        return recipe.changed_store(self.old, 'new-product', b'new-scene', b'new-text', recipe.encoded(self.text),
                                    b'new-wifi', recipe.encoded(self.wifi))

    def test_real_consumer_and_only_bounded_changes(self):
        new = self.compose()
        self.assertEqual(set(new) - set(self.old), recipe.ADDED)
        self.assertEqual({name for name in self.old if self.old[name] != new[name]}, recipe.CHANGED)
        old_boot = json.loads(self.old['boot.json'])
        new_boot = json.loads(new['boot.json'])
        self.assertEqual(new_boot['drivers'][:-1], old_boot['drivers'])
        self.assertEqual(new_boot['drivers'][-1], {'manifest': 'text-input/manifest.json'})
        self.assertEqual(new_boot['app_capabilities'][1:], old_boot['app_capabilities'][1:])
        self.assertEqual(new_boot['app_capabilities'][0]['grants'], old_boot['app_capabilities'][0]['grants'] + [recipe.TEXT_GRANT])
        self.assertEqual(json.loads(new['ui-scene/manifest.json'])['requires'], json.loads(self.old['ui-scene/manifest.json'])['requires'])
        for name in set(self.old) - recipe.CHANGED:
            self.assertEqual(new[name], self.old[name])

    def test_no_unused_provider_only_update(self):
        self.wifi['requires'].remove(recipe.TEXT_REQUIREMENT)
        with self.assertRaisesRegex(ValueError, 'Wi-Fi manifest'):
            self.compose()

    def test_extra_authority_rejected(self):
        self.wifi['requires'].append({'api': 1, 'capability': 'storage.volume.fs'})
        with self.assertRaises(ValueError):
            self.compose()

    def test_removed_requirement_rejected(self):
        self.wifi['requires'].pop(0)
        with self.assertRaises(ValueError):
            self.compose()

    def test_usb_dependency_rejected(self):
        self.text['requires'].append({'api': 1, 'capability': 'usb.hid.keyboard'})
        with self.assertRaises(ValueError):
            self.compose()

    def test_navigation_dependency_rejected(self):
        scene = json.loads(self.old['ui-scene/manifest.json'])
        scene['requires'].append({'api': 1, 'capability': 'input.navigation'})
        self.old['ui-scene/manifest.json'] = recipe.encoded(scene)
        with self.assertRaises(ValueError):
            self.compose()

    def test_wrong_baseline_rejected(self):
        for key, value in [('version', '1.1.15'), ('source_revision', 'not-the-frozen-product')]:
            with self.subTest(key=key):
                saved = self.old['cohort.json']
                cohort = json.loads(saved)
                cohort[key] = value
                self.old['cohort.json'] = recipe.encoded(cohort)
                with self.assertRaises(ValueError):
                    self.compose()
                self.old['cohort.json'] = saved

    def test_existing_provider_and_wrong_versions_rejected(self):
        self.old['text-input/driver.elf'] = b'existing'
        with self.assertRaises(ValueError):
            self.compose()
        del self.old['text-input/driver.elf']
        self.text['version'] = '0.1.3'
        with self.assertRaises(ValueError):
            self.compose()

    def test_boot_graph_bounds_and_activation_rejected(self):
        saved = self.old['boot.json']
        for edit in ('drivers', 'app_capabilities', 'provider_activation'):
            with self.subTest(edit=edit):
                boot = json.loads(saved)
                if edit == 'provider_activation':
                    boot[edit] = 'eager'
                else:
                    boot[edit].pop()
                self.old['boot.json'] = recipe.encoded(boot)
                with self.assertRaises(ValueError):
                    self.compose()
        self.old['boot.json'] = saved

    def test_preservation_rejects_unrelated_change(self):
        previous = b'\xff' * 0x1000000
        new = self.compose()
        proof = recipe.verify_preservation(previous, previous, self.old, new)
        self.assertTrue(proof['native_firmware_byte_preserved'])
        new['file_browser.elf'] += b'changed'
        with self.assertRaisesRegex(ValueError, 'Unapproved store change'):
            recipe.verify_preservation(previous, previous, self.old, new)

    def test_preservation_rejects_native_change(self):
        previous = b'\xff' * 0x1000000
        full = bytearray(previous)
        full[0x10000] = 0
        with self.assertRaisesRegex(ValueError, 'Non-store flash changed'):
            recipe.verify_preservation(previous, full, self.old, self.compose())

    def test_sources_are_mandatory_and_rechecked(self):
        with self.assertRaises(ValueError):
            recipe.check_sources({})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'input.c'
            path.write_bytes(b'compiled')
            record = {'source_sha256': {str(path): recipe.sha(path.read_bytes())}}
            self.assertEqual(recipe.check_sources(record), 1)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                recipe.check_sources(record)


if __name__ == '__main__':
    unittest.main()

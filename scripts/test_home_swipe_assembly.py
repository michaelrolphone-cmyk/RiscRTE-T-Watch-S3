#!/usr/bin/env python3
"""Focused preservation and manifest-authority guards for the Home overlay."""
import copy
import json
import unittest

from assemble_home_swipe_watch import payload, verify_preservation, SELECTION


class HomeOverlayTests(unittest.TestCase):
    def setUp(self):
        self.old = {f'other-{index}.elf': bytes([index]) for index in range(54)}
        self.old.update({
            'default.elf': b'previous-home',
            'default.json': b'{"id":"twatch-clock","requires":[{"api":1,"capability":"display.output"}],"version":"0.11.5"}\n',
            'cohort.json': json.dumps({'version': '1.1.19', 'source_revision': SELECTION['baseline']['source']}).encode(),
            'boot.json': b'unchanged boot authority',
        })
        manifest = json.loads(self.old['default.json'])
        manifest['version'] = '0.11.6'
        self.files = {'default.elf': b'new-home', 'default.json': json.dumps(manifest, indent=2).encode()}

    def test_exact_three_path_delta_and_manifest_format(self):
        result = payload(self.old, self.files, 'a' * 40)
        self.assertEqual({name for name in result if result[name] != self.old[name]}, {'default.elf', 'default.json', 'cohort.json'})
        self.assertEqual(result['default.json'], self.old['default.json'].replace(b'0.11.5', b'0.11.6'))
        self.assertEqual(len(result['default.json']), len(self.old['default.json']))
        self.assertEqual(json.loads(result['cohort.json'])['version'], '1.1.20')

    def test_manifest_authority_change_rejected(self):
        files = copy.deepcopy(self.files)
        manifest = json.loads(files['default.json'])
        manifest['requires'].append({'api': 1, 'capability': 'unexpected'})
        files['default.json'] = json.dumps(manifest).encode()
        with self.assertRaisesRegex(ValueError, 'authority or features'):
            payload(self.old, files, 'a' * 40)

    def test_extra_component_rejected(self):
        with self.assertRaisesRegex(ValueError, 'component member'):
            payload(self.old, dict(self.files, extra=b'unexpected'), 'a' * 40)

    def test_other_elf_change_rejected(self):
        result = payload(self.old, self.files, 'a' * 40)
        result['other-0.elf'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'store delta'):
            verify_preservation(self.old, result)

    def test_boot_authority_change_rejected(self):
        result = payload(self.old, self.files, 'a' * 40)
        result['boot.json'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'store delta'):
            verify_preservation(self.old, result)

    def test_inventory_change_rejected(self):
        result = payload(self.old, self.files, 'a' * 40)
        del result['other-0.elf']
        with self.assertRaisesRegex(ValueError, 'inventory'):
            verify_preservation(self.old, result)


if __name__ == '__main__':
    unittest.main()

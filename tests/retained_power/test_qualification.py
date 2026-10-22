#!/usr/bin/env python3
"""Rejection controls against the actual retained release inputs."""
import argparse
import copy
import json
from pathlib import Path
import sys
import unittest
import qualify

class Rejections(unittest.TestCase):
    def test_wrong_hash_or_size(self):
        raw = self.store['settings.elf']
        for bad in (raw[:-1], raw + b'\0', bytes([raw[0] ^ 1]) + raw[1:]):
            with self.subTest(bytes=len(bad)), self.assertRaises(ValueError):
                qualify.exact(bad, qualify.SETTINGS, 'Settings')

    def test_wrong_source(self):
        with self.assertRaisesRegex(ValueError, 'Source revision differs'):
            qualify.source(self.product, '0' * 40)

    def test_missing_duplicate_or_wrong_grant(self):
        for app in ('settings.json', 'default.json'):
            for cap in ('storage.key-value', 'power.sleep', 'display.power', 'input.power-key'):
                for mutation in ('missing', 'duplicate', 'wrong-instance'):
                    store = dict(self.store)
                    boot = json.loads(store['boot.json'])
                    row = next(x for x in boot['app_capabilities'] if x['manifest'] == app)
                    grant = next(x for x in row['grants'] if x['capability'] == cap and x['instance_id'] == (1 if cap == 'storage.key-value' else 0))
                    if mutation == 'missing': row['grants'].remove(grant)
                    elif mutation == 'duplicate': row['grants'].append(copy.deepcopy(grant))
                    else: grant['instance_id'] = 99
                    store['boot.json'] = json.dumps(boot).encode()
                    with self.subTest(app=app, cap=cap, mutation=mutation), self.assertRaises(ValueError):
                        qualify.binding(store)

    def test_missing_or_wrong_provider(self):
        for path in ('power-sleep/manifest.json', 'display-power/manifest.json'):
            store = dict(self.store)
            boot = json.loads(store['boot.json'])
            boot['drivers'] = [x for x in boot['drivers'] if x['manifest'] != path]
            store['boot.json'] = json.dumps(boot).encode()
            with self.subTest(path=path, mutation='missing'), self.assertRaises(ValueError):
                qualify.binding(store)
            store = dict(self.store)
            manifest = json.loads(store[path]); manifest['provides'][0]['api'] = 2
            store[path] = json.dumps(manifest).encode()
            with self.subTest(path=path, mutation='wrong-api'), self.assertRaises(ValueError):
                qualify.binding(store)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    args = parser.parse_args()
    qualify.source(args.product, qualify.PRODUCT)
    sys.path.insert(0, str(args.product / 'scripts'))
    from read_only_spiffs import read_image
    Rejections.product = args.product
    Rejections.store = read_image(qualify.assets(args.assets)['store.bin'], 0x550000)
    unittest.main(argv=[sys.argv[0]], verbosity=2)

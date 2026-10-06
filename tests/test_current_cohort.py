import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import current_cohort as c
from current_bootfs import build


class CurrentCohort(unittest.TestCase):
    def setUp(self):
        self.native = b'native image fixture' * 8
        self.identity = c.create('1.0.2', '0.1.33', 'a' * 40, self.native)

    def test_exact_canonical_identity_and_native_binding(self):
        self.assertEqual(self.identity, c.parse(c.encode(self.identity)))
        self.assertEqual(c.encode(self.identity), c.encode(dict(reversed(list(self.identity.items())))))
        c.verify(self.identity, self.native, version='1.0.2', runtime_version='0.1.33', source_revision='a' * 40)
        for options in ({'version': '1.0.3'}, {'runtime_version': '0.1.32'}, {'source_revision': 'b' * 40}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                c.verify(self.identity, self.native, **options)
        with self.assertRaises(ValueError):
            c.verify(self.identity, self.native + b'x')

    def test_identity_bounds_and_unknown_or_duplicate_fields(self):
        for key, value in [('schema_version', True), ('store_abi', True), ('store_abi', 1),
                           ('layout', 'riscrte-paired-16m-v1'), ('source_repo', 'other/repo'),
                           ('product', 'other'), ('source_revision', 'A' * 40),
                           ('firmware_sha256', 'z' * 64), ('firmware_size', 31),
                           ('firmware_size', c.NATIVE_SIZE + 1), ('firmware_size', True),
                           ('version', '01.0.2'), ('runtime_version', 'dev')]:
            wrong = {**self.identity, key: value}
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                c.validate(wrong)
        for identity in ({**self.identity, 'extra': 1}, {k: v for k, v in self.identity.items() if k != 'version'}):
            with self.assertRaises(ValueError): c.validate(identity)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            c.parse(c.encode(self.identity).rstrip()[:-1] + b',"version":"1.0.3"}')

    def test_payload_contains_exact_native_then_store_with_bound_identity(self):
        store, _ = build({'cohort.json': c.encode(self.identity), 'boot.json': b'{}\n'}, c.STORE_SIZE)
        payload, ota = c.package(self.identity, self.native, store)
        self.assertEqual(self.native + store, payload)
        self.assertEqual(len(payload), ota['size'])
        self.assertEqual(c.sha(payload), ota['sha256'])
        self.assertEqual(c.sha(store), ota['store_sha256'])
        self.assertEqual('paired-cohort', ota['kind'])
        self.assertEqual('twatch-s3-cohort-1.0.2.bin', ota['asset'])
        self.assertTrue(ota['url'].endswith('/firmware-v1.0.2/' + ota['asset']))
        self.assertNotIn('appdata', ota)
        with self.assertRaises(ValueError): c.package(self.identity, self.native, store[:-1])
        other = copy.deepcopy(self.identity); other['source_revision'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            c.package(other, self.native, store)
        missing, _ = build({'boot.json': b'{}\n'}, c.STORE_SIZE)
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            c.package(self.identity, self.native, missing)


if __name__ == '__main__':
    unittest.main()

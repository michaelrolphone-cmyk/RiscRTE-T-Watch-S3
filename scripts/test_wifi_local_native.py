#!/usr/bin/env python3
"""Selection negative controls; no native, storage or hardware execution."""
import argparse
import unittest
from pathlib import Path
import wifi_local_native_contract as contract

class GeneratorTests(unittest.TestCase):
    def test_exact_cmake_variable_output(self):
        script = contract.cmake_script(Path('/runtime'), 'profiles/native-provisioning.cmake', Path('/output'))
        for key, variable in contract.FIELDS.items():
            self.assertIn(key + '=$' + '{' + variable + '}\\n', script)
        self.assertNotIn('+ variable +', script)
        self.assertIn('include("' + str(contract.ROOT / 'profiles/native-provisioning.cmake') + '")', script)

class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before, cls.after = contract.profile_contract(RUNTIME)

    def test_exact_profile(self):
        contract.validate_delta(self.before, self.after)

    def test_every_preserved_selection(self):
        for key in contract.FIELDS:
            if key in ('definitions', 'settings', 'options'):
                continue
            with self.subTest(key=key):
                changed = dict(self.after)
                changed[key] += '-changed'
                with self.assertRaises(ValueError):
                    contract.validate_delta(self.before, changed)

    def test_every_policy_selection(self):
        for key in contract.EXTRA:
            with self.subTest(key=key):
                changed = dict(self.after)
                changed['definitions'] = changed['definitions'].replace(
                    key + '=' + contract.EXTRA[key], key + '=99')
                with self.assertRaises(ValueError):
                    contract.validate_delta(self.before, changed)

    def test_duplicate_definition(self):
        changed = dict(self.after)
        changed['definitions'] += ';RISC_NATIVE_SETTINGS_LOCAL_ONLY=1'
        with self.assertRaises(ValueError):
            contract.validate_delta(self.before, changed)

    def test_preserved_capacity(self):
        for key in ('RISC_PROVIDER_CAPACITY', 'RISC_PLATFORM_CAPACITY',
                    'RISC_INSTALLED_APP_CAPACITY', 'RISC_APP_POLICY_ROWS'):
            changed = dict(self.after)
            old = contract.definitions(changed['definitions'])[key]
            changed['definitions'] = changed['definitions'].replace(key + '=' + old, key + '=99')
            with self.assertRaises(ValueError):
                contract.validate_delta(self.before, changed)

    def test_header_or_flags(self):
        for key in ('settings', 'options'):
            changed = dict(self.after)
            changed[key] = ''
            with self.assertRaises(ValueError):
                contract.validate_delta(self.before, changed)

    def test_source_is_additive(self):
        rows = ['A\t' + path for path in contract.ADDITIONS]
        contract.validate_source_rows(rows)
        for bad in (rows[:-1], rows + ['M\tprofiles/native-idf61.cmake'],
                    rows + [rows[0]], ['M\t' + row[2:] for row in rows]):
            with self.assertRaises(ValueError):
                contract.validate_source_rows(bad)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', type=Path, required=True)
    a = p.parse_args()
    RUNTIME = a.runtime.resolve()
    contract.source_guard()
    unittest.main(argv=['test_wifi_local_native'], verbosity=2)

"""Source-only bounded midpoint profile tests; full host proof is separate."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_next_watch_cohort import fixture as ordinary_fixture
import build_next_watch_cohort as base
import midpoint_upgrade as midpoint
from current_cohort import create, encode, parse
from test_next_watch_upgrade import check_preserved

FIRMWARE = b'candidate-native-fixture' * 2


def fixture():
    previous, standard = ordinary_fixture()
    for files in (previous, standard):
        boot = base.document(files['boot.json'])
        boot['app_capabilities'].append({'manifest': 'waterfall.json', 'grants': [
            {'capability': 'storage.key-value', 'api': 1, 'instance_id': 1}]})
        index = len(boot['drivers']) - (1 if files is standard else 0)
        boot['drivers'].insert(index, {'manifest': 's3-radio-iq/manifest.json', 'instance_id': 19})
        files.update({'waterfall.json': base.encoded({'id': 'waterfall', 'version': '0.1.0',
                      'file_name': 'waterfall.elf', 'requires': [{'capability': 'storage.key-value', 'api': 1}]}),
                      'waterfall.elf': b'waterfall-fixture',
                      's3-radio-iq/manifest.json': base.encoded({'id': 's3-radio-iq', 'version': '0.1.0',
                                                               'file_name': 'driver.elf', 'provides': []}),
                      's3-radio-iq/driver.elf': b'iq-fixture', 'boot.json': base.encoded(boot)})
    standard['cohort.json'] = encode(create('1.0.5', '0.1.35', 'f' * 40, FIRMWARE))
    source = dict(previous)
    boot = base.document(source['boot.json']);boot.pop('cohort_migration')
    boot['app_capabilities'] = [r for r in boot['app_capabilities'] if r['manifest'] != 'waterfall.json']
    boot['drivers'] = [r for r in boot['drivers'] if r['manifest'] != 's3-radio-iq/manifest.json']
    source['boot.json'] = base.encoded(boot)
    for name in ('waterfall.elf', 'waterfall.json', 's3-radio-iq/manifest.json', 's3-radio-iq/driver.elf'):
        source.pop(name)
    source['cohort.json'] = encode(create('1.0.2', '0.1.33', midpoint.MIDPOINT_SOURCE, b'original' * 8))
    following = midpoint.adapt_candidate(standard, FIRMWARE, midpoint.VERSION)
    return source, previous, standard, following


class MidpointPolicyTest(unittest.TestCase):
    def setUp(self):
        self.source, self.previous, self.standard, self.following = fixture()

    def check(self):
        return midpoint.check_policy(self.source, self.following, self.previous, self.standard,
                                     FIRMWARE, midpoint.VERSION)

    def test_only_boot_and_cohort_change(self):
        self.check()
        changed = sorted(n for n in self.standard if self.standard[n] != self.following[n])
        self.assertEqual(changed, ['boot.json', 'cohort.json'])
        self.assertEqual(parse(self.following['cohort.json'])['version'], '1.0.6')
        self.assertEqual(parse(self.standard['cohort.json'])['version'], '1.0.5')

    def test_exact_migration_and_old_authority_preserved(self):
        result = self.check()
        self.assertEqual(result['migration']['from'], {'product': 'twatch-s3', 'version': '1.0.2',
                                                      'source_revision': midpoint.MIDPOINT_SOURCE})
        self.assertEqual(result['migration']['shared_key_value'], [
            {'application_id': n, 'api': 1, 'namespace': 1}
            for n in ('waterfall', 'ble_touchpad', 'ble_buttons')])
        self.assertEqual(set(result['prior_app_owners']), {'default', 'private'})

    def test_profile_cannot_collide_with_standard_or_choose_unreviewed_version(self):
        for version in ('1.0.4', '1.0.5', '1.0.7', '1.0.6-midpoint'):
            with self.assertRaises(ValueError):midpoint.adapt_candidate(self.standard, FIRMWARE, version)

    def test_standard_origin_must_stay_exact(self):
        boot = base.document(self.standard['boot.json'])
        boot['cohort_migration']['from']['source_revision'] = midpoint.MIDPOINT_SOURCE
        self.standard['boot.json'] = base.encoded(boot)
        with self.assertRaisesRegex(ValueError, 'Ordinary candidate migration'):
            midpoint.adapt_candidate(self.standard, FIRMWARE, midpoint.VERSION)

    def test_variant_source_target_and_grants_fail_closed(self):
        original = copy.deepcopy(self.following)
        for mutate in (
            lambda b: b['cohort_migration']['from'].update(source_revision='0' * 40),
            lambda b: b['cohort_migration']['from'].update(version='1.0.4'),
            lambda b: b['cohort_migration']['to'].update(version='1.0.5'),
            lambda b: b['cohort_migration']['shared_key_value'].pop(0),
            lambda b: b['cohort_migration']['shared_key_value'].append({'application_id': 'other', 'api': 1, 'namespace': 3}),
            lambda b: b['app_capabilities'][0]['grants'].pop()):
            self.following = copy.deepcopy(original);boot = base.document(self.following['boot.json'])
            mutate(boot);self.following['boot.json'] = base.encoded(boot)
            with self.assertRaises(ValueError):self.check()

    def test_variant_cannot_change_an_elf_board_or_extra_file(self):
        for name in ('default.elf', 'ble-hid/driver.elf', 'board.json', 'unexpected.json'):
            original = dict(self.following);self.following[name] = b'changed'
            with self.assertRaisesRegex(ValueError, 'only exact origin/target metadata'):self.check()
            self.following = original

    def test_actual_midpoint_owner_must_not_be_reassigned(self):
        manifest = base.document(self.source['private.json']);manifest['id'] = 'real-original-owner'
        self.source['private.json'] = base.encoded(manifest)
        with self.assertRaisesRegex(ValueError, 'Midpoint existing app authority'):self.check()

    def test_actual_midpoint_board_and_boot_authority_must_match(self):
        self.source['board.json'] += b' '
        with self.assertRaisesRegex(ValueError, 'Midpoint hardware board'):self.check()
        self.setUp();boot = base.document(self.source['boot.json'])
        boot['drivers'][1]['key_value'][0]['namespace'] = 12
        self.source['boot.json'] = base.encoded(boot)
        with self.assertRaisesRegex(ValueError, 'Midpoint existing provider bindings'):self.check()

    def test_baseline_is_the_exact_installed_image(self):
        baseline = midpoint.baseline()
        self.assertEqual(baseline['initial_image_sha256'], midpoint.MIDPOINT_SHA)
        self.assertEqual(len(baseline['files']), 73)
        self.assertEqual(baseline['cohort']['source_revision'], midpoint.MIDPOINT_SOURCE)
        with tempfile.TemporaryDirectory() as d:
            wrong = Path(d) / 'wrong.bin';wrong.write_bytes(b'not installed firmware')
            with self.assertRaisesRegex(ValueError, 'BIN custody'):midpoint.read_midpoint(wrong)


class ProofByteCustodyTest(unittest.TestCase):
    def test_noncanonical_proof_bytes_are_hashed_without_reserialization(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'next-watch-build-proof.json'
            raw = b'{ "second": 2, "first": 1 }\n'
            path.write_bytes(raw)
            self.assertEqual(midpoint.standard_proof_digest(d), hashlib.sha256(raw).hexdigest())
            self.assertNotEqual(midpoint.standard_proof_digest(d),
                                base.sha(base.encoded(base.document(raw))))


class AlternateSourceBankTest(unittest.TestCase):
    def test_bank_one_source_preserves_bridge_pair_and_persisted_regions(self):
        original = bytes([0xa5]) * 0x1000000
        changed = bytearray(original)
        changed[0x10000] ^= 1;changed[0x2f0000] ^= 1;changed[0xff2000] ^= 1
        check_preserved(original, bytes(changed), source_bank=1)
        with self.assertRaisesRegex(ValueError, 'rollback pair'):check_preserved(original, bytes(changed))
        for offset in (0x9000, 0x270000, 0x800000, 0xae0000, 0xff3000):
            candidate = bytearray(original);candidate[offset] ^= 1
            with self.assertRaises(ValueError):check_preserved(original, bytes(candidate), source_bank=1)

    def test_invalid_bank_rejected(self):
        with self.assertRaisesRegex(ValueError, 'source bank'):check_preserved(bytes(0x1000000), bytes(0x1000000), 2)


if __name__ == '__main__':
    unittest.main()

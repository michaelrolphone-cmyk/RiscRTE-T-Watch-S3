"""Bounded packaging policy tests; full production admission is a separate command."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_next_watch_cohort import check_policy, document, encoded, migration, NEW_APPS


def fixture():
    def grant(capability, api, instance):
        return {'capability': capability, 'api': api, 'instance_id': instance}
    shared = [grant('storage.key-value', 1, 1)]
    before = {'board': 'board.json', 'default_app': 'default.elf',
              'cohort_migration': {'retained': 'prior'},
              'app_capabilities': [
                  {'manifest': 'default.json', 'grants': shared},
                  {'manifest': 'private.json', 'grants': shared + [grant('storage.key-value', 1, 3), grant('storage.app-data', 1, 1)]}],
              'drivers': [{'manifest': 'ble/manifest.json', 'instance_id': 16},
                          {'manifest': 'alarm/manifest.json', 'key_value': [{'key': 'owned', 'namespace': 4, 'access': 'read-write'}]}]}
    previous = {'board.json': encoded({'devices': [{'instance_id': 16}]}), 'boot.json': encoded(before),
                'cohort.json': b'{}'}
    for row in before['app_capabilities']:
        name = row['manifest'][:-5]
        previous[row['manifest']] = encoded({'id': name, 'version': '1.0.0', 'file_name': name + '.elf',
             'requires': [{'capability': c, 'api': a} for c, a in sorted({(g['capability'], g['api']) for g in row['grants']})]})
        previous[name + '.elf'] = b'prior-elf'
    for name, cap in [('ble', 'bluetooth.hci'), ('alarm', 'alarm.service')]:
        previous[name + '/manifest.json'] = encoded({'id': name, 'file_name': 'driver.elf', 'version': '1.0.0',
                                                     'provides': [{'capability': cap, 'api': 1}]})
        previous[name + '/driver.elf'] = b'prior-provider'
    following = dict(previous)
    after = copy.deepcopy(before);after['cohort_migration'] = migration()
    common = [('display.output', 1, 5), ('input.touch.raw', 1, 6), ('board.battery', 1, 4),
              ('bluetooth.hid', 1, 0), ('alarm.service', 1, 0), ('storage.key-value', 1, 1),
              ('rtc.clock', 2, 8), ('net.wifi', 1, 15), ('bluetooth.hci', 1, 16), ('motion.accel', 1, 7)]
    for name in NEW_APPS:
        declared = common + ([('storage.key-value', 1, 11)] if name == 'ble_buttons' else [])
        after['app_capabilities'].append({'manifest': name + '.json', 'grants': [grant(*g) for g in declared]})
        following[name + '.json'] = encoded({'id': name, 'file_name': name + '.elf',
            'requires': [{'capability': c, 'api': a} for c, a in sorted({(c, a) for c, a, _ in declared})]})
        following[name + '.elf'] = b'new-elf'
    after['drivers'].append({'manifest': 'ble-hid/manifest.json', 'key_value': [
        {'key': k, 'namespace': 10, 'access': 'read-write'} for k in ('hid_ours', 'hid_peer', 'hid_ccc', 'hid_identity')]})
    following['ble-hid/manifest.json'] = encoded({'id': 'ble-hid', 'driver_abi': 2, 'file_name': 'driver.elf',
        'requires': [{'capability': c, 'api': 1} for c in ('bluetooth.hci', 'platform.clock', 'storage.key-value.bound')],
        'provides': [{'capability': 'bluetooth.hid', 'api': 1}]})
    following['ble-hid/driver.elf'] = b'new-provider'
    following['boot.json'] = encoded(after)
    return previous, following


class NextWatchPolicyTest(unittest.TestCase):
    def setUp(self):
        self.previous, self.following = fixture()

    def check(self):
        return check_policy(self.previous, self.following)

    def boot(self, mutate):
        value = document(self.following['boot.json']);mutate(value)
        self.following['boot.json'] = encoded(value)

    def test_exact_bound_policy_and_all_prior_owners(self):
        result = self.check()
        self.assertEqual(set(result['prior_app_owners']), {'default', 'private'})
        self.assertEqual(result['prior_provider_bindings'], document(self.previous['boot.json'])['drivers'])

    def test_existing_binary_and_version_updates_do_not_change_authority(self):
        self.following['default.elf'] = b'updated-code'
        app = document(self.following['default.json']);app['version'] = '1.1.0';app['description'] = 'new UI'
        self.following['default.json'] = encoded(app)
        self.check()

    def test_wrong_migration_origin_target_entries(self):
        original = copy.deepcopy(self.following)
        for mutate in (
            lambda b: b['cohort_migration']['from'].update(source_revision='0' * 40),
            lambda b: b['cohort_migration']['from'].update(version='1.0.3'),
            lambda b: b['cohort_migration']['to'].update(version='1.0.6'),
            lambda b: b['cohort_migration']['shared_key_value'].pop(),
            lambda b: b['cohort_migration']['shared_key_value'].append({'application_id': 'waterfall', 'api': 1, 'namespace': 1}),
            lambda b: b.pop('cohort_migration')):
            self.following = copy.deepcopy(original);self.boot(mutate)
            with self.assertRaisesRegex(ValueError, 'migration'):self.check()

    def test_extra_private_grant_even_fresh_namespace_is_denied(self):
        self.boot(lambda b: b['app_capabilities'][-1]['grants'].append(
            {'capability': 'storage.key-value', 'api': 1, 'instance_id': 12}))
        with self.assertRaisesRegex(ValueError, 'new app grant'):self.check()

    def test_every_prior_app_row_is_preserved(self):
        for index in range(2):
            self.previous, self.following = fixture()
            self.boot(lambda b: b['app_capabilities'][index]['grants'].pop())
            with self.assertRaisesRegex(ValueError, 'Existing app grants'):self.check()

    def test_prior_app_identity_may_not_change(self):
        app = document(self.following['private.json']);app['id'] = 'hijacker'
        self.following['private.json'] = encoded(app)
        with self.assertRaisesRegex(ValueError, 'manifest authority'):self.check()

    def test_prior_provider_keys_may_not_change(self):
        self.boot(lambda b: b['drivers'][1]['key_value'][0].update(namespace=9))
        with self.assertRaisesRegex(ValueError, 'provider bindings'):self.check()

    def test_hid_may_not_use_hardware_or_private_namespace(self):
        for mutate in (lambda b: b['drivers'][-1].update(instance_id=17),
                       lambda b: b['drivers'][-1]['key_value'][0].update(namespace=4),
                       lambda b: b['drivers'][-1]['key_value'].append({'key': 'extra', 'namespace': 10, 'access': 'read'})):
            self.previous, self.following = fixture();self.boot(mutate)
            with self.assertRaises(ValueError):self.check()

    def test_extra_files_and_hardware_changes_fail(self):
        self.following['extra.bin'] = b'extra'
        with self.assertRaisesRegex(ValueError, 'inventory'):self.check()
        self.following.pop('extra.bin');self.following['board.json'] += b' '
        with self.assertRaisesRegex(ValueError, 'Hardware'):self.check()

    def test_duplicate_json_fields_fail_closed(self):
        self.following['boot.json'] = b'{"board":"board.json","board":"other.json"}'
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):self.check()


if __name__ == '__main__':
    unittest.main()

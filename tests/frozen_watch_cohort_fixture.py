"""Frozen 1.0.4 -> 1.0.5 fixture for midpoint tests, isolated from live apex.

Fixture body retained from Watch 40debe48's test_next_watch_cohort.py. Live
BLE sensor/telemetry additions must never change this accepted-era topology.
"""
import copy
from build_next_watch_cohort import encoded, migration, NEW_APPS


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


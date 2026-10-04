#!/usr/bin/env python3
"""Independent paired store authority, preservation, source and layout verifier."""
import argparse
import copy
import io
import json
from pathlib import Path
import struct

from build_wifi_common import read_zip, require, exact_sha, sha
from build_clock_deployment import ROOT, encoded

BASELINE_SOURCE = '216e2d73b72cca6c3bcf75ad9ef56466b8861144'
APPS = ('default', 'clock', 'springboard', 'battery', 'settings', 'calculator',
        'stopwatch', 'alarms', 'countdown', 'points_in_time', 'wifi_settings')
SELECTIONS = ((), ('ota_update',), ('ota_update', 'app_store'))
CHANGED = {'boot.json', 'default.elf', 'default.json', 'clock.json', 'springboard.elf', 'springboard.json',
           'battery.elf', 'settings.elf', 'calculator.elf', 'stopwatch.elf', 'alarms.elf',
           'countdown.elf', 'points_in_time.elf', 'wifi_settings.elf'}
NATIVE = ('platform.http-client', 'platform.bank-store', 'platform.clock')
PARTITIONS = {'app0': {'offset': 0x10000, 'size': 0x300000},
              'bootfs0': {'offset': 0x310000, 'size': 0x4f0000},
              'app1': {'offset': 0x800000, 'size': 0x300000},
              'bootfs1': {'offset': 0xb00000, 'size': 0x4f0000},
              'otadata': {'offset': 0xff0000, 'size': 0x2000},
              'bank_state': {'offset': 0xff2000, 'size': 0x2000}}


def kind_path(app):
    return ('firmware', 'update-fw') if app == 'ota_update' else ('apps', 'update-apps')


def grants(app):
    return [{'capability': c, 'api': api, 'instance_id': instance} for c, api, instance in
            [('display.output', 1, 5), ('input.touch.raw', 1, 6), ('rtc.clock', 2, 8),
             ('board.battery', 1, 4), ('storage.key-value', 1, 6), ('net.wifi', 1, 15),
             ('software.update.'+kind_path(app)[0], 1, 0), ('alarm.service', 1, 0)]]


def elf_symbols(data):
    """Read actual target dynamic authority, independently of builder metadata."""
    require(len(data) >= 52 and data[:7] == b'\x7fELF\x01\x01\x01' and
            struct.unpack_from('<HH', data, 16) == (3, 94), 'Not an Xtensa ELF32 shared object')
    offset = struct.unpack_from('<I', data, 32)[0]
    width, count, names_index = struct.unpack_from('<HHH', data, 46)
    require(width == 40 and 0 < count < 4096 and names_index < count and
            offset + width*count <= len(data), 'Invalid ELF section table')
    sections = [struct.unpack_from('<10I', data, offset+i*width) for i in range(count)]
    def section_bytes(s):
        require(s[4]+s[5] <= len(data), 'Invalid ELF section range')
        return data[s[4]:s[4]+s[5]]
    names = section_bytes(sections[names_index])
    def string(table, start):
        require(start < len(table) and b'\0' in table[start:], 'Invalid ELF string')
        return table[start:].split(b'\0', 1)[0].decode('ascii')
    sizes = {string(names, s[0]): s[5] for s in sections}
    imports, exports = set(), set()
    symbols = [s for s in sections if s[1] == 11]
    require(len(symbols) == 1, 'ELF requires exactly one dynamic symbol table')
    s = symbols[0]
    require(s[6] < count and s[9] == 16 and s[5] % 16 == 0, 'Invalid dynamic symbols')
    strings, raw = section_bytes(sections[s[6]]), section_bytes(s)
    for at in range(0, len(raw), 16):
        name, value, size, info, other, index = struct.unpack_from('<IIIBBH', raw, at)
        if not name or info >> 4 not in (1, 2):
            continue
        name = string(strings, name)
        if index == 0:
            imports.add(name)
        elif info & 15 in (1, 2) and other & 3 == 0:
            exports.add(name)
    return imports, exports, sizes


def entries(files, record):
    rows = record['entries']
    require(len(rows) == len({e['path'] for e in rows}) and
            {e['path'] for e in rows} == set(files)-{'deployment-record.json'},
            'Deployment entry membership differs')
    for row in rows:
        data = files[row['path']]
        require(len(data) == row['size_bytes'] and sha(data) == row['sha256'],
                'Deployment entry hash differs: '+row['path'])


def verify_files(files, root=ROOT, expected_head=None, common=False):
    record = json.loads(files['deployment-record.json'])
    entries(files, record)
    require(record['schema'] == 'riscrte.watch-update-launcher-deployment' and
            record['schema_version'] == 1 and record['app_version'] == '0.7.1' and
            record['physical_verification'] == 'pending', 'Wrong paired deployment identity')
    require(exact_sha(record['source_sha']) and
            (expected_head is None or expected_head == record['source_sha']), 'Unexpected Watch source')
    update = record['updates']
    selected = tuple(update['apps'])
    require(selected in SELECTIONS, 'Unknown, duplicate, or out-of-order updater selection')
    require(update == {'apps': list(selected), 'layout': 'riscrte-paired-16m-v1',
                       'store_abi': 1, 'flash_bytes': 0x1000000, 'migration_only': True,
                       'existing_8MiB_ota_compatible': False, 'rtc_utc_offset_seconds': 28800,
                       'wifi_namespace': 6, 'wifi_instance': 15, 'native_tables': 'provider-only',
                       'baseline_watch_source_sha': BASELINE_SOURCE}, 'Paired compatibility policy changed')
    baseline = json.loads((root/'scripts/update-preservation-baseline.json').read_text())
    service_sources = json.loads((root/'scripts/update-service-source-baseline.json').read_text())
    require(baseline['watch_source_sha'] == BASELINE_SOURCE and baseline['store_files'] == 44 and
            len(baseline['files']) == 43 and len(baseline['inputs']) == 8,
            'Incorrect preservation baseline')
    require(json.loads(files['shared/update-preservation-baseline.json']) == baseline,
            'Archived preservation baseline differs from reviewed source')
    expected_paths = {'store/board.json'} | {'store/'+n for n in baseline['files']}
    for app in selected:
        short = kind_path(app)[1]
        expected_paths.update({'store/'+app+'.elf', 'store/'+app+'.json',
                               'store/'+short+'/driver.elf', 'store/'+short+'/manifest.json'})
    require({n for n in files if n.startswith('store/')} == expected_paths and
            len(expected_paths) == 44+4*len(selected), 'Paired store inventory differs')
    require(all(len(('/'+n[6:]).encode()) < 32 for n in expected_paths), 'SPIFFS path too long')
    require(sum(len(files[n]) for n in expected_paths) < 0x4f0000, 'Paired store capacity exceeded')
    for name, expected in baseline['files'].items():
        if name in CHANGED:
            continue
        data = files['store/'+name]
        require(len(data) == expected['size_bytes'] and sha(data) == expected['sha256'],
                'Unrelated baseline file changed: '+name)
    board = json.loads(files['store/board.json'])
    require(files['store/board.json'] == encoded(board), 'Noncanonical board encoding')
    if not common:
        source = next((v for v in baseline['inputs'] if v['profile'] == record['profile']), None)
        require(source is not None, 'Unknown explicit hardware profile')
        require(files['source-profile.json'] == (root/'hardware'/(record['profile']+'.json')).read_bytes()
                and sha(files['source-profile.json']) == source['source_profile_sha256'] and
                sha(files['store/board.json']) == source['board_sha256'], 'Board/profile changed')
    expected_boot = copy.deepcopy(baseline['boot'])
    for app in selected:
        expected_boot['drivers'].append({'manifest': kind_path(app)[1]+'/manifest.json'})
        expected_boot['app_capabilities'].append({'manifest': app+'.json', 'grants': grants(app)})
    boot = json.loads(files['store/boot.json'])
    require(boot == expected_boot, 'Application or provider authority broadened/changed')
    pins = json.loads((root/'apps/update-sources.json').read_text())
    runtime = json.loads((root/'apps/update-runtime-requirements.json').read_text())
    require(json.loads(files['shared/update-sources.json']) == json.loads(files['shared/alarm-sources.json'])
            == pins, 'Source pins changed')
    require(json.loads(files['runtime-requirements.json']) == record['runtime_requirements'] == runtime
            and runtime['source_sha'] == pins['runtime']['commit'] and runtime['firmware_version'] == json.loads((root/'apps/update-runtime-artifact.json').read_text())['firmware_version'],
            'Runtime source/version mismatch')
    deployment = runtime['deployment']
    require(deployment['layout'] == update['layout'] and deployment['store_abi'] == 1 and
            deployment['flash_bytes'] == 0x1000000 and deployment['partitions'] == PARTITIONS and
            deployment['target'] == 'esp32s3-16mb-paired' and
            deployment['migration'] == 'explicit-user-controlled-full-16MiB-reflash-only' and
            deployment['existing_8MiB_ota_compatible'] is False, 'Unsafe runtime layout/migration policy')
    require(record['runtime_sdk'] == json.loads((root/'sdk/app/SOURCES.json').read_text()),
            'Watch runtime SDK provenance changed')
    require(json.loads(files['time-policy.json']) == record['time_policy'] ==
            json.loads((root/'apps/clock/time-policy.json').read_text()), 'Clock RTC policy changed')
    metadata = json.loads(files['shared-app-build.json'])
    require(metadata['shared_sources'] == pins and set(metadata['apps']) == set(APPS+selected),
            'App build source/membership mismatch')
    require(metadata['alarm_service']['runtime'] == pins['runtime'] and
            metadata['touch_rotation'] == 0 and metadata['handoff_ms'] == 60 and
            metadata['rtc_policy'] == 'fixed-UTC+08-to-America/Denver' and
            metadata['full_frames'] is True and metadata['retained_handoff'] is True,
            'Build/navigation/RTC policy changed')
    for name, policy in zip(APPS+selected, boot['app_capabilities']):
        manifest = json.loads(files['store/'+name+'.json'])
        if name in APPS:
            expected = copy.deepcopy(baseline['app_manifests'][name])
            if name in ('default', 'clock'):
                expected['version'] = '0.7.1'
            elif name == 'springboard':
                expected['version'] = service_sources['application_versions'][name]
        else:
            expected = {'type': 'application', 'id': name, 'version': service_sources['portable_application_versions'][name],
                        'architecture': 'xtensa-esp32s3', 'file_name': name+'.elf', 'entry': 'app_main',
                        'requires': [{'capability': g['capability'], 'api': g['api']} for g in grants(name)]}
        require(manifest == expected, 'Application manifest/requirements changed: '+name)
        data = files['store/'+name+'.elf']
        imports, exports, _ = elf_symbols(data)
        app = metadata['apps'][name]
        owner = record['source_sha'] if name in ('default', 'clock') else pins[
            'system-apps' if name in ('springboard', 'settings', 'wifi_settings')+selected else
            'productivity' if name == 'points_in_time' else 'utilities']['commit']
        if name in ('default', 'clock'):
            require(app['sdk'] == record['runtime_sdk'] and app['size_bytes'] == len(data),
                    'Paired Clock SDK/size provenance differs')
        require(app['repository_sha'] == owner and app['sha256'] == sha(data) and
                app['version'] == manifest['version'] and app['imports'] == sorted(imports),
                'Actual app ELF/source metadata differs: '+name)
        allowed = {'risc_runtime_get_api', 'memcpy', 'memset', 'memcmp', 'strcmp', 'strlen',
                   'snprintf', 'malloc', 'free', 'strcpy'}
        require(imports <= allowed and exports == ({'app_main'} if name in ('default', 'clock') else
                {'app_main', 'app_module_init', 'app_module_fini'}), 'Unexpected app native imports/exports')
    catalog_apps = ('clock', 'battery', 'settings', 'calculator', 'stopwatch', 'alarms',
                    'countdown', 'wifi_settings') + selected + ('points_in_time',)
    require([v['file_name'] for v in json.loads(files['shared/catalog.json'])] ==
            [a+'.elf' for a in catalog_apps], 'Catalog app membership/order differs')
    require(metadata['return_targets'] == {'springboard': 'clock.elf', **{a: 'springboard.elf'
            for a in APPS+selected if a not in ('default', 'clock', 'springboard')}}, 'Return targets differ')
    service_sources = json.loads((root/'scripts/update-service-source-baseline.json').read_text())
    require(service_sources['system_apps_source_sha'] == pins['system-apps']['commit'] and
            json.loads(files['shared/update-service-source-baseline.json']) == service_sources,
            'Provider source pin/baseline changed')
    update_build = json.loads(files['shared/update-build.json'])
    require(update_build['source_pins'] == pins and update_build['apps'] == list(selected) and
            update_build['layout'] == update['layout'] and update_build['store_abi'] == 1 and
            update_build['migration_only'] is True and update_build['rtc_utc_offset_seconds'] == 28800 and
            update_build['wifi_namespace'] == 6 and update_build['wifi_instance'] == 15 and
            update_build['baseline_watch_source_sha'] == BASELINE_SOURCE and
            set(update_build['providers']) == set(selected), 'Update source/build policy differs')
    expected_preserved = {name: value for name, value in baseline['files'].items()
                          if name.endswith('.elf') and name not in CHANGED and
                          ('/' not in name or name == 'alarm-service/driver.elf')}
    require(update_build['preserved_executables'] == expected_preserved,
            'Preserved executable evidence differs')
    require(update_build['runtime_candidate_status'] == deployment['candidate_artifact']['status'],
            'Runtime candidate custody status differs')
    for app in selected:
        kind, short = kind_path(app)
        manifest = json.loads(files['store/'+short+'/manifest.json'])
        require(manifest == {'type': 'driver', 'id': 'software-update-'+kind, 'version': '0.1.0',
                'driver_abi': 2, 'architecture': 'xtensa-esp32s3', 'file_name': 'driver.elf',
                'requires': [{'capability': c, 'api': 1} for c in NATIVE],
                'provides': [{'capability': 'software.update.'+kind, 'api': 1}],
                'status': 'development-only; no deployment or release publication'}, 'Provider authority differs')
        data = files['store/'+short+'/driver.elf']
        build = json.loads(files['shared/'+short+'-build.json'])
        imports, exports, sizes = elf_symbols(data)
        target = service_sources['target_artifacts'][kind]
        require(sha(data) == target['sha256'] and len(data) == target['size_bytes'] and
                sizes.get('.bss', 0) == target['bss_bytes'] and build['compiler'] == target['compiler'],
                'Pinned provider target bytes/compiler differ')
        require(build['source_sha256'] == service_sources['source_sha256'] and
                build['sha256'] == sha(data) and build['size_bytes'] == len(data) and
                build['imports'] == sorted(imports) and build['exports'] == sorted(exports) and
                imports <= {'memcpy', 'memset', 'memcmp', 'strcmp', 'strlen', 'snprintf', 'strcpy'} and
                exports == {'t5_driver_get'}, 'Provider source/ELF/import evidence differs')
        require(build['bss_bytes'] == sizes.get('.bss', 0) and
                512*1024 <= build['bss_bytes'] <= 704*1024 and
                not sizes.get('.init_array', 0) and not sizes.get('.ctors', 0) and
                build['stack_frames'] and max(build['stack_frames'].values()) <= 2048,
                'Provider workspace, constructors or stack budget changed')
        require(build['build_defines'] == ['-std=c++17', '-fno-exceptions', '-fno-rtti',
                                          '-DUPDATE_FIRMWARE='+str(int(kind == 'firmware'))],
                'Provider kind build define differs')
        require(update_build['providers'][app] == {'kind': kind, 'path': short, 'sha256': sha(data),
                'manifest_sha256': sha(files['store/'+short+'/manifest.json'])}, 'Provider delivery hash differs')
    require(record['drivers'] == baseline['driver_packages'], 'Physical package membership changed')
    for package in record['drivers']:
        data = files['packages/'+package['archive']]
        require(sha(data) == package['sha256'] and len(data) == package['size_bytes'], 'Physical package changed')
    alarm = json.loads(files['shared/alarm-service-build.json'])
    alarm_baseline = json.loads((root/'apps/points-service-baseline.json').read_text())
    require(alarm['source_sha256'] == alarm_baseline['source_sha256'] and
            alarm['size_bytes'] == len(files['store/alarm-service/driver.elf']), 'Alarm provenance changed')
    require(alarm['source_pins'] == pins and alarm['service_version'] == '0.2.1' and
            alarm['elf_sha256'] == sha(files['store/alarm-service/driver.elf']), 'Alarm source/ELF changed')
    return record


def verify(path, root=ROOT, expected_head=None):
    record = verify_files(read_zip(path), root=root, expected_head=expected_head)
    print(Path(path).name, 'verified exact authority, source, 44-file preservation and paired layout')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='+', type=Path)
    parser.add_argument('--expected-head')
    args = parser.parse_args()
    for path in args.archives:
        verify(path, expected_head=args.expected_head)

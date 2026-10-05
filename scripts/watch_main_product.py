#!/usr/bin/env python3
"""Frozen main-style product custody. Reads bytes; never rebuilds or flashes.

Schema 2 is deliberately separate from the immutable schema-1 launcher release.
All published payloads are derived again during verification from pinned inputs.
"""
import copy
import json
from pathlib import Path, PurePosixPath
import re

from read_only_spiffs import read_image
from watch_release_index import EMPTY_INDEX, REPOSITORY, require, update_index, validate_record, version_tuple

FLASH_BYTES = 0x1000000
BOOTFS_OFFSET, BOOTFS_SIZE = 0x310000, 0x4f0000
LAYOUT = 'riscrte-paired-16m-v1'
CI_JOBS = {'software-checks', 'alarm-integration', 'points-integration',
           'points-store-faces', 'wifi-integration', 'production-store-admission',
           'update-integration', 'update-cross-layer', 'latest-main-image'}
ACCEPTANCE = {'kind': 'ci-accepted', 'hardware_qualified': False}
SCOPE = ('Exact frozen CI-accepted main-style image. Physical verification is pending; '
         'no hardware, power-consumption, or optional-peripheral qualification is claimed. '
         'The publication process does not access or flash a device.')
PARTITIONS = [('bootloader.bin', 0, 0x8000), ('partitions.bin', 0x8000, 0x9000),
              ('firmware.bin', 0x10000, BOOTFS_OFFSET),
              ('bootfs.bin', BOOTFS_OFFSET, 0x800000),
              ('otadata.bin', 0xff0000, 0xff2000), ('bank_state.bin', 0xff2000, 0xff4000)]


def exact_hex(value, length):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def basename(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,159}', value) and '..' not in value


def validate_config(p):
    require(p.get('schema') == 2 and p.get('repository') == REPOSITORY, 'Product identity mismatch')
    version_tuple(p['version']); version_tuple(p['accepted_build'])
    require(p.get('tag') == 'firmware-v' + p['version'], 'Product tag/version mismatch')
    require(p.get('acceptance') == ACCEPTANCE, 'Schema 2 requires explicit CI-only acceptance')
    limitations = p.get('known_limitations', [])
    require(isinstance(limitations, list) and len(limitations) <= 10 and
            all(isinstance(item, str) and item.strip() and len(item) <= 500 and '\n' not in item and '\r' not in item
                for item in limitations) and sum(map(len, limitations)) <= 4000,
            'Known limitations must be a bounded list of nonempty single-line strings')
    require(isinstance(p.get('accepted_on'), str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', p['accepted_on']),
            'Acceptance date required')
    require((p.get('bin_size'), p.get('flash_capacity'), p.get('flash_offset')) ==
            (FLASH_BYTES, FLASH_BYTES, '0x0'), 'Main product must replace the complete 16 MiB')
    require(all(exact_hex(p.get(k), 64) for k in ('accepted_bin_sha256', 'accepted_bundle_sha256')),
            'Frozen BIN and install ZIP digests required')
    require(basename(p.get('accepted_bin_name')) and p['accepted_bin_name'].endswith('.bin') and
            basename(p.get('accepted_bundle_name')) and p['accepted_bundle_name'].endswith('.zip'),
            'Exact accepted asset names required')
    require(type(p.get('store_file_count')) is int and p['store_file_count'] >= 58,
            'Full main-style store inventory required')
    require(isinstance(p.get('sources'), dict) and {'watch', 'runtime'} <= p['sources'].keys(),
            'Exact Watch and Runtime sources required')
    for item in p['sources'].values():
        require(isinstance(item, dict) and exact_hex(item.get('accepted_sha'), 40) and
                re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', item.get('repository', '')),
                'Exact source repository and commit required')
    require(p['sources']['watch']['repository'] == REPOSITORY and
            exact_hex(p['sources']['watch'].get('tree'), 40), 'Watch source/tree custody required')
    require(p['sources']['runtime']['repository'] == 'michaelrolphone-cmyk/RiscRTE', 'Runtime repository mismatch')
    for key in ('component_versions', 'driver_versions', 'embedded_driver_versions'):
        require(isinstance(p.get(key), dict) and p[key], 'Complete component version inventory required')
        for name, version in p[key].items():
            require(re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}', name), 'Unsafe component name')
            version_tuple(version)
    reused = p.get('reused_driver_records', {})
    require(isinstance(reused, dict) and set(reused) <= set(p['driver_versions']), 'Unrecognized reused driver identity')
    for identity, record in reused.items():
        validate_record('drivers', record)
        require(record['id'] == identity and record['version'] == p['driver_versions'][identity],
                'Reused driver identity/version mismatch')
    require(p['component_versions'].get('default') == p['accepted_build'] and
            p['component_versions'].get('clock') == p['accepted_build'] and
            'runtime' in p['component_versions'], 'Clock/Runtime component version mismatch')
    artifact_keys = set(p.get('artifacts', {}))
    require(artifact_keys in ({'main', 'audio', 'points', 'drivers'},
                              {'main', 'audio', 'points', 'drivers', 'current-apps'}),
            'Exact main CI input inventory required')
    if 'current-apps' in artifact_keys:
        cfg = p.get('current_apps_configuration')
        require(isinstance(cfg, dict) and cfg.get('schema') == 1 and cfg.get('profile') == 'watch-current-apps-v1',
                'Exact current-apps source/version configuration required')
        repositories = {'system-apps': 'RiscRTE-System-Apps', 'utilities': 'RiscRTE-Utilities',
                        'productivity': 'RiscRTE-Productivity', 'runtime': 'RiscRTE'}
        require(set(cfg.get('sources', {})) == set(repositories), 'Complete current-apps owning sources required')
        for key, repository in repositories.items():
            item = cfg['sources'][key]
            require(item.get('repository') == 'michaelrolphone-cmyk/' + repository and exact_hex(item.get('commit'), 40),
                    'Exact current-apps owning source required: ' + key)
        require(cfg['sources']['runtime']['commit'] == p['sources']['runtime']['accepted_sha'],
                'Current-apps Runtime source differs from final image')
        require(cfg.get('app_versions') == {n: v for n, v in p['component_versions'].items()
                                           if n != 'runtime'},
                'Current-apps configuration must cover every final app version')
        require(cfg.get('service_version') == p['embedded_driver_versions'].get('alarm-service'),
                'Current-apps alarm service version mismatch')
    else:
        require('current_apps_configuration' not in p, 'Current-apps configuration needs its frozen artifact')
    runs = set()
    artifact_names = {'main': 'twatch-flashable-bin-' + p['sources']['watch']['accepted_sha'],
                      'audio': 'twatch-update-integration-' + p['sources']['watch']['accepted_sha'],
                      'points': 'twatch-points-integration-' + p['sources']['watch']['accepted_sha'],
                      'drivers': 'twatch-driver-packages',
                      'current-apps': 'twatch-current-apps-' + p['sources']['watch']['accepted_sha']}
    for name, item in p['artifacts'].items():
        require(item.get('repository') == REPOSITORY and item.get('head_sha') == p['sources']['watch']['accepted_sha'],
                'Artifact repository/source mismatch: ' + name)
        require(all(type(item.get(k)) is int and item[k] > 0 for k in ('run_id', 'artifact_id', 'run_attempt')),
                'Exact Actions run/artifact identity required: ' + name)
        require(exact_hex(item.get('sha256'), 64) and item.get('name') == artifact_names[name], 'Artifact hash/name required: ' + name)
        runs.add((item['run_id'], item['run_attempt']))
        if name in ('audio', 'points'):
            member = item.get('bundle_member', '')
            require(member and str(PurePosixPath(member)) == member and not PurePosixPath(member).is_absolute() and
                    '..' not in PurePosixPath(member).parts and '\\' not in member and member.endswith('.zip'),
                    'Exact deployment bundle member required: ' + name)
    require(len(runs) == 1, 'All frozen Watch artifacts must belong to one accepted CI run attempt')
    require(isinstance(p.get('deployment_sources'), dict) and set(p['deployment_sources']) == {'audio', 'points', 'update'},
            'All compiled deployment source generations must be recorded')
    for group in p['deployment_sources'].values():
        require(isinstance(group, dict) and group, 'Empty deployment source inventory')
        for item in group.values():
            require(exact_hex(item.get('commit'), 40) and
                    re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', item.get('repository', '')),
                    'Unpinned deployment source')
    return p


def verify_ci(p, h):
    item = p['artifacts']['main']
    base = f'repos/{REPOSITORY}/actions/runs/{item["run_id"]}'
    run = h.api(base)
    require(run.get('id') == item['run_id'] and run.get('head_sha') == item['head_sha'] and
            run.get('run_attempt') == item['run_attempt'] and run.get('status') == 'completed' and
            run.get('conclusion') == 'success' and run.get('path') == '.github/workflows/drivers.yml' and
            run.get('repository', {}).get('full_name') == REPOSITORY, 'Accepted CI run identity/conclusion mismatch')
    pages = json.loads(h.gh('api', base + f'/attempts/{item["run_attempt"]}/jobs?per_page=100', '--paginate', '--slurp'))
    jobs = [job for page in pages for job in page['jobs']]
    for name in CI_JOBS:
        matches = [j for j in jobs if j.get('name') == name]
        require(len(matches) == 1 and matches[0].get('conclusion') == 'success', 'Accepted CI job missing or unsuccessful: ' + name)
    return run


def zip_files(data, h):
    with h.checked_zip(data) as z:
        return {name: z.read(name) for name in z.namelist() if not name.endswith('/')}


def verify_checksums(files, h):
    expected = ''.join(f'{h.sha(data)}  {name}\n' for name, data in sorted(files.items()) if name != 'SHA256SUMS')
    require(files.get('SHA256SUMS') == expected.encode(), 'Frozen install checksum inventory mismatch')


def image_custody(p, raw, h):
    """Decode exact frozen bytes, not reconstructed app or driver files."""
    outer = zip_files(raw, h)
    bundle = outer.get(p['accepted_bundle_name'])
    require(bundle is not None and h.sha(bundle) == p['accepted_bundle_sha256'], 'Frozen install ZIP hash mismatch')
    files = zip_files(bundle, h)
    require(set(files) == {p['accepted_bin_name'], 'manifest.json', 'FLASHING.md', 'SHA256SUMS'}, 'Frozen install ZIP inventory mismatch')
    require(set(outer) == set(files) | {p['accepted_bundle_name']} and
            all(outer[name] == data for name, data in files.items()), 'Main artifact and install ZIP disagree')
    verify_checksums(files, h)
    binary = files[p['accepted_bin_name']]
    require(len(binary) == FLASH_BYTES and h.sha(binary) == p['accepted_bin_sha256'], 'Frozen main BIN hash/size mismatch')
    manifest = json.loads(files['manifest.json'])
    expected = {'schema': 1, 'kind': 'latest-merged-main-full-flash', 'file': p['accepted_bin_name'],
                'watch_source': p['sources']['watch']['accepted_sha'], 'watch_tree': p['sources']['watch']['tree'],
                'watch_version': p['accepted_build'], 'runtime_source': p['sources']['runtime']['accepted_sha'],
                'runtime_version': p['component_versions']['runtime'], 'layout': LAYOUT, 'store_abi': 1,
                'bin_sha256': p['accepted_bin_sha256'], 'size_bytes': FLASH_BYTES, 'flash_offset': '0x0',
                'overwrite_bytes': FLASH_BYTES, 'flash_capacity_bytes': FLASH_BYTES, 'physical_verification': 'pending'}
    require(all(manifest.get(k) == v for k, v in expected.items()), 'Frozen main manifest identity mismatch')
    require(len(manifest.get('components', [])) == len(PARTITIONS), 'Incomplete paired component inventory')
    cursor = 0
    for entry, (name, offset, limit) in zip(manifest['components'], PARTITIONS):
        size = entry.get('size_bytes')
        require(entry.get('file') == 'components/' + name and entry.get('offset') == hex(offset) and
                type(size) is int and size > 0 and offset + size <= limit, 'Paired component layout mismatch')
        require(binary[cursor:offset] == b'\xff' * (offset - cursor), 'Unexpected occupied flash gap')
        require(h.sha(binary[offset:offset + size]) == entry.get('sha256'), 'Frozen component bytes differ: ' + name)
        if name in ('bootfs.bin', 'otadata.bin', 'bank_state.bin'):
            require(offset + size == limit, 'Fixed paired partition size mismatch')
        cursor = offset + size
    require(binary[cursor:] == b'\xff' * (len(binary) - cursor), 'Unexpected occupied flash tail')
    image = binary[BOOTFS_OFFSET:BOOTFS_OFFSET + BOOTFS_SIZE]
    require(h.sha(image) == manifest.get('bootfs_sha256'), 'Boot store digest mismatch')
    try:
        store = read_image(image)
    except (AssertionError, KeyError, IndexError) as error:
        raise ValueError('Invalid frozen SPIFFS store') from error
    expected_store = [{'path': n, 'size_bytes': len(b), 'sha256': h.sha(b)} for n, b in sorted(store.items())]
    require(len(store) == p['store_file_count'] and manifest.get('store') == expected_store, 'Exact frozen store inventory mismatch')
    require({'default.json', 'default.elf', 'clock.json', 'clock.elf', 'boot.json', 'board.json'} <= store.keys(), 'Incomplete main store')
    embedded_drivers = {}
    for path, data in store.items():
        if not path.endswith('/manifest.json'):
            continue
        item = json.loads(data)
        require(item.get('type') == 'driver', 'Unrecognized embedded component manifest')
        identity = path.removesuffix('/manifest.json')
        require(identity + '/driver.elf' in store, 'Embedded driver ELF absent')
        embedded_drivers[identity] = item.get('version')
    require(embedded_drivers == p['embedded_driver_versions'], 'Embedded driver/service version inventory mismatch')
    require({n for n in store if '/' in n and n.endswith('.elf')} ==
            {n + '/driver.elf' for n in embedded_drivers}, 'Unmanifested embedded driver')
    # With the current overlay, this record describes the historical intermediate
    # pair. The final pair is checked separately against current-apps Clock proof.
    if manifest.get('current_apps_overlay') is None:
        clock_files = manifest['points_overlay']['paired_clock']['files']
        require(set(clock_files) == {'default.json', 'default.elf', 'clock.json', 'clock.elf'}, 'Incomplete paired Clock custody')
        for name, metadata in clock_files.items():
            require(metadata == {'size_bytes': len(store[name]), 'sha256': h.sha(store[name])},
                    'Frozen paired Clock evidence differs from BIN: ' + name)
    return binary, bundle, manifest, store


def app_inventory(p, store):
    apps = {}
    for path, data in sorted(store.items()):
        if not path.endswith('.json'):
            continue
        manifest = json.loads(data)
        if not isinstance(manifest, dict) or manifest.get('type') != 'application':
            continue
        name = path.removesuffix('.json')
        require('/' not in name and re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}', name), 'Unsafe application identity')
        require(manifest.get('file_name') == name + '.elf' and manifest.get('architecture') == 'xtensa-esp32s3', 'Application identity mismatch')
        require(manifest.get('version') == p['component_versions'].get(name), 'Unpinned application version: ' + name)
        elf = store.get(name + '.elf', b'')
        require(len(elf) >= 52 and elf[:7] == b'\x7fELF\x01\x01\x01' and elf[16:20] == b'\x03\x00\x5e\x00', 'Invalid frozen Xtensa application: ' + name)
        apps[name] = (manifest, data, elf)
    require(set(apps) == set(p['component_versions']) - {'runtime'}, 'Component version inventory differs from embedded applications')
    require({n for n in store if '/' not in n and n.endswith('.elf')} == {n + '.elf' for n in apps}, 'Unmanifested embedded application')
    return apps


def licenses(p, manifest, artifacts, h):
    result = {}
    for key in ('audio', 'points'):
        outer = zip_files(artifacts[key], h)
        raw = outer[p['artifacts'][key]['bundle_member']]
        require(h.sha(raw) == manifest[key + '_common_sha256'], 'Deployment license/source custody mismatch: ' + key)
        files = zip_files(raw, h)
        selected = {key + '/' + name: data for name, data in files.items()
                    if name.startswith(('licenses/', 'shared/', 'reproduce/'))}
        require(any(name.startswith(key + '/licenses/') for name in selected), 'Deployment license evidence absent: ' + key)
        result.update(selected)
        source_name = 'shared/audio-sources.json' if key == 'audio' else 'shared/alarm-sources.json'
        actual = json.loads(files[source_name])
        if key == 'audio':
            actual = actual['sources']
            require(json.loads(files['shared/update-sources.json']) == p['deployment_sources']['update'], 'Update build source generations mismatch')
        require(actual == p['deployment_sources'][key], 'Deployment build source generations mismatch: ' + key)
    require(manifest['audio_tools']['sources'] == p['deployment_sources']['audio'] and
            manifest['points_overlay']['paired_clock']['points_sources'] == p['deployment_sources']['points'],
            'Final overlay source generations mismatch')
    return h.archive(result)


def current_apps_custody(p, manifest, store, artifacts, h):
    overlay = manifest.get('current_apps_overlay')
    require((overlay is not None) == ('current-apps' in artifacts), 'Final current-apps overlay/artifact mismatch')
    if overlay is None:
        return {}
    outer = zip_files(artifacts['current-apps'], h)
    raw = outer.get('current-apps.zip')
    require(raw is not None and h.sha(raw) == overlay.get('archive_sha256'), 'Current-apps archive custody mismatch')
    files = zip_files(raw, h)
    require(set(outer) == set(files) | {'current-apps.zip'} and
            all(outer[n] == b for n, b in files.items()), 'Current-apps artifact/inner ZIP mismatch')
    record_raw = files['current-apps-build.json']
    record = json.loads(record_raw)
    require(h.sha(record_raw) == overlay.get('build_record_sha256') and overlay.get('build_record') == record,
            'Final current-apps build record mismatch')
    require(record.get('schema') == 1 and record.get('profile') == 'watch-current-apps-v1' and
            record.get('watch_source') == p['sources']['watch']['accepted_sha'], 'Current-apps source identity mismatch')
    require(record.get('configuration') == p['current_apps_configuration'] == json.loads(files['source-profile.json']),
            'Current-apps source/version configuration mismatch')
    require(record.get('boot') == json.loads(store['boot.json']), 'Current-apps final boot policy differs from BIN')
    payloads = record['files']
    require(isinstance(payloads, dict) and payloads, 'Current-apps payload inventory absent')
    require(record.get('target_validation') is True, 'Current-apps target validation missing')
    require(set(record.get('apps', {})) == set(p['current_apps_configuration']['app_versions']),
            'Current-apps build record application inventory mismatch')
    for name, version in p['current_apps_configuration']['app_versions'].items():
        app = record['apps'][name]
        require(app.get('version') == version and app.get('sha256') == h.sha(store[name + '.elf']) and
                app.get('size_bytes') == len(store[name + '.elf']), 'Current-apps app build proof mismatch: ' + name)
    clock = record.get('clock', {})
    require(clock.get('watch_source') == p['sources']['watch']['accepted_sha'] and
            clock.get('sources') == p['current_apps_configuration']['sources'] and
            clock.get('paired_boot_confirmation') is True, 'Current Clock source/paired confirmation mismatch')
    require(clock.get('headers') == record.get('service', {}).get('points_headers') and
            set(clock.get('headers', {})) == {'PointsRecords.h', 'PointsSchedule.h'} and
            all(exact_hex(v, 64) for v in clock['headers'].values()), 'Current Clock/service schema header mismatch')
    source_hashes = clock.get('source_sha256')
    require(isinstance(source_hashes, dict) and source_hashes, 'Current Clock Watch source evidence missing')
    for name, digest in source_hashes.items():
        require(name and str(PurePosixPath(name)) == name and not PurePosixPath(name).is_absolute() and
                '..' not in PurePosixPath(name).parts and '\\' not in name and exact_hex(digest, 64),
                'Current Clock Watch source evidence invalid')
    clock_files = clock.get('files', {})
    require(set(clock_files) == {'default.json', 'default.elf', 'clock.json', 'clock.elf'}, 'Current Clock file proof incomplete')
    for name, metadata in clock_files.items():
        require(metadata == {'size_bytes': len(store[name]), 'sha256': h.sha(store[name])},
                'Current Clock bytes differ from final BIN: ' + name)
    expected_files = {name + suffix for name in p['current_apps_configuration']['app_versions']
                      for suffix in ('.elf', '.json')} | {name + '/' + suffix
                      for name in ('alarm-service', 'update-fw', 'update-apps')
                      for suffix in ('driver.elf', 'manifest.json')}
    require({n[6:] for n in files if n.startswith('files/')} == set(payloads) == expected_files,
            'Current-apps payload inventory mismatch')
    for name, metadata in payloads.items():
        data = files['files/' + name]
        require(metadata == {'size_bytes': len(data), 'sha256': h.sha(data)} and store.get(name) == data,
                'Current-apps payload differs from frozen BIN: ' + name)
    changed = overlay['files']
    preserved = overlay['preserved_files']
    require(set(changed) == set(payloads) | {'boot.json'} and not set(changed) & set(preserved) and
            set(changed) | set(preserved) == set(store), 'Current-apps final store partition mismatch')
    for name, metadata in {**changed, **preserved}.items():
        require(metadata == {'size_bytes': len(store[name]), 'sha256': h.sha(store[name])},
                'Current-apps changed/preserved store evidence mismatch')
    selected = {name: data for name, data in files.items() if name.startswith('licenses/')}
    require(selected, 'Current-apps license evidence missing')
    return {'current-apps/' + n: b for n, b in {**selected,
            'current-apps-build.json': record_raw, 'source-profile.json': files['source-profile.json']}.items()}


def driver_records(p, raw, store, h):
    files = zip_files(raw, h)
    catalog = json.loads(files['catalog.json'])
    packages = catalog['packages']
    require(catalog.get('schema') == 1 and len(packages) == len(p['driver_versions']) and
            {x['id']: x['version'] for x in packages} == p['driver_versions'], 'Complete driver version inventory mismatch')
    records, assets = [], {}
    for entry in packages:
        name = entry['archive']
        require(basename(name), 'Unsafe driver asset name')
        data = files[name]
        require(len(data) == entry['size_bytes'] and h.sha(data) == entry['sha256'], 'Driver archive custody mismatch')
        package = zip_files(data, h)
        manifest = json.loads(package['.package.json'])
        entries = manifest['entries']
        require(manifest['id'] == entry['id'] and manifest['version'] == entry['version'] and
                len(entries) == len(package) - 1 and {e['name'] for e in entries} == set(package) - {'.package.json'}, 'Driver package inventory mismatch')
        for item in entries:
            payload = package[item['name']]
            require(len(payload) == item['size_bytes'] and h.sha(payload) == item['sha256'], 'Driver package payload mismatch')
        short = entry['id'].removeprefix('twatch-')
        deployed = short + '/driver.elf'
        if deployed in store:
            require(package['driver.elf'] == store[deployed] and json.loads(package['source-manifest.json']) ==
                    json.loads(store[short + '/manifest.json']), 'Independent driver differs from frozen BIN: ' + entry['id'])
        record = h.record('driver', entry['id'], entry['version'], name, data,
                          format='rte.zip', architecture='xtensa-esp32s3', manifest=manifest,
                          source_repo=REPOSITORY, included_in_accepted_bin=deployed in store)
        previous = p.get('reused_driver_records', {}).get(entry['id'])
        if previous is not None:
            validate_record('drivers', previous)
            fields = ('kind', 'id', 'version', 'tag', 'asset', 'url', 'size', 'sha256',
                      'format', 'architecture', 'manifest', 'source_repo')
            require(all(previous.get(key) == record.get(key) for key in fields),
                    'Reused immutable driver package/manifest collision: ' + entry['id'])
            # Preserve every original field, including historical source and
            # inclusion context. Current installation lives in product provenance.
            record = copy.deepcopy(previous)
        records.append(record); assets[name] = data
    return records, assets


def installed_physical_drivers(p, raw, store, h):
    files = zip_files(raw, h)
    installed = []
    for item in json.loads(files['catalog.json'])['packages']:
        directory = item['id'].removeprefix('twatch-')
        path = directory + '/driver.elf'
        if path not in store:
            continue
        manifest_path = directory + '/manifest.json'
        installed.append({'id': item['id'], 'version': item['version'],
                          'package_asset': item['archive'], 'package_sha256': item['sha256'],
                          'package_size_bytes': item['size_bytes'],
                          'elf': {'path': path, 'size_bytes': len(store[path]), 'sha256': h.sha(store[path])},
                          'source_manifest': {'path': manifest_path, 'size_bytes': len(store[manifest_path]),
                                              'sha256': h.sha(store[manifest_path])}})
    return sorted(installed, key=lambda item: item['id'])


def known_limitations_text(p):
    items = p.get('known_limitations', [])
    return 'Known limitations:\n' + ''.join('- ' + item + '\n' for item in items) if items else ''


def flashing_document(p):
    name = f'twatch-s3-launcher-{p["version"]}.bin'
    return (f'# Watch {p["version"]}\n\nOriginal/non-Plus LILYGO T-Watch-S3, 16 MiB flash / 8 MiB OPI PSRAM.\n\n'
            f'Flashable merged image: {name}, offset 0x0, exactly 16 MiB.\nSHA256: {p["accepted_bin_sha256"]}\n\n'
            f'{SCOPE}\n\n' + (known_limitations_text(p) + '\n' if p.get('known_limitations') else '') +
            'Product promotion preserves every accepted byte and embedded component version. '
            'The original main-style install ZIP is preserved unchanged.\n\n'
            'WARNING: flashing replaces the entire 16 MiB, repartitions flash, and overwrites both banks, '
            'NVS/settings, saved Wi-Fi credentials, Stopwatch, alarms/countdowns and Points records. '
            'Back up first. This is a destructive migration image, not an OTA or settings-preserving update.\n\n'
            'After your own backup and device selection:\n'
            f'python -m esptool --chip esp32s3 --port PORT --baud 460800 write_flash 0x0 {name}\n\n'
            'Independent application ELFs and manifests are extracted from this exact frozen store. '
            'Downloading an ELF does not install it. Retain the matching board, grants and component configuration.\n').encode()


def payloads(p, source, artifacts, h):
    for key, raw in artifacts.items():
        require(h.sha(raw) == p['artifacts'][key]['sha256'], 'Frozen artifact changed: ' + key)
    require(set(artifacts) == set(p['artifacts']), 'Frozen artifact inventory mismatch')
    binary, bundle, manifest, store = image_custody(p, artifacts['main'], h)
    license_archive = licenses(p, manifest, artifacts, h)
    current_evidence = current_apps_custody(p, manifest, store, artifacts, h)
    if current_evidence:
        license_archive = h.archive({**zip_files(license_archive, h), **current_evidence})
    releases = []
    index = copy.deepcopy(EMPTY_INDEX)
    for name, (app, manifest_data, data) in app_inventory(p, store).items():
        record = h.record('app', name, app['version'], name + '.elf', data, manifest=app,
                          source_repo=REPOSITORY, source_sha=p['sources']['watch']['accepted_sha'],
                          build_sources=p['sources'], deployment_sources=p['deployment_sources'],
                          configuration='frozen-watch-main-' + p['accepted_build'],
                          **({'current_apps_configuration': p['current_apps_configuration']} if current_evidence else {}))
        index = update_index(index, 'apps', record)
        releases.append((record, {name + '.elf': data, name + '.json': manifest_data,
                         'LICENSES.zip': license_archive, 'release-record.json': h.encoded(record)},
                         p['sources']['watch']['accepted_sha'], False))
    drivers, assets = driver_records(p, artifacts['drivers'], store, h)
    for record in drivers:
        index = update_index(index, 'drivers', record)
    name = f'twatch-s3-launcher-{p["version"]}.bin'
    firmware = h.record('firmware', '', p['version'], name, binary, source_sha=source,
                        accepted_source_sha=p['sources']['watch']['accepted_sha'], component_versions=p['component_versions'])
    index = update_index(index, 'firmware', firmware)
    provenance = {**p, 'release_source_sha': source, 'binary_rebuilt': False,
                  'version_scope': 'Product release only; every frozen embedded component version and byte is unchanged.',
                  'hardware_acceptance_scope': SCOPE, 'accepted_manifest': manifest,
                  'installed_physical_drivers': installed_physical_drivers(p, artifacts['drivers'], store, h),
                  'driver_installation_scope': 'installed_physical_drivers is authoritative for this product; reused immutable index records retain their original release context.'}
    releases.append((firmware, {name: binary, p['accepted_bundle_name']: bundle,
                     'release-record.json': h.encoded(firmware), 'product-provenance.json': h.encoded(provenance),
                     'release-index.json': h.serialize_index(index).encode(), 'FLASHING.md': flashing_document(p)}, source, True))
    return releases, drivers, assets, index


def stage(p, inputs, accepted_watch, runtime_source, output, h):
    source = h.command('git', 'rev-parse', 'HEAD').decode().strip()
    h.verify_watch_ancestry(p['sources']['watch']['accepted_sha'], source)
    for path, key in ((accepted_watch, 'watch'), (runtime_source, 'runtime')):
        require(h.command('git', 'rev-parse', 'HEAD', cwd=path).decode().strip() == p['sources'][key]['accepted_sha'], 'Source checkout mismatch')
        require(not h.command('git', 'status', '--porcelain', '--untracked-files=no', cwd=path).strip(), 'Source checkout dirty')
    require(h.command('git', 'rev-parse', 'HEAD^{tree}', cwd=accepted_watch).decode().strip() == p['sources']['watch']['tree'], 'Watch source tree mismatch')
    for lane in ('audio', 'points', 'update'):
        actual = json.loads((accepted_watch / f'apps/{lane}-sources.json').read_text())
        require((actual['sources'] if lane == 'audio' else actual) == p['deployment_sources'][lane], 'Source checkout deployment pins mismatch')
    if 'current-apps' in p['artifacts']:
        require(json.loads((accepted_watch / 'apps/current-apps-sources.json').read_text()) == p['current_apps_configuration'],
                'Source checkout current-apps profile mismatch')
    requirements = json.loads((accepted_watch / 'apps/update-runtime-requirements.json').read_text())
    require(requirements['source_sha'] == p['sources']['runtime']['accepted_sha'] and
            requirements['firmware_version'] == p['component_versions']['runtime'], 'Frozen Runtime requirement mismatch')
    require(not output.exists(), 'Output directory already exists; use a fresh staging directory')
    artifacts = {key: (inputs / (key + '.zip')).read_bytes() for key in p['artifacts']}
    releases, drivers, assets, index = payloads(p, source, artifacts, h)
    if 'current-apps' in artifacts:
        current = zip_files(artifacts['current-apps'], h)
        clock = json.loads(current['current-apps-build.json'])['clock']
        for name, digest in clock['source_sha256'].items():
            path = accepted_watch / name
            h.safe_input_path(path)
            require(path.is_file() and h.sha(path.read_bytes()) == digest, 'Current Clock Watch source bytes mismatch: ' + name)
    output.mkdir(parents=True)
    (output / 'inputs').mkdir(); (output / 'driver-assets').mkdir()
    for key, raw in artifacts.items():
        (output / 'inputs' / (key + '.zip')).write_bytes(raw)
    for name, raw in assets.items():
        (output / 'driver-assets' / name).write_bytes(raw)
    plan = {'schema': 1, 'repository': REPOSITORY, 'source_sha': source, 'product': p,
            'releases': [h.write_release(output, *r) for r in releases], 'driver_records': drivers, 'index': index}
    (output / 'publication-plan.json').write_bytes(h.encoded(plan))
    verify_stage(p, output, h)
    print(f'Staged Watch {p["version"]}: exact frozen 16 MiB BIN, {len(releases) - 1} apps, {len(drivers)} driver references; hardware unqualified')


def verify_stage(p, output, h):
    require(not output.is_symlink() and not (output / 'inputs').is_symlink() and
            not (output / 'driver-assets').is_symlink(), 'Staged directory is symlinked')
    plan = json.loads((output / 'publication-plan.json').read_text())
    source = h.command('git', 'rev-parse', 'HEAD').decode().strip()
    require(plan.get('schema') == 1 and plan.get('repository') == REPOSITORY and plan.get('product') == p and
            plan.get('source_sha') == source, 'Staged product/source mismatch')
    h.verify_watch_ancestry(p['sources']['watch']['accepted_sha'], source)
    def read(path):
        require(path.is_file() and not path.is_symlink(), 'Staged input absent or symlinked')
        return path.read_bytes()
    artifacts = {key: read(output / 'inputs' / (key + '.zip')) for key in p['artifacts']}
    releases, drivers, assets, index = payloads(p, source, artifacts, h)
    require(plan.get('driver_records') == drivers and plan.get('index') == index, 'Publication/index records differ from frozen components')
    expected_releases = []
    for record, files, target, latest in releases:
        files['SHA256SUMS'] = ''.join(f'{h.sha(data)}  {name}\n' for name, data in sorted(files.items())).encode()
        directory = output / record['tag']
        require(not directory.is_symlink() and {x.name for x in directory.iterdir()} == set(files), 'Unexpected staged assets')
        for name, raw in files.items():
            require(read(directory / name) == raw, 'Staged asset differs from frozen bytes: ' + name)
        expected_releases.append({'tag': record['tag'], 'source_sha': target, 'latest': latest,
                                  'assets': {n: {'size': len(b), 'sha256': h.sha(b)} for n, b in sorted(files.items())}})
    require(plan.get('releases') == expected_releases, 'Publication release inventory differs')
    require({x.name for x in (output / 'inputs').iterdir()} == {k + '.zip' for k in artifacts}, 'Unexpected staged input')
    require({x.name for x in (output / 'driver-assets').iterdir()} == set(assets), 'Unexpected driver assets')
    for name, raw in assets.items():
        require(read(output / 'driver-assets' / name) == raw, 'Staged driver changed')
    return plan

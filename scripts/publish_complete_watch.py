#!/usr/bin/env python3
"""Package the exact owner-accepted Watch 1.0.7 image without compiling it.

The publication coordinator uses release_preflight/publish_one and publish_index
from publish_watch_product, with an exact predecessor compare-and-swap. This
initial-image release contains no OTA payload or OTA record. Staging and testing
perform no network operations; publication requires its explicit CLI action.
"""
import argparse
import copy
import gzip
import json
import os
from pathlib import Path
import re
import tempfile

import publish_watch_product as pub
from read_only_spiffs import read_image
from watch_release_index import require, serialize_index, update_index, validate_record

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.7'
TAG = 'firmware-v' + VERSION
IMAGE = 'twatch-s3-1.0.7-SDR-CURSOR-FIX-FULL-INITIAL-ERASES-DATA-bma423.bin'
ASSET = 'twatch-s3-launcher-1.0.7.bin'
IMAGE_SHA = 'b039468858ab3cb5d1b53d843257e0e034d0a0b661ddaf3b74b59670519b0b2b'
CURRENT_SHA = 'a6e7269caf66dc7c622954d5ae590a0e3ec44e9fc610776d58113f306233f8b2'
EVIDENCE_SHA = '419f66a79f6718742830adbb223614e266d0a6e25a30635cdafc18b72ac1a0f9'
SUPPLEMENT_SHA = 'a8587a2c8ef5a2b973b5508f09686f33b9eba662a5974b22812bf188884b9a73'
EXISTING_RECORDS_SHA = '6c4454321f97a37e129bcd7b128d7d40a4d933f6a7c0750f9f445818875f4a73'
ACCEPTED_SOURCE = '5c317f80b471d754111dbbe5a14fe97fd0dc377c'
PUBLISHED_SOURCE = '628c7a8f8c4217b5629075f63a42504c43ed70c7'
BASE_COMMIT = '18f36e91d69bf7e4f8d85fb75aa5993991738be8'
BASE_SHA = '93b33591d93a15d21b22ada1e413aea5f4befb060f6fab465707920ee6d1c71e'
CUSTODY = ROOT / 'docs/consolidated-test-1.0.7-sdr-cursor'
CUSTODY_HASHES = {
    'source-and-acceptance.json': '601125f140435690df424d65c71ec8d04ff907cd0b77ea078d1b79d2ddb417dc',
    'provenance.json': '78d040192c25cfe6e8b7046e19473450199dac800cda968515394953b79eb893',
    'assemble_test.py': '079a304f336b8b3e6cd3e4133ca194ab5564e1f8fbcdec8065fbea5a969dd06a',
    'watch-source-5c317f80.bundle': 'ffa7e09aab429e8f15496b564558c89549ee750f98b3f1c35421b7cb26c46111',
    'README.md': '2ee68da22074ad9cbcbe36d2fe1d6c309226995f0b6d6a9301d08ffa16c9121d',
}
# Already assembled immutable driver packages: no rebuild or repack is needed.
EXISTING_NEW_PACKAGES = {
    'driver-twatch-imu-0.4.1-xtensa-esp32s3.rte.zip': '069973093c2dea18e3ce51d9a916db20ffc95acaebe6a15270621b64ca7ac613',
    'driver-twatch-pmu-0.6.1-xtensa-esp32s3.rte.zip': '1e696ecb391d32bb668e1e32973f32ee5a0d021c4ef36894486f473e25ba7805',
}
NOTICE = (
    'Watch 1.0.7: exact owner-accepted SDR image, Runtime 0.1.41. '
    'INITIAL FULL 16 MiB FLASH AT 0x0: erases settings, NVS, Wi-Fi credentials, '
    'Bluetooth bonds, alarms, Points, app-data and both firmware/store banks. '
    'No preserving OTA route is published. SDR operation was reported working; '
    'sustained HID reconnect was not separately confirmed. Embedded development '
    'and physical-verification labels remain historical and unchanged.'
)


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def metadata(raw):
    return {'size_bytes': len(raw), 'sha256': pub.sha(raw)}


def zip_files(raw):
    with pub.checked_zip(raw) as z:
        require(all(not item.is_dir() for item in z.infolist()), 'Unexpected ZIP directory')
        return {name: z.read(name) for name in z.namelist()}


def read_file(path):
    pub.safe_input_path(path)
    require(path.is_file(), 'Missing input: ' + str(path))
    return path.read_bytes()


def read_tree(root):
    pub.safe_input_path(root)
    require(root.is_dir(), 'Missing input directory: ' + str(root))
    result = {}
    for path in sorted(root.rglob('*')):
        pub.safe_input_path(path)
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
        else:
            require(path.is_dir(), 'Unexpected input file type')
    return result


def verify_baseline(index, commit):
    require(commit == BASE_COMMIT, 'Unexpected release-index predecessor commit')
    require(pub.sha(serialize_index(index).encode()) == BASE_SHA,
            'Unexpected release-index predecessor bytes')
    require(index['firmware']['version'] == '1.0.3', 'Historical 1.0.3 index required')


def verify_accepted(image, current_raw, custody):
    require(len(image) == 16 * 1024 * 1024 and pub.sha(image) == IMAGE_SHA,
            'Exact accepted full 16 MiB image hash differs')
    require(pub.sha(current_raw) == EVIDENCE_SHA, 'Exact accepted-app evidence ZIP hash differs')
    require(set(custody) == set(CUSTODY_HASHES), 'Source custody inventory differs')
    for name, digest in CUSTODY_HASHES.items():
        require(pub.sha(custody[name]) == digest, 'Committed source custody changed: ' + name)
    proof = parse(custody['provenance.json'])
    require(proof['runtime_version'] == '0.1.41' and proof['watch_source'] == ACCEPTED_SOURCE,
            'Native/source identity mismatch')
    for component in proof['components']:
        offset = int(component['offset'], 16)
        raw = image[offset:offset + component['size_bytes']]
        require(metadata(raw) == {k: component[k] for k in ('size_bytes', 'sha256')},
                'Accepted native/partition component changed: ' + component['file'])
    store = read_image(image[0x2f0000:0x800000], 0x510000)
    require(len(store) == 89, 'Incomplete accepted store inventory')
    cohort = parse(store['cohort.json'])
    require(cohort['version'] == VERSION and cohort['runtime_version'] == '0.1.41' and
            cohort['source_revision'] == ACCEPTED_SOURCE and
            pub.sha(image[0x10000:0x10000 + cohort['firmware_size']]) == cohort['firmware_sha256'],
            'Embedded cohort/native identity changed')
    current = zip_files(current_raw)
    build = parse(current['current-apps-build.json'])
    require(build['watch_source'] == ACCEPTED_SOURCE and build['target_validation'] is True and
            build['configuration'] == proof['configuration'] == parse(current['source-profile.json']),
            'Accepted app build/source configuration changed')
    for name, entry in build['files'].items():
        require(name in store and metadata(store[name]) == entry,
                'App/provider does not match accepted image: ' + name)
    apps = proof['configuration']['app_versions']
    require(len(apps) == 22 and set(build['apps']) == set(apps) and
            {n[:-4] for n in store if '/' not in n and n.endswith('.elf')} == set(apps),
            'Exactly 22 accepted apps required')
    for name, version in apps.items():
        manifest = parse(store[name + '.json'])
        require(manifest['version'] == version and build['apps'][name]['version'] == version and
                '-DPORTABLE_LOW_BATTERY' in build['apps'][name]['defines'],
                'App version/configuration changed: ' + name)
    for name, raw in store.items():
        if name.endswith('.elf'):
            require(raw[:7] == b'\x7fELF\x01\x01\x01' and raw[16:20] == b'\x03\x00\x5e\x00',
                    'Invalid accepted Xtensa ELF: ' + name)
    providers = sorted(n.rsplit('/', 1)[0] for n in store if n.endswith('/manifest.json'))
    require(len(providers) == 21 and set(store) ==
            {n + ext for n in apps for ext in ('.elf', '.json')} |
            {n + '/' + ext for n in providers for ext in ('driver.elf', 'manifest.json')} |
            {'board.json', 'boot.json', 'cohort.json'}, 'Incomplete provider/store inventory')
    licenses = {n: raw for n, raw in current.items() if n.startswith('licenses/')}
    require(len(licenses) >= 40, 'Missing source licenses')
    return store, current, proof, build, providers, licenses


def verify_supplement(files):
    """A committed input augments the frozen build's own licenses.

    SOURCES.json contains files {path: {size_bytes, sha256}} and sources.
    Its files are copied verbatim and described, never inferred or generated.
    """
    require('SOURCES.json' in files, 'Supplemental license sources missing')
    require(pub.sha(files['SOURCES.json']) == SUPPLEMENT_SHA, 'Supplemental license source custody differs')
    sources = parse(files['SOURCES.json'])
    require(set(sources['files']) == set(files) - {'SOURCES.json'}, 'Supplemental license inventory differs')
    for name, item in sources['files'].items():
        require(metadata(files[name]) == {k: item[k] for k in ('size_bytes', 'sha256')} and
                isinstance(sources['sources'].get(name), str) and sources['sources'][name],
                'Supplemental license integrity/provenance differs: ' + name)


def verify_driver_package(raw, elf, source_manifest):
    files = zip_files(raw)
    manifest = parse(files['.package.json'])
    entries = manifest['entries']
    require(len({e['name'] for e in entries}) == len(entries) and
            {e['name'] for e in entries} == set(files) - {'.package.json'},
            'Driver package inventory differs')
    for entry in entries:
        require(metadata(files[entry['name']]) == {k: entry[k] for k in ('size_bytes', 'sha256')},
                'Driver package checksum differs')
    source = parse(source_manifest)
    require(files['driver.elf'] == elf and parse(files['source-manifest.json']) == source,
            'Immutable driver payload/manifest collision: ' + source['id'])
    require(manifest['id'] == source['id'] and manifest['version'] == source['version'] and
            manifest['driver_abi'] == source['driver_abi'] == 2 and
            manifest['provides'] == source['provides'] and
            manifest['requires'] == [{'capability': r['capability'], 'min_api': r['api']}
                                     for r in source['requires']], 'Driver package contract differs')
    return manifest


def driver_package(elf, manifest_raw, licenses):
    """Use existing package ABI; retain the exact deployed source manifest."""
    source = parse(manifest_raw)
    capability = source['provides'][0]
    files = {'driver.elf': elf, 'source-manifest.json': manifest_raw,
             'provider-abi.v1': (f'os-cpu-abi=1\nprovides={capability["capability"]}\n'
                                 f'api={capability["api"]}\n').encode(),
             'LICENSES.zip': licenses}
    manifest = dict(schema=1, kind='driver', id=source['id'], version=source['version'],
                    architecture=source['architecture'], artifact='driver.elf', driver_abi=2,
                    provides=source['provides'],
                    requires=[{'capability': r['capability'], 'min_api': r['api']} for r in source['requires']],
                    entries=[{'name': n, **metadata(raw), 'executable': n.endswith('.elf')}
                             for n, raw in sorted(files.items())])
    if 'hardware_compatibility' in source:
        manifest['hardware_compatibility'] = source['hardware_compatibility']
    return pub.archive({'.package.json': pub.encoded(manifest), **files})


def sources_for(proof):
    configuration = proof['configuration']
    result = copy.deepcopy(configuration['sources'])
    result['watch'] = {'repository': pub.REPOSITORY, 'commit': ACCEPTED_SOURCE,
                       'published_commit': PUBLISHED_SOURCE}
    for key in ('sdr', 'hid', 'ble_sensors', 'ble_telemetry', 'telemetry_battery'):
        result[key] = {k: configuration[key][k] for k in ('repository', 'commit')}
    return result


def derive(image, current_raw, custody, driver_inputs, baseline, source_sha,
           baseline_commit=BASE_COMMIT, supplement=None, existing_new_raw=None):
    require(isinstance(source_sha, str) and re.fullmatch('[0-9a-f]{40}', source_sha),
            'Exact release source commit required')
    verify_baseline(baseline, baseline_commit)
    store, current, proof, build, providers, licenses = verify_accepted(image, current_raw, custody)
    supplement = supplement or {}
    verify_supplement(supplement)
    require(isinstance(existing_new_raw, bytes) and pub.sha(existing_new_raw) == EXISTING_RECORDS_SHA,
            'Existing published driver record custody differs')
    existing_new = parse(existing_new_raw)
    require(set(existing_new) == {'twatch-imu', 'twatch-pmu'}, 'Existing driver release inventory differs')
    licenses.update({'supplemental/' + n: raw for n, raw in supplement.items()})
    license_zip = pub.archive(licenses)
    sources = sources_for(proof)
    source_record = {'sources': sources, 'accepted_image_sha256': IMAGE_SHA,
                     'accepted_watch_source': ACCEPTED_SOURCE, 'release_source_sha': source_sha,
                     'binary_rebuilt': False, 'scope': NOTICE}
    releases, payloads, app_records, driver_records, installed = [], {}, [], [], []
    reused = {}
    index = copy.deepcopy(baseline)

    def add(record, files, latest=False):
        files = dict(files)
        files['SHA256SUMS'] = ''.join(f'{pub.sha(raw)}  {name}\n'
                                      for name, raw in sorted(files.items())).encode()
        releases.append({'tag': record['tag'], 'source_sha': source_sha, 'latest': latest,
                         'assets': {n: {'size': len(raw), 'sha256': pub.sha(raw)}
                                    for n, raw in sorted(files.items())}})
        payloads[record['tag']] = files

    for identity, version in sorted(proof['configuration']['app_versions'].items()):
        elf, manifest_raw = store[identity + '.elf'], store[identity + '.json']
        record = pub.record('app', identity, version, identity + '.elf', elf,
                            manifest=parse(manifest_raw), source_repo=pub.REPOSITORY,
                            source_sha=source_sha, accepted_source_sha=ACCEPTED_SOURCE,
                            minimum_runtime_version='0.1.41',
                            configuration='accepted-watch-1.0.7-low-battery-bma423', build_sources=sources)
        index = update_index(index, 'apps', record)
        app_records.append(record)
        add(record, {identity + '.elf': elf, identity + '.json': manifest_raw,
                     'release-record.json': pub.encoded(record), 'LICENSES.zip': license_zip,
                     'source-provenance.json': pub.encoded(source_record)})

    previous = {r['id']: r for r in baseline['drivers']}
    packages = {}
    consumed = set()
    for directory in providers:
        elf, manifest_raw = store[directory + '/driver.elf'], store[directory + '/manifest.json']
        manifest = parse(manifest_raw)
        identity, version = manifest['id'], manifest['version']
        name = f'driver-{identity}-{version}-xtensa-esp32s3.rte.zip'
        old = previous.get(identity)
        reuse = old is not None and old['version'] == version
        published_new = existing_new.get(identity)
        if reuse or name in EXISTING_NEW_PACKAGES:
            require(name in driver_inputs, 'Missing immutable driver input: ' + name)
            raw = driver_inputs[name]
            digest = old['sha256'] if reuse else EXISTING_NEW_PACKAGES[name]
            require(pub.sha(raw) == digest, 'Immutable driver input hash differs: ' + name)
            consumed.add(name)
        else:
            raw = driver_package(elf, manifest_raw, license_zip)
        package_manifest = verify_driver_package(raw, elf, manifest_raw)
        if reuse:
            validate_record('drivers', old)
            require(old['manifest'] == package_manifest and old['size'] == len(raw),
                    'Immutable driver record collision: ' + identity)
            record = copy.deepcopy(old)
            reused[identity] = record
        elif published_new is not None:
            require(published_new['id'] == identity and published_new['version'] == version and
                    published_new['kind'] == 'driver' and published_new['architecture'] == 'xtensa-esp32s3' and
                    published_new['archive'] == name and published_new['size_bytes'] == len(raw) and
                    published_new['sha256'] == pub.sha(raw) and
                    published_new['tag'] == f'driver-{identity}-v{version}' and
                    re.fullmatch('[0-9a-f]{40}', published_new['source_sha']),
                    'Existing published driver identity/package differs')
            record = pub.record('driver', identity, version, name, raw,
                                format='rte.zip', architecture='xtensa-esp32s3',
                                manifest=package_manifest, source_repo=pub.REPOSITORY,
                                source_sha=published_new['source_sha'], included_in_accepted_bin=True)
            reused[identity] = record
            reuse = True
        else:
            record = pub.record('driver', identity, version, name, raw,
                                format='rte.zip', architecture='xtensa-esp32s3',
                                manifest=package_manifest, source_repo=pub.REPOSITORY,
                                source_sha=source_sha, accepted_source_sha=ACCEPTED_SOURCE,
                                included_in_accepted_bin=True, build_sources=sources)
            add(record, {name: raw, 'accepted-manifest.json': manifest_raw,
                         'release-record.json': pub.encoded(record), 'LICENSES.zip': license_zip,
                         'source-provenance.json': pub.encoded(source_record)})
        index = update_index(index, 'drivers', record)
        packages[name] = raw
        driver_records.append(record)
        installed.append({'id': identity, 'version': version, 'directory': directory,
                          'elf': metadata(elf), 'accepted_manifest': metadata(manifest_raw),
                          'package': {'asset': name, **metadata(raw)}, 'reused_release': reuse,
                          'package_manifest_byte_identical': zip_files(raw)['source-manifest.json'] == manifest_raw,
                          'package_manifest_semantically_equal': True})
    require(consumed == set(driver_inputs), 'Unexpected immutable driver inputs')
    firmware = pub.record('firmware', '', VERSION, ASSET, image, source_sha=source_sha,
                          accepted_source_sha=ACCEPTED_SOURCE,
                          component_versions={**proof['configuration']['app_versions'], 'runtime': '0.1.41'},
                          flash_offset='0x0', full_initial_image=True, erases_all_saved_data=True,
                          hardware_acceptance_scope='Owner reported SDR works; sustained HID reconnect not separately confirmed.')
    index = update_index(index, 'firmware', firmware)
    require('ota' not in firmware, 'Unproven OTA route must not be published')
    inventory = {n: metadata(raw) for n, raw in sorted(store.items())}
    provenance = {**source_record, 'accepted_build': proof,
                  'source_and_acceptance': parse(custody['source-and-acceptance.json']),
                  'store_inventory': inventory, 'installed_providers': installed,
                  'accepted_app_evidence_zip': metadata(current_raw),
                  'original_current_apps_zip_sha256': CURRENT_SHA,
                  'license_inventory': {n: metadata(raw) for n, raw in sorted(licenses.items())},
                  'historical_firmware_preserved': baseline['firmware'],
                  'baseline_index_commit': baseline_commit,
                  'baseline_index_sha256': BASE_SHA}
    flashing = ('# Watch 1.0.7\n\n' + NOTICE + '\n\n'
                'Original/non-Plus LILYGO T-Watch-S3; BMA423 motion model.\n\n'
                f'Image: {ASSET}\nSize: 16,777,216 bytes\nSHA-256: {IMAGE_SHA}\n\n'
                'After backing up and selecting your own device:\n\n'
                f'python -m esptool --chip esp32s3 --port PORT --baud 460800 write_flash 0x0 {ASSET}\n\n'
                'Independent apps and providers retain their accepted versions, ELF bytes and manifests. '
                'Install this complete initial image before using its independent app updates. '
                'The minimum_runtime_version field documents this requirement; historical clients '
                'do not enforce it. No compatibility claim is made for older installed cohorts. '
                'The accepted-store archive retains the complete board, grants, boot and cohort configuration. '
                'Downloading individual packages does not install them or validate another configuration. '
                'Previously published driver ZIPs retain their original serialization and provenance; '
                'their ELF bytes and manifest semantics match this image, whose exact manifest bytes '
                'are retained in accepted-store.zip.\n').encode()
    add(firmware, {ASSET: image, 'accepted-app-evidence.zip': current_raw,
                   'accepted-store.zip': pub.archive(store), 'provider-packages.zip': pub.archive(packages),
                   'source-custody.zip': pub.archive(custody), 'LICENSES.zip': license_zip,
                   'existing-driver-releases.json': existing_new_raw,
                   'release-record.json': pub.encoded(firmware), 'product-provenance.json': pub.encoded(provenance),
                   'release-index.json': serialize_index(index).encode(), 'FLASHING.md': flashing}, True)
    plan = {'schema': 1, 'repository': pub.REPOSITORY, 'source_sha': source_sha,
            'product': {'version': VERSION, 'tag': TAG, 'accepted_bin_sha256': IMAGE_SHA,
                        'reused_driver_records': reused, 'sources': {'watch': {'accepted_sha': PUBLISHED_SOURCE}}},
            'baseline_index_commit': baseline_commit, 'baseline_index_sha256': BASE_SHA,
            'baseline_index': baseline, 'index': index, 'releases': releases,
            'app_records': app_records, 'driver_records': driver_records,
            'store_inventory': inventory, 'installed_providers': installed,
            'initial_only': True, 'notice': NOTICE}
    return plan, payloads


def verify_predecessor(plan, parent, current):
    verify_baseline(plan['baseline_index'], plan['baseline_index_commit'])
    require(parent == plan['baseline_index_commit'] and current == plan['baseline_index'],
            'Live index predecessor changed; no publication is allowed')
    require(pub.merged_index(current, plan['index']) == plan['index'], 'Unexpected index mutation')


def stage(image_path, acceptance_path, baseline_path, evidence_path, driver_inputs_path,
          output, source_sha, supplement_directory=None, existing_drivers_path=None):
    pub.safe_input_path(output)
    require(not output.exists() or not any(output.iterdir()), 'Refusing to replace existing staged release')
    image = read_file(image_path)
    if image_path.suffix == '.gz':
        # Read a bounded stream; a gzip bomb cannot allocate unbounded memory.
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(image)) as stream:
            image = stream.read(16 * 1024 * 1024 + 1)
            require(len(image) == 16 * 1024 * 1024 and not stream.read(1), 'Invalid compressed image size')
    current = read_file(evidence_path)
    custody = {n: read_file(CUSTODY / n) for n in CUSTODY_HASHES}
    require(read_file(acceptance_path) == custody['provenance.json'], 'Acceptance input differs from fixed custody')
    store, _, _, _, providers, _ = verify_accepted(image, current, custody)
    baseline = parse(read_file(baseline_path))
    verify_baseline(baseline, BASE_COMMIT)
    previous = {r['id']: r for r in baseline['drivers']}
    supplied = zip_files(read_file(driver_inputs_path)) if driver_inputs_path.is_file() else None
    driver_inputs = {}
    for directory in providers:
        manifest = parse(store[directory + '/manifest.json'])
        old = previous.get(manifest['id'])
        name = f'driver-{manifest["id"]}-{manifest["version"]}-xtensa-esp32s3.rte.zip'
        if (old and old['version'] == manifest['version']) or name in EXISTING_NEW_PACKAGES:
            require(supplied is None or name in supplied, 'Missing immutable driver input: ' + name)
            driver_inputs[name] = supplied[name] if supplied is not None else read_file(driver_inputs_path / name)
    require(supplied is None or set(supplied) == set(driver_inputs), 'Unexpected immutable driver inputs')
    supplement = read_tree(supplement_directory) if supplement_directory else {}
    plan, payloads = derive(image, current, custody, driver_inputs, baseline, source_sha,
                            supplement=supplement, existing_new_raw=read_file(existing_drivers_path))
    pub.verify_watch_ancestry(PUBLISHED_SOURCE, source_sha)
    output.mkdir(parents=True, exist_ok=True)
    for tag, files in payloads.items():
        directory = output / tag
        directory.mkdir()
        for name, raw in files.items():
            (directory / name).write_bytes(raw)
    (output / 'immutable-driver-inputs.zip').write_bytes(pub.archive(driver_inputs))
    (output / 'supplemental-licenses.zip').write_bytes(pub.archive(supplement))
    (output / 'baseline-index.json').write_bytes(serialize_index(baseline).encode())
    (output / 'publication-plan.json').write_bytes(pub.encoded(plan))
    verify_stage(output)
    return plan


def verify_stage(output):
    """Regenerate every expected record and asset from fixed accepted inputs."""
    plan = parse(read_file(output / 'publication-plan.json'))
    firmware = output / TAG
    baseline = parse(read_file(output / 'baseline-index.json'))
    expected, payloads = derive(read_file(firmware / ASSET), read_file(firmware / 'accepted-app-evidence.zip'),
                                zip_files(read_file(firmware / 'source-custody.zip')),
                                zip_files(read_file(output / 'immutable-driver-inputs.zip')),
                                baseline, plan['source_sha'], plan['baseline_index_commit'],
                                zip_files(read_file(output / 'supplemental-licenses.zip')),
                                read_file(firmware / 'existing-driver-releases.json'))
    require(plan == expected, 'Publication plan differs from accepted bytes')
    require({p.name for p in output.iterdir()} == set(payloads) |
            {'publication-plan.json', 'baseline-index.json', 'immutable-driver-inputs.zip',
             'supplemental-licenses.zip'}, 'Unexpected staged inventory')
    for tag, files in payloads.items():
        require(read_tree(output / tag) == files, 'Staged release assets changed: ' + tag)
    verify_predecessor(plan, plan['baseline_index_commit'], baseline)
    return plan


def preflight(output):
    """Read-only whole-plan gate; stale predecessors fail before remote writes."""
    plan = verify_stage(output)
    pub.verify_watch_ancestry(PUBLISHED_SOURCE, plan['source_sha'])
    verify_predecessor(plan, *pub.current_release_index())
    # Reused records retain their historical release source and inventory.
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'driver-assets').mkdir()
        packages = zip_files(read_file(output / TAG / 'provider-packages.zip'))
        for record in plan['product']['reused_driver_records'].values():
            (root / 'driver-assets' / record['asset']).write_bytes(packages[record['asset']])
        pub.verify_driver_releases({'driver_records': list(plan['product']['reused_driver_records'].values())}, root)
    originals = parse(read_file(output / TAG / 'existing-driver-releases.json'))
    for original in originals.values():
        release = pub.release_by_tag(original['tag'])
        require(release is not None, 'Existing driver release disappeared')
        records = [asset for asset in release['assets'] if asset['name'] == 'release-record.json']
        require(len(records) == 1, 'Existing driver release record missing or duplicated')
        raw = pub.gh('api', f'repos/{pub.REPOSITORY}/releases/assets/{records[0]["id"]}',
                     '-H', 'Accept: application/octet-stream')
        require(raw == pub.encoded(original), 'Existing driver release record bytes changed')
    pub.release_preflight(plan['releases'], output)
    verify_predecessor(plan, *pub.current_release_index())
    return plan


def publish(output):
    require(not pub.command('git', 'status', '--porcelain', '--untracked-files=no').strip(),
            'Release source checkout dirty')
    source = pub.command('git', 'rev-parse', 'HEAD').decode().strip()
    require(os.environ.get('GITHUB_REPOSITORY') == pub.REPOSITORY and
            os.environ.get('GITHUB_EVENT_NAME') in ('push', 'workflow_dispatch'),
            'Publication requires the authorized repository workflow')
    repository = pub.api('repos/' + pub.REPOSITORY)
    branch = repository['default_branch']
    require(os.environ.get('GITHUB_REF') == 'refs/heads/' + branch and
            pub.api(f'repos/{pub.REPOSITORY}/commits/{branch}')['sha'] == source,
            'Publication requires exact current default-branch source')
    plan = preflight(output)
    require(plan['source_sha'] == source, 'Stage belongs to another release commit')
    # Last read immediately before the first external mutation.
    verify_predecessor(plan, *pub.current_release_index())
    for release in plan['releases']:
        pub.publish_one(release, output, title=('Watch ' + VERSION if release['latest'] else release['tag']),
                        notes=NOTICE + '\n\nExact accepted component bytes. See LICENSES.zip and source provenance.')
    pub.publish_index(plan['index'], expected_parent=plan['baseline_index_commit'],
                      expected_current=plan['baseline_index'])
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'verify', 'preflight', 'publish'))
    inputs = ROOT / 'release/complete-1.0.7'
    parser.add_argument('--image', type=Path, default=inputs / 'accepted.bin.gz')
    parser.add_argument('--acceptance', type=Path, default=inputs / 'acceptance.json')
    parser.add_argument('--app-evidence', type=Path, default=inputs / 'accepted-app-evidence.zip')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/complete-watch-release/staged')
    parser.add_argument('--index', type=Path, default=inputs / 'predecessor-index.json')
    parser.add_argument('--source-sha')
    parser.add_argument('--driver-inputs', type=Path, default=inputs / 'immutable-driver-inputs.zip')
    parser.add_argument('--supplemental-licenses', type=Path, default=inputs / 'licenses/supplemental')
    parser.add_argument('--existing-drivers', type=Path, default=inputs / 'existing-new-driver-records.json')
    args = parser.parse_args()
    if args.action == 'stage':
        source = args.source_sha or pub.command('git', 'rev-parse', 'HEAD').decode().strip()
        plan = stage(args.image, args.acceptance, args.index, args.app_evidence,
                     args.driver_inputs, args.output, source, args.supplemental_licenses,
                     args.existing_drivers)
    elif args.action == 'verify':
        plan = verify_stage(args.output)
    elif args.action == 'preflight':
        plan = preflight(args.output)
    else:
        plan = publish(args.output)
    print(f'Verified Watch {VERSION}: 22 apps, 21 providers, {len(plan["releases"])} releases; exact initial image, no OTA')


if __name__ == '__main__':
    main()

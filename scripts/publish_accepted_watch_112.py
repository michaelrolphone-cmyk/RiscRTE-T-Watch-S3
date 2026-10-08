#!/usr/bin/env python3
"""Publish byte-exact accepted Watch 1.0.12; never rebuild or flash a device.

This is a separate lane from the frozen 1.0.7 publisher. The paired payload is
historical evidence only; this lane publishes an initial image with no OTA route.
"""
import argparse
import copy
import gzip
import io
import os
from pathlib import Path
import re
import tempfile

import publish_complete_watch as common
import publish_watch_product as pub
import reconstruct_watch_112_sources as reconstruction
from read_only_spiffs import read_image
from watch_release_index import require, serialize_index, update_index, validate_record

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / 'release/complete-1.0.12'
VERSION = '1.0.12'
RUNTIME = '0.1.55'
TAG = 'firmware-v' + VERSION
ASSET = 'twatch-s3-launcher-' + VERSION + '.bin'
ORIGINAL_IMAGE = 'twatch-s3-1.0.12-FULL-INITIAL-ERASES-DATA-bma423.bin'
IMAGE_SHA = 'af958e480a3183bde3f448e97930d56b9aeea567a664428892b917a878d014ff'
PAIRED_SHA = '9fdfaed08238524baec6524fe8915e03f9f5b0c8011f9c5b0027dc530629c2f4'
ACCEPTED_SOURCE = 'f3f8755619e94d0078ef16d43d9c6039bee46b8d'
PUBLISHED_SOURCE = 'c2b340a6bce466a24dea8eea5d09213e7f2298d9'
BASE_COMMIT = '4d6237bd5b06fe88ee41e8e754f37ef1b7aea709'
BASE_SHA = '898adb71b8038d93b6f6cd64883cc86f2e9644ce3331a44c9e651cdfd65e231b'
# Hashes of logical accepted inputs, independent of staged metadata. The original
# reconstruction ZIP is restored from the pinned, bounded Git transport parts.
INPUT_HASHES = {
    "LICENSES.zip": "02afaf55a27ae12b30e9f088b7cb3aeceff30a6fb21a275047f487cd128799e8",
    "REPRODUCING.md": "fb4952425339b8400848610c3994e47f695cf70e677354d7284422091a686e96",
    "accepted-app-evidence.zip": "dcb8e18d1bb3ba69c8533a72593b8564e5f4028fe6dcb675536cb8fd835b07b6",
    "accepted.bin.gz": "cf6e157c1ab39e15c3ab890ee84f2b2e103813bdfe4668bb4fc2b60a93db4f6a",
    "existing-new-driver-records.json": "0feaddd0af559c23140f4419bb94db44b03103f70f8ae4de534e6971a7549fd4",
    "immutable-driver-inputs.zip": "caff222ea369a8db7505c5628f47482a9d22d69846e0b8b1aa3631702c1c39c1",
    "installed-app-admission-source.zip": "761272fc900a2125eea9648f39b9677b348f764621e86e9461c2074d8f151b8d",
    "owner-acceptance.json": "f59981d2ee182c7d4fb4ed5f3149d2a826fe31aae4d6f87139b5378e4857371d",
    "predecessor-commit.txt": "c98dfe08712906d52f0eab1612967aeaddda67a32309eec6fef5613783592422",
    "predecessor-index.json": "898adb71b8038d93b6f6cd64883cc86f2e9644ce3331a44c9e651cdfd65e231b",
    "reconstruct_watch_112_sources.py": "f663608cf4c20b21d0c0adb00f0a7cee3c1b383c82b68162ab9b6719e82077b6",
    "reconstruction-inputs.zip": "a65b56c15461807c197c7dbbc8b0eb585a9d1a242f5063f96f011c6829670be3",
    "reconstruction-proof.json": "c67caa54f477eb1f5f0da7f1417608d0496d2651ee9bfb05a0e94703d3793a4b",
    "source-custody.zip": "73f36c7057dbe71525518fe5e80aa018a4ee03621f618fcf9c38aaef50c441d8"
}
NOTICE = (
    'Watch 1.0.12: exact owner-accepted image, Runtime 0.1.55, 22 apps and 22 providers. '
    'INITIAL FULL 16 MiB FLASH AT 0x0: erases settings, NVS, Wi-Fi credentials, '
    'Bluetooth bonds, alarms, Points, app-data and both firmware/store banks. '
    'No preserving OTA route or paired update payload is published. '
    'The owner reported the delivered build stable and reliable; this is not a claim '
    'that every peripheral or physical behavior was separately tested. Historical '
    'development and physical-verification labels remain unchanged inside the image and proofs.'
)
parse = common.parse
metadata = common.metadata
zip_files = common.zip_files
read_file = common.read_file
read_tree = common.read_tree


def load_inputs():
    return {name: reconstruction.build_inputs_bytes(
                tuple(INPUTS / part for part in reconstruction.BUILD_INPUT_PART_NAMES))
            if name == 'reconstruction-inputs.zip' else read_file(INPUTS / name)
            for name in INPUT_HASHES}


def verify_inputs(inputs):
    require(set(inputs) == set(INPUT_HASHES), 'Accepted input inventory differs')
    for name, digest in INPUT_HASHES.items():
        require(pub.sha(inputs[name]) == digest, 'Accepted input changed: ' + name)
    with gzip.GzipFile(fileobj=io.BytesIO(inputs['accepted.bin.gz'])) as stream:
        image = stream.read(16 * 1024 * 1024 + 1)
        require(len(image) == 16 * 1024 * 1024 and not stream.read(1), 'Invalid compressed image size')
    require(pub.sha(image) == IMAGE_SHA, 'Exact accepted full image hash differs')
    custody = zip_files(inputs['source-custody.zip'])
    mapping = parse(custody['source-equivalence.json'])
    require(mapping['built_watch_commit'] == ACCEPTED_SOURCE and mapping['full_image_sha256'] == IMAGE_SHA,
            'Accepted source equivalence differs')
    require(len(mapping['sources']) == 5, 'Five original source bundles required')
    for source in mapping['sources']:
        require(pub.sha(custody[source['bundle_file']]) == source['bundle_sha256'], 'Original source bundle changed')
    proof = parse(custody['proof/runtime-features-watch-build-proof.json'])
    require(proof['watch_source'] == ACCEPTED_SOURCE and proof['native_custody']['firmware_version'] == RUNTIME,
            'Accepted native/source identity differs')
    require(proof['initial']['sha256'] == IMAGE_SHA and proof['initial']['asset'] == ORIGINAL_IMAGE,
            'Accepted initial image identity differs')
    require(proof['ota']['sha256'] == PAIRED_SHA and proof['published'] is False,
            'Historical paired payload status differs')
    for component in proof['initial']['components']:
        offset = int(component['offset'], 16)
        raw = image[offset:offset + component['size_bytes']]
        require(metadata(raw) == {k: component[k] for k in ('size_bytes', 'sha256')},
                'Accepted native/partition component changed: ' + component['file'])
    store = read_image(image[0x2f0000:0x800000], 0x510000)
    cohort = parse(store['cohort.json'])
    require(cohort == proof['target_cohort'] and cohort['version'] == VERSION and
            cohort['runtime_version'] == RUNTIME and cohort['source_revision'] == ACCEPTED_SOURCE,
            'Embedded cohort identity differs')
    require(pub.sha(image[0x10000:0x10000 + cohort['firmware_size']]) == cohort['firmware_sha256'],
            'Embedded native firmware differs')
    require({name: metadata(raw) for name, raw in store.items()} == proof['files'],
            'Full accepted store inventory differs')
    evidence = zip_files(inputs['accepted-app-evidence.zip'])
    require(metadata(inputs['accepted-app-evidence.zip']) == proof['app_archive'], 'Accepted app archive differs')
    build = parse(evidence['current-apps-build.json'])
    require(build['watch_source'] == ACCEPTED_SOURCE and build['target_validation'] is True and
            build['configuration'] == proof['configuration'] == parse(evidence['source-profile.json']),
            'Accepted app build/source configuration differs')
    for name, entry in build['files'].items():
        require(name in store and metadata(store[name]) == entry and evidence['files/' + name] == store[name],
                'App/provider does not match accepted image: ' + name)
    apps = proof['configuration']['app_versions']
    providers = sorted(n.rsplit('/', 1)[0] for n in store if n.endswith('/manifest.json'))
    require(len(apps) == 22 and len(providers) == 22 and set(build['apps']) == set(apps),
            'Exactly 22 accepted apps and 22 providers required')
    require(set(store) == {n + ext for n in apps for ext in ('.elf', '.json')} |
            {n + '/' + ext for n in providers for ext in ('driver.elf', 'manifest.json')} |
            {'board.json', 'boot.json', 'cohort.json'}, 'Incomplete accepted store inventory')
    for name, version in apps.items():
        require(parse(store[name + '.json'])['version'] == version and build['apps'][name]['version'] == version,
                'Accepted app version differs: ' + name)
    for name, raw in store.items():
        if name.endswith('.elf'):
            require(raw[:7] == b'\x7fELF\x01\x01\x01' and raw[16:20] == b'\x03\x00\x5e\x00',
                    'Invalid accepted Xtensa ELF: ' + name)
    require(inputs['LICENSES.zip'] == custody['proof/LICENSES.zip'], 'Original license archive differs')
    reproduced = parse(inputs['reconstruction-proof.json'])
    require(reproduced['byte_identical'] is True and reproduced['native_rebuilt'] is True and
            reproduced['app_and_provider_sources_rebuilt'] is True and
            reproduced['built_image_sha256'] == reproduced['accepted_image_sha256'] == IMAGE_SHA,
            'Original source reconstruction proof differs')
    licenses = zip_files(inputs['LICENSES.zip'])
    require(all(licenses.get(n) == raw for n, raw in evidence.items() if n.startswith('licenses/')),
            'Accepted app license inventory differs')
    return image, store, proof, build, providers, mapping


def verify_baseline(index, commit):
    require(commit == BASE_COMMIT, 'Unexpected release-index predecessor commit')
    require(pub.sha(serialize_index(index).encode()) == BASE_SHA, 'Unexpected release-index predecessor bytes')
    require(index['firmware']['version'] == '1.0.7', 'Historical 1.0.7 predecessor required')


def sources_for(proof, mapping):
    sources = copy.deepcopy(proof['configuration']['sources'])
    sources['watch'] = {'repository': pub.REPOSITORY, 'commit': ACCEPTED_SOURCE}
    for key in ('sdr', 'hid', 'ble_sensors', 'ble_telemetry', 'telemetry_battery'):
        sources[key] = {k: proof['configuration'][key][k] for k in ('repository', 'commit')}
    by_repo = {row['repository']: row for row in mapping['sources']}
    for source in sources.values():
        equivalent = by_repo.get(source['repository'])
        if equivalent:
            require(source['commit'] == equivalent['built_commit'], 'Original source pin differs')
            source.update(public_tree_equivalent_commit=equivalent['public_tree_equivalent_commit'],
                          original_bundle=equivalent['bundle_file'], tree=equivalent['tree'])
    return sources


def derive(inputs, source_sha):
    require(isinstance(source_sha, str) and re.fullmatch('[0-9a-f]{40}', source_sha),
            'Exact release source commit required')
    image, store, proof, build, providers, mapping = verify_inputs(inputs)
    baseline = parse(inputs['predecessor-index.json'])
    verify_baseline(baseline, inputs['predecessor-commit.txt'].decode().strip())
    driver_inputs = zip_files(inputs['immutable-driver-inputs.zip'])
    existing_new = parse(inputs['existing-new-driver-records.json'])
    sources = sources_for(proof, mapping)
    source_record = {'sources': sources, 'accepted_image_sha256': IMAGE_SHA,
                     'accepted_watch_source': ACCEPTED_SOURCE, 'release_source_sha': source_sha,
                     'binary_rebuilt': False, 'scope': NOTICE}
    releases, payloads, app_records, driver_records, installed = [], {}, [], [], []
    reused, packages, consumed = {}, {}, set()
    index = copy.deepcopy(baseline)
    license_zip = inputs['LICENSES.zip']

    def add(record, files, latest=False):
        files = dict(files)
        files['SHA256SUMS'] = ''.join(f'{pub.sha(raw)}  {name}\n' for name, raw in sorted(files.items())).encode()
        releases.append({'tag': record['tag'], 'source_sha': source_sha, 'latest': latest,
                         'assets': {n: {'size': len(raw), 'sha256': pub.sha(raw)} for n, raw in sorted(files.items())}})
        payloads[record['tag']] = files

    for identity, version in sorted(proof['configuration']['app_versions'].items()):
        elf, manifest = store[identity + '.elf'], store[identity + '.json']
        record = pub.record('app', identity, version, identity + '.elf', elf,
                            manifest=parse(manifest), source_repo=pub.REPOSITORY,
                            source_sha=source_sha, accepted_source_sha=ACCEPTED_SOURCE,
                            minimum_runtime_version=RUNTIME, minimum_watch_cohort=VERSION,
                            configuration='accepted-watch-1.0.12-runtime-features-bma423', build_sources=sources)
        index = update_index(index, 'apps', record)
        app_records.append(record)
        add(record, {identity + '.elf': elf, identity + '.json': manifest,
                     'release-record.json': pub.encoded(record), 'LICENSES.zip': license_zip,
                     'source-provenance.json': pub.encoded(source_record)})

    previous = {r['id']: r for r in baseline['drivers']}
    for directory in providers:
        elf, manifest_raw = store[directory + '/driver.elf'], store[directory + '/manifest.json']
        manifest = parse(manifest_raw)
        identity, version = manifest['id'], manifest['version']
        name = f'driver-{identity}-{version}-xtensa-esp32s3.rte.zip'
        old, original = previous.get(identity), existing_new.get(identity)
        reuse = old is not None and old['version'] == version
        if reuse or original is not None:
            require(name in driver_inputs, 'Missing immutable driver input: ' + name)
            raw = driver_inputs[name]
            consumed.add(name)
            require(pub.sha(raw) == (old['sha256'] if reuse else original['sha256']),
                    'Immutable driver input hash differs: ' + name)
        else:
            raw = common.driver_package(elf, manifest_raw, license_zip)
        package_manifest = common.verify_driver_package(raw, elf, manifest_raw)
        if reuse:
            validate_record('drivers', old)
            require(old['manifest'] == package_manifest and old['size'] == len(raw),
                    'Immutable driver record collision: ' + identity)
            record = copy.deepcopy(old)
        elif original is not None:
            require(original['id'] == identity and original['version'] == version and
                    original['kind'] == 'driver' and original['architecture'] == 'xtensa-esp32s3' and
                    original['archive'] == name and original['size_bytes'] == len(raw) and
                    original['tag'] == f'driver-{identity}-v{version}' and
                    re.fullmatch('[0-9a-f]{40}', original['source_sha']), 'Published driver identity differs')
            record = pub.record('driver', identity, version, name, raw, format='rte.zip',
                                architecture='xtensa-esp32s3', manifest=package_manifest,
                                source_repo=pub.REPOSITORY, source_sha=original['source_sha'], included_in_accepted_bin=True)
            reuse = True
        else:
            record = pub.record('driver', identity, version, name, raw, format='rte.zip',
                                architecture='xtensa-esp32s3', manifest=package_manifest,
                                source_repo=pub.REPOSITORY, source_sha=source_sha,
                                accepted_source_sha=ACCEPTED_SOURCE, included_in_accepted_bin=True, build_sources=sources)
            add(record, {name: raw, 'accepted-manifest.json': manifest_raw,
                         'release-record.json': pub.encoded(record), 'LICENSES.zip': license_zip,
                         'source-provenance.json': pub.encoded(source_record)})
        if reuse:
            reused[identity] = record
        index = update_index(index, 'drivers', record)
        packages[name] = raw
        driver_records.append(record)
        installed.append({'id': identity, 'version': version, 'directory': directory,
                          'elf': metadata(elf), 'accepted_manifest': metadata(manifest_raw),
                          'package': {'asset': name, **metadata(raw)}, 'reused_release': reuse,
                          'package_manifest_byte_identical': zip_files(raw)['source-manifest.json'] == manifest_raw,
                          'package_manifest_semantically_equal': True})
    require(consumed == set(driver_inputs), 'Unexpected immutable driver inputs')
    require(set(existing_new) <= set(reused), 'Unexpected published driver records')
    firmware = pub.record('firmware', '', VERSION, ASSET, image, source_sha=source_sha,
                          accepted_source_sha=ACCEPTED_SOURCE, original_image_asset=ORIGINAL_IMAGE,
                          component_versions={**proof['configuration']['app_versions'], 'runtime': RUNTIME},
                          flash_offset='0x0', full_initial_image=True, erases_all_saved_data=True,
                          hardware_acceptance_scope='Owner reported the delivered build stable and reliable.')
    index = update_index(index, 'firmware', firmware)
    require('ota' not in firmware, 'Paired updater route must remain separate')
    inventory = {name: metadata(raw) for name, raw in sorted(store.items())}
    provenance = {**source_record, 'accepted_build': proof, 'source_equivalence': mapping,
                  'owner_acceptance': parse(inputs['owner-acceptance.json']),
                  'store_inventory': inventory, 'installed_providers': installed,
                  'paired_payload': {'sha256': PAIRED_SHA, 'published': False, 'catalog_route_published': False},
                  'historical_firmware_preserved': baseline['firmware'],
                  'baseline_index_commit': BASE_COMMIT, 'baseline_index_sha256': BASE_SHA}
    flashing = ('# Watch 1.0.12\n\n' + NOTICE + '\n\n'
                'Original/non-Plus LILYGO T-Watch-S3; BMA423 motion model.\n\n'
                f'Image: {ASSET}\nSize: 16,777,216 bytes\nSHA-256: {IMAGE_SHA}\n\n'
                f'This asset is a byte-exact filename alias of {ORIGINAL_IMAGE}.\n\n'
                'After backing up and selecting your own device:\n\n'
                f'python -m esptool --chip esp32s3 --port PORT --baud 460800 write_flash 0x0 {ASSET}\n\n'
                'Independent apps and providers retain their accepted versions and ELF bytes. '
                'Install this complete initial image before its independent app updates. '
                'Historical clients do not enforce minimum Runtime/cohort metadata. '
                'No compatibility claim is made for older cohorts. accepted-store.zip retains '
                'all deployed manifest, board, grant, boot and cohort bytes. Reused provider ZIPs '
                'retain their original serialization and provenance; ELF bytes and manifest semantics '
                'match the image. See REPRODUCING.md for the bundled original source commits.\n').encode()
    add(firmware, {ASSET: image, 'accepted-store.zip': pub.archive(store),
                   'accepted-app-evidence.zip': inputs['accepted-app-evidence.zip'],
                   'source-custody.zip': inputs['source-custody.zip'], 'LICENSES.zip': license_zip,
                   'reconstruction-inputs.zip': inputs['reconstruction-inputs.zip'],
                   'reconstruction-proof.json': inputs['reconstruction-proof.json'],
                   'installed-app-admission-source.zip': inputs['installed-app-admission-source.zip'],
                   'provider-packages.zip': pub.archive(packages),
                   'existing-driver-releases.json': inputs['existing-new-driver-records.json'],
                   'release-record.json': pub.encoded(firmware), 'product-provenance.json': pub.encoded(provenance),
                   'release-index.json': serialize_index(index).encode(), 'FLASHING.md': flashing,
                   'REPRODUCING.md': inputs['REPRODUCING.md'],
                   'reconstruct_watch_112_sources.py': inputs['reconstruct_watch_112_sources.py']}, True)
    plan = {'schema': 1, 'repository': pub.REPOSITORY, 'source_sha': source_sha,
            'product': {'version': VERSION, 'tag': TAG, 'accepted_bin_sha256': IMAGE_SHA,
                        'reused_driver_records': reused, 'sources': {'watch': {'accepted_sha': PUBLISHED_SOURCE}}},
            'baseline_index_commit': BASE_COMMIT, 'baseline_index_sha256': BASE_SHA,
            'baseline_index': baseline, 'index': index, 'releases': releases,
            'app_records': app_records, 'driver_records': driver_records,
            'store_inventory': inventory, 'installed_providers': installed,
            'initial_only': True, 'paired_payload_published': False, 'notice': NOTICE}
    return plan, payloads


def verify_predecessor(plan, parent, current):
    verify_baseline(plan['baseline_index'], plan['baseline_index_commit'])
    # A repeat of this exact completed plan is a read-only success. Every release
    # is still independently checked; an unrelated or partial index is rejected.
    require((parent == BASE_COMMIT and current == plan['baseline_index']) or current == plan['index'],
            'Live index predecessor changed; no publication is allowed')
    require(pub.merged_index(current, plan['index']) == plan['index'], 'Unexpected index mutation')


def stage(output, source_sha):
    pub.safe_input_path(output)
    require(not output.exists() or not any(output.iterdir()), 'Refusing to replace existing staged release')
    inputs = load_inputs()
    plan, payloads = derive(inputs, source_sha)
    pub.verify_watch_ancestry(PUBLISHED_SOURCE, source_sha)
    output.mkdir(parents=True, exist_ok=True)
    for tag, files in payloads.items():
        directory = output / tag
        directory.mkdir()
        for name, raw in files.items():
            (directory / name).write_bytes(raw)
    (output / 'accepted-inputs.zip').write_bytes(pub.archive(inputs))
    (output / 'publication-plan.json').write_bytes(pub.encoded(plan))
    return verify_stage(output)


def verify_stage(output):
    plan = parse(read_file(output / 'publication-plan.json'))
    inputs = zip_files(read_file(output / 'accepted-inputs.zip'))
    expected, payloads = derive(inputs, plan['source_sha'])
    require(plan == expected, 'Publication plan differs from accepted bytes')
    require({p.name for p in output.iterdir()} == set(payloads) | {'publication-plan.json', 'accepted-inputs.zip'},
            'Unexpected staged inventory')
    for tag, files in payloads.items():
        require(read_tree(output / tag) == files, 'Staged release assets changed: ' + tag)
    return plan


def verify_reused_releases(plan, output):
    """Both legacy two-asset drivers and complete-1.0.7 releases are immutable.

    The complete-product publisher uses richer records and six assets. Reusing
    its packages must not force them through the standalone driver schema.
    """
    records = plan['product']['reused_driver_records']
    standalone = [r for r in records.values() if 'accepted_source_sha' not in r]
    product = [r for r in records.values() if 'accepted_source_sha' in r]
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'driver-assets').mkdir()
        packages = zip_files(read_file(output / TAG / 'provider-packages.zip'))
        for record in standalone:
            (root / 'driver-assets' / record['asset']).write_bytes(packages[record['asset']])
        pub.verify_driver_releases({'driver_records': standalone}, root)
        # Regenerate the frozen publisher's exact assets at their historical
        # release source. This reuses its fixed custody validation, not its CLI.
        frozen = ROOT / 'release/complete-1.0.7'
        for source in sorted({r['source_sha'] for r in product}):
            prior_plan, prior_payloads = common.derive(
                gzip.decompress(read_file(frozen / 'accepted.bin.gz')),
                read_file(frozen / 'accepted-app-evidence.zip'),
                {n: read_file(common.CUSTODY / n) for n in common.CUSTODY_HASHES},
                zip_files(read_file(frozen / 'immutable-driver-inputs.zip')),
                parse(read_file(frozen / 'predecessor-index.json')), source,
                supplement=read_tree(frozen / 'licenses/supplemental'),
                existing_new_raw=read_file(frozen / 'existing-new-driver-records.json'))
            old_records = {r['id']: r for r in prior_plan['driver_records']}
            tags = set()
            for record in product:
                if record['source_sha'] != source:
                    continue
                require(old_records.get(record['id']) == record, 'Frozen provider release record changed')
                tag = record['tag']
                require(tag in prior_payloads, 'Missing frozen provider release')
                live = pub.release_by_tag(tag)
                require(live is not None and not live['draft'], 'Frozen provider release is not published')
                folder = root / tag
                folder.mkdir()
                for name, raw in prior_payloads[tag].items():
                    (folder / name).write_bytes(raw)
                tags.add(tag)
            pub.release_preflight([r for r in prior_plan['releases'] if r['tag'] in tags], root)


def preflight(output):
    plan = verify_stage(output)
    pub.verify_watch_ancestry(PUBLISHED_SOURCE, plan['source_sha'])
    verify_predecessor(plan, *pub.current_release_index())
    verify_reused_releases(plan, output)
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
    require(not pub.command('git', 'status', '--porcelain', '--untracked-files=no').strip(), 'Release source checkout dirty')
    source = pub.command('git', 'rev-parse', 'HEAD').decode().strip()
    require(os.environ.get('GITHUB_REPOSITORY') == pub.REPOSITORY and
            os.environ.get('GITHUB_EVENT_NAME') in ('push', 'workflow_dispatch'),
            'Publication requires the authorized repository workflow')
    branch = pub.api('repos/' + pub.REPOSITORY)['default_branch']
    require(os.environ.get('GITHUB_REF') == 'refs/heads/' + branch and
            pub.api(f'repos/{pub.REPOSITORY}/commits/{branch}')['sha'] == source,
            'Publication requires exact current default-branch source')
    plan = preflight(output)
    require(plan['source_sha'] == source, 'Stage belongs to another release commit')
    parent, current = pub.current_release_index()
    verify_predecessor(plan, parent, current)
    for release in plan['releases']:
        pub.publish_one(release, output, title=('Watch ' + VERSION if release['latest'] else release['tag']),
                        notes=NOTICE + '\n\nExact accepted component bytes. See LICENSES.zip and source provenance.')
    pub.publish_index(plan['index'], expected_parent=parent, expected_current=current)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'verify', 'preflight', 'publish'))
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/accepted-watch-1.0.12/staged')
    parser.add_argument('--source-sha')
    args = parser.parse_args()
    if args.action == 'stage':
        source = args.source_sha or pub.command('git', 'rev-parse', 'HEAD').decode().strip()
        plan = stage(args.output, source)
    else:
        plan = {'verify': verify_stage, 'preflight': preflight, 'publish': publish}[args.action](args.output)
    print(f'Verified Watch {VERSION}: 22 apps, 22 providers, {len(plan["releases"])} releases; exact initial image, no OTA')


if __name__ == '__main__':
    main()

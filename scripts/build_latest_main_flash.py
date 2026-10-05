#!/usr/bin/env python3
"""Assemble the latest merged Watch update store with the latest merged Runtime.

This is a development full-flash image for the original/non-Plus T-Watch-S3.
It never accesses hardware and never publishes a release.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from build_update_common import ROOT, read_zip, require
from audio_overlay import PROFILE as AUDIO_PROFILE, verify as verify_audio
from build_points_common import PROFILE as POINTS_PROFILE, verify as verify_points
from build_points_paired_clock import verify as verify_points_clock
from build_update_flash_bundle import FLASH_BYTES, LAYOUT, assemble
from build_wifi_store import OFFSET, SIZE, check_image
from check_runtime_store_admission import unpack_image


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def exact_one(root, suffix):
    matches = sorted(Path(root).rglob('*' + suffix))
    require(len(matches) == 1, 'Expected exactly one artifact ending in ' + suffix)
    return matches[0]


def load_runtime_metadata(runtime_source):
    path = Path(runtime_source) / 'scripts' / 'paired_bank_images.py'
    spec = importlib.util.spec_from_file_location('latest_paired_bank_images', path)
    require(spec and spec.loader, 'Unable to load paired-bank metadata implementation')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(artifact_dir, points_artifact_dir, runtime_source, runtime_candidate, mkspiffs, head, output, current_apps_artifact_dir=None):
    artifact_dir = Path(artifact_dir).resolve()
    points_artifact_dir = Path(points_artifact_dir).resolve()
    runtime_source = Path(runtime_source).resolve()
    runtime_candidate = Path(runtime_candidate).resolve()
    mkspiffs = Path(mkspiffs).resolve()
    output = Path(output).resolve()

    require(git(ROOT, 'rev-parse', 'HEAD') == head, 'Watch checkout differs from requested main head')
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Watch checkout has tracked modifications')

    requirements = json.loads((ROOT / 'apps/update-runtime-requirements.json').read_text())
    runtime_head = git(runtime_source, 'rev-parse', 'HEAD')
    require(runtime_head == requirements['source_sha'], 'Runtime checkout differs from Watch runtime requirement')
    require(not git(runtime_source, 'status', '--porcelain', '--untracked-files=no'), 'Runtime checkout has tracked modifications')

    candidate_path = runtime_candidate / 'candidate.json'
    candidate = json.loads(candidate_path.read_text())
    require(candidate.get('source_sha') == runtime_head, 'Runtime candidate source mismatch')
    require(candidate.get('firmware_version') == requirements['firmware_version'], 'Runtime candidate version mismatch')
    require(candidate.get('target') == 'esp32s3-16mb-paired', 'Wrong Runtime target')
    require(candidate.get('layout') == LAYOUT and candidate.get('flash_bytes') == FLASH_BYTES,
            'Wrong Runtime paired layout')

    for name, meta in candidate['assets'].items():
        path = runtime_candidate / name
        require(path.is_file(), 'Missing Runtime candidate component: ' + name)
        data = path.read_bytes()
        require(len(data) == meta['bytes'] and sha(data) == meta['sha256'],
                'Runtime candidate component differs: ' + name)

    common = exact_one(artifact_dir, AUDIO_PROFILE + '.zip')
    points_common = exact_one(points_artifact_dir, '-' + POINTS_PROFILE + '.zip')
    image = exact_one(artifact_dir, AUDIO_PROFILE + '-bootfs.bin')
    image_record_path = image.with_suffix('.json')
    require(image_record_path.is_file(), 'Missing update store image record')

    record = verify_audio(common, root=ROOT, expected_head=head)
    points_record = verify_points(points_common, root=ROOT, expected_head=head)
    common_files = read_zip(common)
    require(json.loads(common_files['runtime-requirements.json']) == requirements,
            'Audio deployment Runtime requirement differs from main')
    points_files = read_zip(points_common)
    store = {name[6:]: data for name, data in common_files.items() if name.startswith('store/')}
    points_store = {name[6:]: data for name, data in points_files.items() if name.startswith('store/')}
    # The paired update lane intentionally preserves its older Points payload for
    # update-custody testing. The installable PR image must carry the actual
    # Points implementation validated by the Points lane.
    update_boot = json.loads(store['boot.json'])
    points_boot = json.loads(points_store['boot.json'])
    update_points_policy = next(x for x in update_boot['app_capabilities'] if x['manifest'] == 'points_in_time.json')
    points_points_policy = next(x for x in points_boot['app_capabilities'] if x['manifest'] == 'points_in_time.json')
    update_alarm_policy = next(x for x in update_boot['drivers'] if x['manifest'] == 'alarm-service/manifest.json')
    points_alarm_policy = next(x for x in points_boot['drivers'] if x['manifest'] == 'alarm-service/manifest.json')
    require(update_points_policy == points_points_policy, 'Points app policy differs between update and Points stores')
    require(update_alarm_policy == points_alarm_policy, 'Alarm service binding differs between update and Points stores')
    overlay = ('points_in_time.elf', 'points_in_time.json',
               'alarm-service/driver.elf', 'alarm-service/manifest.json')
    for name in overlay:
        require(name in points_store and name in store, 'Missing Points overlay member: ' + name)
        store[name] = points_store[name]
    # Rebuild with the current Points schema, retaining paired boot confirmation.
    # Merely finding an UP NEXT string does not establish decoder compatibility.
    clock_record_path = exact_one(points_artifact_dir, 'points-paired-clock.json')
    clock_files, clock_record = verify_points_clock(clock_record_path.parent, head,
        json.loads(points_files['shared/alarm-service-build.json']))
    for name in ('default.json', 'clock.json'):
        require(json.loads(clock_files[name]) == json.loads(store[name]),
                'Paired Points Clock manifest/grants changed: ' + name)
    store.update(clock_files)
    overlay += tuple(clock_files)
    points_manifest = json.loads(store['points_in_time.json'])
    alarm_manifest = json.loads(store['alarm-service/manifest.json'])
    require(points_manifest['id'] == 'points_in_time' and points_manifest['version'] == '0.4.2',
            'Installable image does not contain Points in Time 0.4.2')
    require(alarm_manifest['id'] == 'alarm-service' and alarm_manifest['version'] == '0.3.1',
            'Installable image does not contain Points cue service 0.3.1')
    require(b'UP NEXT' in store['default.elf'] and b'UP NEXT' in store['clock.elf'],
            'Installable Clock payload does not contain the UP NEXT watch face')
    # Historical Points/Clock custody remains separately recorded. The explicit
    # current cohort owns the final installable applications and narrow policy
    # additions, never edits its baseline archives or physical driver payloads.
    historical_points_files = {name: {'size_bytes': len(store[name]), 'sha256': sha(store[name])}
                               for name in overlay}
    current_apps_record = None
    if current_apps_artifact_dir is not None:
        from current_apps_overlay import apply as apply_current_apps
        store, current_apps_record = apply_current_apps(store, current_apps_artifact_dir, head, root=ROOT)

    image_bytes = image.read_bytes()
    image_record = json.loads(image_record_path.read_text())
    expected_image = {
        'profile': AUDIO_PROFILE,
        'watch_source_sha': head,
        'deployment_sha256': sha(common.read_bytes()),
        'sha256': sha(image_bytes),
        'size_bytes': SIZE,
        'partition_label': 'bootfs0',
        'partition_offset': OFFSET,
        'layout': LAYOUT,
        'store_abi': 1,
        'migration_only': True,
        'round_trip_verified': True,
    }
    require(all(image_record.get(k) == v for k, v in expected_image.items()),
            'Update store image record differs from verified main inputs')
    # The source update-store image predates the overlay, so rebuild the SPIFFS
    # partition from the verified merged store rather than reusing its bytes.
    with tempfile.TemporaryDirectory(prefix='latest-main-store-') as temporary:
        source = Path(temporary) / 'store'
        source.mkdir()
        for member, data in sorted(store.items()):
            target = source / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        merged_image = Path(temporary) / 'bootfs.bin'
        subprocess.run([str(mkspiffs), '-c', str(source), '-p', '256', '-b', '4096',
                        '-s', str(SIZE), str(merged_image)], check=True, timeout=60)
        check_image(merged_image, store, mkspiffs)
        image_bytes = merged_image.read_bytes()

    metadata = load_runtime_metadata(runtime_source)
    components = {
        'bootloader.bin': (runtime_candidate / 'bootloader.bin').read_bytes(),
        'partitions.bin': (runtime_candidate / 'partitions.bin').read_bytes(),
        'firmware.bin': (runtime_candidate / 'firmware.bin').read_bytes(),
        'bootfs.bin': image_bytes,
    }
    components['otadata.bin'] = metadata.initial_otadata()
    components['bank_state.bin'] = metadata.initial_bank_state(components['firmware.bin'], image_bytes)
    metadata.parse_record(components['bank_state.bin'][:96])

    merged, parts = assemble(components)
    require(len(merged) == FLASH_BYTES, 'Full-flash image size mismatch')
    require(unpack_image(merged[OFFSET:OFFSET + SIZE], mkspiffs) == store,
            'Final full-flash store differs after assembly')

    version = json.loads((ROOT / 'apps/clock/paired-manifest.json').read_text())['version']
    name = f'twatch-s3-main-{version}-{head[:8]}.bin'
    manifest = {
        'schema': 1,
        'kind': 'latest-merged-main-full-flash',
        'target': 'Original/non-Plus T-Watch-S3,16MiB flash/8MiB OPI PSRAM',
        'watch_source': head,
        'watch_tree': git(ROOT, 'rev-parse', 'HEAD^{tree}'),
        'watch_version': version,
        'runtime_source': runtime_head,
        'runtime_version': candidate['firmware_version'],
        'layout': LAYOUT,
        'store_abi': 1,
        'file': name,
        'bin_sha256': sha(merged),
        'size_bytes': len(merged),
        'flash_offset': '0x0',
        'overwrite_bytes': FLASH_BYTES,
        'flash_capacity_bytes': FLASH_BYTES,
        'components': parts,
        'audio_common_sha256': sha(common.read_bytes()),
        'audio_tools': {
            'apps': record['apps'],
            'minimum_runtime': record['minimum_runtime'],
            'sources': record['sources'],
        },
        'points_common_sha256': sha(points_common.read_bytes()),
        'points_overlay': {
            'app_version': points_manifest['version'],
            'service_version': alarm_manifest['version'],
            'points_source_sha': points_record['source_sha'],
            'paired_clock': clock_record,
            'files': historical_points_files,
            'watch_face_count': 33,
            'required_face': 'UP NEXT',
        },
        'bootfs_sha256': sha(image_bytes),
        'physical_verification': 'pending',
        'flash_warning': (
            'Full 16MiB replacement repartitions flash and overwrites both banks, NVS/settings, '
            'saved Wi-Fi credentials, Stopwatch, alarms/countdowns and Points records. Back up first.'
        ),
        'store': [
            {'path': n, 'size_bytes': len(b), 'sha256': sha(b)}
            for n, b in sorted(store.items())
        ],
    }

    if current_apps_record is not None:
        manifest['current_apps_overlay'] = current_apps_record

    require(not output.exists(), 'Output directory already exists')
    output.mkdir(parents=True)
    (output / name).write_bytes(merged)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    (output / 'FLASHING.md').write_text(
        '# Latest merged T-Watch-S3 main image\n\n'
        'This image targets the original/non-Plus LILYGO T-Watch-S3 with 16MiB flash and 8MiB OPI PSRAM.\n'
        'It is a full 16MiB migration image at offset 0x0 and erases/replaces saved state. Back up first.\n\n'
        f'Watch source: {head}\nRuntime source: {runtime_head}\n'
        f'Watch version: {version}\nRuntime version: {candidate["firmware_version"]}\n'
        f'SHA256: {sha(merged)}\n\n'
        f'Flash: python -m esptool --chip esp32s3 --port PORT --baud 460800 write_flash 0x0 {name}\n'
    )
    sums = {
        name: (output / name).read_bytes(),
        'manifest.json': (output / 'manifest.json').read_bytes(),
        'FLASHING.md': (output / 'FLASHING.md').read_bytes(),
    }
    (output / 'SHA256SUMS').write_text(''.join(f'{sha(data)}  {n}\n' for n, data in sorted(sums.items())))

    archive = output / (Path(name).stem + '-install.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(output.iterdir()):
            if path == archive:
                continue
            info = zipfile.ZipInfo(path.name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, path.read_bytes())
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None, 'Install ZIP failed CRC verification')

    print(json.dumps({**manifest, 'install_zip': archive.name, 'install_zip_sha256': sha(archive.read_bytes())}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-dir', required=True, type=Path)
    parser.add_argument('--points-artifact-dir', required=True, type=Path)
    parser.add_argument('--runtime-source', required=True, type=Path)
    parser.add_argument('--runtime-candidate', required=True, type=Path)
    parser.add_argument('--mkspiffs', required=True, type=Path)
    parser.add_argument('--watch-head', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--current-apps-artifact-dir', type=Path)
    args = parser.parse_args()
    build(args.artifact_dir, args.points_artifact_dir, args.runtime_source, args.runtime_candidate,
          args.mkspiffs, args.watch_head, args.output, args.current_apps_artifact_dir)

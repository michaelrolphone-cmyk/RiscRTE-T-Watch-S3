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
from audio_overlay import PROFILE, verify
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


def build(artifact_dir, runtime_source, runtime_candidate, mkspiffs, head, output):
    artifact_dir = Path(artifact_dir).resolve()
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

    common = exact_one(artifact_dir, '-' + PROFILE + '.zip')
    image = exact_one(artifact_dir, '-' + PROFILE + '-bootfs.bin')
    image_record_path = image.with_suffix('.json')
    require(image_record_path.is_file(), 'Missing update store image record')

    record = verify(common, root=ROOT, expected_head=head)
    common_files = read_zip(common)
    require(json.loads(common_files['runtime-requirements.json']) == requirements, 'Audio deployment Runtime requirement differs from main')
    store = {name[6:]: data for name, data in common_files.items() if name.startswith('store/')}
    image_bytes = image.read_bytes()
    image_record = json.loads(image_record_path.read_text())
    expected_image = {
        'profile': PROFILE,
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
    check_image(image, store, mkspiffs)

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
        'common_sha256': sha(common.read_bytes()),
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
    parser.add_argument('--runtime-source', required=True, type=Path)
    parser.add_argument('--runtime-candidate', required=True, type=Path)
    parser.add_argument('--mkspiffs', required=True, type=Path)
    parser.add_argument('--watch-head', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    build(args.artifact_dir, args.runtime_source, args.runtime_candidate,
          args.mkspiffs, args.watch_head, args.output)

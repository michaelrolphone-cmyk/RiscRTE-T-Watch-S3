#!/usr/bin/env python3
"""Assemble an exact-head Wi-Fi CI store and pinned Runtime; never flash.

This produces a development artifact, not a product promotion. The source tree,
external CI receipt, every original profile ZIP, the unpacked SPIFFS contents,
and all runtime components must agree before any deliverable is written.
"""
import argparse
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zipfile

from build_wifi_common import ROOT, PROFILE, encoded, exact_sha, read_zip, require, sha, verify
from build_wifi_store import SIZE, OFFSET, TOOL_SHA256, check_image
from check_runtime_store_admission import archive_store, unpack_image, preserve_store, admit_many

_RUNTIME = json.loads((ROOT/'apps/wifi-runtime-artifact.json').read_text())
RUNTIME_SHA = _RUNTIME['source_sha']
RUNTIME_VERSION = json.loads((ROOT/'apps/wifi-runtime-requirements.json').read_text())['firmware_version']
RUNTIME_ZIP_SHA256 = _RUNTIME['artifact_sha256']
RUNTIME_ASSETS = {name: (value['size_bytes'], value['sha256'])
                  for name,value in _RUNTIME['components'].items()}
COMPONENT_OFFSETS = [('bootloader.bin', 0), ('partitions.bin', 0x8000),
                     ('firmware.bin', 0x10000), ('bootfs.bin', OFFSET)]
MERGED_SIZE = 0x800000


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def verify_watch_source(root, tree):
    require(exact_sha(tree), 'Exact reviewed Watch tree required')
    require(git(root, 'rev-parse', 'HEAD^{tree}') == tree, 'Watch checkout is not the reviewed tree')
    require(not git(root, 'status', '--porcelain', '--untracked-files=no'),
            'Watch source has tracked modifications')


def verify_source(root, tree, runtime_source):
    verify_watch_source(root, tree)
    require(git(runtime_source, 'rev-parse', 'HEAD') == RUNTIME_SHA,
            'Runtime source must be the exact pinned commit')
    require(not git(runtime_source, 'status', '--porcelain', '--untracked-files=no'),
            'Runtime source has tracked modifications')


def verify_runtime(files):
    require(set(files) == {'SHA256SUMS', 'candidate.json', 'firmware.elf', 'platformio.ini',
                           'partitions.csv', 'requirements-ci.txt', *RUNTIME_ASSETS},
            'Unexpected runtime artifact members')
    candidate = json.loads(files['candidate.json'])
    expected = {'schema': 1, 'source_sha': RUNTIME_SHA, 'firmware_version': RUNTIME_VERSION,
                'target': 'esp32s3-16mb-usb', 'flash_bytes': 0x1000000,
                'layout_used_bytes': MERGED_SIZE, 'app_offset': 0x10000,
                'bootfs_offset': OFFSET, 'bootfs_bytes': SIZE, 'usb_cdc_on_boot': True,
                'flash_mode': 'qio', 'flash_frequency_hz': 80000000, 'psram': 'opi'}
    require(all(candidate.get(k) == v for k, v in expected.items()),
            'Runtime target or provenance differs from exact 16MiB pair')
    require(set(candidate['assets']) == set(files) - {'SHA256SUMS', 'candidate.json'},
            'Runtime asset membership mismatch')
    for name, info in candidate['assets'].items():
        require(len(files[name]) == info['bytes'] and sha(files[name]) == info['sha256'],
                'Runtime candidate checksum mismatch: ' + name)
    for name, (size, digest) in RUNTIME_ASSETS.items():
        require(len(files[name]) == size and sha(files[name]) == digest,
                'Wrong pinned runtime component: ' + name)
    for name in ('bootloader.bin', 'firmware.bin'):
        data = files[name]
        require(data[0] == 0xe9 and data[3] >> 4 == 4 and
                struct.unpack_from('<H', data, 12)[0] == 9,
                'Runtime component is not ESP32-S3 with 16MiB flash header')
    require(RUNTIME_SHA.encode() in files['firmware.bin'], 'Runtime source marker missing')
    partitions = []
    for index in range(0, len(files['partitions.bin']), 32):
        raw = files['partitions.bin'][index:index + 32]
        if raw[:2] != b'\xaaP':
            break
        _, kind, subtype, offset, size, label, flags = struct.unpack('<HBBII16sI', raw)
        partitions.append((kind, subtype, offset, size, label.rstrip(b'\0').decode(), flags))
    require(partitions == [(1, 2, 0x9000, 0x6000, 'nvs', 0),
                           (0, 0, 0x10000, 0x300000, 'factory', 0),
                           (1, 130, OFFSET, SIZE, 'bootfs', 0)],
            'Runtime partition map differs from exact layout')
    return candidate


def verify_receipt(receipt, raw, head, tree):
    expected = {'repository': 'michaelrolphone-cmyk/RiscRTE-T-Watch-S3',
                'head': head, 'tree': tree, 'conclusion': 'success', 'expired': False,
                'artifact_name': 'twatch-wifi-integration-' + head,
                'artifact_sha256': sha(raw)}
    require(exact_sha(head) and exact_sha(tree) and
            all(receipt.get(k) == v for k, v in expected.items()),
            'External exact-head CI receipt mismatch')
    require(all(type(receipt.get(k)) is int and receipt[k] > 0 for k in ('run_id', 'artifact_id')),
            'External CI run/artifact identity missing')
    jobs = receipt.get('jobs')
    names = {'software-checks', 'alarm-integration', 'points-integration',
             'wifi-integration', 'production-store-admission'}
    require(isinstance(jobs, list) and len(jobs) == len(names) and
            all(isinstance(job, dict) and job.get('conclusion') == 'success' for job in jobs) and
            {job.get('name') for job in jobs} == names,
            'All five exact-head CI jobs, including production store admission, must pass')


def assemble_components(components):
    require(set(components) == {n for n, _ in COMPONENT_OFFSETS}, 'Component membership mismatch')
    merged = bytearray(b'\xff' * MERGED_SIZE)
    manifest = []
    cursor = 0
    for name, offset in COMPONENT_OFFSETS:
        data = components[name]
        limit = next((start for _, start in COMPONENT_OFFSETS if start > offset), MERGED_SIZE)
        require(offset >= cursor and offset + len(data) <= limit, 'Component overlaps partition boundary')
        if name == 'bootfs.bin':
            require(len(data) == SIZE, 'Bootfs does not fill the fixed partition')
        merged[offset:offset + len(data)] = data
        manifest.append({'file': 'components/' + name, 'offset': hex(offset),
                         'size_bytes': len(data), 'sha256': sha(data)})
        cursor = offset + len(data)
    cursor = 0
    for name, offset in COMPONENT_OFFSETS:
        require(all(b == 255 for b in merged[cursor:offset]), 'Non-erased gap in merged image')
        require(merged[offset:offset + len(components[name])] == components[name], 'Component copy differs')
        cursor = offset + len(components[name])
    require(all(b == 255 for b in merged[cursor:]), 'Non-erased final padding')
    return bytes(merged), manifest


def build(runtime, artifact, head, tree, receipt_path, runtime_source, tool, out, root=ROOT):
    verify_source(root, tree, runtime_source)
    runtime_raw = Path(runtime).read_bytes()
    require(sha(runtime_raw) == RUNTIME_ZIP_SHA256, 'Runtime archive differs from pinned CI artifact')
    runtime_files = read_zip(io.BytesIO(runtime_raw))
    candidate = verify_runtime(runtime_files)
    raw = Path(artifact).read_bytes()
    receipt = json.loads(Path(receipt_path).read_text())
    verify_receipt(receipt, raw, head, tree)
    artifact_files = read_zip(io.BytesIO(raw))

    def one(suffix):
        matches = [n for n in artifact_files if n.endswith(suffix)]
        require(len(matches) == 1, 'Expected one artifact member: ' + suffix)
        return matches[0]

    common_name = one('-' + PROFILE + '.zip')
    image_name = one('-' + PROFILE + '-bootfs.bin')
    image_record = json.loads(artifact_files[image_name[:-4] + '.json'])
    common, image = artifact_files[common_name], artifact_files[image_name]
    expected = {'schema': 1, 'profile': PROFILE, 'watch_source_sha': head,
                'deployment_sha256': sha(common), 'image': Path(image_name).name,
                'sha256': sha(image), 'size_bytes': SIZE, 'partition_label': 'bootfs',
                'partition_offset': OFFSET, 'page_size': 256, 'block_size': 4096,
                'tool_sha256': TOOL_SHA256, 'files': 44, 'round_trip_verified': True}
    require(all(image_record.get(k) == v for k, v in expected.items()), 'SPIFFS image record mismatch')
    admission_stores = []
    with tempfile.TemporaryDirectory() as temporary:
        common_path = Path(temporary) / 'common.zip'
        common_path.write_bytes(common)
        record = verify(common_path, root=root, expected_head=head)
        files = read_zip(common_path)
        for item in record['common_wifi_launcher']['inputs']:
            original = artifact_files[one(item['archive'])]
            require(sha(original) == item['sha256'] and len(original) == item['size_bytes'],
                    'Common source archive differs from exact CI artifact')
            admission_stores.append((item['archive'], archive_store(original)))
        image_path = Path(temporary) / 'bootfs.bin'
        image_path.write_bytes(image)
        store = {n[6:]: b for n, b in files.items() if n.startswith('store/')}
        require(image_record['payload_bytes'] == sum(map(len, store.values())), 'Incorrect store byte count')
        check_image(image_path, store, Path(tool).resolve())
        preserve_store(store, root / 'apps/wifi-store-baseline.json')
        admission_stores.append(('common-deployment', store))
        admission_stores.append(('hosted-spiffs', unpack_image(image, tool)))
    require(record['runtime_requirements']['source_sha'] == candidate['source_sha'] and
            record['runtime_requirements']['firmware_version'] == candidate['firmware_version'],
            'Deployment and runtime are not the same pinned pair')
    clock_version = record['app_version']
    version = json.loads(files['store/wifi_settings.json'])['version']
    require(re.fullmatch(r'\d+\.\d+\.\d+', version), 'Invalid application version')
    components = {n: runtime_files[n] for n in RUNTIME_ASSETS}
    components['bootfs.bin'] = image
    merged, parts = assemble_components(components)
    # Exercise the bytes extracted from the final candidate before writing any
    # deliverable. Matching manifests/hashes never replaces Runtime admission.
    final_store = unpack_image(merged[OFFSET:OFFSET + SIZE], tool)
    require(final_store == store, 'Final BIN store differs from exact hosted store')
    admission_stores.append(('final-bin-extraction', final_store))
    admission = admit_many(runtime_source, admission_stores)
    name = 'twatch-s3-wifi-settings-' + version + '-' + head[:8] + '.bin'
    manifest = {'schema': 1, 'kind': 'development-hardware-test',
                'target': 'Original/non-Plus LILYGO T-Watch-S3,16MiB flash/8MiB OPI PSRAM',
                'watch_source': head, 'watch_tree': tree, 'clock_version': clock_version, 'wifi_version': version,
                'runtime_source': RUNTIME_SHA, 'runtime_version': RUNTIME_VERSION,
                'runtime_artifact_sha256': RUNTIME_ZIP_SHA256, 'ci_receipt': receipt,
                'common_sha256': sha(common), 'bootfs_sha256': sha(image), 'bin_sha256': sha(merged),
                'size_bytes': len(merged), 'file': name, 'flash_offset': '0x0',
                'overwrite_bytes': MERGED_SIZE, 'flash_capacity_bytes': 0x1000000,
                'components': parts, 'source_pins': json.loads(files['shared/alarm-sources.json']),
                'runtime_admission': admission,
                'store': [{'path': n, 'size_bytes': len(b), 'sha256': sha(b)}
                          for n, b in sorted(store.items())], 'physical_verification': 'pending',
                'flash_warning': 'Full lower8MiB replacement resets NVS/settings, saved Stopwatch, alarm/countdown state, Points in Time records and saved Wi-Fi profile; upper8MiB untouched'}
    deliverables = {name: merged, 'manifest.json': encoded(manifest),
                    'provenance/common-deployment.zip': common,
                    'provenance/bootfs.json': encoded(image_record),
                    'provenance/runtime-candidate.json': runtime_files['candidate.json'],
                    'provenance/watch-ci-receipt.json': encoded(receipt),
                    'licenses/RUNTIME-LICENSE': (Path(runtime_source) / 'LICENSE').read_bytes()}
    deliverables.update({'components/' + n: b for n, b in components.items()})
    deliverables.update({'reproduce/' + n: runtime_files[n]
                         for n in ('platformio.ini', 'partitions.csv', 'requirements-ci.txt')})
    deliverables.update({n: b for n, b in files.items() if n.startswith(('licenses/', 'shared/'))})
    deliverables.update({'licenses/' + p.name: p.read_bytes()
                         for p in (root / 'licenses').glob('*') if p.is_file()})
    deliverables['licenses/BOOT_WORDMARK_LICENSE.txt'] = (
        root / 'apps/clock/effects/reference/BOOT_WORDMARK_LICENSE.txt').read_bytes()
    deliverables['FLASHING.md'] = (
        '# T-Watch-S3 Wi-Fi Settings development candidate ' + version + '\n\n'
        'Original/non-Plus T-Watch-S3, 16MiB flash and 8MiB OPI PSRAM.\n'
        'Flash the merged BIN at 0x0 only after backing up and deciding to replace\n'
        'the lower 8MiB, including NVS, settings, Stopwatch, alarms, Points and saved Wi-Fi\n'
        'state. NVS0x9000..0xefff contains erased0xff bytes in this image. Writing\n'
        'the whole image resets those saved values. The upper8MiB is untouched.\n'
        'Keep the accepted Watch1.0 image for\n'
        'recovery. No device operation was performed.\n\n'
        'Includes the combined Clock picker, eleven app policies, shared alarm service,\n'
        'bounded outputs and Runtime' + RUNTIME_VERSION + '. Host/target checks do not establish\n'
        'physical wake reliability, sound/haptic levels, power loss or current draw.\n\n'
        'After choosing to flash, close serial monitors and replace PORT:\n'
        'python -m esptool --chip esp32s3 --port PORT --baud 460800 write_flash 0x0 ' + name + '\n\n'
        'Watch: ' + head + '\nReviewed tree: ' + tree + '\nRuntime: ' + RUNTIME_SHA +
        '\nMerged SHA256: ' + sha(merged) + '\n').encode()
    deliverables['SHA256SUMS'] = ''.join(sha(b) + '  ' + n + '\n'
                                      for n, b in sorted(deliverables.items())).encode()
    out = Path(out)
    binary = out / name
    archive = out / (Path(name).stem + '-flashing.zip')
    report_path = out / (Path(name).stem + '.json')
    inputs = {Path(p).resolve() for p in (runtime, artifact, receipt_path, tool)}
    require(not inputs.intersection(p.resolve() for p in (binary, archive, report_path)),
            'Output aliases an input')
    out.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(merged)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for n, data in sorted(deliverables.items()):
            entry = zipfile.ZipInfo(n, (2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            output.writestr(entry, data)
    require(read_zip(archive) == deliverables, 'Flashing archive round-trip differs')
    manifest['flashing_zip'] = archive.name
    manifest['flashing_zip_sha256'] = sha(archive.read_bytes())
    report_path.write_bytes(encoded(manifest))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'artifact', 'receipt', 'runtime-source', 'mkspiffs', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--pr-head', required=True)
    parser.add_argument('--source-tree', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.runtime, args.artifact, args.pr_head, args.source_tree,
                           args.receipt, args.runtime_source, args.mkspiffs, args.output), indent=2))

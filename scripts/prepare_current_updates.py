#!/usr/bin/env python3
"""Prepare source-bound ABI2 update release inputs; never publish or flash.

The Firmware Update client installs one native+bootfs cohort transaction.
The optional installed-app update remains compatible. Neither payload contains
NVS, app-data, bootloader or partition-table bytes.
The separately named full USB image remains destructive initial provisioning.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from current_apps_overlay import ROOT, config, verify
from current_flash_layout import validate, assemble as assemble_current
from read_only_spiffs import read_image
from watch_release_index import REPOSITORY, require, update_index, version_tuple, reuse_app_record
from verify_update_elf import verify as verify_update_elf
from current_cohort import parse as parse_cohort, verify as verify_cohort, package as package_cohort


def sha(data):
    return hashlib.sha256(data).hexdigest()


def exact_components(raw, manifest, deployment=None):
    require(len(raw) == 0x1000000 and sha(raw) == manifest['bin_sha256'], 'Full image differs')
    result = {}
    for item in manifest['components']:
        name = Path(item['file']).name
        start, count = int(item['offset'], 16), item['size_bytes']
        require(name not in result and 0 <= start < start + count <= len(raw), 'Invalid component bounds')
        data = raw[start:start + count]
        require(sha(data) == item['sha256'], 'Component differs: ' + name)
        result[name] = data
    if deployment is not None:
        reconstructed, entries = assemble_current(result, deployment, True)
        require(raw == reconstructed and manifest['components'] == entries,
                'Initial image placement, inventory, or erased gaps differ')
    return result


def app_compatibility(previous, following, *, allow_same=False):
    require(previous['id'] == following['id'] == 'audio_spectrum', 'Wrong app identity')
    old_version, new_version = version_tuple(previous['version']), version_tuple(following['version'])
    require(new_version > old_version or (allow_same and new_version == old_version), 'App must advance')
    old, new = copy.deepcopy(previous), copy.deepcopy(following)
    old.pop('version'); new.pop('version')
    require(old == new, 'Spectrum update changes existing manifest authority or metadata')


def asset(kind, version, name, data, identity=None):
    tag = kind + '-' + ((identity + '-') if identity else '') + 'v' + version
    return dict(kind=kind, version=version, tag=tag, asset=name,
                url=f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}',
                size=len(data), sha256=sha(data), source_repo=REPOSITORY,
                **({'id': identity} if identity else {}))


def write_release(root, files):
    root.mkdir(parents=True)
    for name, data in files.items():
        (root / name).write_bytes(data)
    (root / 'SHA256SUMS').write_text(''.join(f'{sha(data)}  {name}\n' for name, data in sorted(files.items())))


def build(full_dir, apps_dir, installed_bin, runtime, native_dir, index_path, product_version, output, system_apps):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True).strip(), 'Dirty Watch source')
    pins = config(); files, apps = verify(apps_dir, head)
    requirements = json.loads((ROOT / 'apps/apex-runtime-requirements.json').read_text())
    validate(requirements['deployment'], True)
    runtime = Path(runtime).resolve()
    system_apps = Path(system_apps).resolve()
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=system_apps, text=True).strip() == pins['sources']['system-apps']['commit'], 'Wrong System Apps source')
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=system_apps, text=True).strip(), 'Dirty System Apps source')
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=runtime, text=True).strip() == pins['sources']['runtime']['commit'], 'Wrong Runtime source')
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=runtime, text=True).strip(), 'Dirty Runtime source')
    sys.path.insert(0, str(runtime / 'scripts'))
    spec = importlib.util.spec_from_file_location('update_candidate_verifier', runtime / 'scripts/paired_candidate.py')
    verifier = importlib.util.module_from_spec(spec); spec.loader.exec_module(verifier)
    full_dir, native_dir, output = Path(full_dir), Path(native_dir), Path(output)
    manifest = json.loads((full_dir / 'manifest.json').read_text())
    require(Path(manifest['file']).name == manifest['file'] and manifest['file'].endswith('.bin'), 'Unsafe full-image basename')
    require(manifest['watch_source'] == head and manifest['runtime_source'] == requirements['source_sha'], 'Full image source differs')
    require(manifest['layout'] == 'riscrte-paired-appdata-v2' and manifest['store_abi'] == 2, 'OTA requires existing ABI2 layout')
    raw = (full_dir / manifest['file']).read_bytes(); components = exact_components(raw, manifest, requirements['deployment'])
    store = read_image(components['bootfs.bin'], 0x510000)
    require(all(store.get(name) == data for name, data in files.items()), 'Current artifact differs from full image')
    native = json.loads((native_dir / 'candidate.json').read_text())
    require(native['source_sha'] == requirements['source_sha'] and native['firmware_version'] == requirements['firmware_version'], 'Native candidate source/version differs')
    require(native['layout'] == manifest['layout'] and native['store_abi'] == 2, 'Native candidate layout differs')
    for name in ('firmware.bin', 'firmware.elf', 'bootloader.bin', 'partitions.bin'):
        data = (native_dir / name).read_bytes(); meta = native['assets'][name]
        require(len(data) == meta['bytes'] and sha(data) == meta['sha256'], 'Native candidate asset differs: ' + name)
        if name in components:
            require(components[name] == data, 'Final native component differs: ' + name)
    verifier.partitions(components['partitions.bin'], verifier.APP_DATA_EXPECTED)
    require(verifier.native_proof((native_dir / 'firmware.elf').read_bytes()) == native['native_proof'], 'Native rollback/TLS/DRAM proof differs')
    firmware = components['firmware.bin']; verifier.esp_image(firmware)
    require(len(firmware) <= 0x260000, 'Native OTA exceeds bank')
    for marker in ('RTE_SOURCE=' + requirements['source_sha'], 'RISC_RUNTIME_VERSION:' + requirements['firmware_version'], 'RISC_PAIRED_STORE_ABI:2'):
        require(marker.encode() + b'\0' in firmware, 'Native OTA marker missing: ' + marker)
    require(b'RISC_PAIRED_STORE_ABI:1\0' not in firmware, 'ABI1 image cannot enter this package')
    elf_proof = verify_update_elf(runtime, (native_dir / 'firmware.elf').read_bytes(), store['audio_spectrum.elf'])
    previous = Path(installed_bin).read_bytes()
    require(len(previous) == 0x1000000, 'Installed custody must be a full ABI2 image')
    verifier.partitions(previous[0x8000:0x8c00], verifier.APP_DATA_EXPECTED)
    previous_store = read_image(previous[0x2f0000:0x800000], 0x510000)
    new_app = json.loads(store['audio_spectrum.json'])
    installed_provider = json.loads(previous_store['update-apps/manifest.json'])['version']
    target_provider = json.loads(store['update-apps/manifest.json'])['version']
    require(version_tuple(target_provider) >= (0,1,3), 'Target provider lacks paired-cohort support')
    require(requirements['required_behavior'].get('paired_cohort_updates'), 'Runtime cohort admission is required')
    identity = verify_cohort(parse_cohort(store['cohort.json']), firmware, version=product_version,
                             runtime_version=requirements['firmware_version'], source_revision=head)
    require(manifest.get('cohort') == identity, 'Full-image cohort custody differs')
    cohort_payload, cohort_ota = package_cohort(identity, firmware, components['bootfs.bin'])
    installed_firmware_provider = json.loads(previous_store['update-fw/manifest.json'])['version']
    installed_versions = set(re.findall(rb'RISC_RUNTIME_VERSION:([0-9]+\.[0-9]+\.[0-9]+)\x00', previous[0x10000:0x270000]))
    require(len(installed_versions) == 1, 'Starting image Runtime identity is ambiguous')
    installed_runtime_version = next(iter(installed_versions)).decode('ascii')
    bootstrap_required = (version_tuple(installed_firmware_provider) < (0,1,3) or
                          version_tuple(installed_runtime_version) < (0,1,33) or 'cohort.json' not in previous_store)
    if not bootstrap_required:
        before = parse_cohort(previous_store['cohort.json'])
        require(version_tuple(product_version) > version_tuple(before['version']), 'Cohort product must advance')
    app_compatibility(json.loads(previous_store['audio_spectrum.json']), new_app, allow_same=True)
    boot_unchanged = json.loads(previous_store['boot.json']) == json.loads(store['boot.json'])
    require(json.loads(previous_store['board.json']) == json.loads(store['board.json']), 'Cohort changes board identity')
    from check_runtime_store_admission import admit_cohort
    cohort_admission = admit_cohort(runtime, (native_dir / 'firmware.elf').read_bytes(), previous_store, store)
    runtime_version = requirements['firmware_version']; app_version = new_app['version']
    index = json.loads(Path(index_path).read_text())
    firmware_name = f'twatch-s3-launcher-{product_version}.bin'
    record = asset('firmware', product_version, firmware_name, raw)
    cohort_name = cohort_ota['asset']
    record['ota'] = cohort_ota
    record['source_sha'] = head; record['runtime_source_sha'] = requirements['source_sha']
    record['component_versions'] = {**pins['app_versions'], 'runtime': runtime_version}
    record['motion_model'] = manifest['motion_model']
    record['hardware_qualified'] = False
    app_record = asset('app', app_version, 'audio_spectrum.elf', store['audio_spectrum.elf'], 'audio_spectrum')
    app_record['manifest'] = new_app; app_record['source_sha'] = head
    app_record['minimum_runtime_version'] = runtime_version
    app_record['minimum_update_provider_version'] = '0.1.2'
    previous_records = [r for r in index.get('apps', []) if r.get('id') == 'audio_spectrum']
    require(len(previous_records) <= 1, 'Duplicate existing Spectrum catalog record')
    app_record, reuse_app = reuse_app_record(previous_records[0] if previous_records else None, app_record)
    # Current clients ignore minimum_runtime_version; install order is explicit
    # in the instructions, not claimed as automatically enforced dependency logic.
    final_index = update_index(update_index(index, 'firmware', record), 'apps', app_record)
    # Exercise the selected provider's fixed grammar and authority comparison.
    # The old installed provider's parsing limitation is reported separately.
    with tempfile.TemporaryDirectory(prefix='watch-update-catalog-') as tmp:
        tmp = Path(tmp); proposed = tmp / 'index.json'; previous_manifest = tmp / 'previous.json'
        proposed.write_text(json.dumps(final_index)); previous_manifest.write_bytes(previous_store['audio_spectrum.json'])
        parser = tmp / 'catalog'
        subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation',
                        '-I' + str(system_apps / 'Services/update'),
                        '-I' + str(system_apps / 'lib/PortableApps/include'),
                        '-I' + str(system_apps / 'lib/NativeApps/include'),
                        str(ROOT / 'tests/current_update_catalog.cpp'), '-o', str(parser)], check=True)
        subprocess.run([str(parser), str(proposed), str(previous_manifest), product_version], check=True)
    require(not output.exists(), 'Output already exists')
    output.mkdir(parents=True)
    licence_files = {str(p.relative_to(Path(apps_dir) / 'licenses')): p.read_bytes()
                     for p in (Path(apps_dir) / 'licenses').rglob('*') if p.is_file()}
    require(licence_files, 'Package notices missing')
    import io
    licence_zip = io.BytesIO()
    with zipfile.ZipFile(licence_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(licence_files.items()):
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)); entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, data)
    encoded = lambda value: (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    write_release(output / record['tag'], {firmware_name: raw, cohort_name: cohort_payload,
                  'release-record.json': encoded(record), 'LICENSES.zip': licence_zip.getvalue()})
    if not reuse_app:
        write_release(output / app_record['tag'], {'audio_spectrum.elf': store['audio_spectrum.elf'],
                      'audio_spectrum.json': store['audio_spectrum.json'],
                      'release-record.json': encoded(app_record), 'LICENSES.zip': licence_zip.getvalue()})
    (output / 'release-index.proposed.json').write_bytes(encoded(final_index))
    proof = dict(watch_source=head, runtime_source=requirements['source_sha'], layout=manifest['layout'],
                 source_full_image_sha256=sha(raw), installed_custody_sha256=sha(previous),
                 runtime_ota_sha256=sha(firmware), app_elf_sha256=sha(store['audio_spectrum.elf']),
                 cohort_ota_sha256=sha(cohort_payload), cohort_identity=identity,
                 app_manifest_authority_unchanged=True, boot_policy_unchanged=boot_unchanged, selected_provider_catalog_grammar_verified=True,
                 installed_update_provider_version=installed_provider, target_update_provider_version=target_provider,
                 installed_firmware_provider_version=installed_firmware_provider,
                 installed_runtime_version=installed_runtime_version,
                 existing_app_release_reused=reuse_app,
                 initial_transition_required=bootstrap_required, directly_installable_via_existing_apps=not bootstrap_required,
                 ota_write_regions=['inactive native slot', 'inactive bootfs slot', 'inactive bank journal', 'OTA boot selection'],
                 excluded_regions=['NVS 0x9000..0xefff', 'app-data 0x270000..0x2effff', 'bootloader', 'partition table'],
                 order=['Firmware Update: Watch ' + product_version + ' complete cohort', 'restart and confirm Clock'],
                 native_app_admission=elf_proof, app_minimum_runtime_automatically_enforced=False,
                 complete_cohort_admission=cohort_admission,
                 publication_performed=False, physical_verification='pending')
    (output / 'update-proof.json').write_bytes(encoded(proof))
    (output / 'README.md').write_text(
        '# Prepared Watch paired-cohort update\n\n'
        'For the existing riscrte-paired-appdata-v2 / ABI2 layout. These are release inputs; '
        'publish the matching immutable assets and catalog before using the built-in client.\n\n'
        + ('The supplied starting image lacks the paired-cohort provider or installed product identity. '
           'Use the explicitly accepted one-time initial full flash first; it erases existing settings and app-data. '
           'That transition installs the provider used for future preserving updates.\n\n' if bootstrap_required else
           'The supplied starting image has the paired-cohort provider and product identity.\n\n') +
        f'In Firmware Update, select Watch {product_version}. It stages Runtime {runtime_version} and '
        f'the complete application/provider store (including Spectrum {app_version}) in one inactive pair. '
        'The Runtime checks both hashes, board and persistent-namespace compatibility, complete graph/policy/ELF admission '
        'and readiness before boot selection. Restart and wait for Clock health confirmation. '
        'Ordinary installed-app updates remain available through App Store.\n\n'
        'The cohort asset contains only native firmware followed by the exact boot store. '
        'NVS/preferences and the independent app-data volume are outside the update write regions. '
        'Interruption, cancellation and rollback have software simulation coverage; physical OTA/power-loss checks are pending.\n\n'
        f'WARNING: twatch-s3-launcher-{product_version}.bin is the separate full 16MiB initial image '
        f'for {manifest["motion_model"]}. Flashing it overwrites NVS and app-data. '
        'Use the built-in Firmware Update path for subsequent preserving updates.\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('full-dir', 'apps-dir', 'installed-bin', 'runtime', 'native-dir', 'index', 'output', 'system-apps'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--product-version', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.full_dir, args.apps_dir, args.installed_bin, args.runtime,
                           args.native_dir, args.index, args.product_version, args.output, args.system_apps), indent=2))

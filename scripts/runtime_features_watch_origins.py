#!/usr/bin/env python3
"""Exact owner-accepted Watch 1.0.11 bytes for the isolated 1.0.12 lane."""
from pathlib import Path, PurePosixPath

from current_apps_overlay import APPS, ROOT, encoded, metadata, require
from current_cohort import parse, verify as verify_identity
from read_only_spiffs import read_image
from rf_watch_candidate import document, module, sha, STORE_BYTES
from power_watch_candidate import checked_source, read_native

ORIGINS = ('accepted-1.0.11',)
DESCRIPTOR = 'apps/runtime-features-1.0.11-origin.json'


def read_origin(selection='accepted-1.0.11', source_bundle=None, root=ROOT):
    require(selection in ORIGINS, 'Only exact accepted Watch 1.0.11 is qualified')
    require(source_bundle is not None, 'The exact accepted Watch 1.0.11 bundle is required')
    descriptor = document((Path(root) / DESCRIPTOR).read_bytes())
    require(descriptor['schema'] == 1 and descriptor['version'] == '1.0.11'
            and descriptor['runtime_version'] == '0.1.54'
            and descriptor['physical_acceptance_claimed'] is True,
            'Invalid accepted 1.0.11 descriptor')
    blobs = {}
    for name, expected in descriptor['assets'].items():
        require(PurePosixPath(name).name == name and name not in ('', '.', '..'), 'Unsafe source member')
        path = Path(source_bundle) / name
        require(path.is_file() and not path.is_symlink(), 'Missing exact accepted member: ' + name)
        blobs[name] = path.read_bytes()
        require(metadata(blobs[name]) == expected, 'Accepted 1.0.11 custody differs: ' + name)
    full = blobs['twatch-s3-1.0.11-FULL-INITIAL-ERASES-DATA-bma423.bin']
    require(len(full) == 0x1000000, 'Accepted 1.0.11 image size differs')
    store = read_image(full[0x2f0000:0x800000], STORE_BYTES)
    identity = parse(store['cohort.json'])
    require(identity == descriptor['identity'], 'Accepted source cohort identity differs')
    verify_identity(identity, full[0x10000:0x10000 + identity['firmware_size']],
                    version='1.0.11', runtime_version='0.1.54', source_revision=descriptor['watch_source'])
    from build_rf_watch_candidate import safe_archive
    app_members = safe_archive(blobs['power-apps.zip'])
    apps = document(app_members['current-apps-build.json'])
    require(apps['watch_source'] == descriptor['watch_source']
            and apps['configuration']['product_version'] == '1.0.11'
            and apps['configuration']['app_versions'] == descriptor['app_versions']
            and set(apps['apps']) == set(APPS), 'Accepted complete app identity differs')
    for name, expected in apps['files'].items():
        require(metadata(app_members['files/' + name]) == expected
                and store[name] == app_members['files/' + name], 'Accepted app bytes differ: ' + name)
    require(store['boot.json'] == encoded(apps['boot']), 'Accepted boot policy differs')
    proof = document(blobs['power-watch-build-proof.json'])
    require(proof['target_cohort'] == identity and proof['native_custody'] == descriptor['native_custody']
            and document(blobs['native-custody.json']) == descriptor['native_custody']
            and proof['files'] == {n: metadata(b) for n, b in sorted(store.items())},
            'Accepted native/store proof differs')
    requirements = document(blobs['runtime-requirements.json'])
    require(requirements['source_sha'] == descriptor['runtime_source']
            and requirements['firmware_version'] == '0.1.54', 'Accepted Runtime requirements differ')
    return {'kind': selection, 'full': full, 'store': store, 'identity': identity, 'apps': apps,
            'evidence_sha256': sha(blobs['power-apps.zip']), 'acceptance': descriptor['acceptance_scope'],
            'runtime_source': descriptor['runtime_source'], 'native_custody': descriptor['native_custody'],
            'native_requirements': requirements, 'physical_acceptance_claimed': True}


def read_installed_native(origin, native_dir, runtime, root=ROOT):
    require(origin['kind'] == 'accepted-1.0.11', 'Unqualified installed origin')
    checked_source(runtime, origin['runtime_source'])
    native = read_native(native_dir, runtime, root, requirements_override=origin['native_requirements'])
    require(native['custody'] == origin['native_custody'], 'Installed native custody differs')
    firmware = native['blobs']['firmware.bin']
    verify_identity(origin['identity'], firmware, version='1.0.11', runtime_version='0.1.54')
    require(origin['full'][0x10000:0x10000 + len(firmware)] == firmware,
            'Installed native bytes do not match accepted image')
    bank = module('runtime_features_origin_bank', Path(runtime) / 'scripts/paired_bank_images.py')
    require(origin['full'][0xff2000:0xff4000] == bank.initial_bank_state(
                firmware, origin['full'][0x2f0000:0x800000], app_data=True),
            'Accepted source journal differs')
    return native

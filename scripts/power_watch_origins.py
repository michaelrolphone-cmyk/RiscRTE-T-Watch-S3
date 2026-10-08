#!/usr/bin/env python3
"""Exact prior-cohort inputs for the cutoff candidate; no device state inference."""
from pathlib import Path
import json
from current_apps_overlay import ROOT, metadata, require
from current_cohort import parse, verify as verify_identity
from read_only_spiffs import read_image
from rf_watch_candidate import accepted, document, sha, checked_source, STORE_BYTES
from rf_spectrum_profile import RUNTIME_SOURCE as ACCEPTED_RUNTIME_SOURCE

ORIGINS = ('accepted-1.0.7', 'delivered-1.0.10')


def read_origin(selection='accepted-1.0.7', source_bundle=None, root=ROOT):
    require(selection in ORIGINS, 'Unqualified source cohort')
    if selection == 'accepted-1.0.7':
        result = accepted(root)
        result.update(kind=selection, runtime_source=ACCEPTED_RUNTIME_SOURCE, physical_acceptance_claimed=True)
        return result
    require(source_bundle is not None, 'The exact delivered 1.0.10 source bundle is required')
    descriptor = document((Path(root) / 'apps/power-1.0.10-origin.json').read_bytes())
    require(descriptor['schema'] == 1 and descriptor['version'] == '1.0.10'
            and descriptor['physical_acceptance_claimed'] is False, 'Invalid delivered origin descriptor')
    source_bundle = Path(source_bundle)
    blobs = {}
    for name, expected in descriptor['assets'].items():
        require(Path(name).name == name, 'Unsafe source bundle member')
        path = source_bundle / name
        require(path.is_file() and not path.is_symlink(), 'Missing delivered origin member: ' + name)
        blobs[name] = path.read_bytes()
        require(metadata(blobs[name]) == expected, 'Delivered 1.0.10 custody differs: ' + name)
    full = blobs['twatch-s3-1.0.10-FULL-INITIAL-ERASES-DATA-bma423.bin']
    require(len(full) == 0x1000000, 'Delivered origin is not a full initial image')
    store = read_image(full[0x2f0000:0x800000], STORE_BYTES)
    identity = parse(store['cohort.json'])
    require(identity == descriptor['identity'], 'Delivered source cohort identity differs')
    verify_identity(identity, full[0x10000:0x10000 + identity['firmware_size']], version='1.0.10',
                    runtime_version=descriptor['runtime_version'], source_revision=descriptor['watch_source'])
    from build_rf_watch_candidate import safe_archive
    app_members = safe_archive(blobs['power-apps.zip'])
    apps = document(app_members['current-apps-build.json'])
    require(apps['watch_source'] == descriptor['watch_source'] and apps['configuration']['product_version'] == '1.0.10',
            'Delivered application source/version differs')
    for name, expected in apps['files'].items():
        require(metadata(app_members['files/' + name]) == expected and store[name] == app_members['files/' + name],
                'Delivered source application differs: ' + name)
    proof = document(blobs['power-watch-build-proof.json'])
    require(proof['target_cohort'] == identity and proof['native_custody'] == descriptor['native_custody'],
            'Delivered native/cohort proof differs')
    return {'kind': selection, 'full': full, 'store': store, 'identity': identity, 'apps': apps,
            'evidence_sha256': sha(blobs['power-apps.zip']), 'acceptance': None,
            'runtime_source': descriptor['runtime_source'], 'native_custody': descriptor['native_custody'],
            'native_requirements': document(blobs['runtime-requirements.json']),
            'physical_acceptance_claimed': False}


def read_installed_native(origin, native_dir, runtime, root=ROOT):
    checked_source(runtime, origin['runtime_source'])
    if origin['kind'] == 'accepted-1.0.7':
        from rf_watch_candidate import read_native, bind_native_to_accepted
        native = read_native(native_dir, runtime, root)
        bind_native_to_accepted(origin, native, runtime)
    else:
        from power_watch_candidate import read_native
        native = read_native(native_dir, runtime, root, requirements_override=origin['native_requirements'])
        require(native['custody']['candidate_sha256'] == origin['native_custody']['candidate_sha256'] and
                native['custody']['assets'] == origin['native_custody']['assets'], 'Delivered native bytes differ')
        verify_identity(origin['identity'], native['blobs']['firmware.bin'], version='1.0.10',
                        runtime_version=origin['identity']['runtime_version'])
        bank = __import__('rf_watch_candidate').module('cutoff_origin_bank', Path(runtime) / 'scripts/paired_bank_images.py')
        require(origin['full'][0xff2000:0xff4000] == bank.initial_bank_state(native['blobs']['firmware.bin'],
                origin['full'][0x2f0000:0x800000], app_data=True), 'Delivered source journal differs')
    return native

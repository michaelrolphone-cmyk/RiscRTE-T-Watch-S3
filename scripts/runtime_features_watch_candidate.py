#!/usr/bin/env python3
"""Strict opt-in Watch 1.0.12 composition from exact accepted Watch 1.0.11."""
from pathlib import Path

from current_apps_overlay import APPS, ROOT, config, configure_board, encoded, require
from current_cohort import create, encode, package, parse, verify as verify_identity
from current_flash_layout import assemble
from read_only_spiffs import read_image
from rf_watch_candidate import (accepted, authority, document, module, sha,
                                STORE_BYTES, FIRMWARE_BYTES, FIRMWARE_OFFSETS, STORE_OFFSETS)
from power_watch_candidate import checked_source, read_native as checked_native
from runtime_features_profile import (PROFILE, VERSION, RUNTIME_VERSION, POWER_DRIVERS,
                                      FEATURE_CAPS, runtime_requirements, upgrade_boot)

SOURCE_VERSION = '1.0.11'
NEW_PROVIDER_FILES = {'broadcast/driver.elf', 'broadcast/manifest.json'}


def read_native(native_dir, runtime, root=ROOT):
    return checked_native(native_dir, runtime, root, requirements_override=runtime_requirements(root))


def check_policy(previous, following, configuration, *, initial_only=False):
    require(set(following) == set(previous) | NEW_PROVIDER_FILES,
            'Runtime-features candidate lost inventory or added unexpected members')
    require(parse(previous['cohort.json'])['version'] == SOURCE_VERSION, 'Unqualified feature source version')
    if not initial_only:
        require(previous['board.json'] == following['board.json'], 'Preserving update changed accepted board')
    old_boot, new_boot = document(previous['boot.json']), document(following['boot.json'])
    require(new_boot == upgrade_boot(old_boot), 'Unexpected Runtime-features boot authority')
    app_authority = {}
    for name in APPS:
        old, new = document(previous[name + '.json']), document(following[name + '.json'])
        expected = authority(old)
        added = {(cap, 1) for cap in (*FEATURE_CAPS.get(name, ()), 'telemetry.broadcast')}
        require(not added & expected['requires'], 'Feature authority already present in origin')
        expected['requires'] |= added
        require(authority(new) == expected and new['version'] == configuration['app_versions'][name],
                'Unexpected app authority/version: ' + name)
        require(tuple(map(int, new['version'].split('.'))) > tuple(map(int, old['version'].split('.'))),
                'Rebuilt app version did not increase: ' + name)
        require(previous[name + '.elf'] != following[name + '.elf'], 'App was not rebuilt: ' + name)
        require(len(new['requires']) <= 16, 'Runtime16 app authority bound exceeded')
        app_authority[name] = [dict(capability=cap, api=api) for cap, api in sorted(added)]
    # Existing providers and persistent ownership stay byte-for-byte intact.
    # All changes in this lane are explicit app clients plus the new service.
    for row in old_boot['drivers']:
        name = row['manifest']
        require(previous[name] == following[name], 'Existing provider manifest changed: ' + name)
        elf = str(Path(name).parent / document(previous[name])['file_name'])
        require(previous[elf] == following[elf], 'Existing provider executable changed: ' + elf)
    for folder, version in POWER_DRIVERS.items():
        require(document(following[folder + '/manifest.json'])['version'] == version,
                'Accepted power repair lost: ' + folder)
    return {'accepted_boot_sha256': sha(previous['boot.json']), 'candidate_boot_sha256': sha(following['boot.json']),
            'prior_app_count': len(APPS), 'candidate_app_count': len(APPS),
            'provider_bindings_preserved': True, 'all_prior_provider_bytes_preserved': True,
            'all_prior_persistent_owners_preserved': True, 'shared_migration_added': False,
            'new_application_authority': app_authority, 'new_provider_files': sorted(NEW_PROVIDER_FILES),
            'provider_activation': 'demand', 'board_bytes_preserved': following['board.json'] == previous['board.json'],
            'power_driver_versions': POWER_DRIVERS}


def compose(origin, native, files, apps, head, root=ROOT, *, initial_only=False):
    configuration = config(root, profile=PROFILE)
    require(apps['configuration'] == configuration and apps['watch_source'] == head,
            'Runtime-features app source/profile differs')
    for key in ('baseline_boot', 'baseline_board', 'baseline_sha256', 'catalog'):
        require(apps[key] == origin['apps'][key], 'Candidate changed accepted baseline: ' + key)
    board = configure_board(apps['baseline_board'], root,
                            motion_model=apps['motion_model'], radio_model=apps['radio_model'])
    require(apps['board'] == board and document(files['board.json']) == board, 'Feature board proof differs')
    require(apps['motion_model'] == 'bma423' and apps['radio_model'] == 'selectable',
            'Feature increment requires accepted BMA423/selectable configuration')
    require(origin['identity']['version'] == SOURCE_VERSION, 'Wrong accepted source')
    require(native['record']['firmware_version'] == RUNTIME_VERSION
            and tuple(map(int, RUNTIME_VERSION.split('.'))) > tuple(map(int, origin['identity']['runtime_version'].split('.'))),
            'Feature increment needs the exact newer Runtime')
    require(native['requirements']['deployment']['partitions'] == origin['native_requirements']['deployment']['partitions'],
            'Feature increment changed persistent flash layout')
    following = {**origin['store'], **files, 'boot.json': encoded(apps['boot'])}
    identity = create(VERSION, RUNTIME_VERSION, head, native['blobs']['firmware.bin'])
    following['cohort.json'] = encode(identity)
    return following, identity, check_policy(origin['store'], following, configuration, initial_only=initial_only)


def paired_payload(identity, firmware, bootfs, motion_model):
    require(motion_model == 'bma423', 'Preserving feature payload requires accepted BMA423 origin')
    verify_identity(identity, firmware, version=VERSION, runtime_version=RUNTIME_VERSION)
    return package(identity, firmware, bootfs)


def initial_image(native, bootfs, runtime, motion_model):
    require(motion_model == 'bma423', 'Feature increment requires accepted BMA423 configuration')
    store = read_image(bootfs, STORE_BYTES)
    verify_identity(parse(store['cohort.json']), native['blobs']['firmware.bin'], version=VERSION, runtime_version=RUNTIME_VERSION)
    bank = module('runtime_features_initial_bank', Path(runtime) / 'scripts/paired_bank_images.py')
    components = {n: native['blobs'][n] for n in ('bootloader.bin', 'partitions.bin', 'firmware.bin', 'appdata.bin')}
    components.update({'bootfs.bin': bootfs, 'otadata.bin': bank.initial_otadata(),
                       'bank_state.bin': bank.initial_bank_state(native['blobs']['firmware.bin'], bootfs, app_data=True)})
    image, parts = assemble(components, native['requirements']['deployment'], True)
    require(read_image(image[0x2f0000:0x800000], STORE_BYTES) == store, 'Feature image store round trip differs')
    return 'twatch-s3-' + VERSION + '-FULL-INITIAL-ERASES-DATA-' + motion_model + '.bin', image, parts

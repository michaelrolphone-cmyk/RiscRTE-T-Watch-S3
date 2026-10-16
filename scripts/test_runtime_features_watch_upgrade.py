#!/usr/bin/env python3
"""Prove fresh Runtime runtime-features OTA through both exact Runtime generations.

The host IDF boundary models flash, mounted file views, active-app state and OTA
selection. Production native API gates, transaction, hashing, graph/ELF checks,
rollback and fresh-process boot admission run unchanged. No physical operations.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from check_runtime_store_admission import compile_harness, store_digest
from current_apps_overlay import ROOT, encoded, metadata, require
from current_bootfs import build as build_store
from current_cohort import create, encode, parse, verify as verify_identity
from read_only_spiffs import read_image
from runtime_features_watch_candidate import (RUNTIME_VERSION, STORE_BYTES, FIRMWARE_BYTES, FIRMWARE_OFFSETS, STORE_OFFSETS,
                                SOURCE_VERSION, VERSION, accepted, read_native,
                                document, sha, paired_payload)
from test_next_watch_upgrade import compile_transaction, admission

SCENARIOS = (
    'power-begin', 'power-native', 'power-store', 'cancel', 'corrupt-native', 'corrupt-store',
    'wrong-runtime-request', 'power-verify-native', 'power-verify-store', 'power-ready',
    'activation-unknown', 'rollback', 'power-selected', 'bad-source', 'bad-product', 'bad-repo',
    'bad-version', 'stale-store', 'unconfirmed-source', 'wrong-source-request',
    'mount-failure', 'unmount-failure', 'write-native-failure',
    'write-store-failure', 'journal-write-failure', 'graph-rejection', 'flash-corrupt-native',
    'flash-corrupt-store', 'post-admission-store-mutation', 'power-reverify-store', 'success')
SELECTED_SCENARIOS = {'activation-unknown', 'rollback', 'power-selected', 'success'}
BAD_REQUESTS = {'bad-source', 'bad-product', 'bad-repo', 'bad-version', 'stale-store', 'wrong-runtime-request', 'unconfirmed-source'}
TEMP_BUDGET = 60 * 1024 * 1024
FREE_RESERVE = 100 * 1024 * 1024
TRANSACTION_FIXTURE = ROOT / 'tests/runtime_features_watch_upgrade/native_transaction.cpp'


def check_disk(path, extra=TEMP_BUDGET):
    require(shutil.disk_usage(path).free >= FREE_RESERVE + extra,
            'RF proof needs its bounded temporary budget plus 100MiB free for other work')


@contextmanager
def host_sanitizer_environment():
    previous = os.environ.get('ASAN_OPTIONS')
    os.environ['ASAN_OPTIONS'] = (previous + ':' if previous else '') + 'detect_leaks=0'
    try:
        yield
    finally:
        if previous is None: os.environ.pop('ASAN_OPTIONS', None)
        else: os.environ['ASAN_OPTIONS'] = previous


def check_preserved(original, snapshot):
    require(len(original) == len(snapshot) == 0x1000000, 'RF flash snapshot size differs')
    for start, length in ((0, 0x10000), (0x270000, 0x80000), (FIRMWARE_OFFSETS[0], FIRMWARE_BYTES),
                          (STORE_OFFSETS[0], STORE_BYTES), (0xff2000, 4096)):
        require(original[start:start + length] == snapshot[start:start + length],
                'RF transaction changed persistent data/source pair at ' + hex(start))


def negative_stores(previous, following):
    for label in ('stale-hid-migration', 'steal-spectrum-kv', 'steal-timecard-data', 'steal-spectrum-data',
                  'remove-shared-preferences', 'seventeenth-grant', 'corrupt-app-elf', 'corrupt-provider-elf',
                  'provider-storage-theft', 'extra-store-member', 'changed-board'):
        store = dict(following)
        boot = document(store['boot.json'])
        row = next(r for r in boot['app_capabilities'] if r['manifest'] == 'waterfall.json')
        private = lambda cap: next(g for g in row['grants'] if g['capability'] == cap and
                                  (cap != 'storage.key-value' or g['api'] == 2))
        if label == 'stale-hid-migration': boot['cohort_migration'] = document(accepted()['store']['boot.json'])['cohort_migration']
        elif label == 'steal-spectrum-kv': private('storage.key-value')['instance_id'] = 7
        elif label == 'steal-timecard-data': private('storage.app-data')['instance_id'] = 1
        elif label == 'steal-spectrum-data': private('storage.app-data')['instance_id'] = 2
        elif label == 'remove-shared-preferences':
            row['grants'] = [g for g in row['grants'] if not (g['capability'] == 'storage.key-value' and g['api'] == 1)]
            manifest = document(store['waterfall.json'])
            manifest['requires'] = [g for g in manifest['requires'] if not (g['capability'] == 'storage.key-value' and g['api'] == 1)]
            store['waterfall.json'] = encoded(manifest)
        elif label == 'seventeenth-grant':
            while len(row['grants']) < 17:
                row['grants'].append({'capability': 'storage.key-value', 'api': 1, 'instance_id': 100 + len(row['grants'])})
        elif label == 'corrupt-app-elf': store['waterfall.elf'] = b'not an ELF'
        elif label == 'corrupt-provider-elf': store['s3-radio-iq/driver.elf'] = b'not an ELF'
        elif label == 'provider-storage-theft':
            next(r for r in boot['drivers'] if r['manifest'] == 'ble-hid/manifest.json')['key_value'][0]['namespace'] = 13
        elif label == 'extra-store-member': store['unexpected.json'] = b'{}'
        else:
            board = document(store['board.json']);board['revision'] = 'changed'
            store['board.json'] = encoded(board)
        store['boot.json'] = encoded(boot)
        yield label, store
    for label in ('broadcast-private-namespace-theft', 'broadcast-provider-missing',
                  'broadcast-elf-corrupt', 'retained-wake-instance', 'realtime-instance'):
        store = dict(following)
        boot = document(store['boot.json'])
        if label == 'broadcast-private-namespace-theft':
            row = next(r for r in boot['drivers'] if r['manifest'] == 'broadcast/manifest.json')
            row['key_value'] = [{'key': 'stolen', 'namespace': 13, 'access': 'read-write'}]
            manifest = document(store['broadcast/manifest.json'])
            if not any(r['capability'] == 'storage.key-value.bound' for r in manifest['requires']):
                manifest['requires'].append({'capability': 'storage.key-value.bound', 'api': 1})
            store['broadcast/manifest.json'] = encoded(manifest)
        elif label == 'broadcast-provider-missing':
            boot['drivers'] = [r for r in boot['drivers'] if r['manifest'] != 'broadcast/manifest.json']
        elif label == 'broadcast-elf-corrupt':
            store['broadcast/driver.elf'] = b'not an ELF'
        else:
            cap = 'runtime.retained-wake' if label == 'retained-wake-instance' else 'runtime.realtime-control'
            row = next(r for r in boot['app_capabilities'] if r['manifest'] == 'default.json')
            next(g for g in row['grants'] if g['capability'] == cap)['instance_id'] = 1
        store['boot.json'] = encoded(boot)
        yield label, store


def cohort_request(identity, firmware, bootfs, active_store):
    return {**{k: identity[k] for k in ('product', 'version', 'runtime_version', 'source_repo',
                                        'source_revision', 'layout', 'store_abi', 'firmware_size', 'firmware_sha256')},
            'store_size': len(bootfs), 'store_sha256': sha(bootfs), 'sha256': sha(firmware + bootfs),
            'active_store_sha256': sha(active_store)}


def _write_store(path, files):
    for name, raw in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)


def _unchanged_store(path, files):
    require({p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*') if p.is_file()} == files,
            'Native proof changed an immutable VFS input')


def prove(origin, native, following, payload, runtime, *, installed_runtime, installed_native, scope='complete-runtime-features-candidate', apps_dir=None):
    RUNTIME_SOURCE = native['record']['source_sha']
    INSTALLED_RUNTIME_SOURCE = origin['runtime_source']
    INSTALLED_RUNTIME_VERSION = origin['identity']['runtime_version']
    require(scope == 'complete-runtime-features-candidate', 'Only a complete fresh feature artifact can qualify')
    firmware, elf = native['blobs']['firmware.bin'], native['blobs']['firmware.elf']
    require(payload[:len(firmware)] == firmware and len(payload) == len(firmware) + STORE_BYTES,
            'RF proof payload must be exact verified native followed by bootfs')
    bootfs = payload[len(firmware):]
    require(read_image(bootfs, STORE_BYTES) == following, 'RF proof store differs from actual OTA bytes')
    identity = parse(following['cohort.json'])
    verify_identity(identity, firmware, version=VERSION, runtime_version=RUNTIME_VERSION)
    app_archive = None
    if scope == 'complete-runtime-features-candidate':
        require(apps_dir is not None, 'Complete RF proof requires the actual full target app artifact')
        from current_apps_overlay import verify as verify_apps
        files, apps = verify_apps(apps_dir, identity['source_revision'], profile='runtime-features')
        require(all(following.get(name) == raw for name, raw in files.items())
                and document(following['boot.json']) == apps['boot'], 'RF proof target differs from complete app artifact')
        app_archive = metadata((Path(apps_dir) / 'current-apps.zip').read_bytes())
    require(origin['identity']['version'] == '1.0.11' and origin['full'][0x10000:0x10000 + len(installed_native['blobs']['firmware.bin'])] == installed_native['blobs']['firmware.bin'],
            'RF proof origin is not the accepted native/source cohort')
    check_disk(Path(tempfile.gettempdir()))
    results, rejections = [], []
    with tempfile.TemporaryDirectory(prefix='watch-rf-transaction-') as temporary, host_sanitizer_environment():
        root = Path(temporary)
        graph_dir = root / 'graph';graph_dir.mkdir()
        graph = compile_harness(installed_runtime, graph_dir / 'admit', True, installed_native['blobs']['firmware.elf'])
        target_graph_dir = root / 'target-graph';target_graph_dir.mkdir()
        target_graph = compile_harness(runtime, target_graph_dir / 'admit', True, elf)
        installed = admission(graph, origin['store'], following)
        candidate_self = admission(target_graph, following, following)
        for label, bad in negative_stores(origin['store'], following):
            rejections.append({'scenario': label, **admission(graph, origin['store'], bad, False)})
        transaction = compile_transaction(installed_runtime, root / 'installed-transaction-build', INSTALLED_RUNTIME_VERSION,
                                          fixture=TRANSACTION_FIXTURE)
        target_transaction = compile_transaction(runtime, root / 'target-transaction-build', RUNTIME_VERSION,
                                                 fixture=TRANSACTION_FIXTURE)
        original = bytearray(origin['full'])
        for start, length, salt in ((0x9000, 0x6000, 37), (0x270000, 0x80000, 173)):
            original[start:start + length] = bytes((i * 67 + (i >> 8) + salt) % 256 for i in range(length))
        original = bytes(original)
        initial = root / 'accepted-with-persisted-data.bin';initial.write_bytes(original)
        asset = root / 'tested-ota.bin';asset.write_bytes(payload)
        snapshot = root / 'snapshot.bin'
        active_path, candidate_path = root / 'accepted-store', root / 'candidate-store'
        _write_store(active_path, origin['store']);_write_store(candidate_path, following)
        for bank, active, inactive in ((0, active_path, candidate_path), (1, candidate_path, active_path)):
            vfs = root / ('vfs' + str(bank));vfs.mkdir()
            (vfs / 'bootfs').symlink_to(active, target_is_directory=True)
            (vfs / 'updatefs').symlink_to(inactive, target_is_directory=True)
        request_path = root / 'request.json'
        request_path.write_bytes(encoded(cohort_request(identity, firmware, bootfs, origin['full'][0x2f0000:0x800000])))

        def execute(input_path, scenario, label, active=0):
            check_disk(root, 0)
            proof_path = root / 'process-proof.json'
            result = subprocess.run([str(target_transaction if active else transaction), str(input_path), str(asset), str(len(firmware)),
                                     str(active), scenario, str(snapshot), str(proof_path),
                                     str(root / ('vfs' + str(active))), str(request_path)],
                                    text=True, capture_output=True, timeout=120,
                                    env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
            require(result.returncode == 0, 'RF native transaction failed: ' + label + '\n' + result.stderr)
            data = snapshot.read_bytes();check_preserved(original, data)
            proof = document(proof_path.read_bytes())
            require(proof['nvs_appdata_preserved'] and proof['previous_pair_preserved'] and
                    proof['target_executed'] is False, 'RF native proof preservation/scope differs')
            proof.update(label=label, executing_runtime_source=RUNTIME_SOURCE if active else INSTALLED_RUNTIME_SOURCE,
                         executing_runtime_version=RUNTIME_VERSION if active else INSTALLED_RUNTIME_VERSION,
                         snapshot_sha256=sha(data), nvs_sha256=sha(data[0x9000:0xf000]),
                         appdata_sha256=sha(data[0x270000:0x2f0000]))
            if proof.get('selected'):
                require(data[0x800000:0x800000 + len(firmware)] == firmware and
                        data[0xae0000:0xff0000] == bootfs, 'Selected RF pair differs from admitted bytes')
            return proof

        for scenario in SCENARIOS:
            first = execute(initial, scenario, scenario);results.append(first)
            if first['selected']:
                results.append(execute(snapshot, 'boot', scenario + '-candidate-pending-boot', 1))
                if scenario != 'success':
                    results.append(execute(snapshot, 'boot-reject', scenario + '-candidate-rejected', 1))
                    require(results[-1]['rollback_calls'] == 1, 'Pending RF candidate did not request rollback')
            if scenario != 'success':
                results.append(execute(snapshot, 'boot', scenario + '-prior-reboot', 0))
                retry = execute(snapshot, 'success', scenario + '-retry', 0);results.append(retry)
                require(retry['selected'], 'RF retry did not select complete pair')
                results.append(execute(snapshot, 'boot', scenario + '-retry-pending-boot', 1))
            results.append(execute(snapshot, 'boot-healthy', scenario + '-candidate-valid-restart', 1))
            print('RF native API, preservation and reboot/retry passed: ' + scenario, flush=True)
        _unchanged_store(active_path, origin['store']);_unchanged_store(candidate_path, following)
        require(initial.read_bytes() == original and asset.read_bytes() == payload, 'RF proof changed bound image/payload inputs')
    record = {'schema': 1, 'scope': scope, 'complete_target_artifact': scope == 'complete-runtime-features-candidate',
              'runtime_source': RUNTIME_SOURCE, 'runtime_version': RUNTIME_VERSION,
              'installed_runtime_source': INSTALLED_RUNTIME_SOURCE, 'installed_runtime_version': INSTALLED_RUNTIME_VERSION,
              'installed_native_elf': metadata(installed_native['blobs']['firmware.elf']),
              'source_kind': origin['kind'], 'source_physical_acceptance_claimed': origin['physical_acceptance_claimed'],
              'source_initial_image': metadata(origin['full']), 'source_cohort': origin['identity'],
              'target_cohort': identity, 'native_elf': metadata(elf), 'payload': metadata(payload),
              'app_archive': app_archive,
              'accepted_store_sha256': store_digest(origin['store']), 'candidate_store_sha256': store_digest(following),
              'installed_runtime_admission': installed, 'target_self_admission': candidate_self,
              'rejections': rejections, 'scenarios': list(SCENARIOS), 'transactions': results,
              'nvs_sha256': sha(original[0x9000:0xf000]), 'appdata_sha256': sha(original[0x270000:0x2f0000]),
              'host_optimization': 'compiler-default-O0', 'native_api_used': True, 'modeled_host_app_active': True, 'modeled_idf_flash_vfs_selection': True,
              'physical_flash_tls_spiffs_and_target_instructions_executed': False,
              'device_health_confirmation_executed': False, 'sanitized': os.environ.get('SANITIZE') == '1',
              'transaction_fixture': metadata(TRANSACTION_FIXTURE.read_bytes()),
              'admission_fixture': metadata((ROOT / 'tests/runtime_store_admission.cpp').read_bytes())}
    validate_proof(record, origin, following, payload, native, complete=scope == 'complete-runtime-features-candidate')
    return record


def validate_proof(record, origin, following, payload, native, *, complete=True):
    RUNTIME_SOURCE = native['record']['source_sha']
    INSTALLED_RUNTIME_SOURCE = origin['runtime_source']
    INSTALLED_RUNTIME_VERSION = origin['identity']['runtime_version']
    require(complete and record['installed_runtime_source'] == INSTALLED_RUNTIME_SOURCE
            and record['installed_runtime_version'] == INSTALLED_RUNTIME_VERSION, 'Installed Runtime identity differs')
    require(record['schema'] == 1 and record['complete_target_artifact'] is complete
            and record['scope'] == ('complete-runtime-features-candidate' if complete else 'accepted-harness-self-test-only'),
            'RF proof scope does not qualify this artifact')
    require((record.get('app_archive') is not None) == complete, 'RF complete artifact custody missing or overstated')
    require(record.get('modeled_host_app_active') is True and record.get('modeled_idf_flash_vfs_selection') is True
            and record.get('physical_flash_tls_spiffs_and_target_instructions_executed') is False
            and record.get('device_health_confirmation_executed') is False,
            'RF proof execution/model boundaries differ')
    require(record['runtime_source'] == RUNTIME_SOURCE and record['runtime_version'] == RUNTIME_VERSION
            and record['native_elf'] == metadata(native['blobs']['firmware.elf'])
            and record['source_initial_image'] == metadata(origin['full'])
            and record['source_cohort'] == origin['identity'] and record['target_cohort'] == parse(following['cohort.json'])
            and record['payload'] == metadata(payload), 'RF transaction proof bytes/source differ')
    require(record['source_kind'] == origin['kind'] and record['source_physical_acceptance_claimed'] is origin['physical_acceptance_claimed'], 'Source qualification differs')
    require(record['transaction_fixture'] == metadata(TRANSACTION_FIXTURE.read_bytes())
            and record['admission_fixture'] == metadata((ROOT / 'tests/runtime_store_admission.cpp').read_bytes()),
            'Feature proof fixture custody differs')
    require(record['host_optimization'] == 'compiler-default-O0', 'Wrong cutoff host compiler profile')
    require(record['scenarios'] == list(SCENARIOS) and record['native_api_used'] is True,
            'RF native API failure/reboot coverage is incomplete')
    require(record['accepted_store_sha256'] == store_digest(origin['store'])
            and record['candidate_store_sha256'] == store_digest(following), 'RF proof store digests differ')
    for key in ('installed_runtime_admission', 'target_self_admission'):
        proof = record[key]
        require(proof['prepared'] and proof['cohort_validated'] and not proof['hardware_calls']
                and not proof['storage_calls'] and proof['elf_count'] == sum(n.endswith('.elf') for n in following)
                and proof['candidate_store_sha256'] == record['candidate_store_sha256']
                and proof['active_store_sha256'] == (record['accepted_store_sha256'] if key == 'installed_runtime_admission'
                                                      else record['candidate_store_sha256']),
                'RF graph/ELF proof failed or differs: ' + key)
    transactions = {r['label']: r for r in record['transactions']}
    require(len(transactions) == len(record['transactions']), 'Duplicate RF transaction label')
    expected_labels = set()
    expected_processes = {}
    def process(label, scenario, bank, candidate, valid, active):
        expected_processes[label] = {'scenario': scenario, 'active_bank': bank, 'target_bank': 1 - bank,
                                     'active_is_candidate': candidate, 'host_idf_valid_state': valid,
                                     'modeled_host_app_active': active, 'native_api_used': active}
    for scenario in SCENARIOS:
        expected_labels |= {scenario, scenario + '-candidate-valid-restart'}
        process(scenario, scenario, 0, False, scenario != 'unconfirmed-source', True)
        process(scenario + '-candidate-valid-restart', 'boot-healthy', 1, True, True, False)
        first = transactions.get(scenario, {})
        require(first.get('native_api_used') is True and first.get('selected') is (scenario in SELECTED_SCENARIOS),
                'RF native API outcome differs: ' + scenario)
        if scenario in BAD_REQUESTS:
            require(first['writes'] == 0 and first['selectors'] == 0 and first['api_begin_result'] != 0,
                    'RF invalid request mutated flash or bypassed API gate')
        if scenario in SELECTED_SCENARIOS:
            expected_labels.add(scenario + '-candidate-pending-boot')
            process(scenario + '-candidate-pending-boot', 'boot', 1, True, False, False)
            if scenario != 'success':
                expected_labels.add(scenario + '-candidate-rejected')
                process(scenario + '-candidate-rejected', 'boot-reject', 1, True, False, False)
                require(transactions.get(scenario + '-candidate-rejected', {}).get('rollback_calls') == 1,
                        'RF candidate rollback proof missing')
        if scenario != 'success':
            expected_labels |= {scenario + suffix for suffix in ('-retry', '-prior-reboot', '-retry-pending-boot')}
            process(scenario + '-retry', 'success', 0, False, True, True)
            process(scenario + '-prior-reboot', 'boot', 0, False, True, False)
            process(scenario + '-retry-pending-boot', 'boot', 1, True, False, False)
            require(transactions.get(scenario + '-retry', {}).get('selected') is True
                    and scenario + '-prior-reboot' in transactions,
                    'RF failure did not prove old-pair reboot and successful retry: ' + scenario)
    require(set(transactions) == expected_labels, 'RF transaction/reboot result inventory differs')
    selected_snapshot = transactions['success']['snapshot_sha256']
    for row in transactions.values():
        require(all(row.get(key) == value for key, value in expected_processes[row['label']].items())
                and row['executing_runtime_source'] == (RUNTIME_SOURCE if row['active_bank'] else INSTALLED_RUNTIME_SOURCE)
                and row['executing_runtime_version'] == row['build_runtime_version'] ==
                    (RUNTIME_VERSION if row['active_bank'] else INSTALLED_RUNTIME_VERSION)
                and row.get('modeled_idf_selection') is True
                and re.fullmatch('[0-9a-f]{64}', row['snapshot_sha256']) is not None,
                'RF process label/state/source/snapshot binding differs: ' + row['label'])
        require(row['nvs_appdata_preserved'] and row['previous_pair_preserved']
                and row['nvs_sha256'] == record['nvs_sha256'] and row['appdata_sha256'] == record['appdata_sha256']
                and row['target_executed'] is False, 'RF transaction lost persistent bytes or overstated execution')
        require(row['hardware_calls'] == row['storage_calls'] == 0, 'RF proof touched a hardware/storage service')
        if row['selected']:
            require(row['native_api_used'] and row['production_graph_validator_used'] and row['graph_validated']
                    and row['selectors'] == 1 and row['active_bank'] == 0, 'RF selection bypassed production graph/native API')
            require(row['snapshot_sha256'] == selected_snapshot, 'RF successful retry selected different flash bytes')
        if row['label'].endswith('-candidate-valid-restart'):
            require(row['active_is_candidate'] and row['host_idf_valid_state'] and not row['rollback_calls'],
                    'RF confirmed candidate restart proof differs')
            require(row['snapshot_sha256'] == selected_snapshot, 'RF confirmed restart changed selected flash bytes')
    for scenario in SCENARIOS:
        first_snapshot = transactions[scenario]['snapshot_sha256']
        for suffix in ('-candidate-pending-boot', '-candidate-rejected', '-prior-reboot'):
            label = scenario + suffix
            if label in transactions:
                require(transactions[label]['snapshot_sha256'] == first_snapshot,
                        'RF read-only reboot/rollback changed flash snapshot: ' + label)
        label = scenario + '-retry-pending-boot'
        if label in transactions:
            require(transactions[label]['snapshot_sha256'] == selected_snapshot,
                    'RF retry pending boot changed selected flash snapshot')
    expected_rejections = {label for label, _ in negative_stores(origin['store'], following)}
    require({r['scenario'] for r in record['rejections']} == expected_rejections
            and len(record['rejections']) == len(expected_rejections), 'RF negative target admission inventory differs')
    for rejection in record['rejections']:
        require(rejection['prepared'] and not rejection['cohort_validated'] and
                rejection['hardware_calls'] == rejection['storage_calls'] == 0,
                'RF invalid target was admitted')


def prove_both(origin, native, following, payload, runtime, **kwargs):
    """Qualify the same exact image in ordinary and ASan/UBSan production paths."""
    previous = os.environ.get('SANITIZE')
    modes = {}
    try:
        for name, value in (('ordinary', '0'), ('asan-ubsan', '1')):
            os.environ['SANITIZE'] = value
            modes[name] = prove(origin, native, following, payload, runtime, **kwargs)
    finally:
        if previous is None:
            os.environ.pop('SANITIZE', None)
        else:
            os.environ['SANITIZE'] = previous
    result = {'schema': 1, 'scope': 'exact-feature-image-dual-mode', 'modes': modes}
    validate_both(result, origin, following, payload, native)
    return result


def validate_both(record, origin, following, payload, native):
    require(record['schema'] == 1 and record['scope'] == 'exact-feature-image-dual-mode'
            and set(record['modes']) == {'ordinary', 'asan-ubsan'}, 'Both host proof modes are required')
    for name, sanitized in (('ordinary', False), ('asan-ubsan', True)):
        proof = record['modes'][name]
        require(proof['sanitized'] is sanitized, 'Host sanitizer mode differs')
        validate_proof(proof, origin, following, payload, native)
    require({k: v for k, v in record['modes']['ordinary'].items() if k != 'sanitized'} ==
            {k: v for k, v in record['modes']['asan-ubsan'].items() if k != 'sanitized'},
            'Ordinary and sanitized exact-image results differ')

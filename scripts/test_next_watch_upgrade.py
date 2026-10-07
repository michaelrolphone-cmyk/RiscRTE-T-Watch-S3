#!/usr/bin/env python3
"""Prove one-stage source-bound admission and PairedBank persistence offline."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile

from build_current_watch_cohort import (ROOT, RUNTIME, RUNTIME_VERSION, VERSION, STORE_BYTES,
    NEW_APPS, read_previous, read_native, runtime_evidence, require, sha, encoded, document, metadata, check_policy, check_requirements)
from current_cohort import parse, verify, package
from check_runtime_store_admission import compile_harness, store_digest
from read_only_spiffs import read_image

SCENARIOS = ('power-begin', 'power-native', 'power-store', 'cancel', 'corrupt-native',
             'corrupt-store', 'wrong-runtime-request', 'power-verify-native', 'power-verify-store', 'power-ready',
             'activation-unknown', 'rollback', 'power-selected', 'success')


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def compile_transaction(runtime, build, version, fixture=None):
    runtime, build = Path(runtime).resolve(), Path(build).resolve()
    build.mkdir(parents=True)
    (build / 'RiscBuildIdentity.h').write_text('#pragma once\n#define RISC_BUILD_VERSION "' + version + '"\n')
    includes = [build] + [runtime / p for p in ('test', 'test/native_bank_stubs', 'test/drivers/stubs',
        'lib/elf_loader/include', 'src', 'sdk/app', 'sdk/driver', 'sdk/hardware', 'lib/ArduinoJson/src')]
    flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') == '1' else []
    inc = ['-I' + str(p) for p in includes]
    run('cc', *flags, '-std=c11', *inc, '-c', runtime / 'lib/elf_loader/src/esp_elf_validate.c', '-o', build / 'validate.o')
    sources = [runtime / p for p in ('src/bootstrap/Json.cpp', 'src/bootstrap/Board.cpp', 'src/bootstrap/Runtime.cpp',
        'src/runtime/drivers/ProviderGraphV2.cpp', 'src/runtime/drivers/ProviderModuleV2.cpp',
        'src/runtime/update/PairedBank.cpp', 'src/runtime/update/StoreAudit.cpp')]
    executable = build / 'transaction'
    run('c++', *flags, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
        '-Wno-deprecated-declarations', '-DRISC_PAIRED_BANKS=1', '-DRISC_PAIRED_APP_DATA=1',
        '-rdynamic', '-no-pie', '-Wl,--wrap=fopen,--wrap=opendir,--wrap=stat,--wrap=lstat',
        *inc, *sources, fixture or ROOT / 'tests/next_watch_upgrade/native_transaction.cpp', build / 'validate.o',
        '-lcrypto', '-ldl', '-o', executable)
    return executable


def admission(executable, active, candidate, expected=True):
    with tempfile.TemporaryDirectory(prefix='next-watch-admission-') as temporary:
        root = Path(temporary)
        for label, files in (('active', active), ('candidate', candidate)):
            for name, data in files.items():
                path = root / label / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        result = run(executable, root / 'active', root / 'candidate', capture_output=True, text=True, timeout=90)
        outcome = document(result.stdout)
        require(outcome['prepared'] and outcome['cohort_validated'] is expected
                and not outcome['hardware_calls'] and not outcome['storage_calls'], 'Unexpected production admission: ' + str(outcome))
        for label, files in (('active', active), ('candidate', candidate)):
            actual = {p.relative_to(root / label).as_posix(): p.read_bytes()
                      for p in (root / label).rglob('*') if p.is_file()}
            require(actual == files, 'Production admission changed input bytes')
    return {**outcome, 'active_store_sha256': store_digest(active), 'candidate_store_sha256': store_digest(candidate)}


def negative_stores(previous, following):
    boot = document(following['boot.json'])
    def changed(label, modify):
        result = dict(following)
        value = copy.deepcopy(boot)
        modify(value, result)
        result['boot.json'] = encoded(value)
        return label, result
    def new_row(value):
        return next(row for row in value['app_capabilities'] if row['manifest'] == 'ble_buttons.json')
    yield changed('missing-migration', lambda b, f: b.pop('cohort_migration'))
    yield changed('wrong-origin-source', lambda b, f: b['cohort_migration']['from'].update(source_revision='0' * 40))
    yield changed('wrong-origin-version', lambda b, f: b['cohort_migration']['from'].update(version='1.0.3'))
    yield changed('wrong-target-version', lambda b, f: b['cohort_migration']['to'].update(version='1.0.6'))
    yield changed('unused-migration-entry', lambda b, f: b['cohort_migration']['shared_key_value'].append(
        {'application_id': 'unlisted', 'api': 1, 'namespace': 1}))
    yield changed('missing-migration-entry', lambda b, f: b['cohort_migration']['shared_key_value'].pop())
    def private(b, f):
        for grant in new_row(b)['grants']:
            if grant['capability'] == 'storage.key-value' and grant['instance_id'] == 11:
                grant['instance_id'] = 3
    yield changed('new-app-steals-private-kv', private)
    def private_migration(b, f):
        for grant in new_row(b)['grants']:
            if grant['capability'] == 'storage.key-value' and grant['instance_id'] == 1:
                grant['instance_id'] = 3
        for entry in b['cohort_migration']['shared_key_value']:
            if entry['application_id'] == 'ble_buttons':
                entry['namespace'] = 3
    yield changed('migration-cannot-share-private-kv', private_migration)
    def provider_private(b, f):
        for key in b['drivers'][-1]['key_value']:
            key['namespace'] = 4
    yield changed('new-provider-steals-private-kv', provider_private)
    def app_data(b, f):
        new_row(b)['grants'].append({'capability': 'storage.app-data', 'api': 1, 'instance_id': 1})
        value = document(f['ble_buttons.json'])
        value['requires'].append({'capability': 'storage.app-data', 'api': 1})
        f['ble_buttons.json'] = encoded(value)
    yield changed('new-app-steals-app-data', app_data)
    def identity(b, f):
        value = document(f['timecard.json']);value['id'] = 'other-owner';f['timecard.json'] = encoded(value)
    yield changed('prior-app-owner-reassigned', identity)
    def old_provider(b, f):
        value = document(f['alarm-service/manifest.json']);value['id'] = 'other-provider'
        f['alarm-service/manifest.json'] = encoded(value)
    yield changed('prior-provider-owner-reassigned', old_provider)
    def changed_board(b, f):
        board = document(f['board.json']);board['devices'][0]['instance_id'] = 123
        f['board.json'] = encoded(board)
    yield changed('hardware-change', changed_board)
    yield changed('extra-store-member', lambda b, f: f.update({'unexpected.json': b'{}'}))
    yield changed('corrupt-app-elf', lambda b, f: f.update({'ble_buttons.elf': b'not an ELF'}))


def check_preserved(original, image, source_bank=0):
    require(len(image) == len(original) == 0x1000000, 'Flash image size changed')
    require(source_bank in (0, 1), 'Invalid source bank')
    for start, length in ((0, 0x10000), (0x270000, 0x80000),
                          ((0x10000, 0x800000)[source_bank], 0x260000),
                          ((0x2f0000, 0xae0000)[source_bank], STORE_BYTES),
                          (0xff2000 + source_bank * 4096, 4096)):
        require(image[start:start + length] == original[start:start + length],
                'Persisted bytes or source rollback pair changed at ' + hex(start))


def transactions(previous_runtime, runtime, full, payload, firmware, native, output, *, source_bank=0):
    require(source_bank in (0, 1), 'Invalid source bank')
    target_bank = 1 - source_bank
    installed_executable = compile_transaction(previous_runtime, output / 'installed-native-build', RUNTIME_VERSION)
    candidate_version = native['firmware_version']
    candidate_executable = compile_transaction(runtime, output / 'candidate-native-build', candidate_version)
    original = bytearray(full)
    # Nonuniform sentinels catch shifts, partial writes and accidental blanking.
    for start, length, salt in ((0x9000, 0x6000, 37), (0x270000, 0x80000, 173)):
        original[start:start + length] = bytes((i * 67 + (i >> 8) + salt) % 256 for i in range(length))
    original = bytes(original)
    initial = output / 'source-with-persisted-data.bin';initial.write_bytes(original)
    asset = output / 'tested-cohort.bin';asset.write_bytes(payload)
    def execute(input_path, scenario, label, active=source_bank):
        image, proof = output / (label + '.bin'), output / (label + '.json')
        executable = candidate_executable if active == target_bank else installed_executable
        run(executable, input_path, asset, len(firmware), active, scenario, image, proof,
            candidate_version, timeout=120, env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
        data = image.read_bytes();check_preserved(original, data, source_bank)
        result = document(proof.read_bytes())
        result.update(label=label, executing_runtime_source=native['source_sha'] if active == target_bank else RUNTIME,
                      executing_runtime_version=candidate_version if active == target_bank else RUNTIME_VERSION,
                      snapshot_sha256=sha(data), nvs_sha256=sha(data[0x9000:0xf000]),
                      appdata_sha256=sha(data[0x270000:0x2f0000]))
        return image, result
    results = []
    for scenario in SCENARIOS:
        image, result = execute(initial, scenario, scenario);results.append(result)
        # Fresh processes discard in-memory state and compile the native version
        # actually running in the selected bank. No candidate code handles the
        # installed transaction or the restored old-bank reboot.
        if result['selected']:
            image, pending_boot = execute(image, 'boot', scenario + '-candidate-pending-boot', active=target_bank)
            results.append(pending_boot)
            if scenario != 'success':
                image, rejection = execute(image, 'boot-reject', scenario + '-candidate-rejected', active=target_bank)
                results.append(rejection)
        if scenario != 'success':
            image, result = execute(image, 'boot', scenario + '-prior-reboot');results.append(result)
            image, result = execute(image, 'success', scenario + '-retry');results.append(result)
            candidate = image.read_bytes()
            firmware_offset = (0x10000, 0x800000)[target_bank]
            store_offset = (0x2f0000, 0xae0000)[target_bank]
            require(candidate[firmware_offset:firmware_offset + len(firmware)] == firmware
                    and candidate[store_offset:store_offset + STORE_BYTES] == payload[len(firmware):], 'Retry pair differs')
            image, result = execute(image, 'boot', scenario + '-retry-pending-boot', active=target_bank);results.append(result)
        image, result = execute(image, 'boot-healthy', scenario + '-candidate-valid-restart', active=target_bank)
        results.append(result)
        # Every snapshot has been consumed by reboot/retry. Preserve digest and
        # comparison results while bounding disk use to the current scenario.
        for snapshot in output.glob(scenario + '*.bin'):
            snapshot.unlink()
    initial.unlink()
    asset.unlink()
    return results


def prove(previous_bundle, native_dir, runtime, output, candidate_bundle=None, *,
          previous_runtime, previous_native_dir):
    output = Path(output).resolve()
    require(not output.exists(), 'Output must be new')
    full, previous, old_identity, old_firmware, old_elf, old_native = read_previous(
        previous_bundle, previous_native_dir, previous_runtime)
    firmware, elf, native = read_native(native_dir, runtime)
    evidence = runtime_evidence(previous_runtime, runtime, old_native, native)
    if candidate_bundle is None:
        # Explicit harness/custody check only. Never reported as a 1.0.5 acceptance.
        require(native['source_sha'] == RUNTIME and firmware == old_firmware and elf == old_elf,
                '--check-installed requires exact accepted native inputs, not a candidate upgrade')
        following = previous
        payload, _ = package(old_identity, firmware, full[0x2f0000:0x800000])
        policy = None
        scope = 'accepted-1.0.4-harness-self-test-only'
    else:
        root = Path(candidate_bundle)
        proof = document((root / 'next-watch-build-proof.json').read_bytes())
        requirements_bytes = (root / 'runtime-requirements.json').read_bytes()
        requirements = check_requirements(document(requirements_bytes), native)
        require(proof.get('runtime_requirements') == requirements
                and proof.get('runtime_requirements_sha256') == sha(requirements_bytes),
                'Candidate Runtime requirements proof/bytes differ')
        payload = (root / ('twatch-s3-cohort-' + VERSION + '.bin')).read_bytes()
        require(payload[:len(firmware)] == firmware and len(payload) == len(firmware) + STORE_BYTES,
                'Payload must contain exact native followed by bootfs only')
        store = payload[len(firmware):]
        following = read_image(store, STORE_BYTES)
        require((root / 'bootfs.bin').read_bytes() == store, 'Candidate bootfs differs')
        extracted = {p.relative_to(root / 'store').as_posix(): p.read_bytes()
                     for p in (root / 'store').rglob('*') if p.is_file()}
        require(extracted == following, 'Candidate extracted store differs')
        identity = parse(following['cohort.json'])
        verify(identity, firmware, version=VERSION, runtime_version=native['firmware_version'],
               source_revision=proof['watch_source'])
        _, ota = package(identity, firmware, store)
        require(proof['configuration']['sources']['runtime']['commit'] == native['source_sha'],
                'Candidate proof configuration names a different Runtime source')
        require(native['firmware_version'] == RUNTIME_VERSION or proof.get('runtime_evidence') == evidence,
                'Candidate Runtime provenance evidence missing or different')
        require(proof['ota'] == ota and proof['target_cohort'] == identity
                and proof['source_cohort'] == old_identity
                and proof['native_elf_sha256'] == sha(elf)
                and proof.get('runtime_evidence', evidence) == evidence
                and proof['files'] == {n: metadata(b) for n, b in following.items()}, 'Candidate proof/bytes differ')
        policy = check_policy(previous, following)
        scope = 'one-stage-accepted-1.0.4-to-1.0.5'
    output.mkdir(parents=True)
    graph_dir = output / 'graph-build';graph_dir.mkdir()
    harness = compile_harness(previous_runtime, graph_dir / 'admit-installed', True, old_elf)
    graph = admission(harness, previous, following)
    candidate_graph_dir = output / 'candidate-graph-build';candidate_graph_dir.mkdir()
    candidate_harness = compile_harness(runtime, candidate_graph_dir / 'admit-candidate', True, elf)
    self_graph = admission(candidate_harness, following, following)
    negatives = []
    if candidate_bundle is not None:
        for label, candidate in negative_stores(previous, following):
            outcome = admission(harness, previous, candidate, False)
            negatives.append({'scenario': label, **outcome})
    results = transactions(previous_runtime, runtime, full, payload, firmware, native, output)
    record = {'schema': 1, 'scope': scope, 'installed_runtime': RUNTIME, 'candidate_runtime': native['source_sha'],
              'runtime_evidence': evidence,
              'runtime_requirements': requirements if candidate_bundle is not None else None,
              'runtime_requirements_sha256': sha(requirements_bytes) if candidate_bundle is not None else None,
              'previous_native_sha256': sha(old_firmware),
              'previous_native_elf_sha256': sha(old_elf),
              'source_cohort': old_identity, 'target_cohort': parse(following['cohort.json']),
              'source_initial_image_sha256': sha(full), 'native_sha256': sha(firmware),
              'native_elf_sha256': sha(elf), 'cohort_sha256': sha(payload),
              'policy': policy, 'installed_runtime_admission': graph, 'target_self_admission': self_graph,
              'rejections': negatives, 'transactions': results,
              'one_stage_cohort_only': candidate_bundle is not None,
              'physical_flash_tls_spiffs_and_target_instructions_executed': False,
              'device_health_confirmation_executed': False}
    (output / 'next-watch-upgrade-proof.json').write_bytes(encoded(record))
    print(scope + ': graph/ELF admission and ' + str(len(results)) + ' transaction/reboot/retry checks passed')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('previous-bundle', 'native-dir', 'runtime', 'previous-native-dir', 'previous-runtime', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--candidate-bundle', type=Path)
    group.add_argument('--check-installed', action='store_true', help='Harness self-test only; not 1.0.5 acceptance')
    args = parser.parse_args()
    prove(args.previous_bundle, args.native_dir, args.runtime, args.output, args.candidate_bundle,
          previous_runtime=args.previous_runtime, previous_native_dir=args.previous_native_dir)


if __name__ == '__main__':
    main()

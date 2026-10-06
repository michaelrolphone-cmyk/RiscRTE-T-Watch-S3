#!/usr/bin/env python3
"""Prove exact midpoint -> native bridge -> source-bound 1.0.6, entirely offline.

--check-fixture proves the harness with an earlier standard cohort, not acceptance
of a deliverable. All simulated flash snapshots are temporary and removed.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile

import build_next_watch_cohort as base
from check_runtime_store_admission import compile_harness, admit
from current_bootfs import build as build_store
from current_cohort import package, parse, verify
from midpoint_upgrade import (ROOT, VERSION, PROFILE, INSTALLED_RUNTIME, INSTALLED_VERSION,
    read_midpoint, read_standard_candidate, standard_proof_digest, adapt_candidate, check_policy,
    require, sha, encoded, document, metadata)
from test_next_watch_upgrade import (compile_transaction, admission, negative_stores,
                                     check_preserved, transactions, run)

INSTALLED_SYSTEM = '2d16d9dfa7abc50ce916eebc11d81423adef0000'
BRIDGE_SCENARIOS = ('power-begin', 'power-copy', 'power-download', 'cancel', 'corrupt',
                    'power-ready', 'activation-unknown', 'rollback', 'power-selected', 'success')


def bridge_transactions(installed_runtime, bridge_runtime, full, firmware, output):
    fixture = ROOT / 'tests/midpoint_upgrade/native_bridge.cpp'
    old = compile_transaction(installed_runtime, output / 'original-native-build', INSTALLED_VERSION, fixture)
    new = compile_transaction(bridge_runtime, output / 'bridge-native-build', base.RUNTIME_VERSION, fixture)
    original = bytearray(full)
    for start, length, salt in ((0x9000, 0x6000, 37), (0x270000, 0x80000, 173)):
        original[start:start + length] = bytes((i * 67 + (i >> 8) + salt) % 256 for i in range(length))
    original = bytes(original)
    results, final = [], None
    with tempfile.TemporaryDirectory(prefix='midpoint-bridge-flash-') as temporary:
        temporary = Path(temporary)
        initial, asset = temporary / 'source.bin', temporary / 'native.bin'
        initial.write_bytes(original);asset.write_bytes(firmware)
        def execute(input_file, scenario, label, active=0):
            image, proof = temporary / (label + '.bin'), output / (label + '.json')
            run(new if active else old, input_file, asset, len(firmware), active, scenario,
                image, proof, base.RUNTIME_VERSION, timeout=120,
                env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
            data = image.read_bytes();check_preserved(original, data)
            result = document(proof.read_bytes())
            result.update(label=label, executing_runtime_source=base.RUNTIME if active else INSTALLED_RUNTIME,
                          executing_runtime_version=base.RUNTIME_VERSION if active else INSTALLED_VERSION,
                          snapshot_sha256=sha(data), nvs_sha256=sha(data[0x9000:0xf000]),
                          appdata_sha256=sha(data[0x270000:0x2f0000]))
            results.append(result)
            return image, result
        for scenario in BRIDGE_SCENARIOS:
            image, result = execute(initial, scenario, scenario)
            if result['selected']:
                image, _ = execute(image, 'boot', scenario + '-bridge-pending', 1)
                if scenario != 'success':
                    image, _ = execute(image, 'boot-reject', scenario + '-bridge-rejected', 1)
            if scenario != 'success':
                image, _ = execute(image, 'boot', scenario + '-prior-reboot')
                image, _ = execute(image, 'success', scenario + '-retry')
                image, _ = execute(image, 'boot', scenario + '-retry-pending', 1)
            image, _ = execute(image, 'boot-healthy', scenario + '-bridge-valid', 1)
            final = image.read_bytes()
            require(final[0x800000:0x800000 + len(firmware)] == firmware
                    and final[0xae0000:0xff0000] == full[0x2f0000:0x800000],
                    'Bridge failed to retain exact midpoint store')
            for snapshot in temporary.glob(scenario + '*.bin'):
                snapshot.unlink()
    return final, results


def catalog_cases(system, previous_bundle, ota, output):
    base.checked_source(system, INSTALLED_SYSTEM)
    executable = output / 'installed-catalog'
    run('c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation',
        *['-I' + str(Path(system) / p) for p in ('Services/update', 'lib/PortableApps/include', 'lib/NativeApps/include')],
        ROOT / 'tests/midpoint_upgrade/catalog.cpp', '-o', executable)
    # A parser fixture only: top-level provisioning-image metadata is irrelevant
    # to OTA parsing and is never represented as a publishable release record.
    fixture = document((Path(previous_bundle) / 'release-index.stage2-cohort.json').read_bytes())
    record = fixture['firmware'];record['version'] = VERSION;record['tag'] = 'firmware-v' + VERSION
    record['asset'] = 'twatch-s3-launcher-' + VERSION + '.bin'
    record['url'] = 'https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/releases/download/' + record['tag'] + '/' + record['asset']
    record['ota'] = ota
    results = []
    with tempfile.TemporaryDirectory(prefix='midpoint-catalog-fixtures-') as temporary:
        path = Path(temporary) / 'index.json'
        cases = [('canonical', fixture, True)]
        for suffix in ('-from-midpoint-27fba6f2', '-midpoint', '-1.0.5'):
            value = copy.deepcopy(fixture);row = value['firmware']['ota']
            row['asset'] = 'twatch-s3-cohort-' + VERSION + suffix + '.bin'
            row['url'] = ota['url'].rsplit('/', 1)[0] + '/' + row['asset']
            cases.append(('rejected-suffix' + suffix, value, False))
        wrong = copy.deepcopy(fixture);wrong['firmware']['ota']['url'] = ota['url'].replace('firmware-v1.0.6/', 'firmware-v1.0.5/')
        cases.append(('wrong-release-url', wrong, False))
        for label, value, accepted in cases:
            path.write_bytes(encoded(value))
            run(executable, path, 'accept' if accepted else 'reject', timeout=30)
            results.append({'scenario': label, 'accepted': accepted, 'parser_assertions_passed': True})
    return {'installed_system_source': INSTALLED_SYSTEM, 'synthetic_parser_envelope_only': True,
            'publishable_catalog_emitted': False, 'cases': results}


def read_variant(bundle, standard, firmware, elf, native, standard_proof, requirements_bytes, evidence,
                 identity, custody, standard_proof_sha256):
    root = Path(bundle)
    proof = document((root / 'midpoint-watch-build-proof.json').read_bytes())
    payload = (root / ('twatch-s3-cohort-' + VERSION + '.bin')).read_bytes()
    require(payload[:len(firmware)] == firmware and len(payload) == len(firmware) + base.STORE_BYTES,
            'Midpoint payload must contain exact native followed by bootfs')
    store = payload[len(firmware):]
    from read_only_spiffs import read_image
    following = read_image(store, base.STORE_BYTES)
    require((root / 'bootfs.bin').read_bytes() == store and following == adapt_candidate(standard, firmware, VERSION),
            'Midpoint store changed outside bounded metadata')
    extracted = {p.relative_to(root / 'store').as_posix(): p.read_bytes()
                 for p in (root / 'store').rglob('*') if p.is_file()}
    require(extracted == following, 'Midpoint extracted store differs')
    _, ota = package(parse(following['cohort.json']), firmware, store)
    verify(parse(following['cohort.json']), firmware, version=VERSION,
           runtime_version=base.CANDIDATE_VERSION, source_revision=standard_proof['watch_source'])
    require(proof['schema'] == 1 and proof['profile'] == PROFILE and proof['version'] == VERSION
            and proof['watch_source'] == standard_proof['watch_source']
            and proof['source_cohort'] == identity and proof['target_cohort'] == parse(following['cohort.json'])
            and proof['source_initial_image_sha256'] == custody['initial_image_sha256']
            and proof['source_store_sha256'] == custody['store_sha256']
            and proof['source_baseline_sha256'] == sha((ROOT / 'apps/midpoint-origin-baseline.json').read_bytes())
            and proof['original_installed_runtime'] == INSTALLED_RUNTIME
            and proof['standard_candidate_version'] == base.VERSION
            and proof['standard_candidate_sha256'] == standard_proof['ota']['sha256']
            and proof['standard_candidate_proof_sha256'] == standard_proof_sha256
            and proof['standard_configuration'] == standard_proof['configuration']
            and proof['native_elf_sha256'] == sha(elf) and proof['runtime_evidence'] == evidence
            and proof['runtime_requirements'] == standard_proof['runtime_requirements']
            and proof['runtime_requirements_sha256'] == sha(requirements_bytes)
            and (root / 'runtime-requirements.json').read_bytes() == requirements_bytes
            and proof['ota'] == ota and proof['files'] == {n: metadata(b) for n, b in following.items()}
            and proof['licenses_sha256'] == sha((root / 'LICENSES.zip').read_bytes()),
            'Midpoint proof or custody differs')
    require(proof['bridge']['runtime_source'] == base.RUNTIME
            and proof['bridge']['runtime_version'] == base.RUNTIME_VERSION
            and proof['bridge']['native_sha256'] == base.NATIVE_SHA
            and proof['bridge']['native_elf_sha256'] == base.ELF_SHA
            and proof['bridge']['retained_source_revision'] == identity['source_revision']
            and proof['bridge']['retained_cohort_version'] == '1.0.2'
            and proof['bridge']['retained_store_sha256'] == custody['store_sha256'],
            'Bridge proof identity differs')
    return following, payload, ota, proof


def prove(installed_bin, previous_bundle, candidate_bundle, native_dir, runtime, output, *,
          installed_runtime, previous_runtime, previous_native_dir, installed_system,
          midpoint_bundle=None, check_fixture=False):
    require((midpoint_bundle is not None) != bool(check_fixture), 'Select final bundle or explicit fixture-only mode')
    output = Path(output).resolve();require(not output.exists(), 'Output must be new')
    full, midpoint, identity, custody = read_midpoint(installed_bin, installed_runtime)
    _, prior, prior_identity, bridge, old_elf, old_native = base.read_previous(
        previous_bundle, previous_native_dir, previous_runtime)
    firmware, elf, native = base.read_native(native_dir, runtime)
    standard, standard_proof, requirements_bytes, evidence = read_standard_candidate(
        candidate_bundle, prior, prior_identity, old_native, native, firmware, elf, previous_runtime, runtime,
        expected_source=None if check_fixture else base.checked_source(ROOT))
    if midpoint_bundle is None:
        following = adapt_candidate(standard, firmware, VERSION)
        store, _ = build_store(following);payload, ota = package(parse(following['cohort.json']), firmware, store)
        proof = None
    else:
        following, payload, ota, proof = read_variant(midpoint_bundle, standard, firmware, elf, native,
            standard_proof, requirements_bytes, evidence, identity, custody,
            standard_proof_digest(candidate_bundle))
    policy = check_policy(midpoint, following, prior, standard, firmware, VERSION)
    if proof is not None:
        require(proof['policy'] == document(encoded(policy)), 'Midpoint policy proof differs')
        require(proof['native_candidate_sha256'] == sha((Path(native_dir) / 'candidate.json').read_bytes()),
                'Midpoint native candidate record differs')
        require((Path(midpoint_bundle) / 'LICENSES.zip').read_bytes() ==
                (Path(candidate_bundle) / 'LICENSES.zip').read_bytes(), 'Midpoint license archive differs')
    output.mkdir(parents=True)
    for name in ('original-graph', 'bridge-graph', 'candidate-graph'):(output / name).mkdir()
    original_boot = compile_harness(installed_runtime, output / 'original-graph/boot', True)
    original_admission = admit(original_boot, midpoint)
    harness = compile_harness(previous_runtime, output / 'bridge-graph/admit', True, old_elf)
    bridge_self = admission(harness, midpoint, midpoint)
    graph = admission(harness, midpoint, following)
    candidate = compile_harness(runtime, output / 'candidate-graph/admit', True, elf)
    self_graph = admission(candidate, following, following)
    rejections = []
    for label, changed in [('frozen-104-wrong-origin', prior), ('ordinary-105-wrong-origin', standard),
                            *negative_stores(midpoint, following)]:
        if label == 'wrong-target-version':
            changed = dict(changed);boot = document(changed['boot.json'])
            boot['cohort_migration']['to']['version'] = '1.0.7';changed['boot.json'] = encoded(boot)
        rejections.append({'scenario': label, **admission(harness, midpoint, changed, False)})
    for label, change in [('missing-waterfall-grant', lambda b: b['cohort_migration']['shared_key_value'].pop(0)),
                          ('wrong-midpoint-source', lambda b: b['cohort_migration']['from'].update(source_revision=base.SOURCE))]:
        changed = dict(following);boot = document(following['boot.json']);change(boot);changed['boot.json'] = encoded(boot)
        rejections.append({'scenario': label, **admission(harness, midpoint, changed, False)})
    catalog = catalog_cases(installed_system, previous_bundle, ota, output)
    bridge_dir = output / 'bridge-transactions';bridge_dir.mkdir()
    bridged, bridge_results = bridge_transactions(installed_runtime, previous_runtime, full, bridge, bridge_dir)
    final_dir = output / 'final-transactions';final_dir.mkdir()
    # Source is now the real bridge-selected bank 1. Runtime 0.1.34 installs the
    # final pair into bank 0; candidate reboot checks use Runtime 0.1.35.
    with tempfile.TemporaryDirectory(prefix='midpoint-final-flash-') as temporary:
        final_results = transactions(previous_runtime, runtime, bridged, payload, firmware, native,
                                     Path(temporary), source_bank=1)
    record = {'schema': 1, 'profile': PROFILE, 'version': VERSION,
              'scope': 'historical-input-harness-self-test-only' if check_fixture else 'exact-midpoint-two-stage-upgrade',
              'final_artifact_acceptance': not check_fixture,
              'source_initial_image_sha256': sha(full), 'source_cohort': identity,
              'target_cohort': parse(following['cohort.json']), 'ota': ota,
              'policy': policy, 'runtime_evidence': evidence,
              'original_runtime_boot_admission': original_admission,
              'bridge_retained_store_self_admission': bridge_self,
              'bridge_runtime_admission': graph, 'target_self_admission': self_graph,
              'rejections': rejections, 'installed_catalog': catalog,
              'bridge_transactions': bridge_results, 'final_transactions': final_results,
              'all_flash_snapshots_temporary': True, 'initial_image_emitted': False,
              'physical_flash_tls_spiffs_and_target_instructions_executed': False,
              'device_health_confirmation_executed': False, 'publication_performed': False}
    (output / 'midpoint-watch-upgrade-proof.json').write_bytes(encoded(record))
    print(record['scope'] + ': ' + str(len(bridge_results) + len(final_results)) +
          ' transaction/reboot/retry checks, ' + str(len(rejections)) + ' admission rejections passed')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('installed-bin', 'previous-bundle', 'candidate-bundle', 'native-dir', 'runtime', 'output',
                 'installed-runtime', 'previous-runtime', 'previous-native-dir', 'installed-system'):
        parser.add_argument('--' + name, required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--midpoint-bundle', type=Path)
    group.add_argument('--check-fixture', action='store_true')
    a = parser.parse_args()
    prove(a.installed_bin, a.previous_bundle, a.candidate_bundle, a.native_dir, a.runtime, a.output,
          installed_runtime=a.installed_runtime, previous_runtime=a.previous_runtime,
          previous_native_dir=a.previous_native_dir, installed_system=a.installed_system,
          midpoint_bundle=a.midpoint_bundle, check_fixture=a.check_fixture)


if __name__ == '__main__':
    main()

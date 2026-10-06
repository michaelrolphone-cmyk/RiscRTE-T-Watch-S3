#!/usr/bin/env python3
"""Freeze, verify and manually publish the exact midpoint-origin 1.0.6 derivation.

The original GitHub ZIPs remain original hosted inputs. The midpoint store and
initial-only image are explicitly derived, never represented as hosted artifacts.
No firmware compilation, device operation, bridge publication or automatic advancement.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

import current_cohort as cohort
from current_bootfs import build as build_store
from current_flash_layout import assemble
import midpoint_upgrade as midpoint
import publish_sdr_test as sdr
import publish_watch_product as pub
from read_only_spiffs import read_image
from watch_release_index import REPOSITORY, require, update_index, validate_record

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / 'release/midpoint-test-acceptance.json'
EVIDENCE = ROOT / 'release/midpoint-test-evidence'
SOURCE = '9c8ecf7e2e20bdda24e6f5fb97273ffd7797a94a'
NATIVE_SOURCE = '146ee7fed8ba97e4de5bfafb1ad745f1eee48158'
SYSTEM_SOURCE = '2d16d9dfa7abc50ce916eebc11d81423adef0000'
VERSION = '1.0.6'
TAG = 'firmware-v' + VERSION
METHOD = 'metadata-only-midpoint-from-original-hosted-ordinary-and-native-v1'
NOT_BEFORE = '2026-10-06T22:30:00Z'
SOURCE_FILES = ('scripts/midpoint_upgrade.py', 'scripts/build_next_watch_cohort.py',
    'scripts/current_cohort.py', 'scripts/current_bootfs.py', 'scripts/current_flash_layout.py',
    'scripts/read_only_spiffs.py', 'scripts/build_update_flash_bundle.py',
    'vendor/esp-idf-spiffs/spiffsgen.py', 'apps/current-apps-sources.json',
    'apps/current-runtime-requirements.json', 'apps/midpoint-origin-baseline.json',
    'tests/midpoint_upgrade/catalog.cpp', 'scripts/publish_sdr_test.py',
    'scripts/publish_watch_product.py', 'scripts/watch_release_index.py',
    'release/sdr-test-acceptance.json', 'apps/sdr-upgrade-baseline.json')
NOTICE = ('Experimental exact-midpoint Watch 1.0.6; not hardware-qualified. Only for installed '
    'source 27fba6f26a64501eadd308d4b1e7225c712ea50b after native bridge 1.0.3 '
    '(Runtime 0.1.34) and an operator-confirmed healthy restart with retained data. '
    'Use built-in Firmware Update for the native+bootfs OTA; it excludes NVS/app-data. '
    'Frozen 1.0.4 and ordinary 1.0.5 are not this midpoint route. The full launcher '
    'image is DESTRUCTIVE INITIAL PROVISIONING ONLY, never an installed-Watch upgrade. '
    'Host tests are not physical-device attestation. No device operation is performed.')
INSTALL = (NOTICE + '\n\nAfter the separately confirmed bridge restart, use Firmware Update '
    'to install 1.0.6, then restart and check Clock, alarms and retained settings/data. '
    'Stop if the bridge is unhealthy. Never flash an OTA at offset zero or write an '
    'empty app-data image. Publication does not install anything.\n').encode()
decode, encoded, sha = sdr.decode, pub.encoded, pub.sha


def files_from_zip(raw):
    with pub.checked_zip(raw) as archive:
        return {n: archive.read(n) for n in archive.namelist() if not n.endswith('/')}


def source_guards():
    result = {}
    for name in SOURCE_FILES:
        original = pub.command('git', 'show', SOURCE + ':' + name)
        require((ROOT / name).read_bytes() == original, 'Frozen derivation source changed: ' + name)
        result[name] = sha(original)
    return result


def validate_input(role, item):
    require(role in ('ordinary', 'native') and isinstance(item, dict), 'Unknown hosted input')
    prefix = 'twatch-next-cohort-' if role == 'ordinary' else 'twatch-native-runtime-'
    require(item.get('repository') == REPOSITORY and item.get('source_sha') == SOURCE and
            item.get('name') == prefix + SOURCE and sdr.exact_hex(item.get('sha256'), 64),
            'Wrong original hosted input identity')
    require(all(type(item.get(k)) is int and item[k] > 0
                for k in ('artifact_id', 'run_id', 'run_attempt')), 'Exact hosted CI identity required')
    return item


def verify_input_ci(role, item):
    validate_input(role, item)
    # The generic SDR CI verifier checks run/attempt/source/path/status and the
    # artifact's own name, creation interval, expiry and original ZIP digest.
    sdr.verify_ci(item)


def verify_ci_snapshot(item, snapshot):
    run, artifact = snapshot['run'], snapshot['artifact']
    require(run.get('id') == item['run_id'] and run.get('run_attempt') == item['run_attempt']
            and run.get('head_sha') == item['source_sha'] and run.get('status') == 'completed'
            and run.get('conclusion') == 'success' and run.get('path') == '.github/workflows/drivers.yml'
            and run.get('repository', {}).get('full_name') == REPOSITORY, 'Snapshot CI run differs')
    require(artifact.get('id') == item['artifact_id'] and artifact.get('name') == item['name']
            and artifact.get('expired') is False and artifact.get('workflow_run', {}).get('id') == item['run_id']
            and artifact['workflow_run'].get('head_sha') == item['source_sha']
            and artifact.get('digest') == 'sha256:' + item['sha256'], 'Snapshot artifact differs')
    parse = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parse(run['run_started_at']) <= parse(artifact['created_at']) <= parse(run['updated_at']),
            'Snapshot artifact belongs to another attempt')


def validate_acceptance(a):
    require(isinstance(a, dict) and a.get('schema') == 1 and type(a['schema']) is int
            and a.get('repository') == REPOSITORY and a.get('source_sha') == SOURCE
            and a.get('version') == VERSION and a.get('derivation') == METHOD
            and a.get('not_before') == NOT_BEFORE, 'Wrong midpoint acceptance identity')
    require(a.get('midpoint_source') == midpoint.MIDPOINT_SOURCE and
            a.get('midpoint_initial_sha256') == midpoint.MIDPOINT_SHA and
            a.get('native_source') == NATIVE_SOURCE, 'Wrong frozen source route')
    require(a.get('bridge_acceptance_sha256') == sha(sdr.ACCEPTANCE.read_bytes()),
            'Original bridge acceptance changed')
    require(set(a.get('inputs', {})) == {'ordinary', 'native'}, 'Missing hosted inputs')
    for role, item in a['inputs'].items(): validate_input(role, item)
    require((a['inputs']['ordinary']['run_id'], a['inputs']['ordinary']['run_attempt']) ==
            (a['inputs']['native']['run_id'], a['inputs']['native']['run_attempt']), 'Mixed CI attempts')
    require(a.get('derivation_sources') == source_guards(), 'Derivation source custody differs')
    require(set(a.get('evidence', {})) == {'build', 'normal', 'sanitized', 'execution', 'ci'},
            'Exact independent midpoint evidence required')
    for role, item in a['evidence'].items():
        require(item.get('path') == 'release/midpoint-test-evidence/' + role + '.json' and
                sdr.exact_hex(item.get('sha256'), 64), 'Wrong committed evidence identity')
    require(a.get('hosted_midpoint_artifact') is False and a.get('physical_qualification') is False,
            'Derived bytes must not claim hosted/hardware acceptance')
    return a


def read_evidence(a):
    result = {}
    for role, item in a['evidence'].items():
        raw = (ROOT / item['path']).read_bytes()
        require(sha(raw) == item['sha256'], 'Committed evidence changed: ' + role)
        result[role] = raw
    return result


def original_inputs(a, directory=None, *, remote=False):
    result = {}
    bridge = decode(sdr.ACCEPTANCE.read_bytes())
    for role, item in {'bridge': bridge, **a['inputs']}.items():
        if remote:
            (sdr.verify_ci(item) if role == 'bridge' else verify_input_ci(role, item))
        raw = ((Path(directory) / (role + '.zip')).read_bytes() if directory else
               pub.gh('api', f'repos/{REPOSITORY}/actions/artifacts/{item["artifact_id"]}/zip'))
        require(sha(raw) == item['sha256'], 'Original hosted ZIP hash differs: ' + role)
        result[role] = raw
    return result


def initial_bank_state(firmware, store):
    # Runtime paired_bank_images.py ABI2 record, bank0 VALID, second slot erased.
    data = struct.pack('<6I32s32sI', 0x314b4252, 1, 0, len(firmware), len(store), 2,
                       bytes.fromhex(sha(firmware)), bytes.fromhex(sha(store)), 0)
    return data + struct.pack('<I', zlib.crc32(data) & 0xffffffff) + b'\xff' * (8192 - 96)


def initial_image(scaffold, native, firmware, store, requirements):
    require(len(scaffold) == 0x1000000 and sha(scaffold) == midpoint.base.FULL_SHA,
            'Frozen initial-only scaffold differs')
    for name, offset in (('bootloader.bin', 0), ('partitions.bin', 0x8000), ('appdata.bin', 0x270000)):
        data = native[name]
        require(scaffold[offset:offset + len(data)] == data, 'Initial scaffold component differs: ' + name)
    require(scaffold[0x800000:0xff0000] == b'\xff' * 0x7f0000,
            'Initial scaffold inactive bank is not erased')
    seq = struct.pack('<I', 1)
    otadata = seq + b'\xff' * 20 + struct.pack('<II', 2, zlib.crc32(seq, 0xffffffff) & 0xffffffff)
    otadata += b'\xff' * (8192 - len(otadata))
    require(scaffold[0xff0000:0xff2000] == otadata, 'Initial scaffold OTA metadata differs')
    parts = {k: native[k] for k in ('bootloader.bin', 'partitions.bin', 'appdata.bin')}
    parts.update({'firmware.bin': firmware, 'bootfs.bin': store, 'otadata.bin': otadata,
                  'bank_state.bin': initial_bank_state(firmware, store)})
    full, placement = assemble(parts, requirements['deployment'], True)
    # Only bank0 native/store and their journal may differ from the accepted
    # provisioning scaffold. No installed image or persisted user state is used.
    for start, end in ((0, 0x10000), (0x270000, 0x2f0000),
                       (0x800000, 0xff2000), (0xff4000, 0x1000000)):
        require(full[start:end] == scaffold[start:end], 'Unrelated initial image region changed')
    return full, placement


def logical_store_digest(files):
    return sha(json.dumps([{'path': n, **m} for n, m in sorted(files.items())],
                          sort_keys=True, separators=(',', ':')).encode())


def verify_build_admissions(build):
    old_digest = logical_store_digest(midpoint.baseline()['files'])
    new_digest = logical_store_digest(build['files'])
    for name, count, old, new, elf in (
        ('bridge_retained_store_self_admission', 35, old_digest, old_digest, midpoint.base.ELF_SHA),
        ('installed_runtime_admission', 40, old_digest, new_digest, midpoint.base.ELF_SHA),
        ('target_self_admission', 40, new_digest, new_digest, build['native_elf_sha256'])):
        row = build[name]
        require(row.get('prepared') is True and row.get('cohort_validated') is True and
                row.get('elf_count') == count and row.get('hardware_calls') == 0 and row.get('storage_calls') == 0
                and row.get('target_instructions_executed') is False and row.get('error') == ''
                and row.get('active_store_sha256') == old and row.get('candidate_store_sha256') == new
                and row.get('native_elf_sha256') == elf, 'Wrong build admission: ' + name)


def verify_transactions(proof, ota, files):
    sentinels = {field: sha(bytes((i * 67 + (i >> 8) + salt) % 256 for i in range(length)))
                 for field, length, salt in (('nvs_sha256', 0x6000, 37), ('appdata_sha256', 0x80000, 173))}
    require(proof.get('schema') == 1 and proof.get('scope') == 'exact-midpoint-two-stage-upgrade'
            and proof.get('final_artifact_acceptance') is True and proof.get('version') == VERSION
            and proof.get('profile') == midpoint.PROFILE and proof.get('ota') == ota
            and proof.get('source_initial_image_sha256') == midpoint.MIDPOINT_SHA,
            'Not final exact midpoint upgrade evidence')
    expected_identity = {'schema': 'riscrte.cohort', 'schema_version': 1,
                         **{k: ota[k] for k in cohort.FIELDS - {'schema', 'schema_version'}}}
    require(proof.get('source_cohort') == midpoint.baseline()['cohort'] and
            proof.get('target_cohort') == expected_identity,
            'Wrong midpoint proof source/target')
    old_digest, new_digest = logical_store_digest(midpoint.baseline()['files']), logical_store_digest(files)
    for name, count in (('bridge_retained_store_self_admission', 35),
                        ('bridge_runtime_admission', 40), ('target_self_admission', 40)):
        item = proof.get(name, {})
        require(item.get('cohort_validated') is True and item.get('prepared') is True
                and item.get('elf_count') == count and item.get('hardware_calls') == 0
                and item.get('storage_calls') == 0 and item.get('error') == '', 'Missing exact ELF admission: ' + name)
        expected_pair = ((old_digest, old_digest) if name == 'bridge_retained_store_self_admission' else
                         (old_digest, new_digest) if name == 'bridge_runtime_admission' else (new_digest, new_digest))
        require((item.get('active_store_sha256'), item.get('candidate_store_sha256')) == expected_pair,
                'Admission store digest differs: ' + name)
    boot = proof.get('original_runtime_boot_admission', {})
    require(boot.get('prepared') is True and boot.get('store_files') == 73 and
            boot.get('hardware_calls') == 0 and boot.get('storage_calls') == 0 and boot.get('error') == '',
            'Missing exact original boot admission')
    require(boot.get('store_sha256') == old_digest, 'Original boot store digest differs')
    rejection_names = {'frozen-104-wrong-origin', 'ordinary-105-wrong-origin', 'missing-migration',
        'wrong-origin-source', 'wrong-origin-version', 'wrong-target-version', 'unused-migration-entry',
        'missing-migration-entry', 'new-app-steals-private-kv', 'migration-cannot-share-private-kv',
        'new-provider-steals-private-kv', 'new-app-steals-app-data', 'prior-app-owner-reassigned',
        'prior-provider-owner-reassigned', 'hardware-change', 'extra-store-member', 'corrupt-app-elf',
        'missing-waterfall-grant', 'wrong-midpoint-source'}
    require(len(proof.get('rejections', [])) == 19 and
            {r['scenario'] for r in proof['rejections']} == rejection_names and
            all(r.get('cohort_validated') is False for r in proof['rejections']), 'Missing admission rejections')
    for name, count in (('bridge_transactions', 54), ('final_transactions', 74)):
        rows = proof.get(name, [])
        require(len(rows) == count and len({r['label'] for r in rows}) == count,
                'Missing transaction/reboot/retry coverage: ' + name)
        require(all(r.get('nvs_appdata_preserved') is True and r.get('previous_pair_preserved') is True
                    and r.get('target_executed') is False for r in rows), 'Failed preservation proof')
        bridge = name == 'bridge_transactions'
        ordinary = (('power-begin', 'power-copy', 'power-download', 'cancel', 'corrupt', 'power-ready') if bridge else
                    ('power-begin', 'power-native', 'power-store', 'cancel', 'corrupt-native', 'corrupt-store',
                     'wrong-runtime-request', 'power-verify-native', 'power-verify-store', 'power-ready'))
        activated = ('activation-unknown', 'rollback', 'power-selected')
        suffixes = ('', '-prior-reboot', '-retry', '-retry-pending', '-bridge-valid') if bridge else (
                    '', '-prior-reboot', '-retry', '-retry-pending-boot', '-candidate-valid-restart')
        names = {p + suffix for p in (*ordinary, *activated) for suffix in suffixes}
        names |= {p + suffix for p in activated for suffix in (
                  ('-bridge-pending', '-bridge-rejected') if bridge else ('-candidate-pending-boot', '-candidate-rejected'))}
        names |= {'success', 'success-bridge-pending', 'success-bridge-valid'} if bridge else {
                  'success', 'success-candidate-pending-boot', 'success-candidate-valid-restart'}
        require({r['label'] for r in rows} == names, 'Incomplete named transaction coverage')
        versions = {'0.1.33': midpoint.INSTALLED_RUNTIME, '0.1.34': sdr.RUNTIME, '0.1.35': NATIVE_SOURCE}
        allowed = {'0.1.33', '0.1.34'} if bridge else {'0.1.34', '0.1.35'}
        for row in rows:
            version = row.get('executing_runtime_version')
            require(version in allowed and row.get('build_runtime_version') == version and
                    row.get('executing_runtime_source') == versions[version], 'Wrong transaction native source/version')
            label = row['label']
            candidate = (label.endswith(('-bridge-pending', '-bridge-rejected', '-bridge-valid', '-retry-pending'))
                         if bridge else '-candidate-' in label or label.endswith('-retry-pending-boot'))
            expected_version = ('0.1.34' if candidate else '0.1.33') if bridge else ('0.1.35' if candidate else '0.1.34')
            active = (1 if candidate else 0) if bridge else (0 if candidate else 1)
            scenario = (label if label in (*ordinary, *activated, 'success') else
                        'success' if label.endswith('-retry') else
                        'boot-healthy' if label.endswith(('-bridge-valid', '-candidate-valid-restart')) else
                        'boot-reject' if label.endswith('-rejected') else 'boot')
            require(version == expected_version and row.get('active_bank') == active
                    and row.get('target_bank') == 1 - active and row.get('scenario') == scenario,
                    'Wrong transaction label/runtime/bank direction')
            require(row.get('native_bytes') == (1209232 if bridge else ota['firmware_size']) and
                    (bridge or row.get('payload_bytes') == ota['size']), 'Wrong transaction payload/native length')
            require(row.get('host_idf_valid_state') is (scenario == 'boot-healthy'), 'Wrong healthy restart IDF state')
            for field, sentinel in sentinels.items():
                require(row.get(field) == sentinel, 'Persisted sentinel digest differs')
            require(sdr.exact_hex(row.get('snapshot_sha256'), 64), 'Missing persisted snapshot digest')
    require(proof['bridge_transactions'][0]['active_bank'] == 0 and
            proof['final_transactions'][0]['active_bank'] == 1, 'Wrong real bridge/final bank transition')
    for key in ('physical_flash_tls_spiffs_and_target_instructions_executed',
                'device_health_confirmation_executed', 'publication_performed'):
        require(proof.get(key) is False, 'Host evidence must not claim device action')


def derive(a, raw, evidence):
    """Deterministic metadata transformation, with no local compiler or inputs substituted."""
    bridge_a = decode(sdr.ACCEPTANCE.read_bytes())
    ci = decode(evidence['ci'])
    require(ci.get('transport') == 'read-only-github-connector' and set(ci.get('inputs', {})) == {'bridge', 'ordinary', 'native'},
            'Missing original hosted metadata custody')
    for role, item in {'bridge': bridge_a, **a['inputs']}.items(): verify_ci_snapshot(item, ci['inputs'][role])
    indexes, bridge_assets, old_install = sdr.verify_bundle(bridge_a, raw['bridge'])
    ordinary, native = files_from_zip(raw['ordinary']), files_from_zip(raw['native'])
    get = lambda name: ordinary['next-watch-cohort/' + name]
    native_record = decode(native['candidate.json'])
    require(native_record['source_sha'] == NATIVE_SOURCE and native_record['firmware_version'] == '0.1.35'
            and native_record['target'] == 'esp32s3-16mb-appdata-iq'
            and native_record['layout'] == cohort.LAYOUT and native_record['store_abi'] == 2,
            'Wrong hosted native identity')
    expected_native = {'firmware.bin', 'firmware.elf', 'bootloader.bin', 'partitions.bin', 'appdata.bin',
        'appdata-image.json', 'partitions-paired-appdata.csv', 'platformio.ini', 'requirements-ci.txt', 'radio-iq-proof.json'}
    require(set(native_record['assets']) == expected_native and
            set(native) <= expected_native | {'candidate.json', 'SHA256SUMS'}, 'Wrong native ZIP inventory')
    for name, item in native_record['assets'].items():
        require(len(native[name]) == item['bytes'] and sha(native[name]) == item['sha256'], 'Native member differs: ' + name)
    firmware = native['firmware.bin']
    for marker in (("RTE_SOURCE=" + NATIVE_SOURCE).encode() + b'\0', b'RISC_RUNTIME_VERSION:0.1.35\0', b'RISC_PAIRED_STORE_ABI:2\0'):
        require(marker in firmware and marker in native['firmware.elf'], 'Missing native compiled identity')
    proof = decode(get('next-watch-build-proof.json'))
    requirements_raw = get('runtime-requirements.json'); requirements = decode(requirements_raw)
    require(requirements_raw == (ROOT / 'apps/current-runtime-requirements.json').read_bytes(), 'Runtime requirements differ')
    require(proof['watch_source'] == SOURCE and proof['configuration'] == decode((ROOT / 'apps/current-apps-sources.json').read_bytes())
            and proof['runtime_requirements'] == requirements and proof['runtime_requirements_sha256'] == sha(requirements_raw)
            and proof['native_elf_sha256'] == sha(native['firmware.elf']), 'Ordinary proof/source differs')
    standard_store = get('bootfs.bin'); standard = read_image(standard_store, cohort.STORE_SIZE)
    cohort.verify(cohort.parse(standard['cohort.json']), firmware, version='1.0.5', runtime_version='0.1.35', source_revision=SOURCE)
    standard_payload, standard_ota = cohort.package(cohort.parse(standard['cohort.json']), firmware, standard_store)
    require(get(standard_ota['asset']) == standard_payload and proof['ota'] == standard_ota
            and proof['files'] == {n: midpoint.metadata(b) for n, b in standard.items()}, 'Ordinary hosted payload differs')
    extracted = {n.removeprefix('next-watch-cohort/store/'): b for n, b in ordinary.items() if n.startswith('next-watch-cohort/store/')}
    require(extracted == standard, 'Ordinary extracted store differs')
    prior_store = bridge_assets['cohort']['twatch-s3-launcher-1.0.4.bin'][0x2f0000:0x800000]
    prior = read_image(prior_store, cohort.STORE_SIZE)
    require(proof['policy'] == decode(encoded(midpoint.base.check_policy(prior, standard))) and
            proof['source_cohort'] == cohort.parse(prior['cohort.json']) and
            proof['source_initial_image_sha256'] == midpoint.base.FULL_SHA and
            proof['source_cohort_sha256'] == midpoint.base.COHORT_SHA and
            proof['previous_native_sha256'] == midpoint.base.NATIVE_SHA and
            proof['previous_native_elf_sha256'] == midpoint.base.ELF_SHA,
            'Ordinary source/policy custody differs')
    following = midpoint.adapt_candidate(standard, firmware, VERSION)
    store, packing = build_store(following)
    payload, ota = cohort.package(cohort.parse(following['cohort.json']), firmware, store)
    build = decode(evidence['build'])
    require(build['watch_source'] == SOURCE and build['ota'] == ota and
            build['standard_candidate_proof_sha256'] == sha(get('next-watch-build-proof.json')) and
            build['standard_candidate_sha256'] == standard_ota['sha256'] and
            build['native_candidate_sha256'] == sha(native['candidate.json']) and
            build['native_elf_sha256'] == sha(native['firmware.elf']) and
            build['files'] == {n: midpoint.metadata(b) for n, b in following.items()} and build['packing'] == packing,
            'Independent midpoint build evidence differs from hosted derivation')
    require(build['policy']['only_standard_store_changes'] == ['boot.json', 'cohort.json']
            and build['policy']['migration'] == midpoint.migration(VERSION), 'Wrong derived migration policy')
    require(build['licenses_sha256'] == sha(get('LICENSES.zip')) and
            build['runtime_requirements'] == requirements and
            build['runtime_requirements_sha256'] == sha(requirements_raw) and
            build['bridge']['native_sha256'] == midpoint.base.NATIVE_SHA and
            build['bridge']['retained_source_revision'] == midpoint.MIDPOINT_SOURCE and
            build['source_initial_image_sha256'] == midpoint.MIDPOINT_SHA and
            build['source_baseline_sha256'] == sha((ROOT / 'apps/midpoint-origin-baseline.json').read_bytes()),
            'Midpoint custody differs')
    verify_build_admissions(build)
    for role in ('normal', 'sanitized'):
        test = decode(evidence[role]); verify_transactions(test, ota, build['files'])
        require(test['policy'] == build['policy'] and test['runtime_evidence'] == build['runtime_evidence'], 'Mixed route proof')
    execution = decode(evidence['execution'])
    require(execution.get('source_sha') == SOURCE and execution.get('ota_sha256') == ota['sha256']
            and execution.get('scope') == 'independent-local-exact-artifact-rechecks'
            and set(execution.get('runs', {})) == {'normal', 'sanitized'}, 'Missing truthful execution custody')
    for role in ('normal', 'sanitized'):
        item = execution['runs'][role]
        require(item.get('exit_code') == 0 and item.get('proof_sha256') == sha(evidence[role])
                and isinstance(item.get('command'), str) and 'test_midpoint_watch_upgrade.py' in item['command']
                and item.get('sanitized') is (role == 'sanitized'), 'Wrong execution evidence: ' + role)
    require(execution['runs']['sanitized'].get('environment', {}).get('SANITIZE') == '1', 'Missing sanitizer invocation')
    require(execution['runs']['normal'].get('environment', {}).get('SANITIZE') == '0', 'Missing normal invocation')
    scaffold = bridge_assets['cohort']['twatch-s3-launcher-1.0.4.bin']
    full, placement = initial_image(scaffold, native, firmware, store, requirements)
    record = dict(kind='firmware', version=VERSION, tag=TAG, asset='twatch-s3-launcher-' + VERSION + '.bin',
        url=f'https://github.com/{REPOSITORY}/releases/download/{TAG}/twatch-s3-launcher-{VERSION}.bin',
        size=len(full), sha256=sha(full), source_sha=SOURCE, hardware_qualified=False,
        component_versions={**proof['configuration']['app_versions'], 'runtime': '0.1.35'},
        required_origin={'product': 'twatch-s3', 'version': '1.0.2', 'source_revision': midpoint.MIDPOINT_SOURCE},
        required_native_bridge='1.0.3', ota=ota)
    validate_record('firmware', record)
    index = update_index(indexes['native'], 'firmware', record)
    provenance = dict(schema=1, derivation=METHOD, source_sha=SOURCE, hosted_midpoint_artifact=False,
        inputs=a['inputs'], bridge_acceptance_sha256=a['bridge_acceptance_sha256'],
        derivation_sources=a['derivation_sources'], evidence=a['evidence'], ota=ota,
        initial_image_sha256=sha(full), initial_component_placement=placement,
        initial_image_is_destructive=True, only_standard_store_changes=['boot.json', 'cohort.json'],
        publication_performed=False, physical_qualification=False)
    assets = {record['asset']: full, ota['asset']: payload, 'release-record.json': encoded(record),
        'LICENSES.zip': get('LICENSES.zip'), 'INSTALL.txt': INSTALL, 'PUBLICATION.txt': (NOTICE + '\n').encode(),
        'midpoint-publication-provenance.json': encoded(provenance),
        'midpoint-watch-build-proof.json': evidence['build'], 'midpoint-upgrade-normal.json': evidence['normal'],
        'midpoint-upgrade-sanitized.json': evidence['sanitized'], 'midpoint-execution-custody.json': evidence['execution']}
    return indexes['native'], index, assets, (bridge_assets, old_install)


def verify_catalog(index, system, output):
    system = Path(system).resolve()
    require(pub.command('git', '-C', system, 'rev-parse', 'HEAD').decode().strip() == SYSTEM_SOURCE,
            'Wrong installed catalog parser source')
    require(not pub.command('git', '-C', system, 'status', '--porcelain', '--untracked-files=no').strip(), 'Dirty installed parser')
    output = Path(output)
    path = output / 'release-index.json'; path.write_bytes(encoded(index))
    for sanitized in (False, True):
        executable = output / ('installed-catalog-san' if sanitized else 'installed-catalog')
        flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie'] if sanitized else []
        subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation', *flags,
            *['-I' + str(system / p) for p in ('Services/update', 'lib/PortableApps/include', 'lib/NativeApps/include')],
            str(ROOT / 'tests/midpoint_upgrade/catalog.cpp'), '-o', str(executable)], check=True)
        env = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0', 'UBSAN_OPTIONS': 'halt_on_error=1'}
        subprocess.run([str(executable), str(path), 'accept'], check=True, env=env)
    return {'source_sha': SYSTEM_SOURCE, 'index_sha256': sha(encoded(index)),
            'real_release_record': True, 'accepted': True, 'normal_and_asan_ubsan': True}


def verify(a, raw, evidence):
    validate_acceptance(a)
    for role, item in {'bridge': decode(sdr.ACCEPTANCE.read_bytes()), **a['inputs']}.items():
        require(sha(raw[role]) == item['sha256'], 'Original ZIP changed: ' + role)
    for role, data in evidence.items(): require(sha(data) == a['evidence'][role]['sha256'], 'Evidence hash differs')
    predecessor, index, assets, bridge = derive(a, raw, evidence)
    require(a.get('derived_assets') == {n: midpoint.metadata(b) for n, b in assets.items()}
            and a.get('ota') == index['firmware']['ota']
            and a.get('release_index_sha256') == sha(encoded(index))
            and a.get('stage1_index_sha256') == sha(encoded(predecessor)), 'Frozen derived output differs')
    require(a.get('installed_catalog') == {'source_sha': SYSTEM_SOURCE, 'index_sha256': sha(encoded(index)),
            'real_release_record': True, 'accepted': True, 'normal_and_asan_ubsan': True}, 'Missing real catalog parser acceptance')
    return predecessor, index, assets, bridge


def confirmation(a, predecessor):
    require(sdr.exact_hex(predecessor, 40), 'Exact stage-1 index SHA required')
    return ('I confirm the Watch from source ' + midpoint.MIDPOINT_SOURCE +
        ' completed native bridge 1.0.3 through Firmware Update, restarted with Runtime 0.1.34, '
        'a healthy Clock and retained data; proceed to midpoint cohort 1.0.6. '
        f'OTA SHA256 {a["ota"]["sha256"]}; acceptance SHA256 {sha(encoded(a))}; stage-1 index {predecessor}.')


def check_transition(a, expected, index, predecessor, parent, current, operator_confirmation):
    require(sdr.exact_hex(predecessor, 40) and parent == predecessor, 'Live stage-1 index commit changed')
    require(current == expected and current['firmware']['version'] == '1.0.3', 'Exact native bridge index required; no skipped stage or rewrite')
    require(operator_confirmation == confirmation(a, predecessor), 'Exact operator-confirmed bridge health required')
    require(update_index(current, 'firmware', index['firmware']) == index, 'Only monotonic firmware advancement is permitted')


def publish(a, raw, evidence, predecessor, operator_confirmation, system, *, mutate=False):
    expected, index, assets, bridge = verify(a, raw, evidence)
    for role, item in a['inputs'].items(): verify_input_ci(role, item)
    sdr.verify_ci(decode(sdr.ACCEPTANCE.read_bytes()))
    source = pub.command('git', 'rev-parse', 'HEAD').decode().strip()
    require(not pub.command('git', 'status', '--porcelain', '--untracked-files=no').strip(), 'Dirty publisher source')
    for path in [ACCEPTANCE, sdr.ACCEPTANCE, *(ROOT / item['path'] for item in a['evidence'].values())]:
        require(pub.command('git', 'show', 'HEAD:' + path.relative_to(ROOT).as_posix()) == path.read_bytes(), 'Acceptance/evidence must be committed')
    require(decode(ACCEPTANCE.read_bytes()) == a, 'Canonical committed acceptance required')
    pub.verify_watch_ancestry(SOURCE, source)
    require(pub.command('git', 'show', SOURCE + ':release/product.json') == pub.CONFIG.read_bytes(), 'Frozen 1.0.2 product changed')
    if mutate:
        repo = pub.api('repos/' + REPOSITORY)
        require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' and
                os.environ.get('GITHUB_REPOSITORY') == REPOSITORY and
                os.environ.get('GITHUB_REF') == 'refs/heads/' + repo['default_branch'] and
                pub.api(f'repos/{REPOSITORY}/commits/{repo["default_branch"]}')['sha'] == source,
                'Publication requires explicit manual dispatch at current default source')
        require(datetime.now(timezone.utc) >= datetime.fromisoformat(NOT_BEFORE.replace('Z', '+00:00')),
                'BIN publication is not allowed before ' + NOT_BEFORE)
    parent, current = pub.current_release_index()
    check_transition(a, expected, index, predecessor, parent, current, operator_confirmation)
    with tempfile.TemporaryDirectory(prefix='midpoint-publish-') as tmp:
        output = Path(tmp)
        require(verify_catalog(index, system, output) == a['installed_catalog'], 'Real installed catalog check changed')
        # Stage only bridge files for byte-for-byte read-only comparison. Never
        # create, repair or republish the bridge, and never publish 1.0.4 here.
        bridge_assets, old_install = bridge
        bridge_files = dict(bridge_assets['native']); bridge_files.pop('SHA256SUMS')
        bridge_files.update({'INSTALL.txt': old_install, 'PUBLICATION.txt': (sdr.NOTICE + '\n').encode()})
        bridge_release = pub.write_release(output, expected['firmware'], bridge_files,
                                           decode(sdr.ACCEPTANCE.read_bytes())['source_sha'], False)
        existing = pub.release_by_tag('firmware-v1.0.3')
        require(existing and not existing['draft'], 'Native bridge must already be published')
        pub.release_preflight([bridge_release], output, prerelease=True)
        release = pub.write_release(output, index['firmware'], assets, SOURCE, False)
        pub.release_preflight([release], output, prerelease=True)
        if mutate:
            parent2, current2 = pub.current_release_index()
            check_transition(a, expected, index, predecessor, parent2, current2, operator_confirmation)
            pub.publish_one(release, output, title='Watch midpoint test 1.0.6', notes=NOTICE, prerelease=True)
            pub.publish_index(index, expected_parent=parent, expected_current=current)
    print(('Published' if mutate else 'Read-only preflight passed for') + ' exact midpoint 1.0.6')


def freeze(args):
    require(not ACCEPTANCE.exists() and not EVIDENCE.exists(), 'Refusing to replace frozen acceptance/evidence')
    inputs = decode(args.inputs.read_bytes())
    for role, item in inputs.items(): validate_input(role, item)
    evidence = {role: getattr(args, role + '_proof').read_bytes() for role in ('build', 'normal', 'sanitized', 'execution', 'ci')}
    a = dict(schema=1, repository=REPOSITORY, source_sha=SOURCE, native_source=NATIVE_SOURCE,
        version=VERSION, derivation=METHOD, not_before=NOT_BEFORE, inputs=inputs,
        midpoint_source=midpoint.MIDPOINT_SOURCE, midpoint_initial_sha256=midpoint.MIDPOINT_SHA,
        bridge_acceptance_sha256=sha(sdr.ACCEPTANCE.read_bytes()), derivation_sources=source_guards(),
        hosted_midpoint_artifact=False, physical_qualification=False,
        evidence={role: {'path': 'release/midpoint-test-evidence/' + role + '.json', 'sha256': sha(raw)}
                  for role, raw in evidence.items()})
    validate_acceptance(a)
    raw = original_inputs(a, args.artifact_dir)
    predecessor, index, assets, _ = derive(a, raw, evidence)
    # The actual independently exercised local OTA must equal this derivation of
    # the original hosted inputs, before either identity is frozen.
    ota = index['firmware']['ota']
    require((args.midpoint_bundle / ota['asset']).read_bytes() == assets[ota['asset']], 'Independently tested OTA differs')
    a.update(ota=ota, derived_assets={n: midpoint.metadata(b) for n, b in assets.items()},
             release_index_sha256=sha(encoded(index)), stage1_index_sha256=sha(encoded(predecessor)))
    with tempfile.TemporaryDirectory(prefix='midpoint-catalog-') as tmp:
        a['installed_catalog'] = verify_catalog(index, args.installed_system, tmp)
    verify(a, raw, evidence)
    pub.safe_input_path(ACCEPTANCE)
    pub.safe_input_path(EVIDENCE)
    EVIDENCE.mkdir()
    for role, raw in evidence.items():
        with (EVIDENCE / (role + '.json')).open('xb') as stream: stream.write(raw)
    with ACCEPTANCE.open('xb') as stream: stream.write(encoded(a))
    print('Frozen original hosted inputs and explicitly derived midpoint bytes; review and commit before publication')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='action', required=True)
    sub = subs.add_parser('freeze')
    for flag in ('inputs', 'artifact-dir', 'midpoint-bundle', 'installed-system',
                 'build-proof', 'normal-proof', 'sanitized-proof', 'execution-proof'):
        sub.add_argument('--' + flag, type=Path, required=True)
    sub.add_argument('--ci-proof', type=Path, required=True)
    for action in ('verify', 'confirmation', 'preflight', 'publish'):
        sub = subs.add_parser(action)
        if action != 'confirmation': sub.add_argument('--artifact-dir', type=Path)
        if action != 'verify': sub.add_argument('--expected-index-commit', required=True)
        if action in ('preflight', 'publish'):
            sub.add_argument('--operator-confirmation', required=True)
            sub.add_argument('--installed-system', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'freeze': return freeze(args)
    a = validate_acceptance(decode(ACCEPTANCE.read_bytes()))
    if args.action == 'confirmation': print(confirmation(a, args.expected_index_commit)); return
    raw = original_inputs(a, args.artifact_dir, remote=args.action != 'verify')
    evidence = read_evidence(a)
    if args.action == 'verify':
        verify(a, raw, evidence); print('Verified frozen derived bytes offline; no publication or device attestation'); return
    publish(a, raw, evidence, args.expected_index_commit, args.operator_confirmation, args.installed_system,
            mutate=args.action == 'publish')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Verify and transport same-run native candidates; never attest detached builds."""
import argparse
import io
import json
from pathlib import Path
import re
import sys
import zipfile

import package_shared_default as package
import native_idf61_candidate as native
from package_shared_default import require, record, sha, encoded
from transport_native_idf61_release import archive_members, checksums, decode
from package_alarm_sleep import make_archive

NATIVE = {'factory-candidate-erases-data-0x0.bin', 'firmware.bin', 'bootloader.bin', 'partitions.bin', 'store.bin'}
CANDIDATE = NATIVE | {'qualification.json', 'source-lock.json', 'source-pins.json', 'default.elf', 'default.json', 'candidate-evidence.zip', 'SHA256SUMS'}
ROLES = {'product', 'runtime', 'system', 'utilities', 'drivers', 'sdk', 'watch', 'image_helper'}
PRODUCTS = {'twatch': ('RiscRTE-T-Watch-S3', 'TWatch'), 'waveshare': ('RiscRTE-Wavshare-S3-Touch-AMOLED-2.06', 'Waveshare')}


def check_directory(root, expected_sha=None, expected_names=None):
    require(root.is_dir() and not root.is_symlink(), 'Invalid output directory')
    sums_file = root / 'SHA256SUMS'
    require(sums_file.is_file() and not sums_file.is_symlink(), 'Missing checksum custody')
    data = sums_file.read_bytes()
    if expected_sha is not None: require(sha(data) == expected_sha, 'Checksum custody differs')
    rows = checksums(data)
    names = {p.name for p in root.iterdir()}
    require(names == set(rows) | {'SHA256SUMS'}, 'Output inventory differs')
    if expected_names is not None: require(names == expected_names, 'Unexpected candidate inventory')
    for name, digest in rows.items():
        path = root / name
        require(path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == digest, 'Asset changed: ' + name)
    return rows


def check_qualification(q, p, revision):
    require(re.fullmatch('[0-9a-f]{40}', revision), 'Immutable product revision required')
    require(q['schema'] == 1 and q['status'] == 'software-qualified-candidate-hardware-pending', 'Native qualification required')
    require(q['product'] == p['product'] and q['version'] == p['version'] and q['source_revision'] == revision, 'Candidate identity differs')
    for key, value in {'publication_enabled': False, 'hardware_tested': False, 'device_accessed': False,
                       'factory_erases_data': True, 'preserving_update_kit_emitted': False, 'native_rebuilt': True}.items():
        require(q.get(key) is value, 'Qualification limits differ: ' + key)
    lock = q['input_lock']
    require(lock['schema'] == 1 and lock['publication_enabled'] is False and lock['candidate_version'] == p['version'], 'Source lock identity differs')
    require(set(lock['sources']) == ROLES, 'Incomplete source closure')
    for role, row in lock['sources'].items():
        require(row['revision'] == (revision if role == 'product' else p[role + '_revision']), 'Source revision differs: ' + role)
        require(re.fullmatch('[0-9a-f]{40}', row['tree']) and isinstance(row['submodules'], list), 'Malformed source closure')
        require(all(re.fullmatch('[0-9a-f]{40} [^\n\r]+', s) for s in row['submodules']), 'Malformed submodule closure')
    proof = q['controlled_build']
    require(proof['fresh_build'] is True and proof['same_process_qualification'] is True
            and proof['detached_receipt_is_attestation'] is False and proof['compile_jobs'] == 1, 'Fresh controlled native build required')
    require(proof['sources'] == lock['sources'], 'Controlled source closure differs')
    require(set(q['artifacts']) == NATIVE, 'Native artifact inventory differs')
    canonical = q['default']
    require(canonical['independent_builds_identical'] is True and canonical['hardware_tested'] is False, 'Two canonical builds required')
    require(canonical['default_sha256'] == p['default_sha256'] and canonical['default_bytes'] == p['default_bytes']
            and canonical['manifest_sha256'] == p['default_manifest_sha256'], 'Canonical default differs')
    require(q.get('serial_files') == p['serial_files'], 'Native serial admission differs')
    baseline = q['baseline_contract']
    require(baseline == package.baseline_contract(p), 'Released baseline contract differs')
    for key, sanitized in [('admission', False), ('admission_sanitized', True)]:
        row = q[key]
        require(row['elf_count'] == baseline['elf_count'] and row['sanitized'] is sanitized
                and row['hardware_calls'] == 0 and row['storage_calls'] == 0 and row['target_instructions_executed'] is False,
                'Complete production-loader admission required: ' + key)
    for key in ('arduino_core_linked', 'ordinary_app_payloads_rebuilt', 'unselected_usb_host_controller'):
        require(q['native'][key] is False, 'Unexpected native composition: ' + key)
    require(q['native']['elf_bin_identical'] is True, 'Native ELF/BIN identity required')
    model = q['preservation_software_model']
    require(model['passed'] is True and model['cases'] == 496 and model['nvs_and_appdata_preserved'] is True
            and model['bootloader_compatibility_tested'] is False and model['hardware_tested'] is False, 'Preservation model differs')
    require(q['preservation']['changed_store_files'] == package.CHANGED
            and q['preservation']['unchanged_store_payloads'] == len(baseline['files']) - len(package.CHANGED)
            and q['preservation']['unchanged_elf_count'] == baseline['elf_count'] - 1
            and q['preservation']['alarm_sha256'] == package.ALARM_SHA, 'Payload preservation differs')
    return lock


def validate_candidate_payloads(root, p, revision, names=None):
    names = names or {}
    path = lambda n: root / names.get(n, n)
    q = decode((path('qualification.json')).read_bytes())
    lock = check_qualification(q, p, revision)
    require(lock == decode((path('source-lock.json')).read_bytes()), 'Candidate source lock differs')
    require((path('source-pins.json')).read_bytes() == (package.DOCS / 'source-pins.json').read_bytes(), 'Recipe pins differ')
    for name in NATIVE: require(record((path(name)).read_bytes()) == q['artifacts'][name], 'Native artifact changed: ' + name)
    require(record((path('default.elf')).read_bytes()) == {'bytes': p['default_bytes'], 'sha256': p['default_sha256']}, 'Default ELF changed')
    require(sha((path('default.json')).read_bytes()) == p['default_manifest_sha256'], 'Default manifest changed')
    require(set(lock['native_files']) == native.ARTIFACT_KEYS and set(q['controlled_build']['artifacts']) == native.ARTIFACT_KEYS, 'Incomplete native evidence inventory')
    members = archive_members(path('candidate-evidence.zip'))
    with zipfile.ZipFile(path('candidate-evidence.zip')) as z:
        for name in ('qualification.json', 'default.elf', 'default.json'):
            require(z.read(name) == (path(name)).read_bytes(), 'Evidence differs: ' + name)
        require(decode(z.read('build-evidence/build-closure.json')) == q['controlled_build'], 'Build closure differs')
        require(z.read('build-evidence/source-lock.json') == (path('source-lock.json')).read_bytes(), 'Evidence lock differs')
        for role, row in lock['native_files'].items():
            expected = {k: row[k] for k in ('bytes', 'sha256')}
            require(members.get('build/' + row['path']) == expected
                    and q['controlled_build']['artifacts'][role] == expected, 'Native evidence differs: ' + role)
    for name, role in [('firmware.bin', 'firmware_bin'), ('bootloader.bin', 'bootloader'), ('partitions.bin', 'partitions')]:
        require(q['artifacts'][name] == {k: lock['native_files'][role][k] for k in ('bytes', 'sha256')}, 'Linked payload differs')
    return q


def validate_candidate(root, p, revision):
    check_directory(root, expected_names=CANDIDATE)
    return validate_candidate_payloads(root, p, revision)


def release_names(p):
    prefix = PRODUCTS[p['product']][1] + '-' + p['version'] + '-Shared-Default'
    renamed = {'factory-candidate-erases-data-0x0.bin': prefix + '-factory-erases-data-0x0.bin',
               'candidate-evidence.zip': prefix + '-Evidence.zip'}
    names = {renamed.get(n, n) for n in CANDIDATE} | {'RELEASE-NOTES.txt', 'TESTING.txt', 'release.json', 'ci-provenance.zip'}
    return names, renamed


CI_FILES = {'ci-run.json', 'workflow.yml', 'baseline-release.json', 'baseline-tag.json', 'compiler-version.txt', 'iq-linked.json'}


def verify_ci_provenance(path, p, revision, native_proof):
    members = archive_members(path)
    require(set(members) == CI_FILES, 'CI provenance inventory differs')
    repo = 'michaelrolphone-cmyk/' + PRODUCTS[p['product']][0]
    with zipfile.ZipFile(path) as z:
        ci = decode(z.read('ci-run.json'))
        require(ci['GITHUB_REPOSITORY'] == repo and ci['GITHUB_SHA'] == revision and ci['GITHUB_WORKFLOW_SHA'] == revision, 'CI source identity differs')
        require(ci['GITHUB_REF'] in ('refs/heads/work/serial-files-native', 'refs/heads/' + p['release_branch']), 'Unexpected CI source branch')
        require(ci['GITHUB_WORKFLOW_REF'] == repo + '/.github/workflows/shared-default-native.yml@' + ci['GITHUB_REF'], 'CI workflow identity differs')
        require(all(re.fullmatch('[1-9][0-9]*', ci[k]) for k in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')), 'CI run identity missing')
        require(z.read('workflow.yml') == (package.ROOT / '.github/workflows/shared-default-native.yml').read_bytes(), 'Published workflow snapshot differs')
        c = package.baseline_contract(p); tag = decode(z.read('baseline-tag.json')); baseline = decode(z.read('baseline-release.json'))
        require(tag['ref'] == 'refs/tags/' + c['release_tag'] and tag['object']['type'] == 'commit' and tag['object']['sha'] == c['source_revision'], 'Baseline tag provenance differs')
        require(baseline['tag_name'] == c['release_tag'] and baseline['draft'] is False, 'Baseline release provenance differs')
        assets = [a for a in baseline['assets'] if a['name'] == c['factory_asset']]
        require(len(assets) == 1 and assets[0]['browser_download_url'] == 'https://github.com/' + repo + '/releases/download/' + c['release_tag'] + '/' + c['factory_asset'], 'Baseline asset provenance differs')
        require(b'esp-15.2.0_20251204' in z.read('compiler-version.txt'), 'Compiler provenance differs')
        iq = decode(z.read('iq-linked.json'))
        require(iq == native_proof['radio_iq'], 'CI/qualified IQ proof differs')
        target = decode((package.ROOT / 'docs/native-idf61/released-baseline.json').read_bytes())['target']
        require(iq['schema'] == 1 and iq['target_identity'] == target and re.fullmatch('[0-9a-f]{64}', iq['elf_sha256']), 'Final IQ link qualification missing')
    return {'repository': repo, 'run_id': int(ci['GITHUB_RUN_ID']), 'run_attempt': int(ci['GITHUB_RUN_ATTEMPT']),
            'source_revision': revision, 'firmware_elf_sha256': iq['elf_sha256'], 'workflow_sha256': sha((package.ROOT / '.github/workflows/shared-default-native.yml').read_bytes())}


def transport(args):
    p = package.pins()
    package.clean_source(package.ROOT, args.source_revision)
    q = validate_candidate(args.candidate, p, args.source_revision)
    require(not args.output.exists(), 'Release output must be new')
    # The same-run caller supplies exact clean sources; never load executable
    # Python from candidate ZIPs or accept a detached receipt as an attestation.
    for role in ('runtime', 'image_helper'):
        package.clean_source(getattr(args, role), p[role + '_revision'])
    sys.path[:0] = [str(args.runtime / 'scripts'), str(args.image_helper / 'scripts')]
    from read_only_spiffs import read_image
    from prepare_preserving_update import layout, pair
    baseline = args.baseline.read_bytes()
    c = package.baseline_contract(p)
    require(record(baseline) == {'bytes': c['factory_bytes'], 'sha256': c['factory_sha256']}, 'Released factory differs')
    before = read_image(pair(baseline, 0, layout(baseline))[2], 0x550000)
    package.check_baseline(before, c)
    factory = (args.candidate / 'factory-candidate-erases-data-0x0.bin').read_bytes()
    _, firmware, store = pair(factory, 0, layout(factory))
    require(firmware == (args.candidate / 'firmware.bin').read_bytes() and store == (args.candidate / 'store.bin').read_bytes(), 'Factory pair differs')
    extracted = read_image(store, 0x550000)
    require(package.verify_store(before, extracted, (args.candidate / 'default.elf').read_bytes(),
        (args.candidate / 'default.json').read_bytes(), p, args.source_revision, firmware) == q['preservation'], 'Final extraction proof differs')
    repository, prefix = PRODUCTS[p['product']]
    stem = prefix + '-' + p['version'] + '-Shared-Default'
    _, rename = release_names(p)
    files = {rename.get(n, n): (args.candidate / n).read_bytes() for n in CANDIDATE - {'SHA256SUMS'}}
    notes = (prefix + ' ' + p['version'] + ' shared default\n\n'
        'Both watch products use default.elf SHA256 ' + p['default_sha256'] + '.\n'
        'Native ESP-IDF 6.1 / GCC 15.2 Runtime with generic file and settings providers.\n'
        'RTEF1 serial individual-file transfers use writable private namespace 2; ' +
        ('Waveshare also admits writable SD namespace 12.\n' if p['product'] == 'waveshare' else 'TWatch does not admit SD.\n') +
        'Serial writes never target the active boot bank. Replace is explicit and not atomic; interrupted writes can remain partial.\n'
        'Native faces and the existing alarm repair are retained. All unrelated store payloads are byte-identical.\n'
        'Software-qualified; hardware has not been tested for this release.\n'
        'The factory image erases existing device data. Back up first. No data-preserving update kit is supplied.\n'
        'Do not flash standalone firmware/store files independently; their bank binding must remain paired.\n')
    files['ci-provenance.zip'] = make_archive({n: (args.metadata / n).read_bytes() for n in CI_FILES})
    # Verify the exact same metadata bytes that are included in the public release.
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        provenance = Path(temp) / 'ci-provenance.zip'; provenance.write_bytes(files['ci-provenance.zip'])
        ci_proof = verify_ci_provenance(provenance, p, args.source_revision, q['native'])
        require(ci_proof['firmware_elf_sha256'] == q['input_lock']['native_files']['firmware_elf']['sha256'], 'CI IQ/firmware ELF binding differs')
    files['RELEASE-NOTES.txt'] = notes.encode()
    files['TESTING.txt'] = (notes + '\nHardware checks:\n'
        '1. Back up device data, then flash the factory image at offset 0x0 only if erasure is acceptable.\n'
        '2. Confirm Home renders natively at the physical display resolution and touch reaches every edge.\n'
        '3. Change a clock preference, reboot, and verify it persists. Check brightness and configuration reads.\n'
        '4. Open and return from installed applications; check application ELF loading and normal platform operation.\n'
        '5. Verify alarms across light/deep sleep and wake, including an existing scheduled alarm.\n'
        '6. Exercise optional file export when provisioned, and normal Home use when it is absent.\n'
        '7. Use the pinned Runtime scripts/serial_files.py client over an owner-trusted serial port: enumerate namespaces, create, read back, then explicitly replace a test file.\n'
        '8. Check binary and empty files, nested sibling preservation, missing SD, interrupted writes and AppData isolation. No boot-bank namespace may be writable.\n'
        'Report the device, firmware version, steps, expected and actual result, and serial logs for failures.\n').encode()
    release = dict(schema=1, repository='michaelrolphone-cmyk/' + repository, product=p['product'], version=p['version'],
        source_revision=args.source_revision, release_tag=p['release_tag'], publication_enabled=p['publication_enabled'],
        native_rebuilt=True, hardware_tested=False, device_accessed=False, factory_erases_data=True,
        preserving_update_kit_emitted=False, default_sha256=p['default_sha256'], default_manifest_sha256=p['default_manifest_sha256'],
        changed_store_files=package.CHANGED, source_lock=q['input_lock'], qualification_sha256=sha(files['qualification.json']),
        final_factory_default_extracted=True, ci=ci_proof, artifacts={n: record(b) for n, b in sorted(files.items())})
    files['release.json'] = encoded(release)
    files['SHA256SUMS'] = ''.join(sha(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    args.output.mkdir(parents=True)
    for name, data in files.items(): (args.output / name).write_bytes(data)
    verify_output(args.output, sha(files['SHA256SUMS']), args.source_revision)
    print('Same-run native release transport and final factory extraction PASS; hardware not tested')


def verify_output(root, expected_sha, revision):
    p = package.pins()
    names, renamed = release_names(p)
    rows = check_directory(root, expected_sha, names)
    release = decode((root / 'release.json').read_bytes())
    require(release['schema'] == 1 and release['repository'] == 'michaelrolphone-cmyk/' + PRODUCTS[p['product']][0], 'Release repository/schema differs')
    require(set(release['artifacts']) == set(rows) - {'release.json'}, 'Release inventory differs')
    require(release['source_revision'] == revision and release['version'] == p['version'] and release['product'] == p['product']
            and release['release_tag'] == p['release_tag'] and release['publication_enabled'] is p['publication_enabled'], 'Release identity differs')
    for key, value in {'native_rebuilt': True, 'hardware_tested': False, 'device_accessed': False,
                       'factory_erases_data': True, 'preserving_update_kit_emitted': False, 'final_factory_default_extracted': True}.items():
        require(release[key] is value, 'Release limit differs: ' + key)
    require(release['changed_store_files'] == package.CHANGED and release['default_sha256'] == p['default_sha256']
            and release['default_manifest_sha256'] == p['default_manifest_sha256'], 'Release scope differs')
    for name, row in release['artifacts'].items(): require(record((root / name).read_bytes()) == row, 'Released bytes changed')
    q = validate_candidate_payloads(root, p, revision, renamed)
    require(release['ci'] == verify_ci_provenance(root / 'ci-provenance.zip', p, revision, q['native']), 'Release CI binding differs')
    require(release['ci']['firmware_elf_sha256'] == q['input_lock']['native_files']['firmware_elf']['sha256'], 'Released CI IQ/firmware binding differs')
    require(release['source_lock'] == q['input_lock'] and release['qualification_sha256'] == sha((root / 'qualification.json').read_bytes()), 'Release qualification binding differs')
    require(sha((root / 'default.elf').read_bytes()) == p['default_sha256'] and sha((root / 'default.json').read_bytes()) == p['default_manifest_sha256'], 'Released default differs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--expected-sha')
    for name in ('candidate', 'runtime', 'image-helper', 'baseline', 'output', 'metadata'): parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    require(__debug__, 'Validation cannot be disabled')
    if args.verify:
        require(args.expected_sha is not None, 'Expected checksum custody required')
        verify_output(args.verify, args.expected_sha, args.source_revision)
    else:
        require(all(getattr(args, n) is not None for n in ('candidate', 'runtime', 'image_helper', 'baseline', 'output', 'metadata')), 'Complete same-run input set required')
        transport(args)

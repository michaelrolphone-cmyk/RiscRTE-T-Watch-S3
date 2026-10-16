#!/usr/bin/env python3
"""Offline exact-byte transport of an already qualified official CI artifact.

This is not a build/qualification tool. Trust is anchored in the separately
approved contract and successful official Runtime CI/release custody record.
A detached build receipt is never promoted to a new attestation here.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


FILES = {'factory-candidate-erases-data-0x0.bin', 'firmware.bin', 'bootloader.bin',
         'partitions.bin', 'store.bin'}
CANDIDATE_FILES = FILES | {'qualification.json', 'source-lock.json', 'SHA256SUMS'}
LIMITS = {'publication_enabled': False, 'hardware_tested': False, 'device_accessed': False,
          'version_reserved_by_recipe': False, 'factory_erases_data': True,
          'preserving_update_kit_emitted': False, 'preserving_sdk_migration_eligible': False}
ROLES = {'product', 'runtime', 'system', 'drivers', 'sdk', 'image_helper'}
PRODUCTS = {
    'twatch': ('michaelrolphone-cmyk/RiscRTE-T-Watch-S3', 'TWatch', '1.1.40', 'Watch'),
    'waveshare': ('michaelrolphone-cmyk/RiscRTE-Wavshare-S3-Touch-AMOLED-2.06', 'Waveshare', '0.1.49', 'Wave'),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def decode(data):
    def unique(pairs):
        out = {}
        for name, value in pairs:
            require(name not in out, 'Duplicate JSON key: ' + name)
            out[name] = value
        return out
    return json.loads(data, object_pairs_hook=unique)


def hex_value(value, length):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{%d}' % length, value)


def record(data):
    return {'bytes': len(data), 'sha256': digest(data)}


def safe_name(name):
    path = PurePosixPath(name)
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name
            and not path.is_absolute() and '..' not in path.parts and str(path) == name
            and all(ord(c) >= 32 and ord(c) < 127 for c in name), 'Unsafe/noncanonical ZIP member')
    return path


def archive_members(path):
    """Hash every member without extraction, bounded against archive expansion."""
    members = {}
    total = 0
    with zipfile.ZipFile(path) as archive:
        require(len(archive.infolist()) <= 20000, 'Too many ZIP members')
        seen = set()
        for info in archive.infolist():
            name = info.filename[:-1] if info.is_dir() else info.filename
            safe_name(name)
            require(name not in seen, 'Duplicate ZIP member')
            seen.add(name)
            mode = (info.external_attr >> 16) & 0xFFFF
            require(not stat.S_ISLNK(mode) and (stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR)), 'Nonregular ZIP member')
            require(not info.flag_bits & 1, 'Encrypted ZIP member')
            if info.is_dir():
                require(info.file_size == 0, 'Nonempty ZIP directory')
                continue
            require(info.file_size <= 256 * 1024 * 1024, 'Oversized ZIP member')
            total += info.file_size
            require(total <= 2 * 1024 * 1024 * 1024, 'Oversized ZIP expansion')
            h = hashlib.sha256()
            count = 0
            with archive.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    count += len(block); h.update(block)
                    require(count <= info.file_size, 'ZIP size mismatch')
            require(count == info.file_size, 'ZIP size mismatch')
            members[name] = {'bytes': count, 'sha256': h.hexdigest()}
    require(members, 'Empty ZIP')
    return members


def checksums(data):
    rows = {}
    for line in data.decode('ascii').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        require(match is not None, 'Malformed checksum row')
        sha, name = match.groups()
        require(name not in rows, 'Duplicate checksum row')
        rows[name] = sha
    return rows


def final_contract(contract):
    require(contract.get('schema') == 1 and contract.get('finalized') is True, 'Transport contract is not finalized')
    require(type(contract.get('publication_enabled')) is bool, 'Missing explicit publication gate')
    product = contract.get('product')
    require(product in PRODUCTS, 'Unknown selected product')
    repository, prefix, version, label = PRODUCTS[product]
    require(contract['repository'] == repository and contract['version'] == version, 'Product identity differs')
    require(contract['release_tag'] == 'test-native-idf61-' + version, 'Unreviewed product release tag')
    require(contract['release_branch'] == 'work/native-idf-6.1', 'Unreviewed release branch')
    require(contract['runtime_repository'] == 'michaelrolphone-cmyk/RiscRTE' and contract['runtime_tag'] == 'firmware-v0.4.0', 'Unreviewed Runtime release')
    require(contract['evidence_asset'] == 'Runtime-0.4.0-' + label + '-' + version + '-Native-IDF61-Evidence.zip', 'Wrong evidence asset')
    require(set(contract['sources']) == ROLES, 'Incomplete source roles')
    for revision in contract['sources'].values():
        require(hex_value(revision, 40), 'Full source pin required')
    require(contract['sources']['runtime'] == contract['runtime_revision'], 'Runtime source mismatch')
    for field in ('runtime_revision', 'runtime_release_revision'):
        require(hex_value(contract[field], 40), 'Invalid revision: ' + field)
    for field in ('runtime_manifest_sha256', 'evidence_sha256', 'qualification_sha256', 'baseline_contract_sha256'):
        require(hex_value(contract[field], 64), 'Invalid digest: ' + field)
    require(contract['candidate_version'] in (version, version + '-idf61.' + contract['runtime_revision'][:12]), 'Candidate version mismatch')
    require(set(contract['candidate_artifacts']) == FILES, 'Incomplete candidate artifact pins')
    for row in contract['candidate_artifacts'].values():
        require(type(row['bytes']) is int and row['bytes'] > 0 and hex_value(row['sha256'], 64), 'Invalid candidate artifact pin')
    require(type(contract['runtime_run_id']) is int and contract['runtime_run_id'] > 0
            and type(contract['runtime_run_attempt']) is int and contract['runtime_run_attempt'] > 0, 'Exact Runtime run required')
    require(type(contract['runtime_artifact_id']) is int and contract['runtime_artifact_id'] > 0, 'Exact original artifact ID required')
    return repository, prefix, version


def validate_candidate(archive, members, contract):
    expected = {'candidate/' + name for name in CANDIDATE_FILES}
    require({name for name in members if name.startswith('candidate/')} == expected, 'Candidate output set differs')
    require([name for name in members if PurePosixPath(name).name == 'qualification.json'] == ['candidate/qualification.json'], 'Ambiguous qualification')
    blobs = {name: archive.read('candidate/' + name) for name in CANDIDATE_FILES}
    require(digest(blobs['qualification.json']) == contract['qualification_sha256'], 'Qualification hash differs')
    sums = checksums(blobs['SHA256SUMS'])
    require(set(sums) == CANDIDATE_FILES - {'SHA256SUMS'}, 'Candidate checksum inventory differs')
    for name, sha in sums.items():
        require(digest(blobs[name]) == sha, 'Candidate checksum differs: ' + name)
    q, lock = decode(blobs['qualification.json']), decode(blobs['source-lock.json'])
    require(q.get('schema') == 1 and q.get('status') == 'software-qualified-candidate-hardware-pending', 'Candidate not software-qualified')
    for field, value in LIMITS.items():
        require(q.get(field) is value, 'Qualification limit changed: ' + field)
    require(q.get('input_lock') == lock and q.get('input_lock_sha256') == digest(blobs['source-lock.json']), 'Input lock mismatch')
    require(lock.get('schema') == 1 and lock.get('publication_enabled') is False, 'Input lock not candidate-only')
    require(lock.get('candidate_version') == contract['candidate_version'], 'Candidate version differs')
    require(set(lock['sources']) == ROLES, 'Source role set differs')
    for role, revision in contract['sources'].items():
        row = lock['sources'][role]
        require(row['revision'] == revision and hex_value(row['tree'], 40) and isinstance(row['submodules'], list), 'Source lock differs: ' + role)
        require(all(re.fullmatch(r'[0-9a-f]{40} .+', entry) for entry in row['submodules']), 'Invalid submodule source lock')
    proof = q['controlled_build']
    require(proof.get('fresh_build') is True and proof.get('same_process_qualification') is True
            and proof.get('detached_receipt_is_attestation') is False and proof.get('compile_jobs') == 1, 'Missing controlled single-job qualification')
    require(proof['sources'] == lock['sources'], 'Controlled source closure differs')
    require(decode(archive.read('build/native-build-evidence/build-closure.json')) == proof, 'Uploaded closure differs')
    require(q['artifacts'] == contract['candidate_artifacts'], 'Qualified artifact inventory differs')
    for name in FILES:
        require(record(blobs[name]) == contract['candidate_artifacts'][name], 'Payload differs: ' + name)
    baseline_bytes = archive.read('metadata/released-baseline.json')
    require(digest(baseline_bytes) == contract['baseline_contract_sha256'] == lock['baseline_contract_sha256']
            and decode(baseline_bytes) == q['baseline_contract'], 'Released baseline contract differs')
    require(q['baseline_contract']['product'] == contract['product'], 'Wrong baseline product')
    require(archive.read('build/native-build-evidence/source-lock.json') == blobs['source-lock.json'], 'Build/candidate lock bytes differ')
    require(q['unchanged_store_payloads'] == q['baseline_contract']['store_file_count'] - 1, 'Retained payload inventory differs')
    for field, sanitized in (('admission', False), ('admission_sanitized', True)):
        admission = q[field]
        require(admission['elf_count'] == q['baseline_contract']['elf_count']
                and admission['sanitized'] is sanitized and admission['hardware_calls'] == 0
                and admission['storage_calls'] == 0 and admission['target_instructions_executed'] is False,
                'Incomplete retained ELF admission: ' + field)
    for key in ('arduino_core_linked', 'ordinary_app_payloads_rebuilt', 'unselected_usb_host_controller'):
        require(q['native'].get(key) is False, 'Native composition limit differs: ' + key)
    require(q['native'].get('elf_bin_identical') is True, 'Native ELF/BIN proof missing')
    model = q['preservation_software_model']
    require(model.get('passed') is True and model.get('cases') == 496
            and model.get('nvs_and_appdata_preserved') is True
            and model.get('bootloader_compatibility_tested') is False and model.get('hardware_tested') is False,
            'Preservation model or hardware limits differ')
    for name, row in lock['native_files'].items():
        path = 'build/' + str(safe_name(row['path']))
        expected = {key: row[key] for key in ('bytes', 'sha256')}
        require(members.get(path) == expected and proof['artifacts'].get(name) == expected, 'Uploaded native input differs: ' + name)
    for name, key in (('firmware.bin', 'firmware_bin'), ('bootloader.bin', 'bootloader'), ('partitions.bin', 'partitions')):
        require(q['artifacts'][name] == {field: lock['native_files'][key][field] for field in ('bytes', 'sha256')}, 'Payload/linked build mismatch')
    return blobs, q


def validate_runtime_manifest(manifest, contract, members):
    require(manifest.get('schema') == 1 and manifest.get('enabled') is True, 'Runtime manifest is disabled/unknown')
    require(manifest.get('repository') == contract['runtime_repository'] == 'michaelrolphone-cmyk/RiscRTE'
            and manifest.get('tag') == contract['runtime_tag'] == 'firmware-v0.4.0'
            and manifest.get('version') == '0.4.0'
            and manifest.get('publication_branch') == 'work/native-idf-6.1', 'Runtime release identity differs')
    require(manifest.get('source_sha') == contract['runtime_revision'] == contract['runtime_release_revision'], 'Runtime source/release tag differs')
    require(manifest.get('run_id') == contract['runtime_run_id']
            and manifest.get('run_attempt') == contract['runtime_run_attempt'], 'Runtime run/attempt differs')
    require(type(manifest.get('workflow_id')) is int and manifest['workflow_id'] > 0
            and hex_value(manifest.get('source_workflow_sha256'), 64), 'Runtime workflow identity missing')
    require(set(manifest.get('artifacts', {})) == {'generic', 'twatch', 'waveshare', 'x4'}, 'Runtime product matrix incomplete')
    row = manifest['artifacts'][contract['product']]
    require(row.get('id') == contract['runtime_artifact_id']
            and row.get('name') == 'native-idf6-' + contract['product'] + '-' + contract['runtime_revision']
            and row.get('sha256') == contract['evidence_sha256'], 'Original CI artifact differs')
    require(type(row.get('job_id')) is int and row['job_id'] > 0
            and isinstance(row.get('job_name'), str) and row['job_name'], 'Original CI job missing')
    require(row.get('members') == members, 'Complete ZIP member inventory differs')
    require(set(row.get('sources', {})) == set(contract['sources']), 'Runtime artifact source roles differ')
    for role, revision in contract['sources'].items():
        pin = row['sources'][role]
        require(set(pin) == {'revision', 'tree', 'submodules'} and pin['revision'] == revision
                and hex_value(pin['tree'], 40) and isinstance(pin['submodules'], list), 'Runtime artifact source differs: ' + role)
        require(all(re.fullmatch(r'[0-9a-f]{40} [^\n\r]+', entry) for entry in pin['submodules'])
                and len(pin['submodules']) == len(set(pin['submodules'])), 'Runtime submodule lock differs')
    return row


def verify_runtime_envelope(contract, manifest_bytes, evidence_path):
    require(evidence_path.is_file() and not evidence_path.is_symlink()
            and evidence_path.stat().st_size <= 1024 * 1024 * 1024, 'Invalid/oversized evidence ZIP')
    require(digest(manifest_bytes) == contract['runtime_manifest_sha256'], 'Runtime manifest digest differs')
    require(digest(evidence_path.read_bytes()) == contract['evidence_sha256'], 'Original evidence digest differs')
    members = archive_members(evidence_path)
    row = validate_runtime_manifest(decode(manifest_bytes), contract, members)
    require(row['bytes'] == evidence_path.stat().st_size, 'Original ZIP size differs')
    manifest = decode(manifest_bytes)
    with zipfile.ZipFile(evidence_path) as archive:
        require(digest(archive.read('metadata/workflow.yml')) == manifest['source_workflow_sha256'], 'Archived workflow differs')
        ci = decode(archive.read('metadata/ci-run.json'))
        expected = {'GITHUB_REPOSITORY': contract['runtime_repository'], 'GITHUB_SHA': contract['runtime_revision'],
                    'GITHUB_REF': 'refs/heads/work/native-idf-6.1', 'GITHUB_RUN_ID': str(contract['runtime_run_id']),
                    'GITHUB_RUN_ATTEMPT': str(contract['runtime_run_attempt']),
                    'GITHUB_WORKFLOW_REF': contract['runtime_repository'] + '/.github/workflows/native-idf6.yml@refs/heads/work/native-idf-6.1',
                    'GITHUB_WORKFLOW_SHA': contract['runtime_revision'], 'PRODUCT': contract['product']}
        for key, value in expected.items():
            require(ci.get(key) == value, 'Archived CI identity differs: ' + key)
        before, after = (decode(archive.read('metadata/sources-' + phase + '.json')) for phase in ('before', 'after'))
        require(before == after and before.get('schema') == 1 and set(before['sources']) == set(row['sources']), 'CI source custody differs')
        for role, pin in row['sources'].items():
            actual = before['sources'][role]
            require(actual.get('clean') is True and {key: actual[key] for key in ('revision', 'tree', 'submodules')} == pin, 'Unclean/mismatched CI source: ' + role)
    return members, row


def transport(contract_path, manifest_path, evidence_path, source_revision, output):
    contract_bytes = contract_path.read_bytes()
    contract = decode(contract_bytes)
    repository, prefix, version = final_contract(contract)
    require(hex_value(source_revision, 40), 'Transport source revision required')
    require(not output.exists(), 'Output must be new')
    manifest_bytes = manifest_path.read_bytes()
    members, runtime_artifact = verify_runtime_envelope(contract, manifest_bytes, evidence_path)
    with zipfile.ZipFile(evidence_path) as archive:
        blobs, qualification = validate_candidate(archive, members, contract)
    require(qualification['input_lock']['sources'] == runtime_artifact['sources'], 'Runtime/candidate source locks differ')
    evidence_bytes = evidence_path.read_bytes()
    require(digest(evidence_bytes) == contract['evidence_sha256'], 'Evidence changed during validation')
    stem = prefix + '-' + version + '-Native-IDF61'
    output_files = {
        stem + '-factory-erases-data-0x0.bin': blobs['factory-candidate-erases-data-0x0.bin'],
        stem + '-firmware.bin': blobs['firmware.bin'],
        stem + '-bootloader.bin': blobs['bootloader.bin'],
        stem + '-partitions.bin': blobs['partitions.bin'],
        stem + '-store.bin': blobs['store.bin'],
        stem + '-Evidence.zip': evidence_bytes,
        'qualification.json': blobs['qualification.json'], 'source-lock.json': blobs['source-lock.json'],
        'runtime-release-manifest.json': manifest_bytes, 'transport-contract.json': contract_bytes,
    }
    output_files['RELEASE-NOTES.txt'] = (prefix + ' ' + version + ' native ESP-IDF 6.1 candidate\n\n'
        'Software-qualified; hardware testing is pending.\n'
        'WARNING: the factory image erases internal saved settings and data.\n'
        'No data-preserving SDK migration or OTA kit is supplied. The separate firmware,\n'
        'bootloader, partitions and store files are evidence, not a flashing procedure.\n'
        'Exact deployed-bootloader boot, health confirmation and rollback remain untested.\n'
        'The original controlled Runtime CI evidence ZIP is copied byte-for-byte.\n'
        'Released application/provider payloads and board/boot/data layouts were retained\n'
        'and checked by the candidate qualification. No hardware access occurred.\n').encode()
    custody = dict(schema=1, repository=repository, version=version, candidate_version=contract['candidate_version'],
                   source_revision=source_revision, compiled_product_revision=contract['sources']['product'],
                   runtime_revision=contract['runtime_revision'], runtime_release_revision=contract['runtime_release_revision'],
                   runtime_tag=contract['runtime_tag'], runtime_run_id=contract['runtime_run_id'],
                   runtime_run_attempt=contract['runtime_run_attempt'], runtime_artifact_id=contract['runtime_artifact_id'],
                   original_evidence_sha256=contract['evidence_sha256'], runtime_manifest_sha256=contract['runtime_manifest_sha256'],
                   qualification_sha256=contract['qualification_sha256'], rebuilt=False, evidence_repacked=False,
                   limits=LIMITS, artifacts={name: record(data) for name, data in sorted(output_files.items())})
    output_files['release.json'] = encoded(custody)
    output_files['SHA256SUMS'] = ''.join(digest(data) + '  ' + name + '\n' for name, data in sorted(output_files.items())).encode()
    output.mkdir(parents=True)
    for name, data in output_files.items():
        (output / name).write_bytes(data)
    verify_output(output, digest(output_files['SHA256SUMS']), source_revision)


def verify_output(output, expected_sha, source_revision):
    require(digest((output / 'SHA256SUMS').read_bytes()) == expected_sha, 'Output checksum custody differs')
    sums = checksums((output / 'SHA256SUMS').read_bytes())
    require({p.name for p in output.iterdir()} == set(sums) | {'SHA256SUMS'}, 'Output asset set differs')
    for name, sha in sums.items():
        path = output / name
        require(path.is_file() and not path.is_symlink() and digest(path.read_bytes()) == sha, 'Output asset changed: ' + name)
    custody = decode((output / 'release.json').read_bytes())
    require(custody['source_revision'] == source_revision and custody['rebuilt'] is False
            and custody['evidence_repacked'] is False and custody['limits'] == LIMITS, 'Output custody differs')
    for name, row in custody['artifacts'].items():
        require(record((output / name).read_bytes()) == row, 'Output custody hash differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--runtime-manifest', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    transport(args.contract, args.runtime_manifest, args.evidence, args.source_revision, args.output)


if __name__ == '__main__':
    main()

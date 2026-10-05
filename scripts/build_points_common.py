#!/usr/bin/env python3
"""Derive a variant-neutral Points store from eight exact-head CI deployments.

Only board.revision is normalized. Reconstructing every deterministic input ZIP
proves the common payload still has the recorded input archive hashes.
"""
import argparse
import copy
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

if not __debug__:
    raise RuntimeError('Verification requires normal Python, never optimized mode')

from build_clock_deployment import ROOT, ALARM_DEVICES, encoded, selected_board, sha
from verify_points_deployment import verify as verify_alarm

PROFILE = 'points-launcher-common'
APPS = ('default', 'clock', 'springboard', 'battery', 'settings', 'calculator',
        'stopwatch', 'alarms', 'countdown', 'points_in_time')
DRIVERS = ('gpio', 'i2c', 'pmu', 'panel', 'rtc', 'touch', 'haptic', 'speaker',
           'alarm-service')
STORE_PATHS = {'store/board.json', 'store/boot.json'} | {
    'store/' + app + ext for app in APPS for ext in ('.elf', '.json')
} | {'store/' + driver + '/' + name for driver in DRIVERS
     for name in ('driver.elf', 'manifest.json')}
# Exact output/lifecycle prerequisites, already reviewed and target-built at
# Watch f5b1418. A new transport generation needs an explicit custody update.
DRIVER_PACKAGES = {
    'twatch-gpio': '0f079b1d8957725ef38c037252eb8cf25e42f2dfff10157bd71cedf4aec78549',
    'twatch-i2c': 'ec6c7e5919c9eec4cfddf23936e44d9ec2afa2a01c875063b1f332427c269f05',
    'twatch-pmu': 'bad863125be0bcc56f3478f86ebc6a0dca7ef1ff232bfb7b7612f30be487c476',
    'twatch-panel': '6b59a6c443becc77ca8240cbc7624bca0865e408e45f46973cf0639f8fd6b90d',
    'twatch-touch': 'ae61e587bf83d57c5c1b8d9ed40b66b87026629eb70ded60c7fd550e1c7a80b5',
    'twatch-rtc': '982527a90259f3149376f4198b8b8689499504be946e8af84903874a5a2cb56f',
    'twatch-haptic': '55a070d37fec9470e541bebdcccd75824a7f1601cf75a6ac20b522ec0b27069e',
    'twatch-speaker': '74954eaea49ca49ed7c52305436553b9270da64ce2572febbbbf5a84b4a1c9e6',
}
_SERVICE_BASELINE = json.loads((ROOT/'apps/points-service-baseline.json').read_text())
SERVICE_SHA256 = _SERVICE_BASELINE['elf_sha256']
SERVICE_SOURCE_SHA256 = _SERVICE_BASELINE['source_sha256']
SERVICE_SIZE = _SERVICE_BASELINE['size_bytes']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value)


def read_zip(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and len(names) <= 1000,
                'Unsafe or duplicate archive membership')
        require(sum(e.file_size for e in archive.infolist()) <= 160 * 1024 * 1024,
                'Archive exceeds bounded artifact size')
        require(all(n and not n.startswith('/') and '\\' not in n and
                    '..' not in PurePosixPath(n).parts and not n.endswith('/')
                    for n in names), 'Unsafe archive path')
        return {n: archive.read(n) for n in names}


def zip_bytes(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def profiles(root):
    result = {Path(p).stem for p in json.loads((root / 'board.json').read_text())['profiles']}
    require(len(result) == 8, 'Exactly eight explicit profiles required')
    return result


def store(files, profile, root):
    result = {n: b for n, b in files.items() if n.startswith('store/')}
    require(set(result) == STORE_PATHS, 'Points store must contain exactly 40 selected files')
    require(files['source-profile.json'] == (root / 'hardware' / (profile + '.json')).read_bytes(),
            'Source profile differs from reviewed checkout')
    board = json.loads(result['store/board.json'])
    require(board == selected_board(json.loads(files['source-profile.json']), ALARM_DEVICES, True),
            'Selected wiring differs from the exact source profile')
    require(result['store/board.json'] == encoded(board), 'Noncanonical board encoding')
    require(board['revision'] == profile, 'Board revision differs from source profile')
    board['revision'] = PROFILE
    result['store/board.json'] = encoded(board)
    return result


def shared_record(record):
    return {k: v for k, v in record.items() if k not in ('entries', 'profile')}


def verify_provenance(files, record, root):
    """Reject stale build records and self-consistently rehashed prerequisites."""
    head = record['source_sha']
    require(exact_sha(head), 'Missing exact source SHA')
    pins = json.loads((root / 'apps/points-sources.json').read_text())
    runtime = json.loads((root / 'apps/alarm-runtime-requirements.json').read_text())
    require(json.loads(files['runtime-requirements.json']) == record['runtime_requirements'] == runtime,
            'Runtime provenance differs from source pins')
    require(json.loads(files['time-policy.json']) == record['time_policy'] ==
            json.loads((root / 'apps/clock/time-policy.json').read_text()), 'Clock time policy mismatch')
    metadata = json.loads(files['shared-app-build.json'])
    require(metadata['shared_sources'] == json.loads(files['shared/alarm-sources.json']) == pins,
            'Shared source pins differ from build provenance')
    require(set(metadata['apps']) == set(APPS), 'Build record app membership mismatch')
    require(metadata['alarm_service']['runtime'] == pins['runtime'], 'Stale service runtime pin')
    require(metadata['touch_rotation'] == 0 and metadata['handoff_ms'] == 60 and
            metadata['rtc_policy'] == 'fixed-UTC+08-to-America/Denver' and
            metadata['full_frames'] is True and metadata['retained_handoff'] is True,
            'Launcher build policy mismatch')
    for name in APPS:
        owner = head if name in ('default', 'clock') else pins[
            'system-apps' if name in ('springboard', 'settings') else 'productivity' if name=='points_in_time' else 'utilities']['commit']
        app = metadata['apps'][name]
        manifest = json.loads(files['store/' + name + '.json'])
        require(app['repository_sha'] == owner and app['version'] == manifest['version'],
                'Stale application source/build record: ' + name)
        if name in ('default', 'clock'):
            require(app['version'] == record['app_version'] and
                    app['size_bytes'] == len(files['store/' + name + '.elf']),
                    'Clock payload provenance mismatch')
    service = json.loads(files['shared/alarm-service-build.json'])
    require(service['source_pins'] == pins and service['service_version'] == '0.3.0' and
            service['source_sha256'] == SERVICE_SOURCE_SHA256 and service['size_bytes'] == SERVICE_SIZE and
            service['elf_sha256'] == sha(files['store/alarm-service/driver.elf']) == SERVICE_SHA256,
            'Canonical alarm service changed')
    require(len(record['drivers']) == 9 and {d['id'] for d in record['drivers']} == set(DRIVER_PACKAGES),
            'Driver package membership mismatch')
    boot = json.loads(files['store/boot.json'])
    for driver in record['drivers']:
        raw = files['packages/' + driver['archive']]
        require(driver['sha256'] == sha(raw) == DRIVER_PACKAGES[driver['id']] and
                driver['size_bytes'] == len(raw), 'Canonical driver package changed')
        package = read_zip(io.BytesIO(raw))
        source_manifest = json.loads(package['source-manifest.json'])
        require(source_manifest['id'] == driver['id'] and source_manifest['version'] == driver['version'],
                'Driver package identity mismatch')
        deployed = next(d for d in boot['drivers'] if d.get('instance_id') == driver['instance_id'])
        require(files['store/' + deployed['manifest']] == encoded(source_manifest),
                'Deployed driver manifest differs from package')
        elf_path = 'store/' + str(PurePosixPath(deployed['manifest']).parent / source_manifest['file_name'])
        require(files[elf_path] == package['driver.elf'], 'Deployed driver ELF differs from package')


def verify(path, root=ROOT, expected_head=None):
    """Verify policy, all eight original ZIP hashes, and the sole normalization."""
    files = read_zip(path)
    record = verify_alarm(path)
    verify_provenance(files, record, root)
    head = record['source_sha']
    require(exact_sha(head) and record.get('pull_request_head_sha') == head,
            'Common store requires one exact source and PR head')
    require(expected_head is None or head == expected_head, 'Unexpected source head')
    require(record['profile'] == PROFILE, 'Not an alarm common deployment')
    proof = record['common_points_launcher']
    require(proof['normalization'] == {'path': 'store/board.json', 'field': 'revision',
                                      'value': PROFILE}, 'Unexpected normalization')
    require(proof['store_files'] == 40, 'Incorrect common store file count')
    inputs = proof['inputs']
    require(len(inputs) == 8 and {i['profile'] for i in inputs} == profiles(root),
            'Missing or duplicate explicit profile')
    actual_store = {n: b for n, b in files.items() if n.startswith('store/')}
    require(set(actual_store) == STORE_PATHS, 'Points store must contain exactly 40 selected files')
    shared = {n: b for n, b in files.items() if not n.startswith(('store/', 'sources/'))
              and n != 'deployment-record.json'}
    expected_names = set(shared) | STORE_PATHS | {'deployment-record.json'}
    for item in inputs:
        profile = item['profile']
        prefix = 'sources/' + profile + '/'
        expected_names.update(prefix + n for n in ('source-profile.json', 'deployment-record.json'))
        original_record = json.loads(files[prefix + 'deployment-record.json'])
        require(original_record['profile'] == profile and original_record['source_sha'] == head,
                'Input source provenance mismatch')
        expected_record = copy.deepcopy(original_record)
        expected_record.update(profile=PROFILE, pull_request_head_sha=head)
        expected_record['transformations'].append(
            'Normalize only board.revision after all eight Points stores compare byte-for-byte')
        require({k: v for k, v in record.items() if k not in ('entries', 'common_points_launcher')} ==
                {k: v for k, v in expected_record.items() if k != 'entries'},
                'Common record does not preserve original provenance')
        original_store = dict(actual_store)
        board = json.loads(original_store['store/board.json'])
        board['revision'] = profile
        original_store['store/board.json'] = encoded(board)
        original = {**shared, **original_store,
                    'source-profile.json': files[prefix + 'source-profile.json'],
                    'deployment-record.json': files[prefix + 'deployment-record.json']}
        entries = original_record['entries']
        require(len(entries) == len({e['path'] for e in entries}) and
                {e['path'] for e in entries} == set(original) - {'deployment-record.json'},
                'Original input membership mismatch')
        require(all(len(original[e['path']]) == e['size_bytes'] and
                    sha(original[e['path']]) == e['sha256'] for e in entries),
                'Original input checksum mismatch')
        require(store(original, profile, root) == actual_store, 'Unexpected store transformation')
        raw = zip_bytes(original)
        require(item['source_sha'] == head and item['size_bytes'] == len(raw) and
                item['sha256'] == sha(raw) and
                item['source_profile_sha256'] == sha(original['source-profile.json']),
                'Reconstructed original archive differs from input custody')
    require(set(files) == expected_names, 'Unexpected common deployment member')
    return record


def build(archives, out, pr_head_sha, root=ROOT):
    require(exact_sha(pr_head_sha), 'Exact PR head required')
    require(len(archives) == 8, 'Common Points store requires all eight explicit archives')
    allowed_profiles = profiles(root)
    inputs = []
    for path in map(Path, archives):
        files = read_zip(path)
        record = verify_alarm(path)
        verify_provenance(files, record, root)
        profile = record['profile']
        require(profile in allowed_profiles and profile not in {i['profile'] for i in inputs},
                'Unknown or duplicate input profile')
        require(record['source_sha'] == pr_head_sha, 'Input source differs from exact PR head')
        require(path.read_bytes() == zip_bytes(files), 'Input archive is not canonical')
        inputs.append({'path': path, 'profile': profile, 'record': record,
                       'files': files, 'store': store(files, profile, root)})
    inputs.sort(key=lambda i: i['profile'])
    first = inputs[0]
    other_files = lambda f: {n: b for n, b in f.items() if not n.startswith('store/')
                             and n not in ('deployment-record.json', 'source-profile.json')}
    shared = other_files(first['files'])
    for item in inputs[1:]:
        require(item['store'] == first['store'], 'Selected Points store differs across profiles')
        require(shared_record(item['record']) == shared_record(first['record']),
                'Input deployment provenance differs')
        require(other_files(item['files']) == shared, 'Non-profile deployment files differ')
    files = {**shared, **first['store']}
    provenance = []
    for item in inputs:
        profile = item['profile']
        for n in ('source-profile.json', 'deployment-record.json'):
            files['sources/' + profile + '/' + n] = item['files'][n]
        raw = item['path'].read_bytes()
        provenance.append({'profile': profile, 'archive': item['path'].name,
                           'source_sha': pr_head_sha, 'size_bytes': len(raw), 'sha256': sha(raw),
                           'source_profile_sha256': sha(item['files']['source-profile.json'])})
    record = copy.deepcopy(first['record'])
    record.update(profile=PROFILE, pull_request_head_sha=pr_head_sha)
    record['common_points_launcher'] = {
        'normalization': {'path': 'store/board.json', 'field': 'revision', 'value': PROFILE},
        'store_files': 40, 'inputs': provenance,
        'scope': 'Ten app policies, nine physical instances and one service; no radio or IMU selected',
        'physical_verification': 'pending'}
    record['transformations'].append(
        'Normalize only board.revision after all eight Points stores compare byte-for-byte')
    record['entries'] = [{'path': n, 'size_bytes': len(b), 'sha256': sha(b)}
                         for n, b in sorted(files.items())]
    files['deployment-record.json'] = encoded(record)
    out = Path(out)
    archive = out / ('twatch-points-launcher-' + record['app_version'] + '-' + PROFILE + '.zip')
    require(archive.resolve() not in {Path(p).resolve() for p in archives}, 'Output aliases an input')
    out.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(zip_bytes(files))
    verify(archive, root=root, expected_head=pr_head_sha)
    row = {'profile': PROFILE, 'archive': archive.name, 'sha256': sha(archive.read_bytes()),
           'source_sha': pr_head_sha}
    (out / 'catalog.json').write_bytes(encoded({'schema': 1, 'deployments': [row]}))
    return row


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/points-common')
    parser.add_argument('--pr-head-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.archives, args.output, args.pr_head_sha), indent=2))

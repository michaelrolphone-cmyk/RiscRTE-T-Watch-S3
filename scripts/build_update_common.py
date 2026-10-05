#!/usr/bin/env python3
"""Derive a variant-neutral paired update store from eight exact-head CI deployments.

Only board.revision is normalized. Reconstructing every deterministic input ZIP
proves the common payload still has the recorded input archive hashes.
"""
from build_legacy_sleep import legacy_inputs
import argparse
import copy
import json
from pathlib import Path

if not __debug__:
    raise RuntimeError('Verification requires normal Python, never optimized mode')

from build_clock_deployment import ROOT, WIFI_DEVICES, encoded, selected_board, sha
from verify_update_deployment import verify as verify_update

PROFILE = 'update-launcher-common'
from verify_update_deployment import verify_files, SELECTIONS, kind_path
from build_wifi_common import read_zip, require, exact_sha, zip_bytes, profiles

def store_paths(files, root=ROOT):
    record = json.loads(files['deployment-record.json'])
    selected = tuple(record['updates']['apps'])
    require(selected in SELECTIONS, 'Unknown updater selection')
    baseline = json.loads((root/'scripts/update-preservation-baseline.json').read_text())
    names = {'store/board.json'} | {'store/'+n for n in baseline['files']}
    for app in selected:
        short = kind_path(app)[1]
        names.update({'store/'+app+'.elf', 'store/'+app+'.json',
                      'store/'+short+'/driver.elf', 'store/'+short+'/manifest.json'})
    return names


def store(files, profile, root):
    result = {n: b for n, b in files.items() if n.startswith('store/')}
    require(set(result) == store_paths(files, root), 'Paired store membership differs from baseline and selected updates')
    require(files['source-profile.json'] == (legacy_inputs(root) / 'hardware' / (profile + '.json')).read_bytes(),
            'Source profile differs from reviewed checkout')
    board = json.loads(result['store/board.json'])
    require(board == selected_board(json.loads(files['source-profile.json']), WIFI_DEVICES, True),
            'Selected wiring differs from the exact source profile')
    require(result['store/board.json'] == encoded(board), 'Noncanonical board encoding')
    require(board['revision'] == profile, 'Board revision differs from source profile')
    board['revision'] = PROFILE
    result['store/board.json'] = encoded(board)
    return result


def shared_record(record):
    return {k: v for k, v in record.items() if k not in ('entries', 'profile')}



def verify(path, root=ROOT, expected_head=None):
    """Verify policy, all eight original ZIP hashes, and the sole normalization."""
    files = read_zip(path)
    record = verify_files(files, root=root, common=True)
    head = record['source_sha']
    require(exact_sha(head) and record.get('pull_request_head_sha') == head,
            'Common store requires one exact source and PR head')
    require(expected_head is None or head == expected_head, 'Unexpected source head')
    require(json.loads(files['store/board.json'])['revision'] == PROFILE, 'Incorrect common board revision')
    require(record['profile'] == PROFILE, 'Not a paired update common deployment')
    proof = record['common_update_launcher']
    require(proof['normalization'] == {'path': 'store/board.json', 'field': 'revision',
                                      'value': PROFILE}, 'Unexpected normalization')
    require(proof['store_files'] == len(store_paths(files, root)), 'Incorrect common store file count')
    inputs = proof['inputs']
    require(len(inputs) == 8 and {i['profile'] for i in inputs} == profiles(root),
            'Missing or duplicate explicit profile')
    actual_store = {n: b for n, b in files.items() if n.startswith('store/')}
    require(set(actual_store) == store_paths(files, root), 'Paired store membership differs from baseline and selected updates')
    shared = {n: b for n, b in files.items() if not n.startswith(('store/', 'sources/'))
              and n != 'deployment-record.json'}
    expected_names = set(shared) | store_paths(files, root) | {'deployment-record.json'}
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
            'Normalize only board.revision after all eight paired update stores compare byte-for-byte')
        require({k: v for k, v in record.items() if k not in ('entries', 'common_update_launcher')} ==
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
        verify_files(original, root=root, expected_head=head)
        raw = zip_bytes(original)
        require(item['source_sha'] == head and item['size_bytes'] == len(raw) and
                item['sha256'] == sha(raw) and
                item['source_profile_sha256'] == sha(original['source-profile.json']),
                'Reconstructed original archive differs from input custody')
    require(set(files) == expected_names, 'Unexpected common deployment member')
    return record


def build(archives, out, pr_head_sha, root=ROOT):
    require(exact_sha(pr_head_sha), 'Exact PR head required')
    require(len(archives) == 8, 'Common paired update store requires all eight explicit archives')
    allowed_profiles = profiles(root)
    inputs = []
    for path in map(Path, archives):
        files = read_zip(path)
        record = verify_update(path, root=root)
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
        require(item['store'] == first['store'], 'Selected paired update store differs across profiles')
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
    record['common_update_launcher'] = {
        'normalization': {'path': 'store/board.json', 'field': 'revision', 'value': PROFILE},
        'store_files': len(first['store']), 'inputs': provenance,
        'scope': 'Exact baseline authority and selected updater app/provider pairs; only board.revision normalized',
        'physical_verification': 'pending'}
    record['transformations'].append(
        'Normalize only board.revision after all eight paired update stores compare byte-for-byte')
    record['entries'] = [{'path': n, 'size_bytes': len(b), 'sha256': sha(b)}
                         for n, b in sorted(files.items())]
    files['deployment-record.json'] = encoded(record)
    out = Path(out)
    archive = out / ('twatch-update-launcher-' + record['app_version'] + '-' + PROFILE + '.zip')
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
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/update-common')
    parser.add_argument('--pr-head-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.archives, args.output, args.pr_head_sha), indent=2))

#!/usr/bin/env python3
"""Derive a clock-only common store from all eight verified explicit deployments.

Only the top-level board.revision value may differ. This does not identify the
watch's radio/IMU or permit loading their drivers. Payload provenance is inherited
from the inputs, never relabeled with the builder checkout's current commit.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import zipfile

from build_clock_deployment import DEVICES, ROOT, encoded, sha
from verify_clock_deployment import verify

PROFILE = 'crown-clock-common'
STORE_PATHS = {'store/board.json', 'store/boot.json', 'store/default.elf',
               'store/default.json'} | {
    f'store/{driver}/{name}' for driver in DEVICES.values()
    for name in ('driver.elf', 'manifest.json')}


def normalized_store(files, profile):
    store = {name: data for name, data in files.items() if name.startswith('store/')}
    if set(store) != STORE_PATHS:
        raise ValueError('Common clock requires exactly the 14 selected store files')
    board = json.loads(store['store/board.json'])
    if board['revision'] != profile:
        raise ValueError('Board revision differs from the deployment profile')
    # Reject formatting changes too: reserialization must not mask any difference
    # other than the single revision value in the existing canonical builder format.
    if store['store/board.json'] != encoded(board):
        raise ValueError('Board bytes are not the canonical deployment encoding')
    board['revision'] = PROFILE
    store['store/board.json'] = encoded(board)
    return store


def build(archives, out=None, root=ROOT, pr_head_sha=None):
    out = Path(out) if out is not None else root / 'dist/clock-common'
    if pr_head_sha is not None and not re.fullmatch(r'[0-9a-f]{40}', pr_head_sha):
        raise ValueError('Pull-request head must be a complete Git SHA')
    selector = json.loads((root / 'board.json').read_text())
    profiles = {Path(path).stem for path in selector['profiles']}
    if len(profiles) != 8 or len(archives) != 8:
        raise ValueError('Common clock requires all eight explicit profile archives')

    inputs = []
    for path in archives:
        path = Path(path)
        record = verify(path)
        profile = record['profile']
        if not re.fullmatch(r'[0-9a-f]{40}', record['source_sha']):
            raise ValueError('Input source must be a complete Git SHA')
        if not re.fullmatch(r'\d+\.\d+\.\d+', record['app_version']):
            raise ValueError('Input application version must be numeric MAJOR.MINOR.PATCH')
        with zipfile.ZipFile(path) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        if profile not in profiles or any(item['profile'] == profile for item in inputs):
            raise ValueError('Unknown or duplicate input profile')
        if json.loads(files['source-profile.json'])['revision'] != profile:
            raise ValueError('Source profile differs from the deployment profile')
        app = json.loads(files['store/default.json'])
        if record['app_version'] != app['version'] or record['app_id'] != app['id']:
            raise ValueError('Application provenance differs from the payload')
        inputs.append({'path': path, 'profile': profile, 'record': record,
                       'files': files, 'store': normalized_store(files, profile)})

    inputs.sort(key=lambda item: item['profile'])
    first = inputs[0]
    shared_record = {key: value for key, value in first['record'].items()
                     if key not in ('entries', 'profile')}
    shared_files = {name: data for name, data in first['files'].items()
                    if not name.startswith('store/') and
                    name not in ('deployment-record.json', 'source-profile.json')}
    for item in inputs[1:]:
        differing = [name for name in sorted(STORE_PATHS)
                     if item['store'][name] != first['store'][name]]
        if differing:
            raise ValueError(f"Selected store differs for {item['profile']}: {', '.join(differing)}")
        metadata = {key: value for key, value in item['record'].items()
                    if key not in ('entries', 'profile')}
        if metadata != shared_record:
            raise ValueError('Input deployment provenance differs; do not mix generations')
        other_files = {name: data for name, data in item['files'].items()
                       if not name.startswith('store/') and
                       name not in ('deployment-record.json', 'source-profile.json')}
        if other_files != shared_files:
            raise ValueError('Non-profile deployment files differ')

    files = {**shared_files, **first['store']}
    provenance = []
    for item in inputs:
        profile = item['profile']
        for name in ('source-profile.json', 'deployment-record.json'):
            files[f'sources/{profile}/{name}'] = item['files'][name]
        data = item['path'].read_bytes()
        provenance.append({'profile': profile, 'archive': item['path'].name,
                           'size_bytes': len(data), 'sha256': sha(data),
                           'source_sha': item['record']['source_sha'],
                           'source_profile_sha256': sha(item['files']['source-profile.json'])})
    record = copy.deepcopy(shared_record)
    if pr_head_sha is not None:
        record['pull_request_head_sha'] = pr_head_sha
    record.update(profile=PROFILE, common_clock={
        'normalization': {'path': 'store/board.json', 'field': 'revision', 'value': PROFILE},
        'store_files': len(STORE_PATHS), 'inputs': provenance,
        'scope': 'Five-driver clock closure only; no radio or IMU variant is selected',
        'physical_verification': 'pending'})
    record['transformations'].append('Normalize only board.revision after all eight selected stores compare byte-for-byte')
    record['entries'] = [{'path': name, 'size_bytes': len(data), 'sha256': sha(data)}
                         for name, data in sorted(files.items())]
    files['deployment-record.json'] = encoded(record)
    out.mkdir(parents=True, exist_ok=True)
    archive_path = out / f"twatch-clock-{record['app_version']}-{PROFILE}.zip"
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    verify(archive_path)
    for name, data in files.items():
        path = out / PROFILE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    row = {'profile': PROFILE, 'archive': archive_path.name,
           'sha256': sha(archive_path.read_bytes()), 'source_sha': record['source_sha']}
    (out / 'catalog.json').write_bytes(encoded({'schema': 1, 'deployments': [row]}))
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='*', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/clock-common')
    parser.add_argument('--pr-head-sha', help='PR head, separate from the input CI checkout/source SHA')
    args = parser.parse_args()
    paths = args.archives or sorted((ROOT / 'dist/clock-deployments').glob('*.zip'))
    row = build(paths, args.output, pr_head_sha=args.pr_head_sha)
    print('Verified common clock deployment:', row['archive'], row['sha256'])


if __name__ == '__main__':
    main()

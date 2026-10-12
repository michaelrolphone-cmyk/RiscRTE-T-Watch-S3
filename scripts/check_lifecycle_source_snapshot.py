#!/usr/bin/env python3
"""Verify original Watch18 custody and explicitly pinned current input successors."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('docs/lifecycle/watch-1.0.18')
CURRENT = Path('docs/lifecycle/current-target-inputs.json')


def require(value, message):
    if not value:
        raise ValueError(message)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def ordinary_file(root, name):
    path = root / name
    require(not Path(name).is_absolute() and '..' not in Path(name).parts and
            path.is_file() and path.resolve() == path.absolute(),
            'Missing or linked custody file: ' + name)
    return path.read_bytes()


def verify_target_inputs(root, record, current):
    # The historical digests always describe the original app-build tree. A
    # later approved live input must not replace or relabel that evidence.
    original = record['heads']['app-build']['commit']
    require(current['schema'] == 1, 'Wrong current input custody schema')
    successors = current['target_watch_inputs']
    require(set(successors) <= set(record['target_watch_inputs']),
            'Current successor is not an original target input')
    for name, digest in record['target_watch_inputs'].items():
        historical = git(root, 'show', original + ':' + name)
        require(hashlib.sha256(historical).hexdigest() == digest,
                'Original target input differs: ' + name)
        expected = historical
        if name in successors:
            item = successors[name]
            source = item['source_commit']
            require(len(source) == 40 and all(c in '0123456789abcdef' for c in source),
                    'Current successor requires an exact source commit: ' + name)
            require(subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor',
                                    source, 'HEAD']).returncode == 0,
                    'Current successor source is not in this checkout history: ' + name)
            expected = git(root, 'show', source + ':' + name)
            require(hashlib.sha256(expected).hexdigest() == item['sha256'],
                    'Current successor source hash differs: ' + name)
            require(expected != historical, 'Redundant current successor: ' + name)
        require(ordinary_file(root, name) == expected, 'Current target input differs: ' + name)


def verify(root=ROOT):
    record = json.loads(ordinary_file(root, str(BASE / 'source-custody.json')))
    require(record['schema'] == 1 and record['dependency_sources_included'] is False and
            record['provisioning_payloads_included'] is False and
            record['separate_model_header_or_provisioning_payloads_included'] is False,
            'Wrong original custody scope')
    bundle = BASE / record['bundle']['file']
    raw = ordinary_file(root, str(bundle))
    require(len(raw) == record['bundle']['size_bytes'] and
            hashlib.sha256(raw).hexdigest() == record['bundle']['sha256'],
            'Original source bundle bytes differ')
    subprocess.run(['git', '-C', str(root), 'bundle', 'verify', str(root / bundle)], check=True)
    subprocess.run(['git', '-C', str(root), 'fetch', str(root / bundle),
                    'refs/watch-custody/1.0.18/*:refs/watch-custody/1.0.18/*'], check=True)
    for item in record['heads'].values():
        actual = git(root, 'rev-parse', item['bundle_ref']).decode().strip()
        require(actual == item['commit'], 'Original source commit differs')
        require(git(root, 'rev-parse', actual + '^{tree}').decode().strip() == item['tree'],
                'Original source tree differs')
    for name, ref in record['selected_source_files'].items():
        expected = git(root, 'show', record['heads'][ref]['commit'] + ':' + name)
        require(ordinary_file(root, name) == expected, 'Selected original source differs: ' + name)
    current = json.loads(ordinary_file(root, str(CURRENT)))
    verify_target_inputs(root, record, current)
    print('Original Watch18 history, selected source files, historical inputs and pinned current successors match')


if __name__ == '__main__':
    verify()

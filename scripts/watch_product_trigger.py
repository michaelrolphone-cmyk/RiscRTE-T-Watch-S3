#!/usr/bin/env python3
"""Read-only gate for automatic re-promotion of an unchanged published product."""
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'michaelrolphone-cmyk/RiscRTE-T-Watch-S3'
PRODUCT_PATH = 'release/product.json'


def document(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate product field: ' + key)
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    # Canonical JSON preserves scalar types while ignoring formatting/key order.
    return value, json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def should_promote(event, current, release_lookup, tag_lookup, source_lookup):
    if event in ('pull_request', 'workflow_dispatch'):
        return True
    if event != 'workflow_run':
        raise ValueError('Unsupported product workflow event')
    product, current_canonical = document(current)
    version = product.get('version')
    if (not isinstance(version, str) or
            not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version) or
            product.get('tag') != 'firmware-v' + version or
            product.get('repository') != REPOSITORY):
        raise ValueError('Invalid canonical product identity')
    tag = product['tag']
    release = release_lookup(tag)
    if release is None or release.get('draft') is True:
        return True
    if (release.get('tag_name') != tag or release.get('draft') is not False or
            release.get('prerelease') is not False):
        raise ValueError('Published product release identity differs')
    source = tag_lookup(tag)
    if (not isinstance(source, str) or not re.fullmatch(r'[0-9a-f]{40}', source) or
            release.get('target_commitish') != source):
        raise ValueError('Published product source is not pinned to its tag')
    _, published_canonical = document(source_lookup(source))
    return current_canonical != published_canonical


def release_lookup(tag):
    result = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/releases/tags/{tag}'],
                            cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        if '(HTTP 404)' in result.stderr:
            return None
        raise RuntimeError('Release lookup failed: ' + result.stderr.strip())
    return json.loads(result.stdout)


def tag_lookup(tag):
    result = subprocess.check_output(['gh', 'api', f'repos/{REPOSITORY}/commits/{tag}'], cwd=ROOT)
    return json.loads(result)['sha']


def source_lookup(source):
    return subprocess.check_output(['git', 'show', source + ':' + PRODUCT_PATH], cwd=ROOT)


def main():
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise ValueError('Wrong product workflow repository')
    proceed = should_promote(os.environ['WATCH_PRODUCT_EVENT'], (ROOT / PRODUCT_PATH).read_bytes(),
                             release_lookup, tag_lookup, source_lookup)
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('proceed=' + str(proceed).lower() + '\n')
    print('Product verification/promotion requested' if proceed else
          'Published product configuration unchanged; automatic promotion skipped')


if __name__ == '__main__':
    main()

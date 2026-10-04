#!/usr/bin/env python3
"""Reader-compatible schema-1 release index, adapted to Watch package metadata.
The monotonic, immutable update rules follow T5S3-Reader's
scripts/update_release_index.py. Reader content and repositories are not changed.
"""
import copy
import json
import re

REPOSITORY = 'michaelrolphone-cmyk/RiscRTE-T-Watch-S3'
EMPTY_INDEX = {'schema': 1, 'firmware': None, 'apps': [], 'drivers': []}
VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,159}\Z')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def version_tuple(value):
    m = VERSION.fullmatch(value) if isinstance(value, str) else None
    require(m is not None, 'Expected numeric MAJOR.MINOR.PATCH')
    return tuple(map(int, m.groups()))


def validate_record(product, record):
    require(product in ('firmware', 'apps', 'drivers'), 'Unsupported product')
    require(isinstance(record, dict), 'Expected record object')
    require({'version', 'tag', 'asset', 'url', 'size', 'sha256'} <= record.keys(), 'Incomplete record')
    version_tuple(record['version'])
    kind = {'firmware': 'firmware', 'apps': 'app', 'drivers': 'driver'}[product]
    require(record.get('kind', kind) == kind, 'Wrong record kind')
    asset = record['asset']
    require(isinstance(asset, str) and NAME.fullmatch(asset) and '..' not in asset, 'Unsafe asset name')
    require(type(record['size']) is int and record['size'] > 0, 'Invalid asset size')
    require(isinstance(record['sha256'], str) and re.fullmatch('[0-9a-f]{64}', record['sha256']), 'Invalid digest')
    if product == 'firmware':
        tag = 'firmware-v' + record['version']
        require(asset == 'twatch-s3-launcher-' + record['version'] + '.bin', 'Wrong firmware asset')
    else:
        identity = record.get('id')
        require(isinstance(identity, str) and re.fullmatch('[a-z0-9][a-z0-9._-]{0,63}', identity), 'Invalid identity')
        manifest = record.get('manifest')
        require(isinstance(manifest, dict) and manifest.get('version') == record['version'], 'Manifest version mismatch')
        require(manifest.get('architecture') == 'xtensa-esp32s3', 'Wrong manifest architecture')
        tag = kind + '-' + identity + '-v' + record['version']
        if product == 'apps':
            require(manifest.get('file_name') == identity + '.elf' and asset == identity + '.elf', 'App filename mismatch')
            require(manifest.get('type') == 'application', 'Wrong app manifest')
        else:
            require(record.get('format') == 'rte.zip' and record.get('architecture') == 'xtensa-esp32s3', 'Wrong driver format')
            require(manifest.get('id') == identity and manifest.get('kind') == 'driver', 'Wrong driver identity')
            require(asset == f'driver-{identity}-{record["version"]}-xtensa-esp32s3.rte.zip', 'Wrong driver asset')
    require(record['tag'] == tag, 'Wrong immutable tag')
    require(record.get('source_repo', REPOSITORY) == REPOSITORY, 'Release must belong to Watch repository')
    require(record['url'] == f'https://github.com/{REPOSITORY}/releases/download/{tag}/{asset}', 'Wrong immutable URL')
    return {**copy.deepcopy(record), 'kind': kind}


def serialize_index(index):
    return json.dumps(index, sort_keys=True, separators=(',', ':')) + '\n'


def update_index(index, product, record):
    require(isinstance(index, dict) and index.get('schema') == 1, 'Index schema mismatch')
    result = copy.deepcopy(index)
    normalized = validate_record(product, record)
    for key in ('apps', 'drivers', 'services', 'providers'):
        if key in result:
            require(isinstance(result[key], list), 'Index product must be an array')
    if product == 'firmware':
        old = result.get(product)
        if old is not None:
            require(version_tuple(normalized['version']) >= version_tuple(old['version']), 'Version rollback')
            require(normalized['version'] != old['version'] or normalized == old, 'Immutable version collision')
        result[product] = normalized
    else:
        entries = result.get(product, [])
        require(all(isinstance(x, dict) and isinstance(x.get('id'), str) for x in entries), 'Malformed index entry')
        current = {x['id']: x for x in entries}
        require(len(current) == len(entries), 'Duplicate index identity')
        old = current.get(normalized['id'])
        if old is not None:
            require(version_tuple(normalized['version']) >= version_tuple(old['version']), 'Version rollback')
            require(normalized['version'] != old['version'] or normalized == old, 'Immutable version collision')
        current[normalized['id']] = normalized
        result[product] = [current[k] for k in sorted(current)]
    require(len(result.get('apps', [])) <= 128 and len(result.get('drivers', [])) <= 64, 'Index count limit')
    require(len(serialize_index(result).encode()) <= 512 * 1024, 'Index byte limit')
    return result

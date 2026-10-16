"""Bind the paired native image and complete boot store to one Watch release.

Only the initial provisioning builder writes an empty app-data volume. Cohort
update payloads contain exactly the native image followed by the boot store.
"""
import hashlib
import json
import re

from watch_release_index import REPOSITORY, require, version_tuple

LAYOUT = 'riscrte-paired-appdata-v2'
STORE_SIZE = 0x510000
NATIVE_SIZE = 0x260000
FIELDS = {'schema', 'schema_version', 'product', 'version', 'runtime_version',
          'source_repo', 'source_revision', 'layout', 'store_abi',
          'firmware_size', 'firmware_sha256'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate(identity):
    require(isinstance(identity, dict) and set(identity) == FIELDS,
            'Exact cohort identity fields required')
    require(identity['schema'] == 'riscrte.cohort' and
            type(identity['schema_version']) is int and identity['schema_version'] == 1,
            'Unsupported cohort identity schema')
    require(identity['product'] == 'twatch-s3' and identity['source_repo'] == REPOSITORY,
            'Wrong cohort product or repository')
    version_tuple(identity['version']); version_tuple(identity['runtime_version'])
    require(isinstance(identity['source_revision'], str) and
            re.fullmatch('[0-9a-f]{40}', identity['source_revision']),
            'Exact cohort source revision required')
    require(identity['layout'] == LAYOUT and type(identity['store_abi']) is int and
            identity['store_abi'] == 2, 'Wrong cohort layout or ABI')
    require(type(identity['firmware_size']) is int and
            32 <= identity['firmware_size'] <= NATIVE_SIZE, 'Invalid cohort native size')
    require(isinstance(identity['firmware_sha256'], str) and
            re.fullmatch('[0-9a-f]{64}', identity['firmware_sha256']),
            'Invalid cohort native digest')
    return identity


def create(version, runtime_version, source_revision, firmware):
    return validate(dict(schema='riscrte.cohort', schema_version=1, product='twatch-s3',
                         version=version, runtime_version=runtime_version,
                         source_repo=REPOSITORY, source_revision=source_revision,
                         layout=LAYOUT, store_abi=2, firmware_size=len(firmware),
                         firmware_sha256=sha(firmware)))


def encode(identity):
    return (json.dumps(validate(identity), sort_keys=True, separators=(',', ':')) + '\n').encode()


def parse(data):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            require(name not in result, 'Duplicate cohort identity field')
            result[name] = value
        return result
    require(isinstance(data, bytes) and len(data) <= 2048, 'Invalid cohort identity bytes')
    return validate(json.loads(data, object_pairs_hook=unique))


def verify(identity, firmware, *, version=None, runtime_version=None, source_revision=None):
    validate(identity)
    require(identity['firmware_size'] == len(firmware) and
            identity['firmware_sha256'] == sha(firmware), 'Cohort native image differs')
    for key, expected in (('version', version), ('runtime_version', runtime_version),
                          ('source_revision', source_revision)):
        require(expected is None or identity[key] == expected, 'Cohort ' + key + ' differs')
    return identity


def package(identity, firmware, store):
    from read_only_spiffs import read_image
    verify(identity, firmware)
    require(len(store) == STORE_SIZE, 'Cohort boot store size differs')
    files = read_image(store, STORE_SIZE)
    require('cohort.json' in files and parse(files['cohort.json']) == identity,
            'Cohort boot store identity differs')
    payload = firmware + store
    name = 'twatch-s3-cohort-' + identity['version'] + '.bin'
    ota = {key: identity[key] for key in ('product', 'version', 'runtime_version',
           'source_repo', 'source_revision', 'layout', 'store_abi',
           'firmware_size', 'firmware_sha256')}
    ota.update(kind='paired-cohort', store_size=len(store), store_sha256=sha(store),
               asset=name, size=len(payload), sha256=sha(payload),
               url=f'https://github.com/{REPOSITORY}/releases/download/firmware-v{identity["version"]}/{name}')
    return payload, ota

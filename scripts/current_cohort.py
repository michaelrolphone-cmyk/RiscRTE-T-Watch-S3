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
EXPANDED_LAYOUT = 'riscrte-paired-appdata-v3'
EXPANDED_STORE_SIZE = 0x550000


def native_layout(firmware):
    require(b'RISC_PAIRED_STORE_ABI:3\0' in firmware and
            all(marker not in firmware for marker in (b'RISC_PAIRED_STORE_ABI:1\0',
                b'RISC_PAIRED_STORE_ABI:2\0', b'RISC_OWNER_INSTALLER:1\0')),
            'Expanded native lacks exclusive ordinary ABI3 marker')
FIELDS = {'schema', 'schema_version', 'product', 'version', 'runtime_version',
          'source_repo', 'source_revision', 'layout', 'store_abi',
          'firmware_size', 'firmware_sha256'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate(identity, *, expanded=False):
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
    require(identity['layout'] == (EXPANDED_LAYOUT if expanded else LAYOUT) and type(identity['store_abi']) is int and
            identity['store_abi'] == (3 if expanded else 2), 'Wrong cohort layout or ABI')
    require(type(identity['firmware_size']) is int and
            32 <= identity['firmware_size'] <= NATIVE_SIZE, 'Invalid cohort native size')
    require(isinstance(identity['firmware_sha256'], str) and
            re.fullmatch('[0-9a-f]{64}', identity['firmware_sha256']),
            'Invalid cohort native digest')
    return identity


def create(version, runtime_version, source_revision, firmware, *, expanded=False):
    if expanded: native_layout(firmware)
    return validate(dict(schema='riscrte.cohort', schema_version=1, product='twatch-s3',
                         version=version, runtime_version=runtime_version,
                         source_repo=REPOSITORY, source_revision=source_revision,
                         layout=EXPANDED_LAYOUT if expanded else LAYOUT, store_abi=3 if expanded else 2, firmware_size=len(firmware),
                         firmware_sha256=sha(firmware)), expanded=expanded)


def encode(identity, *, expanded=False):
    return (json.dumps(validate(identity, expanded=expanded), sort_keys=True, separators=(',', ':')) + '\n').encode()


def parse(data, *, expanded=False):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            require(name not in result, 'Duplicate cohort identity field')
            result[name] = value
        return result
    require(isinstance(data, bytes) and len(data) <= 2048, 'Invalid cohort identity bytes')
    return validate(json.loads(data, object_pairs_hook=unique), expanded=expanded)


def verify(identity, firmware, *, version=None, runtime_version=None, source_revision=None, expanded=False):
    validate(identity, expanded=expanded)
    if expanded: native_layout(firmware)
    require(identity['firmware_size'] == len(firmware) and
            identity['firmware_sha256'] == sha(firmware), 'Cohort native image differs')
    for key, expected in (('version', version), ('runtime_version', runtime_version),
                          ('source_revision', source_revision)):
        require(expected is None or identity[key] == expected, 'Cohort ' + key + ' differs')
    return identity


def package(identity, firmware, store, *, expanded=False):
    from read_only_spiffs import read_image
    verify(identity, firmware, expanded=expanded)
    store_size = EXPANDED_STORE_SIZE if expanded else STORE_SIZE
    require(len(store) == store_size, 'Cohort boot store size differs')
    files = read_image(store, store_size)
    require('cohort.json' in files and parse(files['cohort.json'], expanded=expanded) == identity,
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

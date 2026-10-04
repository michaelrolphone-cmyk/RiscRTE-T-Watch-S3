#!/usr/bin/env python3
"""Deterministic data baseline, separate from installable driver packages."""
import hashlib
import json
from pathlib import Path
import subprocess
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = 'lilygo-t-watch-s3'
MANIFEST = 'releases/board-baseline.json'
FIXED = (MANIFEST, 'board.json', 'load-order.json', 'platform-resources.json',
         'docs/board-manifest-v1.schema.json', 'docs/twatch-board-v1.schema.json',
         'docs/HARDWARE_MAPPING.md', 'docs/CAPABILITY_BACKFILL.md',
         'docs/HARDWARE_INVENTORY.md', 'docs/SCHEMA_PROVENANCE.json', 'sdk/SOURCES.json', 'include/twatch_caps.h',
         'licenses/NOTICE.md')


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inputs(root=ROOT):
    # Directory discovery covers newly added profiles, interfaces and driver IDs;
    # callers cannot silently omit a changed profile from an editable input list.
    paths = set(FIXED)
    for pattern in ('hardware/*.json', 'sdk/driver/*.h', 'drivers/*/manifest.json', 'licenses/*'):
        paths.update(str(p.relative_to(root)) for p in root.glob(pattern) if p.is_file())
    result = {}
    for name in sorted(paths):
        path = root / name
        if not path.is_file() or any((root / Path(*Path(name).parts[:i])).is_symlink()
                                      for i in range(1, len(Path(name).parts) + 1)):
            raise ValueError(f'Missing or symlinked baseline input: {name}')
        result[name] = path.read_bytes()
    return result


def snapshot(root=ROOT):
    files = inputs(root)
    manifest = json.loads(files[MANIFEST])
    if (manifest['id'] != IDENTITY or manifest['schema_version'] != 1 or
            manifest['schema'] != 'riscrte.board-baseline' or
            not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', manifest['version'])):
        raise ValueError('Unknown board baseline identity/schema')
    profile_paths = {name for name in files if name.startswith('hardware/')}
    if set(json.loads(files['board.json'])['profiles']) != profile_paths:
        raise ValueError('Board index does not name every bundled profile')
    provenance = json.loads(files['docs/SCHEMA_PROVENANCE.json'])
    for name, expected in provenance['derived_schemas'].items():
        if digest(files['docs/' + name]) != expected:
            raise ValueError('Schema provenance hash mismatch')
    entries = [{'path': name, 'size_bytes': len(data), 'sha256': digest(data)}
               for name, data in files.items()]
    return manifest, files, entries, digest(encoded(entries))


def archive_bytes(root, sha):
    import io
    manifest, files, entries, source_digest = snapshot(root)
    provenance = {'schema': 1, 'kind': 'board-baseline', 'id': IDENTITY,
                  'version': manifest['version'], 'source_sha': sha,
                  'source_repository': 'https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3',
                  'source_digest': source_digest, 'entries': entries}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, data in sorted({**files, 'baseline-record.json': encoded(provenance)}.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    return output.getvalue(), provenance


def build(root=ROOT):
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    data, record = archive_bytes(root, sha)
    name = f"board-{IDENTITY}-{record['version']}.zip"
    dist = root / 'dist'
    dist.mkdir(exist_ok=True)
    (dist / name).write_bytes(data)
    catalog = {'schema': 1, 'packages': [{
        'id': IDENTITY, 'version': record['version'], 'kind': 'board-baseline',
        'architecture': 'independent', 'archive': name, 'size_bytes': len(data),
        'sha256': digest(data), 'source_digest': record['source_digest']}]}
    (dist / 'board-catalog.json').write_bytes(encoded(catalog))
    print(f"Board baseline {record['version']}: {len(record['entries'])} checksummed files")


def verify_record(record, manifest, source_digest):
    if (record.get('id'), record.get('version'), record.get('kind'), record.get('source_digest')) != (
            IDENTITY, manifest['version'], 'board-baseline', source_digest):
        raise ValueError('Board baseline content changed without a version increment, or release record is invalid')


if __name__ == '__main__':
    build()

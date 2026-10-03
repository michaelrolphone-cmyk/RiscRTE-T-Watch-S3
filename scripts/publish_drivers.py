#!/usr/bin/env python3
"""Version-driven GitHub releases; no mutation unless explicitly called with publish."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
TAG = re.compile(r'driver-([a-z0-9]+(?:-[a-z0-9]+)*)-v(' + VERSION + r')\Z')


def version(value):
    if not isinstance(value, str) or not re.fullmatch(VERSION, value):
        raise ValueError(f'Expected numeric MAJOR.MINOR.PATCH: {value!r}')
    return tuple(map(int, value.split('.')))


def gh(*args):
    return subprocess.check_output(['gh', *args], cwd=ROOT, text=True)


def releases(repo):
    return [r for page in json.loads(gh('api', '--paginate', '--slurp',
            f'repos/{repo}/releases?per_page=100')) for r in page]


def sources(root=ROOT):
    result = {}
    for path in sorted((root / 'drivers').glob('*/manifest.json')):
        m = json.loads(path.read_text())
        identity = m['id']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', identity) or identity in result:
            raise ValueError(f'Invalid or duplicate driver ID: {identity}')
        version(m['version'])
        result[identity] = m['version']
    if not result:
        raise ValueError('No source manifests found')
    return result


def candidates(source, existing):
    latest, tags = {}, {}
    for release in existing:
        match = TAG.fullmatch(release['tag_name'])
        if not match:
            continue
        identity, value = match.group(1, 2)
        if release['tag_name'] in tags:
            raise ValueError('Duplicate release tag')
        tags[release['tag_name']] = release
        latest[identity] = max(latest.get(identity, (0, 0, 0)), version(value))
    result = []
    for identity, value in sorted(source.items()):
        current = version(value)
        if identity in latest and current < latest[identity]:
            raise ValueError(f'{identity}: version rollback below published/draft release')
        tag = f'driver-{identity}-v{value}'
        prior = tags.get(tag)
        if prior and not prior['draft']:
            continue
        result.append({'id': identity, 'version': value, 'tag': tag})
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stage(plan, root=ROOT):
    catalog = json.loads((root / 'dist/catalog.json').read_text())
    packages = catalog['packages']
    if len({p['id'] for p in packages}) != len(packages):
        raise ValueError('Duplicate catalog identity')
    records = []
    for item in plan['packages']:
        matches = [p for p in packages if p['id'] == item['id'] and p['version'] == item['version']]
        if len(matches) != 1:
            raise ValueError('Plan/catalog version mismatch')
        p = matches[0]
        name = f"driver-{item['id']}-{item['version']}-xtensa-esp32s3.rte.zip"
        if p['archive'] != name or p['architecture'] != 'xtensa-esp32s3':
            raise ValueError('Wrong archive name or architecture')
        path = root / 'dist' / name
        data = path.read_bytes()
        if path.is_symlink() or len(data) != p['size_bytes'] or digest(data) != p['sha256']:
            raise ValueError('Archive hash/size mismatch')
        with zipfile.ZipFile(path) as z:
            m = json.loads(z.read('.package.json'))
            if (m['id'], m['version'], m['architecture'], m['kind']) != (
                    item['id'], item['version'], 'xtensa-esp32s3', 'driver'):
                raise ValueError('Embedded manifest mismatch')
            if len(z.namelist()) != len(set(z.namelist())):
                raise ValueError('Duplicate ZIP member')
            for entry in m['entries']:
                payload = z.read(entry['name'])
                if len(payload) != entry['size_bytes'] or digest(payload) != entry['sha256']:
                    raise ValueError('Embedded payload hash mismatch')
        records.append({**p, 'tag': item['tag'], 'source_sha': plan['source_sha']})
    return {'schema': 1, 'packages': records}


def verify_existing_tag(repo, tag, sha):
    result = subprocess.run(['gh', 'api', f'repos/{repo}/git/ref/tags/{tag}'],
                            cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        if '(HTTP 404)' in result.stderr:
            return
        raise RuntimeError(result.stderr)
    if json.loads(gh('api', f'repos/{repo}/commits/{tag}'))['sha'] != sha:
        raise ValueError(f'{tag}: existing tag belongs to another commit')


def publish_one(repo, record):
    tag = record['tag']
    verify_existing_tag(repo, tag, record['source_sha'])
    # Draft first: a failed upload never exposes a half-populated release.
    existing = next((r for r in releases(repo) if r['tag_name'] == tag), None)
    if existing is None:
        gh('release', 'create', tag, '--repo', repo, '--target', record['source_sha'],
           '--draft', '--title', tag, '--notes',
           f"Independent driver {record['id']} {record['version']}. Source {record['source_sha']}. "
           'Software validated; physical verification and RiscRTE runtime backfill remain pending.')
        existing = next(r for r in releases(repo) if r['tag_name'] == tag)
    # A draft can be resumed only from its original source commit. Published
    # releases are verified byte-for-byte on retries, never clobbered.
    if existing['target_commitish'] != record['source_sha']:
        raise ValueError(f'{tag}: release belongs to another source commit')
    with tempfile.TemporaryDirectory() as tmp:
        record_path = Path(tmp) / 'release-record.json'
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        expected = {record['archive']: ROOT / 'dist' / record['archive'],
                    'release-record.json': record_path}
        assets = existing['assets']
        if len({a['name'] for a in assets}) != len(assets) or set(a['name'] for a in assets) - expected.keys():
            raise ValueError(f'{tag}: unexpected release assets')
        for name, path in expected.items():
            if any(a['name'] == name for a in assets):
                destination = Path(tmp) / 'download'
                destination.mkdir(exist_ok=True)
                gh('release', 'download', tag, '--repo', repo, '--pattern', name,
                   '--dir', str(destination))
                if (destination / name).read_bytes() != path.read_bytes():
                    raise ValueError(f'{tag}: existing {name} differs; refusing overwrite')
            elif existing['draft']:
                gh('release', 'upload', tag, str(path), '--repo', repo)
            else:
                raise ValueError(f'{tag}: published release has a missing asset')
        # Download newly uploaded assets too before making the release public.
        verify = Path(tmp) / 'verify'
        verify.mkdir()
        gh('release', 'download', tag, '--repo', repo, '--dir', str(verify))
        if any((verify / name).read_bytes() != path.read_bytes() for name, path in expected.items()):
            raise ValueError('Uploaded bytes do not match')
    if existing['draft']:
        gh('release', 'edit', tag, '--repo', repo, '--draft=false', '--latest=false')
    # GitHub creates the lightweight tag when publishing the draft.
    actual = json.loads(gh('api', f'repos/{repo}/commits/{tag}'))['sha']
    if actual != record['source_sha']:
        raise ValueError(f'{tag}: tag does not resolve to the planned source')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'stage', 'publish'])
    parser.add_argument('--plan', type=Path, default=ROOT / 'dist/release-plan.json')
    args = parser.parse_args()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if args.action == 'plan':
        repo = os.environ['GITHUB_REPOSITORY']
        plan = {'schema': 1, 'repository': repo, 'source_sha': sha,
                'packages': candidates(sources(), releases(repo))}
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        args.plan.write_text(json.dumps(plan, indent=2) + '\n')
        print(json.dumps(plan, indent=2))
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
                out.write(f"changed={'true' if plan['packages'] else 'false'}\n")
        return
    plan = json.loads(args.plan.read_text())
    if plan['schema'] != 1 or plan['source_sha'] != sha:
        raise ValueError('Plan belongs to another source commit/schema')
    current = sources()
    if any(current.get(p['id']) != p['version'] or p['tag'] != f"driver-{p['id']}-v{p['version']}"
           for p in plan['packages']) or len({p['id'] for p in plan['packages']}) != len(plan['packages']):
        raise ValueError('Plan differs from source manifests')
    staged = stage(plan)
    if args.action == 'stage':
        (ROOT / 'dist/release-catalog.json').write_text(json.dumps(staged, indent=2) + '\n')
    else:
        if plan['repository'] != os.environ['GITHUB_REPOSITORY']:
            raise ValueError('Plan repository mismatch')
        # Prevent stale lower-version plans even when invoked outside workflow concurrency.
        candidates(current, releases(plan['repository']))
        for record in staged['packages']:
            publish_one(plan['repository'], record)


if __name__ == '__main__':
    main()

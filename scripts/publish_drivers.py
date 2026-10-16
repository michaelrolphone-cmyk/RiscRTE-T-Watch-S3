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
import board_baseline as board
import accepted_touch_release as accepted_touch

ROOT = Path(__file__).resolve().parents[1]
VERSION = r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
TAG = re.compile(r'(?:driver|board)-([a-z0-9]+(?:-[a-z0-9]+)*)-v(' + VERSION + r')\Z')


def version(value):
    if not isinstance(value, str) or not re.fullmatch(VERSION, value):
        raise ValueError(f'Expected numeric MAJOR.MINOR.PATCH: {value!r}')
    return tuple(map(int, value.split('.')))


def gh(*args):
    return subprocess.check_output(['gh', *map(str, args)], cwd=ROOT)


def releases(repo):
    return [r for page in json.loads(gh('api', '--paginate', '--slurp',
            f'repos/{repo}/releases?per_page=100')) for r in page]


def tag_for(identity, value):
    kind = 'board' if identity == board.IDENTITY else 'driver'
    return f'{kind}-{identity}-v{value}'


def sources(root=ROOT):
    result = {}
    for path in sorted((root / 'drivers').glob('*/manifest.json')):
        m = json.loads(path.read_text())
        identity = m['id']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', identity) or identity in result:
            raise ValueError(f'Invalid or duplicate driver ID: {identity}')
        version(m['version'])
        result[identity] = (accepted_touch.source_version(root) if identity == accepted_touch.IDENTITY else m['version'])
    if not result:
        raise ValueError('No source manifests found')
    baseline = json.loads((root / board.MANIFEST).read_text())
    if board.IDENTITY in result:
        raise ValueError('Board/driver identity collision')
    version(baseline['version'])
    result[board.IDENTITY] = baseline['version']
    return result


def candidates(source, existing):
    latest, tags = {}, {}
    for release in existing:
        match = TAG.fullmatch(release['tag_name'])
        if not match:
            continue
        identity, value = match.group(1, 2)
        if release['tag_name'] != tag_for(identity, value):
            raise ValueError('Release tag uses wrong product namespace')
        if release['tag_name'] in tags:
            raise ValueError('Duplicate release tag')
        tags[release['tag_name']] = release
        latest[identity] = max(latest.get(identity, (0, 0, 0)), version(value))
    result = []
    for identity, value in sorted(source.items()):
        current = version(value)
        if identity in latest and current < latest[identity]:
            raise ValueError(f'{identity}: version rollback below published/draft release')
        tag = tag_for(identity, value)
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
    if any(item['id'] == board.IDENTITY for item in plan['packages']):
        packages += json.loads((root / 'dist/board-catalog.json').read_text())['packages']
    if len({p['id'] for p in packages}) != len(packages):
        raise ValueError('Duplicate catalog identity')
    records = []
    for item in plan['packages']:
        matches = [p for p in packages if p['id'] == item['id'] and p['version'] == item['version']]
        if len(matches) != 1:
            raise ValueError('Plan/catalog version mismatch')
        p = matches[0]
        if item['id'] == board.IDENTITY:
            name = f"board-{board.IDENTITY}-{item['version']}.zip"
            expected, provenance = board.archive_bytes(root, plan['source_sha'])
            path = root / 'dist' / name
            if (p.get('kind'), p.get('architecture'), p.get('archive'), p.get('sha256'),
                    p.get('size_bytes'), p.get('source_digest')) != (
                    'board-baseline', 'independent', name, digest(expected), len(expected),
                    provenance['source_digest']) or path.is_symlink() or path.read_bytes() != expected:
                raise ValueError('Board archive/catalog differs from exact source baseline')
            records.append({**p, 'tag': item['tag'], 'source_sha': plan['source_sha']})
            continue
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
        # Use the creation response. Immediately listing releases can return a
        # stale page without the new draft (observed on the first merged run).
        existing = json.loads(gh('api', f'repos/{repo}/releases', '--method', 'POST',
            '-f', f'tag_name={tag}', '-f', f'target_commitish={record["source_sha"]}',
            '-f', f'name={tag}', '-F', 'draft=true', '-f',
            f'body=Independent {record["kind"]} {record["id"]} {record["version"]}. '
            f'Source {record["source_sha"]}. Software validated; physical verification '
            'and RiscRTE runtime backfill remain pending.'))
    # An empty unpublished draft has no baseline bytes to preserve. Recover the
    # previous workflow's create-before-list failure without a version bump.
    # Existing tags were checked above; drafts with ANY assets remain immutable.
    if existing['target_commitish'] != record['source_sha']:
        if not existing['draft'] or existing['assets']:
            raise ValueError(f'{tag}: release belongs to another source commit')
        existing = json.loads(gh('api', f'repos/{repo}/releases/{existing["id"]}',
            '--method', 'PATCH', '-f', f'target_commitish={record["source_sha"]}',
            '-f', f'body=Recovered empty draft. Source {record["source_sha"]}. '
            'Software validated; physical verification and runtime backfill remain pending.'))
    if existing.get('prerelease', False):
        raise ValueError('Stable driver publication cannot resume a prerelease')
    with tempfile.TemporaryDirectory() as tmp:
        record_path = Path(tmp) / 'release-record.json'
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        expected = {record['archive']: ROOT / 'dist' / record['archive'],
                    'release-record.json': record_path}
        release_id = existing['id']
        current = json.loads(gh('api', f'repos/{repo}/releases/{release_id}'))
        assets = current['assets']
        if len({a['name'] for a in assets}) != len(assets) or set(a['name'] for a in assets) - expected.keys():
            raise ValueError(f'{tag}: unexpected release assets')
        for name, path in expected.items():
            asset = next((a for a in assets if a['name'] == name), None)
            if asset:
                payload = gh('api', f'repos/{repo}/releases/assets/{asset["id"]}', '-H', 'Accept: application/octet-stream')
                if payload != path.read_bytes():
                    raise ValueError(f'{tag}: existing {name} differs; refusing overwrite')
            elif current['draft']:
                # Use the stable release ID. gh release upload first resolves the
                # draft by tag and can fail even immediately after draft creation.
                gh('api', f'https://uploads.github.com/repos/{repo}/releases/{release_id}/assets?name={name}',
                   '--method', 'POST', '--input', str(path), '-H', 'Content-Type: application/octet-stream')
            else:
                raise ValueError(f'{tag}: published release has a missing asset')
        current = json.loads(gh('api', f'repos/{repo}/releases/{release_id}'))
        if len(current['assets']) != len(expected) or {a['name'] for a in current['assets']} != set(expected):
            raise ValueError('Uploaded release inventory differs')
        for asset in current['assets']:
            payload = gh('api', f'repos/{repo}/releases/assets/{asset["id"]}', '-H', 'Accept: application/octet-stream')
            if payload != expected[asset['name']].read_bytes():
                raise ValueError('Uploaded bytes do not match')
    if current['draft']:
        gh('api', f'repos/{repo}/releases/{release_id}', '--method', 'PATCH',
           '-F', 'draft=false', '-f', 'make_latest=false')
    published = json.loads(gh('api', f'repos/{repo}/releases/{release_id}'))
    if published['draft']:
        raise ValueError('Driver publication was not confirmed')
    actual = json.loads(gh('api', f'repos/{repo}/commits/{tag}'))['sha']
    if actual != record['source_sha']:
        raise ValueError(f'{tag}: tag does not resolve to the planned source')


def verify_board_version(repo, existing, root=ROOT):
    manifest, _, _, source_digest = board.snapshot(root)
    tag = tag_for(board.IDENTITY, manifest['version'])
    prior = next((r for r in existing if r['tag_name'] == tag), None)
    if prior is None:
        return
    # A partial draft may not have its record yet; publish verifies every
    # existing byte and its source commit before completing that draft.
    if prior['draft'] and not any(a['name'] == 'release-record.json' for a in prior['assets']):
        return
    matches = [a for a in prior['assets'] if a['name'] == 'release-record.json']
    if len(matches) != 1:
        raise ValueError('Board release must have exactly one custody record')
    record = json.loads(gh('api', f'repos/{repo}/releases/assets/{matches[0]["id"]}',
                           '-H', 'Accept: application/octet-stream'))
    board.verify_record(record, manifest, source_digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'stage', 'publish'])
    parser.add_argument('--plan', type=Path, default=ROOT / 'dist/release-plan.json')
    args = parser.parse_args()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if args.action == 'plan':
        repo = os.environ['GITHUB_REPOSITORY']
        existing = releases(repo)
        verify_board_version(repo, existing)
        accepted_touch.verify_published(repo, existing, gh, ROOT)
        plan = {'schema': 1, 'repository': repo, 'source_sha': sha,
                'packages': candidates(sources(), existing)}
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
    if any(current.get(p['id']) != p['version'] or p['tag'] != tag_for(p['id'], p['version'])
           for p in plan['packages']) or len({p['id'] for p in plan['packages']}) != len(plan['packages']):
        raise ValueError('Plan differs from source manifests')
    staged = stage(plan)
    if args.action == 'stage':
        (ROOT / 'dist/release-catalog.json').write_text(json.dumps(staged, indent=2) + '\n')
    else:
        if plan['repository'] != os.environ['GITHUB_REPOSITORY']:
            raise ValueError('Plan repository mismatch')
        # Prevent stale lower-version plans even when invoked outside workflow concurrency.
        existing = releases(plan['repository'])
        verify_board_version(plan['repository'], existing)
        accepted_touch.verify_published(plan['repository'], existing, gh, ROOT)
        candidates(current, existing)
        for record in staged['packages']:
            publish_one(plan['repository'], record)


if __name__ == '__main__':
    main()

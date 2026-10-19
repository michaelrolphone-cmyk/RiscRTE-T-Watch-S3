#!/usr/bin/env python3
"""Resume only exact-source immutable releases; publish after byte verification."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

import package_provisioning as package
from package_provisioning import require, sha
from provisioning_release import verify_output, PRODUCTS


def gh(*args, absent=False):
    result = subprocess.run(['gh', *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        if absent and '(HTTP 404)' in result.stderr: return None
        raise RuntimeError('GitHub command failed: ' + result.stderr.strip())
    return result.stdout


def object_json(*args, absent=False):
    data = gh(*args, absent=absent)
    return None if data is None else json.loads(data)


def check_tags(rows, tag, version, revision):
    expected = 'refs/tags/' + tag
    exact = []
    for row in rows:
        if re.search(r'(?<![0-9])' + re.escape(version) + r'(?![0-9])', row['ref']):
            require(row['ref'] == expected, 'Version already reserved by another tag')
            require(row['object']['type'] == 'commit' and row['object']['sha'] == revision, 'Existing tag source differs')
            exact.append(row)
    require(len(exact) <= 1, 'Ambiguous release tag')
    return bool(exact)


def find_release(repo, tag):
    pages = object_json('api', '--paginate', '--slurp', 'repos/' + repo + '/releases?per_page=100')
    require(isinstance(pages, list) and all(isinstance(page, list) for page in pages), 'Malformed release pages')
    require(all(isinstance(row, dict) and isinstance(row.get('tag_name'), str)
                for page in pages for row in page), 'Malformed release row')
    rows = [row for page in pages for row in page if row['tag_name'] == tag]
    require(len(rows) <= 1, 'Ambiguous release tag')
    return rows[0] if rows else None



def wait_for_created_release(repo, tag):
    """Reconcile successful creation with reads only; errors are never retried.

    Five reads and at most 3.75 seconds of intentional sleep. This is not a
    wall-clock timeout: each existing gh read can paginate or wait on network I/O.
    """
    delays = (0.25, 0.5, 1.0, 2.0)
    for attempt in range(len(delays) + 1):
        row = find_release(repo, tag)
        if row is not None:
            return row  # The caller immediately applies all identity/asset checks.
        if attempt < len(delays):
            time.sleep(delays[attempt])
    raise RuntimeError(
        'Created release readback unavailable after 5 reads: ' + repo + ' ' + tag
        + '; draft may exist. Reconcile with read-only inspection before resuming;'
        + ' do not recreate or replace it.')


def check_release(row, tag, names, title=None, body=None):
    require(row['tag_name'] == tag and row['prerelease'] is True, 'Release identity differs')
    if title is not None: require(row['name'] == title and row['body'] == body, 'Existing release text differs')
    assets = row['assets']
    actual = [a['name'] for a in assets]
    require(len(actual) == len(set(actual)) and set(actual) <= names, 'Unexpected or duplicate release assets')
    require(all(a['state'] == 'uploaded' for a in assets), 'Incomplete remote asset requires explicit recovery')
    if row['draft'] is False: require(set(actual) == names, 'Published release is incomplete')
    return names - set(actual)


def publish(root, digest, revision):
    p = package.pins()
    require(p['publication_enabled'] is True, 'Product release publication not selected')
    verify_output(root, digest, revision)
    repo = 'michaelrolphone-cmyk/' + PRODUCTS[p['product']][0]
    title = PRODUCTS[p['product']][1] + ' ' + p['version'] + ' complete provisioning, hardware pending'
    body = (root / 'RELEASE-NOTES.txt').read_text()
    tag = p['release_tag']; names = {f.name for f in root.iterdir()}
    pages = object_json('api', '--paginate', '--slurp', 'repos/' + repo + '/git/matching-refs/tags/')
    tags = [row for page in pages for row in page]
    if not check_tags(tags, tag, p['version'], revision):
        object_json('api', '--method', 'POST', 'repos/' + repo + '/git/refs', '-f', 'ref=refs/tags/' + tag, '-f', 'sha=' + revision)
    exact = object_json('api', 'repos/' + repo + '/git/ref/tags/' + tag)
    require(exact['object']['type'] == 'commit' and exact['object']['sha'] == revision, 'Created tag readback differs')
    row = find_release(repo, tag)
    if row is None:
        gh('release', 'create', tag, '--repo', repo, '--verify-tag', '--target', revision, '--draft', '--prerelease', '--latest=false',
           '--title', title,
           '--notes-file', str(root / 'RELEASE-NOTES.txt'))
        row = wait_for_created_release(repo, tag)
    missing = check_release(row, tag, names, title, body)
    # A resumed upload may only add missing names. Existing bytes must match;
    # no tag/asset replacement or deletion is performed.
    with tempfile.TemporaryDirectory(prefix='shared-default-release-readback-') as d:
        existing = Path(d) / 'existing'; existing.mkdir()
        if row['assets']:
            gh('release', 'download', tag, '--repo', repo, '--dir', str(existing))
            require({f.name for f in existing.iterdir()} == names - missing, 'Remote inventory changed during readback')
            for f in existing.iterdir(): require(sha(f.read_bytes()) == sha((root / f.name).read_bytes()), 'Existing asset bytes differ: ' + f.name)
        if missing:
            require(row['draft'] is True, 'Only draft upload may be resumed')
            gh('release', 'upload', tag, *[str(root / n) for n in sorted(missing)], '--repo', repo)
        staged = Path(d) / 'staged'
        gh('release', 'download', tag, '--repo', repo, '--dir', str(staged))
        verify_output(staged, digest, revision)
        row = find_release(repo, tag)
        require(not check_release(row, tag, names, title, body), 'Draft release incomplete')
        exact = object_json('api', 'repos/' + repo + '/git/ref/tags/' + tag)
        require(exact['object']['type'] == 'commit' and exact['object']['sha'] == revision, 'Tag changed before publication')
        if row['draft'] is True: gh('release', 'edit', tag, '--repo', repo, '--draft=false', '--prerelease', '--latest=false')
        final = find_release(repo, tag)
        require(final['draft'] is False and not check_release(final, tag, names, title, body), 'Published release readback differs')
        public = Path(d) / 'published'
        gh('release', 'download', tag, '--repo', repo, '--dir', str(public))
        verify_output(public, digest, revision)
    exact = object_json('api', 'repos/' + repo + '/git/ref/tags/' + tag)
    require(exact['object']['type'] == 'commit' and exact['object']['sha'] == revision, 'Final tag readback differs')
    print(final['html_url'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args()
    require(__debug__, 'Validation cannot be disabled')
    publish(args.assets.resolve(), args.expected_sha, args.source_revision)

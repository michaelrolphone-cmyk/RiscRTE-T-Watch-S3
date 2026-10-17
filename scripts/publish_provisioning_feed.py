#!/usr/bin/env python3
"""Publish a verified public release's credential-free core feed with a Git lease."""
import argparse
import base64
import json
from pathlib import Path
from package_provisioning import pins, require, sha
from provisioning_release import verify_output
from publish_provisioning_release import object_json, find_release, check_tags


def select_update(old, new, tag, previous_raw=None, expected_previous_sha=None):
    require(new['apps'] == [] and new['profiles'] == {'core': []} and set(new['boot_profiles']) == {'core'}, 'Exact bootstrap-only feed required')
    core = new['boot_profiles']['core']
    require(len(core['profile']['files']) == 125 and not core['mirrors'], 'Complete internal core required')
    require('/' + tag + '/bootfs-' in core['profile']['image']['url'], 'Wrong immutable release URL')
    if old is not None:
        if old == new:
            return False
        require(previous_raw is not None and expected_previous_sha is not None
                and sha(previous_raw) == expected_previous_sha
                and json.loads(previous_raw) == old, 'Existing feed differs from pinned predecessor')
        return True
    return True


def publish(root, digest, revision):
    p = pins(); verify_output(root, digest, revision)
    repo = 'michaelrolphone-cmyk/RiscRTE-T-Watch-S3'; branch = 'provisioning-index'; name = 'native-packages-v1.json'
    release = find_release(repo, p['release_tag'])
    require(release is not None and not release['draft'] and release['prerelease'], 'Public qualified release required before feed publication')
    tag = object_json('api', 'repos/' + repo + '/git/ref/tags/' + p['release_tag'])
    require(check_tags([tag], p['release_tag'], p['version'], revision), 'Release tag differs')
    raw = (root / name).read_bytes(); new = json.loads(raw)
    existing = object_json('api', 'repos/' + repo + '/contents/' + name + '?ref=' + branch, absent=True)
    previous_raw = base64.b64decode(existing['content']) if existing is not None else None
    old = json.loads(previous_raw) if previous_raw is not None else None
    if select_update(old, new, p['release_tag'], previous_raw, p.get('previous_feed_sha256')):
        ref = object_json('api', 'repos/' + repo + '/git/ref/heads/' + branch, absent=True)
        if ref is None:
            object_json('api', '--method', 'POST', 'repos/' + repo + '/git/refs', '-f', 'ref=refs/heads/' + branch, '-f', 'sha=' + revision)
        lease = ['-f', 'sha=' + existing['sha']] if existing is not None else []
        object_json('api', '--method', 'PUT', 'repos/' + repo + '/contents/' + name,
            '-f', 'message=Publish qualified T-Watch ' + p['version'] + ' core feed', '-f', 'branch=' + branch,
            '-f', 'content=' + base64.b64encode(raw).decode('ascii'), *lease)
    final = object_json('api', 'repos/' + repo + '/contents/' + name + '?ref=' + branch)
    require(base64.b64decode(final['content']) == raw, 'Published feed readback differs')
    print(p['feed_url'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args(); require(__debug__, 'Validation cannot be disabled')
    publish(args.assets.resolve(), args.expected_sha, args.source_revision)

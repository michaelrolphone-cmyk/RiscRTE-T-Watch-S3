#!/usr/bin/env python3
"""Fetch only the immutable public baseline; verify release, tag and all bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'factory': 'TWatch-1.1.46-Provisioning-factory-erases-data-0x0.bin', 'store': 'store.bin', 'feed': 'native-packages-v1.json'}
OUTPUTS = {'factory': 'factory.bin', 'store': 'store.bin', 'feed': 'native-packages-v1.json'}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def validate_release(contract, release, tag):
    require(release['id'] == contract['release_id'] and not release['draft'] and
            release['tag_name'] == contract['release_tag'], 'Released baseline identity changed')
    require(tag['object']['type'] == 'commit' and
            tag['object']['sha'] == contract['source_revision'], 'Baseline tag source changed')
    urls = {}
    for key, name in NAMES.items():
        rows = [a for a in release['assets'] if a['name'] == name]
        require(len(rows) == 1, 'Missing or duplicate baseline asset: ' + name)
        row = rows[0]
        expected = contract[key]
        require(row['id'] == expected['id'] and row['size'] == expected['bytes'], 'Asset identity/size changed: ' + name)
        url = 'https://github.com/' + contract['repo'] + '/releases/download/' + contract['release_tag'] + '/' + name
        require(row['browser_download_url'] == url, 'Asset destination changed: ' + name)
        urls[key] = url
    return urls

def verify_bytes(expected, value):
    require(len(value) == expected['bytes'] and hashlib.sha256(value).hexdigest() == expected['sha256'], 'Baseline asset bytes changed')

def read(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'RiscRTE-shared-host-native-qualification'}), timeout=180) as response:
        return response.read()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads((ROOT / 'docs/shared-app-native/baseline-1.1.46.json').read_bytes())
    release_raw = read('https://api.github.com/repos/' + contract['repo'] + '/releases/' + str(contract['release_id']))
    tag_raw = read('https://api.github.com/repos/' + contract['repo'] + '/git/ref/tags/' + contract['release_tag'])
    urls = validate_release(contract, json.loads(release_raw), json.loads(tag_raw))
    args.output.mkdir(parents=True, exist_ok=True)
    for key, url in urls.items():
        target = args.output / OUTPUTS[key]
        require(not target.exists(), 'Refuse to replace baseline input: ' + str(target))
        value = read(url)
        verify_bytes(contract[key], value)
        target.write_bytes(value)
    (args.output / 'release.json').write_bytes(release_raw)
    (args.output / 'tag.json').write_bytes(tag_raw)
    print('Exact public baseline release/tag/three asset byte hashes verified')

if __name__ == '__main__':
    main()

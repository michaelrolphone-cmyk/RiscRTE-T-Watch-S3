"""Reuse the exact published current-touch 0.2.1 in generic release planning.

The canonical 0.2.0 source remains a historical build input. The separately
compiled current-touch source was already released by the complete 1.0.7 lane;
it must neither be relabeled nor recreated by the generic driver publisher.
"""
import hashlib
import json

IDENTITY = 'twatch-touch'
VERSION = '0.2.1'
TAG = 'driver-twatch-touch-v0.2.1'
REPOSITORY = 'michaelrolphone-cmyk/RiscRTE-T-Watch-S3'
SOURCE_SHA = 'cf30d732271db19a74492d4753736cafeafb92bb'
SOURCE_FILES = {
    "drivers/current/twatch_touch/driver.c": "01b5247d473f3bc7ce34a6de79d259854902637bf78547ce3cbe53a4e407fbc6",
    "drivers/current/twatch_touch/manifest.json": "65d72fad8e7a926bb5ab79b9b480e93c5dcd03d621926d48d11e3edb1f704321",
    "drivers/twatch_touch/driver.c": "0d976c03897d7afd5d405b811436b1ec7d65e8a817c16c527397fb2bc9f47e07",
    "drivers/twatch_touch/manifest.json": "7ed8fd18ea919cfef693b7903f4e303b38225bcb4109c17bd50a3813d9f53ba9"
}
ASSETS = {
    "LICENSES.zip": {
        "sha256": "80c78794f8ea969cc831ca6e774dfa497b484ad3937e3a49d6778d540177aebc",
        "size": 87073
    },
    "SHA256SUMS": {
        "sha256": "76d18aef8ab9f35765e7d83fd2d57de2e655213719a8053d0194d74f7eac0e23",
        "size": 458
    },
    "accepted-manifest.json": {
        "sha256": "e516d1bf0cb428190d66cafe32ad3f04f0e660d88d1a076d6326cddd80cbc548",
        "size": 871
    },
    "driver-twatch-touch-0.2.1-xtensa-esp32s3.rte.zip": {
        "sha256": "d68179e23e4f02db148cbdf8264a057c7a4cdbdd37a0413e748613655ebed98e",
        "size": 65085
    },
    "release-record.json": {
        "sha256": "d01a5522ce20b84bfb0a9aafaeaa62dca94241f2b67a439a2a34ca465398bfa2",
        "size": 3981
    },
    "source-provenance.json": {
        "sha256": "008490b6db7721272513058d44f3477eccc64c5c10e09fd15f498c76ae6c6e0d",
        "size": 2248
    }
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_version(root):
    for name, expected in SOURCE_FILES.items():
        path = root / name
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError('Accepted touch source custody changed: ' + name)
    manifest = json.loads((root / 'drivers/current/twatch_touch/manifest.json').read_text())
    historical = json.loads((root / 'drivers/twatch_touch/manifest.json').read_text())
    if manifest['id'] != IDENTITY or manifest['version'] != VERSION or historical['version'] != '0.2.0':
        raise ValueError('Accepted/historical touch source identities differ')
    return VERSION


def verify_published(repo, existing, gh, root):
    """Read-only fixed inventory/source/asset gate before planning or publishing."""
    source_version(root)
    if repo != REPOSITORY:
        raise ValueError('Wrong accepted touch release repository')
    matches = [row for row in existing if row['tag_name'] == TAG]
    if len(matches) != 1:
        raise ValueError('Exact accepted touch release is missing or duplicated')
    release = matches[0]
    if release['draft'] or release.get('prerelease', False) or release.get('target_commitish') != SOURCE_SHA:
        raise ValueError('Accepted touch release state/source differs')
    names = [row['name'] for row in release['assets']]
    if len(names) != len(set(names)) or set(names) != set(ASSETS):
        raise ValueError('Accepted touch release inventory differs')
    commit = json.loads(gh('api', f'repos/{repo}/commits/{TAG}'))
    if commit['sha'] != SOURCE_SHA:
        raise ValueError('Accepted touch tag source differs')
    for asset in release['assets']:
        raw = gh('api', f'repos/{repo}/releases/assets/{asset["id"]}', '-H', 'Accept: application/octet-stream')
        expected = ASSETS[asset['name']]
        if len(raw) != expected['size'] or digest(raw) != expected['sha256']:
            raise ValueError('Accepted touch immutable asset changed: ' + asset['name'])

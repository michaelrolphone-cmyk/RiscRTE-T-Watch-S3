#!/usr/bin/env python3
"""Pack and independently unpack the verified paired update common store."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from build_update_common import ROOT, PROFILE, read_zip, require, sha, verify

from build_wifi_store import SIZE, OFFSET, TOOL_SHA256, check_tool, check_image


def build(archive, tool, out):
    archive, tool, out = Path(archive), Path(tool).resolve(), Path(out)
    check_tool(tool)
    record = verify(archive)
    expected = {n[6:]: b for n, b in read_zip(archive).items() if n.startswith('store/')}
    require(all(len(('/' + n).encode()) < 32 for n in expected),
            'SPIFFS object name exceeds pinned runtime limit')
    require(sum(map(len, expected.values())) < SIZE, 'Store payload exceeds partition capacity')
    image = out / (archive.stem + '-bootfs.bin')
    require(image.resolve() not in (archive.resolve(), tool), 'Output aliases an input')
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / 'store'
        source.mkdir()
        for name, data in sorted(expected.items()):
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        subprocess.run([str(tool), '-c', str(source), '-p', '256', '-b', '4096',
                        '-s', str(SIZE), str(image)], check=True, timeout=60)
    check_image(image, expected, tool)
    metadata = {'schema': 1, 'profile': PROFILE, 'watch_source_sha': record['source_sha'],
                'deployment_sha256': sha(archive.read_bytes()), 'image': image.name,
                'sha256': sha(image.read_bytes()), 'size_bytes': SIZE,
                'partition_label': 'bootfs0', 'partition_offset': OFFSET, 'page_size': 256,
                'block_size': 4096, 'tool_sha256': TOOL_SHA256, 'files': len(expected),
                'payload_bytes': sum(map(len, expected.values())), 'round_trip_verified': True,
                'physical_verification': 'pending', 'layout': 'riscrte-paired-16m-v1',
                'store_abi': 1, 'migration_only': True, 'apps': record['updates']['apps']}
    image.with_suffix('.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--mkspiffs', required=True, type=Path)
    parser.add_argument('--output', default=ROOT / 'dist/update-common', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.archive, args.mkspiffs, args.output), indent=2))

#!/usr/bin/env python3
"""Reject coherent byte/provenance/claim changes to an exact Watch19 package."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from package_demand_retained import verify
from current_apps_overlay import ROOT, encoded, metadata, require
from build_contexts_cohort import clean

CASES = ('initial-bootloader', 'initial-nvs', 'initial-appdata', 'initial-journal', 'payload',
         'source-pin', 'image-size', 'nested-qualification', 'file-inventory', 'notices',
         'catalog-url', 'checksum', 'linked-member', 'policy-mode', 'app-byte', 'grant-owner')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('target', 'parent', 'build-repository', 'stage', 'runtime', 'native', 'baseline', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--package-source', required=True)
    a = p.parse_args(); head = clean(ROOT); require(not a.output.exists(), 'Output must be new')
    args = (a.parent, a.build_repository, a.stage, a.runtime, a.native, a.baseline, a.package_source)
    before = verify(a.target, *args)
    results = []
    with tempfile.TemporaryDirectory(prefix='watch119-package-') as temp:
        for case in CASES:
            directory = Path(temp) / case; shutil.copytree(a.target, directory)
            path = directory / 'package-proof.json'; proof = json.loads(path.read_bytes())
            image_path = directory / 'twatch-s3-launcher-1.0.19.bin'
            if case.startswith('initial-'):
                offset = {'initial-bootloader': 20, 'initial-nvs': 0x9000, 'initial-appdata': 0x270000, 'initial-journal': 0xff2000}[case]
                image = bytearray(image_path.read_bytes()); image[offset] ^= 1; image_path.write_bytes(image)
                proof['initial_image'] = metadata(image)
                release_path = directory / 'release-record.json'; release = json.loads(release_path.read_bytes())
                release['sha256'] = metadata(image)['sha256']; release_path.write_bytes(encoded(release))
                (directory / 'catalog-fixture.json').write_bytes(encoded({'schema': 1, 'firmware': release, 'apps': []}))
            elif case == 'payload':
                payload = directory / 'twatch-s3-cohort-1.0.19.bin'; raw = bytearray(payload.read_bytes()); raw[-1] ^= 1
                payload.write_bytes(raw); proof['payload'] = metadata(raw)
            elif case == 'source-pin': proof['watch_source'] = '0' * 40
            elif case == 'image-size': proof['initial_image']['size_bytes'] = 1
            elif case == 'nested-qualification': proof['initial_image']['hardware_qualified'] = True
            elif case == 'file-inventory': (directory / 'files/unqualified.json').write_bytes(b'{}')
            elif case == 'notices': (directory / 'LICENSES.zip').write_bytes(b'changed notice')
            elif case == 'catalog-url':
                catalog = directory / 'catalog-fixture.json'; value = json.loads(catalog.read_bytes())
                value['firmware']['url'] = 'https://invalid.example/image.bin'; catalog.write_bytes(encoded(value))
            elif case == 'policy-mode':
                p = directory / 'files/boot.json'; b = json.loads(p.read_bytes()); b['provider_activation'] = 'eager'; p.write_bytes(encoded(b))
            elif case == 'app-byte':
                p = directory / 'files/default.elf'; b = bytearray(p.read_bytes()); b[-1] ^= 1; p.write_bytes(b)
            elif case == 'grant-owner':
                p = directory / 'files/boot.json'; b = json.loads(p.read_bytes()); b['app_capabilities'][0]['grants'][0]['instance_id'] = 999; p.write_bytes(encoded(b))
            elif case == 'linked-member':
                member = directory / 'LICENSES.zip'; member.unlink(); member.symlink_to((a.target / 'LICENSES.zip').resolve())
            path.write_bytes(encoded(proof))
            names = sorted(p.name for p in directory.iterdir() if p.is_file() and p.name != 'SHA256SUMS')
            sums = ''.join(metadata((directory / n).read_bytes())['sha256'] + '  ' + n + '\n' for n in names)
            (directory / 'SHA256SUMS').write_text(sums if case != 'checksum' else 'invalid')
            try: verify(directory, *args)
            except ValueError as error: results.append({'case': case, 'rejected': True, 'reason': str(error)})
            else: raise AssertionError('Mutated package accepted: ' + case)
            shutil.rmtree(directory)
    require(verify(a.target, *args) == before and clean(ROOT) == head, 'Frozen package/source changed')
    output = {'schema': 1, 'test_source': head, 'package_source': a.package_source,
              'package_proof': metadata((a.target / 'package-proof.json').read_bytes()), 'cases': results,
              'positive_before_after': True, 'hardware_qualified': False}
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_bytes(encoded(output))
    print(json.dumps({'rejected_cases': len(results), 'output': str(a.output)}))


if __name__ == '__main__': main()

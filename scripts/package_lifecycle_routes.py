#!/usr/bin/env python3
"""Freeze exact Watch18 bytes as an initial image and a paired update payload."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from current_apps_overlay import ROOT, encoded, metadata, require
from current_cohort import package, parse
from current_flash_layout import APP_DATA_PARTS, assemble
from build_contexts_cohort import clean
from rf_watch_candidate import module
import watch_native_binding as binding

CONTRACT = ROOT / 'apps/lifecycle-packaging-118.json'


def inputs(build_repository, stage, runtime, native, baseline):
    c = json.loads(CONTRACT.read_bytes())
    require(c['schema'] == 1 and c['version'] == '1.0.18' and c['runtime_version'] == '0.1.73' and
            c['catalog_deployed'] is False, 'Wrong packaging contract')
    build_repository, stage, runtime, native = map(lambda p: Path(p).resolve(), (build_repository, stage, runtime, native))
    clean(build_repository, c['build_source']); clean(runtime, c['runtime_source'])
    require(metadata((stage / 'build.json').read_bytes()) == c['build_receipt'], 'Qualified build receipt differs')
    code = ('import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
            'from build_lifecycle_routes import verify;'
            'r=verify(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]),Path(sys.argv[5]),sys.argv[6]);'
            'print(json.dumps(r,sort_keys=True))')
    build = json.loads(subprocess.check_output([sys.executable, '-c', code, str(build_repository / 'scripts'),
                       str(stage), str(baseline), str(runtime), str(native), c['build_source']], text=True))
    files = binding.files_at(stage / 'store'); image = (stage / 'bootfs.bin').read_bytes()
    licenses = (stage / 'LICENSES.zip').read_bytes()
    require(build['files'] == binding.inventory(files) and metadata(image) == c['bootfs'] and
            metadata(licenses) == c['licenses'], 'Qualified build changed while loading')
    native_record, blobs, native_proof = binding.native_inputs(runtime, native)
    require(native_proof == build['runtime'], 'Native candidate differs from app build')
    identity = parse(files['cohort.json'])
    require(identity['version'] == c['version'] and identity['source_revision'] == c['build_source'], 'App cohort identity differs')
    payload, ota = package(identity, blobs['firmware.bin'], image)
    bank = module('watch118_initial_banks', runtime / 'scripts/paired_bank_images.py')
    components = {n: blobs[n] for n in ('bootloader.bin', 'partitions.bin', 'firmware.bin', 'appdata.bin')}
    components.update({'bootfs.bin': image, 'otadata.bin': bank.initial_otadata(),
                       'bank_state.bin': bank.initial_bank_state(blobs['firmware.bin'], image, app_data=True)})
    deployment = {k: native_record[k] for k in ('layout', 'target', 'store_abi', 'flash_bytes')}
    deployment.update(partitions=APP_DATA_PARTS, radio_iq=True)
    initial, placement = assemble(components, deployment, True)
    require(len(initial) == 0x1000000 and initial[0x9000:0xf000] == b'\xff' * 0x6000, 'Initial image erase scope differs')
    name = 'twatch-s3-launcher-1.0.18.bin'; tag = 'firmware-v1.0.18'
    release = {'kind': 'firmware', 'version': c['version'], 'tag': tag, 'asset': name,
               'url': 'https://github.com/' + identity['source_repo'] + '/releases/download/' + tag + '/' + name,
               'size': len(initial), 'sha256': metadata(initial)['sha256'], 'ota': ota}
    values = {'contract': metadata(CONTRACT.read_bytes()), 'build_receipt': c['build_receipt'],
              'build_source': c['build_source'], 'runtime_source': c['runtime_source'], 'native': native_proof,
              'target_cohort': identity, 'files': build['files'], 'payload': metadata(payload),
              'initial_image': metadata(initial), 'initial_component_placement': placement,
              'licenses': metadata(licenses), 'catalog_deployed': False, 'device_accessed': False,
              'qualification': 'Exact packaging only; transaction and hardware qualification are separate',
              'initial_image_effect': 'Full initial image erases all user data; paired payload is not a serial flash image'}
    members = {'files/' + n: raw for n, raw in files.items()}
    members.update({name: initial, ota['asset']: payload, 'bootfs.bin': image, 'LICENSES.zip': licenses,
                    'release-record.json': encoded(release), 'catalog-fixture.json': encoded({'schema': 1, 'firmware': release, 'apps': []})})
    return values, members


def expected_members(build_repository, stage, runtime, native, baseline, package_source):
    require(isinstance(package_source, str) and len(package_source) == 40 and
            all(c in '0123456789abcdef' for c in package_source), 'Independently pinned packaging source required')
    values, members = inputs(build_repository, stage, runtime, native, baseline)
    proof = {'schema': 1, 'scope': 'watch18-lifecycle-routes-package', 'package_source': package_source, **values}
    members['package-proof.json'] = encoded(proof)
    members['SHA256SUMS'] = ''.join(metadata(raw)['sha256'] + '  ' + name + '\n'
            for name, raw in sorted(members.items()) if '/' not in name).encode()
    return proof, members


def verify(directory, build_repository, stage, runtime, native, baseline, expected_package_source):
    proof, members = expected_members(build_repository, stage, runtime, native, baseline, expected_package_source)
    require(binding.files_at(directory) == members, 'Package bytes, inventory, source or qualification metadata differs')
    return proof


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('build-repository', 'stage', 'runtime', 'native', 'baseline', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args(); head = clean(ROOT)
    require(not a.output.exists(), 'Package output must be new')
    args = (a.build_repository, a.stage, a.runtime, a.native, a.baseline)
    proof, members = expected_members(*args, head)
    for name, raw in members.items():
        dest = a.output / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
    require(verify(a.output, *args, head) == proof and clean(ROOT) == head, 'Package/source changed')
    print(json.dumps({k: proof[k] for k in ('package_source', 'target_cohort', 'payload', 'initial_image')}))


if __name__ == '__main__': main()

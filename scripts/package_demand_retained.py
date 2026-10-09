#!/usr/bin/env python3
"""Bind the qualified demand-retained boot policy to an exact Watch19 cohort."""
import argparse
import json
from pathlib import Path
import re

from current_apps_overlay import ROOT, encoded, metadata, require
from build_contexts_cohort import clean
from current_bootfs import build as pack_store
from current_cohort import encode, package
from current_flash_layout import APP_DATA_PARTS, assemble
from read_only_spiffs import read_image
from rf_watch_candidate import module
from package_lifecycle_routes import expected_members as parent_members
import watch_native_binding as binding

PARENT_SOURCE = '014f3e7e4566d4e87f0ab4a1c9e538e557224faa'
PARENT_INITIAL = '216ed021bb42eca460b5ef1fd0c41b5e4a7a39a6230dafded4819530d7eafafb'
PARENT_PAIRED = 'f5949967d28e91cc58e83913dbbe1744f0a291bec3604e46acdaa1a3cd29e7be'
VERSION = '1.0.19'


def construct(parent, build_repository, stage, runtime, native, baseline, source):
    require(isinstance(source, str) and re.fullmatch('[0-9a-f]{40}', source), 'Independent Watch source required')
    original, expected = parent_members(build_repository, stage, runtime, native, baseline, PARENT_SOURCE)
    require(binding.files_at(parent) == expected, 'Frozen Watch18 package differs')
    require(metadata(expected['twatch-s3-launcher-1.0.18.bin'])['sha256'] == PARENT_INITIAL and
            metadata(expected['twatch-s3-cohort-1.0.18.bin'])['sha256'] == PARENT_PAIRED, 'Wrong parent artifact')
    before = {n.removeprefix('files/'): raw for n, raw in expected.items() if n.startswith('files/')}
    require(len(before) == 95 and len([n for n in before if n.endswith('.elf')]) == 46, 'Parent app/provider inventory differs')
    files = dict(before)
    boot = json.loads(before['boot.json'])
    require(boot['provider_activation'] == 'demand' and 'cohort_migration' not in boot, 'Wrong parent policy')
    boot['provider_activation'] = 'demand-retained'
    files['boot.json'] = (json.dumps(boot, sort_keys=True, separators=(',', ':')) + '\n').encode()
    cohort = {**original['target_cohort'], 'version': VERSION, 'source_revision': source}
    require(cohort['runtime_version'] == '0.1.73', 'Demand retention requires the selected supporting native')
    files['cohort.json'] = encode(cohort)
    require({n for n in files if files[n] != before[n]} == {'boot.json', 'cohort.json'}, 'Policy change escaped its scope')
    require(len(boot['app_capabilities']) == 23 and len(boot['drivers']) == 24 and
            max(len(r['grants']) for r in boot['app_capabilities']) == 15, 'Policy capacity changed')
    image, packing = pack_store(files)
    require(read_image(image, 0x510000) == files and packing['empty_blocks'] >= 4, 'SPIFFS custody/reserve differs')
    native_record, blobs, native_proof = binding.native_inputs(runtime, native)
    require(native_proof == original['native'], 'Native changed from the qualified Watch18 pair')
    payload, ota = package(cohort, blobs['firmware.bin'], image)
    bank = module('watch119_initial_banks', Path(runtime) / 'scripts/paired_bank_images.py')
    components = {n: blobs[n] for n in ('bootloader.bin', 'partitions.bin', 'firmware.bin', 'appdata.bin')}
    components.update({'bootfs.bin': image, 'otadata.bin': bank.initial_otadata(),
                       'bank_state.bin': bank.initial_bank_state(blobs['firmware.bin'], image, app_data=True)})
    deployment = {k: native_record[k] for k in ('layout', 'target', 'store_abi', 'flash_bytes')}
    deployment.update(partitions=APP_DATA_PARTS, radio_iq=True)
    initial, placement = assemble(components, deployment, True)
    name = 'twatch-s3-launcher-' + VERSION + '.bin'; tag = 'firmware-v' + VERSION
    release = {'kind': 'firmware', 'version': VERSION, 'tag': tag, 'asset': name,
               'url': 'https://github.com/' + cohort['source_repo'] + '/releases/download/' + tag + '/' + name,
               'size': len(initial), 'sha256': metadata(initial)['sha256'], 'ota': ota}
    proof = {'schema': 1, 'scope': 'watch-demand-retained-policy-candidate', 'watch_source': source,
             'parent_packager_source': PARENT_SOURCE, 'parent_package_proof': metadata(expected['package-proof.json']),
             'parent_initial_image': metadata(expected['twatch-s3-launcher-1.0.18.bin']),
             'parent_paired_payload': metadata(expected['twatch-s3-cohort-1.0.18.bin']),
             'app_build_source': original['build_source'], 'runtime': native_proof, 'cohort': cohort,
             'files': binding.inventory(files), 'changed_store_members': ['boot.json', 'cohort.json'],
             'policy_change': {'from': 'demand', 'to': 'demand-retained'},
             'all_app_provider_native_bytes_unchanged': True, 'app_count': 23, 'provider_selections': 24,
             'packing': packing, 'bootfs': metadata(image), 'payload': metadata(payload),
             'initial_image': metadata(initial), 'initial_component_placement': placement,
             'licenses': metadata(expected['LICENSES.zip']), 'hardware_qualified': False, 'catalog_deployed': False,
             'qualification': 'Packaging custody only; exact-artifact lifecycle and preserving proofs are separate',
             'legacy_update_limit': 'Installed Runtime0.1.55 rejects this policy; use the qualified native bridge first',
             'initial_image_effect': 'Full initial image erases user data; paired payload is not a serial flash image'}
    members = {'files/' + n: raw for n, raw in files.items()}
    members.update({name: initial, ota['asset']: payload, 'bootfs.bin': image, 'LICENSES.zip': expected['LICENSES.zip'],
                    'package-proof.json': encoded(proof), 'release-record.json': encoded(release),
                    'catalog-fixture.json': encoded({'schema': 1, 'firmware': release, 'apps': []})})
    members['SHA256SUMS'] = ''.join(metadata(raw)['sha256'] + '  ' + n + '\n'
            for n, raw in sorted(members.items()) if '/' not in n).encode()
    return proof, members


def verify(directory, parent, build_repository, stage, runtime, native, baseline, expected_source):
    proof, members = construct(parent, build_repository, stage, runtime, native, baseline, expected_source)
    require(binding.files_at(directory) == members, 'Watch19 package bytes, inventory, provenance or claims differ')
    return proof


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('parent', 'build-repository', 'stage', 'runtime', 'native', 'baseline', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args(); source = clean(ROOT)
    require(not a.output.exists(), 'New package output required')
    args = (a.parent, a.build_repository, a.stage, a.runtime, a.native, a.baseline)
    proof, members = construct(*args, source)
    for name, raw in members.items():
        dest = a.output / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
    require(verify(a.output, *args, source) == proof and clean(ROOT) == source, 'Source or constructed package changed')
    print(json.dumps({k: proof[k] for k in ('watch_source', 'cohort', 'payload', 'initial_image', 'packing')}))


if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Prepare exact-origin paired updates, without publishing or touching a device."""
import argparse
import json
from pathlib import Path
import subprocess

from current_apps_overlay import ROOT, encoded, metadata, require
from current_bootfs import build as pack_store
from current_cohort import create, encode, package, parse, verify
from read_only_spiffs import read_image
from rf_watch_candidate import module

PROFILE = ROOT / 'apps/preserving-update-profile.json'
STORE_START, STORE_END = 0x2f0000, 0x800000


def profile():
    return json.loads(PROFILE.read_bytes())


def clean(path, expected=None):
    head = subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    require(expected is None or head == expected, 'Wrong exact source: ' + str(path))
    require(not subprocess.check_output(['git','-C',str(path),'status','--porcelain','--untracked-files=no'],text=True).strip(),
            'Dirty source: ' + str(path))
    return head


def read_origin(path, version):
    contract = profile()
    require(version in contract['origins'], 'Unqualified origin')
    full = Path(path).read_bytes()
    require(len(full) == 0x1000000 and metadata(full)['sha256'] == contract['origins'][version]['image_sha256'],
            'Origin image custody differs: ' + version)
    store = read_image(full[STORE_START:STORE_END], STORE_END-STORE_START)
    identity = parse(store['cohort.json'])
    firmware = full[0x10000:0x10000+identity['firmware_size']]
    verify(identity, firmware, version=version, runtime_version=contract['runtime_version'])
    require(metadata(firmware) == contract['firmware'], 'Origin native bytes differ')
    return {'kind':'delivered-'+version,'full':full,'store':store,'identity':identity,
            'runtime_source':contract['runtime_source'],
            'physical_acceptance_claimed':contract['origins'][version]['hardware_accepted']}


def following_store(baseline, source):
    """Retire the consumed migration without changing any persistent grant."""
    contract = profile()
    require(baseline['identity']['version'] == contract['executable_baseline'], 'Wrong executable baseline')
    files = dict(baseline['store'])
    boot = json.loads(files['boot.json'])
    migration = boot.pop('cohort_migration')
    require(migration['from']['version'] == '1.0.12' and migration['to']['version'] == '1.0.15' and
            migration['shared_key_value'] == [{'application_id':'contexts','api':1,'namespace':1}],
            'Baseline migration contract differs')
    files['boot.json'] = encoded(boot)
    firmware = baseline['full'][0x10000:0x10000+baseline['identity']['firmware_size']]
    identity = create(contract['version'], contract['runtime_version'], source, firmware)
    files['cohort.json'] = encode(identity)
    require(set(files) == set(baseline['store']) and
            {n for n in files if files[n] != baseline['store'][n]} == {'boot.json','cohort.json'},
            'Packaging-only candidate changed executable, provider or application metadata')
    return files


def write_files(directory, files):
    for name, raw in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def build(baseline_path, runtime, output):
    contract = profile(); head = clean(ROOT)
    runtime = Path(runtime).resolve();clean(runtime,contract['runtime_source'])
    output = Path(output).resolve();require(not output.exists(), 'Output already exists')
    baseline = read_origin(baseline_path,contract['executable_baseline'])
    following = following_store(baseline,head)
    bootfs, packing = pack_store(following)
    firmware = baseline['full'][0x10000:0x10000+baseline['identity']['firmware_size']]
    identity = parse(following['cohort.json'])
    payload, ota = package(identity,firmware,bootfs)
    bank = module('preserving_initial_bank',runtime/'scripts/paired_bank_images.py')
    original = baseline['full']; initial = bytearray(original)
    initial[STORE_START:STORE_END] = bootfs
    initial[0xff2000:0xff4000] = bank.initial_bank_state(firmware,bootfs,app_data=True)
    initial = bytes(initial)
    require(initial[:STORE_START] == original[:STORE_START] and initial[STORE_END:0xff2000] == original[STORE_END:0xff2000] and
            initial[0xff4000:] == original[0xff4000:], 'Initial image changed unrelated regions')
    full_name = 'twatch-s3-launcher-'+identity['version']+'.bin'
    tag = 'firmware-v'+identity['version']
    record = {'kind':'firmware','version':identity['version'],'tag':tag,'asset':full_name,
              'url':'https://github.com/'+identity['source_repo']+'/releases/download/'+tag+'/'+full_name,
              'size':len(initial),'sha256':metadata(initial)['sha256'],'ota':ota}
    proof = {'schema':1,'scope':'exact-origin-preserving-update','watch_source':head,
             'runtime_source':contract['runtime_source'],'source_image':metadata(original),
             'target_cohort':identity,'payload':metadata(payload),'initial_image':metadata(initial),
             'packing':packing,'files':{n:metadata(b) for n,b in sorted(following.items())},
             'changed_store_members':['boot.json','cohort.json'],'executable_bytes_unchanged':True,
             'persistent_grants_unchanged':True,'compatible_origins':['1.0.13','1.0.14','1.0.15'],
             'catalog_limitation':contract['catalog_limitation'],'device_accessed':False,
             'transaction_qualification':'Separate exact-byte proof required before deployment',
             'initial_image_effect':'Full initial image erases all user data; use only paired payload for updating'}
    write_files(output/'files',following)
    blobs = {ota['asset']:payload, full_name:initial,'bootfs.bin':bootfs,
             'package-proof.json':encoded(proof),'release-record.json':encoded(record),
             'catalog-fixture.json':encoded({'schema':1,'firmware':record,'apps':[]})}
    write_files(output,blobs)
    (output/'SHA256SUMS').write_text(''.join(metadata(raw)['sha256']+'  '+name+'\n' for name,raw in sorted(blobs.items())))
    return proof


def bridge(baseline_path, runtime, output):
    """Stage the unchanged delivered15 bytes for the exact12 migration route."""
    contract=profile();head=clean(ROOT);clean(runtime,contract['runtime_source'])
    output=Path(output).resolve();require(not output.exists(),'Output already exists')
    target=read_origin(baseline_path,'1.0.15');identity=target['identity']
    firmware=target['full'][0x10000:0x10000+identity['firmware_size']]
    bootfs=target['full'][STORE_START:STORE_END]
    payload,ota=package(identity,firmware,bootfs)
    proof={'schema':1,'scope':'unchanged-delivered15-bridge-from-exact12','watch_packager_source':head,
           'runtime_source':contract['runtime_source'],'target_cohort':identity,
           'source_image':metadata(target['full']),'payload':metadata(payload),
           'files':{n:metadata(b) for n,b in sorted(target['store'].items())},
           'compatible_origins':['1.0.12'],'executable_bytes_unchanged':True,
           'catalog_limitation':contract['catalog_limitation'],'device_accessed':False}
    name='twatch-s3-launcher-1.0.15.bin';tag='firmware-v1.0.15'
    record={'kind':'firmware','version':'1.0.15','tag':tag,'asset':name,
            'url':'https://github.com/'+identity['source_repo']+'/releases/download/'+tag+'/'+name,
            'size':len(target['full']),'sha256':metadata(target['full'])['sha256'],'ota':ota}
    write_files(output/'files',target['store'])
    write_files(output,{ota['asset']:payload,'package-proof.json':encoded(proof),
                        'release-record.json':encoded(record),
                        'catalog-fixture.json':encoded({'schema':1,'firmware':record,'apps':[]})})
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-image',required=True,type=Path)
    parser.add_argument('--runtime',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--bridge-from12',action='store_true')
    args = parser.parse_args()
    print(json.dumps((bridge if args.bridge_from12 else build)(args.baseline_image,args.runtime,args.output),indent=2))


if __name__ == '__main__':
    main()

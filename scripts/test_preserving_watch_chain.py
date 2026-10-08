#!/usr/bin/env python3
"""Prove the actual modeled bank0→1→0 Watch12→15→17 preserving sequence."""
import argparse,json
from pathlib import Path
from bound_preserving_watch_update import arguments,verify_package
from build_preserving_watch_update import clean,profile,read_origin
from current_apps_overlay import ROOT,encoded,metadata,require
from current_cohort import package,parse,verify as verify_identity
from read_only_spiffs import read_image
from runtime_features_watch_candidate import read_native,FIRMWARE_OFFSETS,STORE_OFFSETS,STORE_BYTES
from test_preserving_watch_upgrade import prove,files_at,sha


def main():
    p=argparse.ArgumentParser(description=__doc__);arguments(p)
    for name in ('installed-runtime','installed-native','origin-image','bridge-image','bridge','target','output'):
        p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();require(not a.output.exists(),'Chain proof output must be new');head=clean(ROOT)
    clean(a.installed_runtime,profile()['runtime_source'])
    origin=read_origin(a.origin_image,'1.0.12');bridge=read_origin(a.bridge_image,'1.0.15')
    installed=read_native(a.installed_native,a.installed_runtime,ROOT)
    middle_payload,middle_ota=package(bridge['identity'],installed['blobs']['firmware.bin'],bridge['full'][0x2f0000:0x800000])
    require(files_at(a.bridge/'files')==bridge['store'] and (a.bridge/middle_ota['asset']).read_bytes()==middle_payload,
            'Bridge differs from exact delivered15 bytes')
    final=verify_package(a.target,a.binding_repository,a.binding,a.runtime,a.native)
    binding,files,bootfs,payload,ota,native=final
    a.output.mkdir(parents=True)
    middle_path=a.output/'model-bank1-after-bridge.bin'
    first=prove(origin,installed,bridge['store'],middle_payload,a.installed_runtime,
                installed_runtime=a.installed_runtime,installed_native=installed,apps_dir=a.bridge,export_snapshot=middle_path)
    (a.output/'first-hop.json').write_bytes(encoded(first))
    snapshot=middle_path.read_bytes();require(metadata(snapshot)==first['selected_snapshot'],'Bridge export differs')
    active_store=read_image(snapshot[STORE_OFFSETS[1]:STORE_OFFSETS[1]+STORE_BYTES],STORE_BYTES)
    require(active_store==bridge['store'],'Actual selected bank1 is not the delivered15 store')
    identity=parse(active_store['cohort.json'])
    active_native=snapshot[FIRMWARE_OFFSETS[1]:FIRMWARE_OFFSETS[1]+identity['firmware_size']]
    verify_identity(identity,active_native,version='1.0.15',runtime_version=profile()['runtime_version'])
    require(active_native==installed['blobs']['firmware.bin'] and
            sha(snapshot[0x9000:0xf000])==first['nvs_sha256'] and
            sha(snapshot[0x270000:0x2f0000])==first['appdata_sha256'],'Bridge native or persistent bytes differ')
    chained={'kind':'actual-modeled-selected-bridge-from-delivered12','full':snapshot,'store':active_store,'identity':identity,
             'runtime_source':profile()['runtime_source'],'physical_acceptance_claimed':False,
             'active_bank':1,'preserve_existing_data':True}
    print('First hop complete; using its actual selected bank1 snapshot for the second hop',flush=True)
    second_path=a.output/'model-bank0-after-final.bin'
    second=prove(chained,native,files,payload,a.runtime,installed_runtime=a.installed_runtime,
                 installed_native=installed,apps_dir=a.target,export_snapshot=second_path)
    (a.output/'second-hop.json').write_bytes(encoded(second))
    require(second['source_initial_image']==first['selected_snapshot'] and
            second['source_bank']==1 and second['destination_bank']==0 and second['input_persistent_data_kept'] and
            all(first[k]==second[k] for k in ('nvs_sha256','appdata_sha256')),
            'Second hop did not consume and preserve the actual first-hop result')
    result=second_path.read_bytes();require(metadata(result)==second['selected_snapshot'],'Final export differs')
    require(read_image(result[STORE_OFFSETS[0]:STORE_OFFSETS[0]+STORE_BYTES],STORE_BYTES)==files and
            result[FIRMWARE_OFFSETS[0]:FIRMWARE_OFFSETS[0]+len(native['blobs']['firmware.bin'])]==native['blobs']['firmware.bin'],
            'Final bank0 differs from the bound17 pair')
    require(middle_path.read_bytes()==snapshot and clean(ROOT)==head and
            verify_package(a.target,a.binding_repository,a.binding,a.runtime,a.native)==final,'Chain input or source changed')
    record={'schema':1,'kind':'actual-modeled-watch12-to15-to17-chain','qualification_source':head,
            'origin':origin['identity'],'intermediate':identity,'target':binding['cohort'],
            'bank_path':[0,1,0],'first_hop':metadata((a.output/'first-hop.json').read_bytes()),
            'second_hop':metadata((a.output/'second-hop.json').read_bytes()),
            'intermediate_snapshot':first['selected_snapshot'],'final_snapshot':second['selected_snapshot'],
            'nvs_sha256':second['nvs_sha256'],'appdata_sha256':second['appdata_sha256'],
            'scenarios_per_hop':31,'process_cases':len(first['transactions'])+len(second['transactions']),
            'negative_admissions':len(first['rejections'])+len(second['rejections']),
            'sanitized':first['sanitized'],'second_hop_data_not_reinitialized':True,
            'idf_selection_and_confirmation_modeled':True,'target_instructions_executed':False,
            'hardware_qualified':False,'device_accessed':False,'live_catalog_deployment':False}
    require(record['process_cases']==318 and record['negative_admissions']==32 and first['sanitized']==second['sanitized'],
            'Chain scenario/mode inventory differs')
    (a.output/'chain.json').write_bytes(encoded(record));print(json.dumps(record))

if __name__=='__main__':main()

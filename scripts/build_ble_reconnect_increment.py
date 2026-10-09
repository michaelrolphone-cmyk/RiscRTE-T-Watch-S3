#!/usr/bin/env python3
"""Reproduce Watch 21 from frozen Watch 20 and qualified BLE HID 0.1.4.

Only the provider bytes, its version and the cohort identity change. The full
16 MiB output is an initial image: erase all flash, then write at 0x0. No device,
release, live feed or preserving-update operation is performed by this tool.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from current_apps_overlay import encoded, metadata, require
from build_contexts_cohort import clean
from current_bootfs import build as pack_store
from current_cohort import encode, parse, package
from current_flash_layout import APP_DATA_PARTS, assemble
from read_only_spiffs import read_image
from build_wifi_common import zip_bytes
import watch_native_binding as binding
from check_runtime_store_admission import compile_harness, admit, admit_cohort

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'apps/ble-reconnect-121.json'
NAME='twatch-s3-1.0.21-FULL-INITIAL-ERASES-DATA-bma423.bin'
CHANGED={'ble-hid/driver.elf','ble-hid/manifest.json','cohort.json'}

def config():return json.loads(CONFIG.read_bytes())
def write_files(root,files):
    for name,data in files.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)

def baseline(args):
    c=config();raw=args.baseline_bin.read_bytes()
    require(metadata(raw)==c['baseline_full'] and len(raw)==0x1000000,'Frozen Watch 20 full image differs')
    image=raw[0x2f0000:0x800000]
    require(metadata(image)==c['baseline_bootfs'],'Watch 20 bootfs differs')
    files=read_image(image,0x510000)
    require(binding.inventory(files)==c['baseline_files'],'Watch 20 complete inventory differs')
    require(metadata(args.baseline_licenses.read_bytes())==c['baseline_licenses'],'Baseline licenses differ')
    return raw,files

def provider(args):
    c=config();clean(args.drivers,c['driver_source'])
    tree=subprocess.check_output(['git','-C',str(args.drivers),'rev-parse','HEAD:Drivers/ble_hid'],text=True).strip()
    require(tree==c['driver_tree'],'Qualified provider directory differs')
    folder=args.drivers/'dist/ble-hid';raw=(folder/'driver.elf').read_bytes()
    proof=json.loads((folder/'build-record.json').read_bytes())
    require(metadata(raw)==c['driver_elf'],'Qualified provider ELF differs')
    require(proof['source_revision']==c['driver_source'] and proof['source_dirty'] is False,'Provider build source differs')
    require({k:proof[k] for k in ('sha256','size_bytes')}==c['driver_elf'],'Provider build receipt differs')
    manifest=(folder/'manifest.json').read_bytes()
    expected=(json.dumps(json.loads((args.drivers/'Drivers/ble_hid/manifest.json').read_bytes()),indent=2)+'\n').encode()
    require(manifest==expected,'Provider manifest serialization differs')
    notices={p.name:p.read_bytes() for p in folder.glob('*') if p.name in ('NimBLE-LICENSE','NimBLE-NOTICE','NimBLE-SOURCE.json','TinyCrypt-LICENSE')}
    require(len(notices)==4,'Provider notices incomplete')
    return raw,manifest,proof,zip_bytes(notices)

def scope(before,after,head):
    c=config()
    require(set(before)==set(after) and len(after)==95,'Store membership differs')
    require({n for n in before if before[n]!=after[n]}==CHANGED,'Only three provider/cohort paths may change')
    require(json.loads(after['ble-hid/manifest.json'])=={**json.loads(before['ble-hid/manifest.json']),'version':c['driver_version']},'Provider authority changed')
    require(parse(after['cohort.json'])=={**parse(before['cohort.json']),'version':c['version'],'source_revision':head},'Unexpected cohort change')
    apps=sorted(n for n in before if n.endswith('.elf') and '/' not in n)
    require(len(apps)==23 and all(after[n]==before[n] for n in apps),'Application bytes changed')
    require(after['boot.json']==before['boot.json'] and after['board.json']==before['board.json'],'Product policy changed')
    return {'changed_store_members':sorted(CHANGED),'app_count':23,'all_apps_byte_identical':True,'unchanged_store_members':92,'boot_board_grants_byte_identical':True}

def assemble_artifacts(args,files):
    c=config();bootfs,packing=pack_store(files)
    require(packing['empty_blocks']>=4,'SPIFFS reserve below four blocks')
    record,blobs,native=binding.native_inputs(args.native_runtime,args.native_candidate)
    require(native['source']==c['native_runtime'],'Frozen native Runtime differs')
    spec=importlib.util.spec_from_file_location('watch21_banks',args.native_runtime/'scripts/paired_bank_images.py')
    bank=importlib.util.module_from_spec(spec);spec.loader.exec_module(bank)
    components={n:blobs[n] for n in ('bootloader.bin','partitions.bin','firmware.bin','appdata.bin')}
    components.update({'bootfs.bin':bootfs,'otadata.bin':bank.initial_otadata(),'bank_state.bin':bank.initial_bank_state(blobs['firmware.bin'],bootfs,app_data=True)})
    deployment={k:record[k] for k in ('layout','target','store_abi','flash_bytes')};deployment.update(partitions=APP_DATA_PARTS,radio_iq=True)
    initial,placement=assemble(components,deployment,True)
    payload,ota=package(parse(files['cohort.json']),blobs['firmware.bin'],bootfs)
    artifacts={'bootfs.bin':bootfs,NAME:initial,ota['asset']:payload,'store.zip':zip_bytes({'store/'+n:b for n,b in files.items()})}
    return artifacts,{'packing':packing,'native':native,'placement':placement,'paired_asset':ota['asset'],'deployment':deployment},blobs

def verify(args,expected_source):
    clean(ROOT,expected_source);out=args.output;c=config();old,before=baseline(args)
    files=binding.files_at(out/'files');record=json.loads((out/'build.json').read_bytes())
    require(record['source_revision']==expected_source and record['config']==metadata(CONFIG.read_bytes()),'Recipe identity differs')
    require(record['files']==binding.inventory(files) and record['scope']==scope(before,files,expected_source),'Store custody differs')
    raw,manifest,proof,notices=provider(args)
    require(files['ble-hid/driver.elf']==raw and files['ble-hid/manifest.json']==manifest and record['provider']==proof,'Provider inputs differ')
    artifacts,packing,_=assemble_artifacts(args,files)
    require(record['packaging']==packing,'Packaging receipt differs')
    for name,data in artifacts.items():require((out/name).read_bytes()==data and record['artifacts'][name]==metadata(data),'Artifact differs: '+name)
    full=artifacts[NAME]
    require(read_image(full[0x2f0000:0x800000],0x510000)==files,'Extracted full-image store differs')
    require(full[:0x2f0000]==old[:0x2f0000] and full[0x800000:0xff2000]==old[0x800000:0xff2000] and full[0xff4000:]==old[0xff4000:],'Native/appdata/inactive/OTA/unused bytes changed')
    require((out/'LICENSES-baseline.zip').read_bytes()==args.baseline_licenses.read_bytes() and (out/'BLE-HID-NOTICES.zip').read_bytes()==notices,'License custody differs')
    for key in ('hardware_qualified','live_feed_published','preserving_transaction_qualified'):require(record[key] is False,'Qualification overclaim')
    clean(ROOT,expected_source);return record

def build(args):
    head=clean(ROOT);_,before=baseline(args);raw,manifest,proof,notices=provider(args);out=args.output
    require(not out.exists(),'New output required');out.mkdir(parents=True)
    files=dict(before);files['ble-hid/driver.elf']=raw;files['ble-hid/manifest.json']=manifest
    files['cohort.json']=encode({**parse(before['cohort.json']),'version':config()['version'],'source_revision':head})
    scoped=scope(before,files,head);artifacts,packing,blobs=assemble_artifacts(args,files)
    write_files(out/'files',files);write_files(out,artifacts)
    (out/'LICENSES-baseline.zip').write_bytes(args.baseline_licenses.read_bytes());(out/'BLE-HID-NOTICES.zip').write_bytes(notices)
    record={'schema':1,'profile':'watch21-ble-reconnect','source_revision':head,'config':metadata(CONFIG.read_bytes()),'baseline':metadata(args.baseline_bin.read_bytes()),'scope':scoped,'provider':proof,'files':binding.inventory(files),'packaging':packing,'artifacts':{n:metadata(b) for n,b in artifacts.items()},'hardware_qualified':False,'live_feed_published':False,'preserving_transaction_qualified':False,'installation':'Full 16 MiB initial image; erase all flash and write at 0x0. Settings, bonds, saved events and training data are erased.'}
    (out/'build.json').write_bytes(encoded(record));verify(args,head)
    results={}
    for sanitized in (False,True):
        os.environ['SANITIZE']='1' if sanitized else '0';os.environ['ASAN_OPTIONS']='detect_leaks=0'
        folder=out/('admission-sanitized' if sanitized else 'admission-normal');folder.mkdir()
        harness=compile_harness(args.native_runtime,folder/'admit',True)
        actual=read_image(artifacts[NAME][0x2f0000:0x800000],0x510000)
        results['sanitized' if sanitized else 'normal']={'whole_store':admit(harness,actual),'cohort':admit_cohort(args.native_runtime,blobs['firmware.elf'],before,actual)}
    (out/'admission.json').write_bytes(encoded({'source_revision':head,'runtime_source':config()['native_runtime'],'actual_full_image':metadata(artifacts[NAME]),'results':results,'target_instructions_executed':False,'hardware_qualified':False,'leak_detection':False}))
    print(json.dumps({'verified':str(out/NAME),'metadata':metadata(artifacts[NAME]),'normal_sanitized_store_and_cohort':True}),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('drivers','native-runtime','native-candidate','baseline-bin','baseline-licenses','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--verify-source');args=p.parse_args()
    if args.verify_source:verify(args,args.verify_source)
    else:build(args)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Build/verify isolated Watch20 HID increment on exact delivered Watch19 bytes.

Full image is initial installation and erases data. This recipe never publishes,
flashes, or claims physical or preserving-transaction qualification.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from current_apps_overlay import encoded, metadata, require
from build_contexts_cohort import clean, definitions, write_catalog
from build_current_apps import application_inputs
from contexts_profile import catalog
from lifecycle_source_custody import SourceCustody, QualifiedCompiler, catalog_inputs, application_command
from current_bootfs import build as pack_store
from current_cohort import encode, parse, package
from current_flash_layout import APP_DATA_PARTS, assemble
from read_only_spiffs import read_image
from build_wifi_common import zip_bytes
import watch_native_binding as binding
from check_runtime_store_admission import compile_harness, admit, admit_cohort

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'apps/touchpad-increment-120.json'
APPS = ('ble_touchpad', 'ble_buttons')
CHANGED = {n+s for n in APPS for s in ('.elf','.json')} | {'ble-hid/driver.elf','ble-hid/manifest.json','cohort.json'}
NAME = 'twatch-s3-1.0.20-FULL-INITIAL-ERASES-DATA-bma423.bin'


def config():
    return json.loads(CONFIG.read_bytes())


def module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def write_files(directory, files):
    for name, raw in files.items():
        p=directory/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)


def baseline(args):
    c=config();raw=args.baseline_bin.read_bytes()
    require(len(raw)==0x1000000 and metadata(raw)['sha256']==c['baseline_full_sha256'],'Delivered Watch19 full image differs')
    image=raw[0x2f0000:0x800000]
    require(metadata(image)['sha256']==c['baseline_bootfs_sha256'],'Delivered Watch19 bootfs differs')
    files=read_image(image,0x510000)
    require(binding.inventory(files)==c['baseline_files'],'Delivered Watch19 member inventory differs')
    require(binding.files_at(args.baseline_store)==files,'Watch19 extracted directory differs from delivered full image')
    return raw,files


def scope(before, after, head):
    require(set(before)==set(after) and len(after)==95,'Complete store membership differs')
    require({n for n in before if before[n]!=after[n]}==CHANGED,'Only seven allowed store paths may change')
    for n in APPS:
        require(json.loads(after[n+'.json'])=={**json.loads(before[n+'.json']),'version':'0.1.14'},'App authority changed: '+n)
    require(json.loads(after['ble-hid/manifest.json'])=={**json.loads(before['ble-hid/manifest.json']),'version':'0.1.3'},'BLE provider authority changed')
    require(parse(after['cohort.json'])=={**parse(before['cohort.json']),'version':'1.0.20','source_revision':head},'Unexpected cohort changes')
    require(after['boot.json']==before['boot.json'] and after['board.json']==before['board.json'],'Boot or board policy changed')
    require(json.loads(after['boot.json'])['provider_activation']=='demand-retained','Demand-retained policy differs')
    apps=sorted(n for n in after if n.endswith('.elf') and '/' not in n)
    require(len(apps)==23,'App count differs')
    return {'changed_store_members':sorted(CHANGED),'app_count':23,'preserved_apps':sorted(set(apps)-{n+'.elf' for n in APPS}),'boot_board_grants_byte_identical':True,'unchanged_store_members':88}


def selected_sources(args):
    c=config();roots={n:Path(getattr(args,n.replace('-','_'))).resolve() for n in c['source_pins']}
    for n,p in roots.items():clean(p,c['source_pins'][n])
    for n in ('utilities','drivers'):
        tree=subprocess.check_output(['git','-C',str(roots[n]),'rev-parse','HEAD^{tree}'],text=True).strip()
        require(tree==c[n+'_tree'],'Source tree differs: '+n)
    return roots


def input_plan(n, roots, out):
    repos={k:v for k,v in roots.items() if k not in ('watch','drivers')}
    src=roots['utilities']/'Apps'/(n+'.c')
    sources,includes,allowed=application_inputs(n,src,repos,roots['watch'],out,'runtime-features')
    includes += [roots['utilities']/'lib/Contexts/include']
    flags=definitions(n,'0.1.14',roots['watch'])
    # Exact full Watch19 feature selection; app versions do not enter these flags.
    expected=[f.replace('/workspace/scratch/c744abbbbd60/watch-lifecycle-routes-118',str(roots['watch'])) for f in config()['baseline_app_builds'][n]['defines']]
    require(flags==expected,'Watch19 feature flags changed')
    return sources,includes,allowed|{'memchr','strncmp'},flags


def check_dependency_delta(n,deps):
    before=config()['baseline_app_builds'][n]['target_dependencies']
    old={k:v for k,v in before.items() if not k.startswith('utilities:')}
    new={k:v for k,v in deps.items() if not k.startswith('utilities:')}
    require(new==old,'Watch19 non-HID compiler inputs changed')
    required={'utilities:Apps/ble_touchpad_gesture.h','utilities:lib/Bluetooth/include/RiscBluetoothHidV1.h'}
    require(required<=set(deps),'New gesture/header absent from target compiler closure')
    return {'non_utility_inputs_byte_identical':len(old),'utility_inputs':{k:v for k,v in deps.items() if k.startswith('utilities:')}}


def assemble_artifacts(args,files):
    c=config();identity=parse(files['cohort.json']);bootfs,packing=pack_store(files)
    require(packing['empty_blocks']>=4,'SPIFFS reserve below four blocks')
    record,blobs,native=binding.native_inputs(args.native_runtime,args.native_candidate)
    require(native['source']==c['native_runtime'],'Supporting Runtime differs')
    bank=module(args.native_runtime/'scripts/paired_bank_images.py','watch20_banks')
    components={n:blobs[n] for n in ('bootloader.bin','partitions.bin','firmware.bin','appdata.bin')}
    components.update({'bootfs.bin':bootfs,'otadata.bin':bank.initial_otadata(),'bank_state.bin':bank.initial_bank_state(blobs['firmware.bin'],bootfs,app_data=True)})
    deployment={k:record[k] for k in ('layout','target','store_abi','flash_bytes')}
    deployment.update(partitions=APP_DATA_PARTS,radio_iq=True)
    initial,placement=assemble(components,deployment,True)
    payload,ota=package(identity,blobs['firmware.bin'],bootfs)
    return {'bootfs.bin':bootfs,NAME:initial,ota['asset']:payload,'store.zip':zip_bytes({'store/'+n:b for n,b in files.items()})}, {'packing':packing,'native':native,'placement':placement,'paired_asset':ota['asset'],'deployment':deployment},blobs


def provider(roots):
    c=config();base=roots['drivers']/'dist/ble-hid';raw=(base/'driver.elf').read_bytes()
    require(metadata(raw)==c['driver_elf'],'Qualified BLE HID driver bytes differ')
    proof=json.loads((base/'build-record.json').read_bytes())
    require(proof['source_revision']==c['source_pins']['drivers'] and proof['source_dirty'] is False and {k:proof[k] for k in ('sha256','size_bytes')}==c['driver_elf'],'Driver source receipt differs')
    manifest=(base/'manifest.json').read_bytes()
    require(manifest==(json.dumps(json.loads((roots['drivers']/'Drivers/ble_hid/manifest.json').read_bytes()),indent=2)+'\n').encode(),'Provider manifest not exact pinned source serialization')
    require((roots['utilities']/'lib/Bluetooth/include/RiscBluetoothHidV1.h').read_bytes()==(roots['drivers']/'sdk/driver/RiscBluetoothHidV1.h').read_bytes(),'App and provider HID ABI headers differ')
    return raw,manifest,proof


def verify(args,expected_source):
    c=config();clean(ROOT,expected_source);roots=selected_sources(args)
    _,before=baseline(args);out=args.output
    record=json.loads((out/'build.json').read_bytes());files=binding.files_at(out/'files')
    require(record['source_revision']==expected_source and record['config']==metadata(CONFIG.read_bytes()),'Recipe identity differs')
    require(record['scope']==scope(before,files,expected_source) and record['files']==binding.inventory(files),'Store receipt differs')
    guard=SourceCustody(roots,c['source_pins'],catalog_inputs(out/'compiler',catalog()))
    for n in APPS:
        sources,includes,allowed,flags=input_plan(n,roots,out/'compiler')
        deps=guard.check(application_command(args.cc,out/'compiler',n,sources,flags,includes))
        require(record['apps'][n]['target_dependencies']==deps and record['apps'][n]['defines']==flags,'Target dependency or flags proof differs')
        require(record['apps'][n]['dependency_delta']==check_dependency_delta(n,deps),'Target dependency preservation differs')
        require(metadata(files[n+'.elf'])=={k:record['apps'][n][k] for k in ('sha256','size_bytes')},'Target app bytes differ')
        require(record['apps'][n]['compaction']['before_sha256']==metadata((out/'compiler/debug'/(n+'.elf')).read_bytes())['sha256'],'Pre-compaction ELF differs')
    raw,manifest,proof=provider(roots)
    require(files['ble-hid/driver.elf']==raw and files['ble-hid/manifest.json']==manifest and record['provider']==proof,'Provider bytes differ')
    artifacts,packaging,_=assemble_artifacts(args,files)
    require(record['packaging']==packaging,'Packaging proof differs')
    for n,b in artifacts.items():require((out/n).read_bytes()==b and record['artifacts'][n]==metadata(b),'Packaged artifact differs: '+n)
    # Actual extracted full-image and store must independently agree.
    full=(out/NAME).read_bytes();require(read_image(full[0x2f0000:0x800000],0x510000)==files,'Full-image store differs')
    old=args.baseline_bin.read_bytes()
    require(full[:0x2f0000]==old[:0x2f0000] and full[0x800000:0xff2000]==old[0x800000:0xff2000] and full[0xff4000:]==old[0xff4000:],'Native, appdata, inactive bank, OTA data or unused partitions changed')
    require(record['hardware_qualified'] is False and record['live_feed_published'] is False and record['preserving_transaction_qualified'] is False,'Qualification claim exceeds recipe scope')
    clean(ROOT,expected_source)
    return record


def build(args):
    c=config();head=clean(ROOT);roots=selected_sources(args)
    _,before=baseline(args);out=args.output.resolve();require(not out.exists(),'New output required')
    out.mkdir(parents=True);buildout=out/'compiler';buildout.mkdir()
    write_catalog(buildout,catalog())
    guard=SourceCustody(roots,c['source_pins'],catalog_inputs(buildout,catalog()))
    repos={k:v for k,v in roots.items() if k not in ('watch','drivers')}
    compiler_version=subprocess.check_output([str(args.cc),'--version'],text=True).splitlines()[0]
    require('8.4.0' in compiler_version,'Pinned GCC8.4 required')
    compiler=QualifiedCompiler(str(args.cc),roots['watch'],buildout,repos,roots['drivers'],guard)
    after=dict(before);proofs={}
    for n in APPS:
        require(json.loads((roots['utilities']/'Apps'/(n+'.json')).read_bytes())['version']=='0.1.14','Source manifest version differs')
        sources,includes,allowed,flags=input_plan(n,roots,buildout)
        raw,proof=compiler.build(n,sources,flags,includes,{'app_main','app_module_init','app_module_fini'},allowed)
        proof['dependency_delta']=check_dependency_delta(n,proof['target_dependencies'])
        after[n+'.elf']=raw;after[n+'.json']=encoded({**json.loads(before[n+'.json']),'version':'0.1.14'});proofs[n]=proof
    raw,manifest,provider_proof=provider(roots)
    subprocess.run([str(compiler.validator),str(roots['drivers']/'dist/ble-hid/driver.elf')],check=True)
    after['ble-hid/driver.elf']=raw;after['ble-hid/manifest.json']=manifest
    after['cohort.json']=encode({**parse(before['cohort.json']),'version':'1.0.20','source_revision':head})
    scoped=scope(before,after,head)
    artifacts,packaging,blobs=assemble_artifacts(args,after)
    write_files(out/'files',after);write_files(out,artifacts)
    # Preserve the delivered license archive and append current component notices separately.
    (out/'LICENSES-baseline.zip').write_bytes((args.baseline_store.parent/'LICENSES.zip').read_bytes())
    notices={p.name:p.read_bytes() for p in (roots['drivers']/'dist/ble-hid').glob('*') if p.name in ('NimBLE-LICENSE','NimBLE-NOTICE','NimBLE-SOURCE.json','TinyCrypt-LICENSE')}
    (out/'BLE-HID-NOTICES.zip').write_bytes(zip_bytes(notices))
    record={'schema':1,'profile':'watch20-touchpad-increment','source_revision':head,'config':metadata(CONFIG.read_bytes()),'source_pins':c['source_pins'],'source_roots':{n:str(p) for n,p in roots.items()},'compiler':compiler_version,'baseline':metadata(args.baseline_bin.read_bytes()),'scope':scoped,'apps':proofs,'provider':provider_proof,'files':binding.inventory(after),'packaging':packaging,'artifacts':{n:metadata(b) for n,b in artifacts.items()},'hardware_qualified':False,'live_feed_published':False,'preserving_transaction_qualified':False,'installation':'Full 16 MiB image is INITIAL installation and ERASES DATA. Paired payload is built but no preserving transaction qualification is implied.'}
    (out/'build.json').write_bytes(encoded(record))
    verify(args,head)
    print(json.dumps({'ready_for_admission':str(out/NAME),'metadata':metadata(artifacts[NAME]),'empty_blocks':packaging['packing']['empty_blocks']}),flush=True)
    admissions={}
    for sanitized in (False,True):
        os.environ['SANITIZE']='1' if sanitized else '0'
        os.environ['ASAN_OPTIONS']='detect_leaks=0'  # LeakSanitizer cannot run under executor ptrace.
        folder=out/('admission-sanitized' if sanitized else 'admission-normal');folder.mkdir()
        harness=compile_harness(args.native_runtime,folder/'admit',True)
        actual=read_image((out/NAME).read_bytes()[0x2f0000:0x800000],0x510000)
        admissions['sanitized' if sanitized else 'normal']={'whole_store':admit(harness,actual),'cohort':admit_cohort(args.native_runtime,blobs['firmware.elf'],before,actual)}
    (out/'admission.json').write_bytes(encoded({'source_revision':head,'runtime_source':c['native_runtime'],'actual_full_image':metadata(artifacts[NAME]),'results':admissions,'target_instructions_executed':False,'hardware_qualified':False,'leak_detection':False,'leak_detection_reason':'LeakSanitizer unsupported under executor ptrace'}))
    print(json.dumps({'verified':str(out/NAME),'metadata':metadata(artifacts[NAME]),'normal_and_sanitized_whole_store_and_cohort_admission':True}),flush=True)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('watch','system-apps','utilities','productivity','runtime','drivers','native-runtime','native-candidate','baseline-bin','baseline-store','cc','output'):
        p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--verify-source')
    args=p.parse_args()
    if args.verify_source:verify(args,args.verify_source)
    else:build(args)

if __name__=='__main__':main()

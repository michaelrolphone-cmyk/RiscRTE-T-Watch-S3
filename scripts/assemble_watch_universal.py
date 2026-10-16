#!/usr/bin/env python3
"""Compose a complete T-Watch candidate using the canonical shared Home build.

All 25 apps and every existing provider from delivered 1.1.17 remain. The new
native profile has space for three independent generic power services. This
produces an initial image, not a data-preserving OTA/update transaction.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
from current_bootfs import build,read_image
from watch_boot_order_spiffs import build as ordered_build
from universal_admission import compile_harness,admit
from universal_native import RUNTIME,require,sha

ROOT=Path(__file__).resolve().parents[1]
BASE_SHA='c33562f158fae21344bfbbfb465cece5a5511616ee1c864555752be8d4fd5946'
BASE_SOURCE='e0b43ef70f312cc512861926109ebe99f41c964d'
SHARED_SOURCE='76aa47728192531ca9812f3e026057e0b174cb00'
HOME_SHA='15b948d12b32548762858a3e9aed7f906da19283423c997e48fa6bf2f7a2332f'
RETURN_SHA='cfd7de71d1949e415ba6662862feba4733e384258670ec73760425436d3fcde1'
VERSION='1.2.0'
IMAGE='T-Watch-1.2.0-Shared-Home-0.15.0-full-0x0.bin'
APP=(0x10000,0x270000);BOOTFS=(0x2f0000,0x800000);BANK=(0xff2000,0xff4000)
PRESERVED=((0,APP[0]),(APP[1],BOOTFS[0]),(BOOTFS[1],BANK[0]),(BANK[1],0x1000000))

def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def save_store(root,store):
    for name,raw in store.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
def check_native_bytes(firmware,elf):
    require(len(firmware)>208 and len(firmware)<=APP[1]-APP[0] and firmware[0]==0xe9 and struct.unpack_from('<H',firmware,12)[0]==9,'Invalid native ESP32-S3 image')
    require(firmware[23]==1 and hashlib.sha256(firmware[:-32]).digest()==firmware[-32:],'Native appended SHA mismatch')
    require(firmware[32:36]==b'\x32\x54\xcd\xab' and firmware[176:208]==hashlib.sha256(elf).digest(),'Native BIN does not correspond to its ELF')
    offset=24;checksum=0xef
    for _ in range(firmware[1]):
        require(offset+8<=len(firmware)-32,'Truncated native segment header')
        _,size=struct.unpack_from('<II',firmware,offset);offset+=8
        require(size<=len(firmware)-32-offset,'Truncated native segment')
        for byte in firmware[offset:offset+size]:checksum^=byte
        offset+=size
    end=(offset+16)//16*16-1
    require(end+1+32==len(firmware) and firmware[end]==checksum,'Native segment checksum/extent mismatch')

def rebind(store,firmware,revision):
    result=dict(store);cohort=json.loads(store['cohort.json'])
    require(cohort['version']=='1.1.17' and cohort['source_revision']==BASE_SOURCE and cohort['product']=='twatch-s3' and cohort['layout']=='riscrte-paired-appdata-v2','Wrong predecessor cohort')
    cohort.update(version=VERSION,source_revision=revision,runtime_version='0.3.2',firmware_size=len(firmware),firmware_sha256=sha(firmware))
    result['cohort.json']=encoded(cohort);return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['baseline-image','shared-source','shared-apps','generic-power','runtime','native','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source-revision',help='Exact published device commit for an offline source archive')
    a=parser.parse_args()
    require(not a.output.exists(),'Use a new output directory')
    revision=a.source_revision
    if (ROOT/'.git').exists():
        actual=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
        require(not revision or revision==actual,'Source revision differs from checkout')
        require(not subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=no'],text=True).strip(),'Device source changed')
        revision=actual
    require(bool(re.fullmatch('[0-9a-f]{40}',revision or '')),'Exact device source revision required')
    require((a.shared_apps/'COMMIT.txt').read_text().strip()==SHARED_SOURCE,'Wrong shared build revision')
    # Import only the selected public stager, not a device-local copy.
    sys.path.insert(0,str(a.shared_source.resolve()/'scripts'))
    from stage_product import app_bundle,stage
    apps,app_record=app_bundle(a.shared_apps)
    require(sha(apps['default.elf'])==HOME_SHA and sha(apps['clock.elf'])==RETURN_SHA,'Shared build is not the selected 0.15.0 binary pair')
    require(all(json.loads(apps[r+'.json'])['version']=='0.15.0' for r in ['default','clock']),'Wrong shared role versions')
    profile=json.loads((ROOT/'profiles/shared-home.json').read_bytes());services={}
    service_record=json.loads((a.generic_power/'build.json').read_bytes())
    for selected in profile['services']:
        role=selected['artifact'];record=service_record['providers'][role]
        for name in ['driver.elf','manifest.json']:services[role+'/'+name]=(a.generic_power/role/name).read_bytes()
        require(sha(services[role+'/driver.elf'])==record['sha256'] and len(services[role+'/driver.elf'])==record['bytes'],'Generic service receipt mismatch')
    previous=a.baseline_image.read_bytes()
    require(len(previous)==0x1000000 and sha(previous)==BASE_SHA,'Not delivered T-Watch 1.1.17')
    old=read_image(previous[slice(*BOOTFS)],BOOTFS[1]-BOOTFS[0]);boot=json.loads(old['boot.json'])
    require(len(old)==113 and len(boot['app_capabilities'])==25 and len(boot['drivers'])==31,'Incorrect complete baseline inventory')
    firmware=(a.native/'firmware.bin').read_bytes();native_elf=(a.native/'firmware.elf').read_bytes()
    check_native_bytes(firmware,native_elf)
    for name,offset in [('bootloader.bin',0),('partitions.bin',0x8000)]:
        raw=(a.native/name).read_bytes();require(raw==previous[offset:offset+len(raw)],'Native partition/bootloader differs from the retained layout')
    staged,staging=stage(old,apps,services,profile,provider_capacity=40)
    new=rebind(staged,firmware,revision)
    require(len(new)==119 and len(json.loads(new['boot.json'])['drivers'])==34,'Incomplete universal composition')
    image,packing=ordered_build(new,build)
    sys.path.insert(0,str(a.runtime.resolve()/'scripts'))
    from paired_bank_images import initial_bank_state,parse_record
    result=bytearray(previous)
    result[slice(*APP)]=b'\xff'*(APP[1]-APP[0]);result[APP[0]:APP[0]+len(firmware)]=firmware
    result[slice(*BOOTFS)]=image;result[slice(*BANK)]=initial_bank_state(firmware,image,True)
    for begin,end in PRESERVED:require(result[begin:end]==previous[begin:end],'Unrelated flash region changed')
    decoded=read_image(result[slice(*BOOTFS)],len(image));require(decoded==new,'Merged SPIFFS readback differs')
    state=result[slice(*BANK)];bank=parse_record(state[:96],True)
    require(bank[2]==0 and bank[3]==len(firmware) and bank[6]==hashlib.sha256(firmware).digest() and bank[7]==hashlib.sha256(image).digest() and state[96:]==b'\xff'*(8192-96),'Paired native/store binding mismatch')
    a.output.mkdir(parents=True);proofdir=a.output/'evidence';proofdir.mkdir()
    save_store(a.output/'store',new)
    proof={'product':VERSION,'shared_home':'0.15.0','source_revision':revision,'runtime_source':RUNTIME,'shared_source':SHARED_SOURCE,'baseline_sha256':BASE_SHA,'image_sha256':sha(result),'image_bytes':len(result),'initial_image_erases_data':True,'hardware_verified':False,'preserved_flash_ranges':PRESERVED,'staging':staging,'packing':packing,'native_elf_sha256':sha(native_elf),'native_bin_sha256':sha(firmware),'changed_original_store_files':sorted(n for n in old if old[n]!=new[n]),'new_store_files':sorted(set(new)-set(old)),'shared_app_record':app_record,'generic_service_record':service_record}
    for sanitize in [False,True]:
        label='sanitized' if sanitize else 'normal';harness=proofdir/label/'admit'
        native_proof=compile_harness(a.runtime,native_elf,a.native/'universal-native.ini',harness,sanitize)
        admission=admit(harness,old,decoded);require(admission['elf_count']==58,'Incomplete ELF admission')
        cases={}
        mutations={'missing-power-provider':lambda d:d.pop('power-sleep/manifest.json'),'corrupt-home':lambda d:d.__setitem__('default.elf',b'invalid ELF'),'corrupt-return':lambda d:d.__setitem__('clock.elf',b'invalid ELF')}
        for name,mutate in mutations.items():
            invalid=dict(new);mutate(invalid);cases[name]=admit(harness,old,invalid,False)
        proof[label]={'native':native_proof,'admission':admission,'negative_cases':cases}
    # Publish the BIN only after complete normal/sanitized native/graph admission.
    (a.output/IMAGE).write_bytes(result)
    (proofdir/'build.json').write_bytes(encoded(proof))
    (a.output/'SHA256SUMS.txt').write_text(sha(result)+'  '+IMAGE+'\n')
    print(json.dumps({k:proof[k] for k in ['product','shared_home','image_sha256','image_bytes','changed_original_store_files','new_store_files']},indent=2))
    print('All 25 apps / 34 providers / 58 ELFs admitted normally and with ASan/UBSan; physical test pending.')
if __name__=='__main__':main()

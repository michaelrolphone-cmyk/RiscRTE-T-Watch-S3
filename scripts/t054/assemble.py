#!/usr/bin/env python3
"""Compose the Watch NVS profile over exact cumulative 1.1.31; no device access."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
p=argparse.ArgumentParser()
for n in ('baseline','home','components','runtime','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();root=Path(__file__).resolve().parents[2];sys.path[:0]=[str(a.runtime.resolve()/'scripts'),str(root/'scripts')]
from spiffs_image import read_image
from paired_bank_images import initial_bank_state,parse_record
import current_bootfs
sha=lambda b:hashlib.sha256(b).hexdigest();enc=lambda x:(json.dumps(x,separators=(',',':'))+'\n').encode()
raw=a.baseline.read_bytes();expected='5895c631a9e1181de86ad14a0e7cf95b409de04c30a9d45da12b50d456189b67';assert sha(raw)==expected and len(raw)==0x1000000
size=0x550000;before=read_image(raw[0x2f0000:0x840000],size);assert current_bootfs.build(before,size=size)[0]==raw[0x2f0000:0x840000];store=dict(before)
home=json.loads((a.home/'build.json').read_text());assert home['preferences']=='nvs';assert not any('ATOMIC' in f for f in home['artifacts']['default']['defines'])
for name,source in [('default',a.home/'default.elf'),('settings',a.components/'settings.elf'),('springboard',a.components/'springboard.elf')]:
 data=source.read_bytes();assert b'storage.key-value.atomic\0' not in data;assert data!=before[name+'.elf'];store[name+'.elf']=data
 manifest=json.loads(before[name+'.json']);assert all(r['capability']!='storage.key-value.atomic' for r in manifest['requires']);v=manifest['version'].split('.');v[-1]=str(int(v[-1])+1);manifest['version']='.'.join(v);store[name+'.json']=enc(manifest)
head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip();cohort=json.loads(before['cohort.json']);assert cohort['version']=='1.1.31';cohort.update(version='1.1.32',source_revision=head);store['cohort.json']=enc(cohort)
image,packing=current_bootfs.build(store,size=size);assert current_bootfs.build(store,size=size)[0]==image and read_image(image,size)==store
fw=raw[0x10000:0x10000+cohort['firmware_size']];assert sha(fw)==cohort['firmware_sha256'];state=initial_bank_state(fw,image,True,True);parse_record(state[:96],True,True)
full=bytearray(raw);full[0x2f0000:0x840000]=image;full[0xff2000:0xff2000+len(state)]=state
assert full[:0x2f0000]==raw[:0x2f0000] and full[0x840000:0xff2000]==raw[0x840000:0xff2000] and full[0xff3000:]==raw[0xff3000:]
changed=sorted(n for n in store if store[n]!=before[n]);assert changed==sorted(['default.elf','default.json','settings.elf','settings.json','springboard.elf','springboard.json','cohort.json'])
out=a.output;out.mkdir(parents=True,exist_ok=True);filename='TWatch-1.1.32-T054-Preferences-factory-erases-data-0x0.bin';(out/filename).write_bytes(full)
for n,b in store.items():f=out/'store'/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
proof={'file':filename,'version':'1.1.32','image_sha256':sha(full),'baseline_sha256':expected,'product_commit':head,'runtime_commit':'26a54ff7769f7c9072a2a133790cd293b72abcba','native_sha256':sha(fw),'native_unchanged':True,'bootloader_partitions_unchanged':True,'settings_partitions_unchanged':True,'boot_and_grants_unchanged':True,'all_other_store_files_unchanged':True,'changed_store_files':changed,'storage_profile':'existing synchronous internal NVS namespaces; no atomic service required','packing':packing,'hardware_tested':False,'inventory':{n:sha(b) for n,b in store.items()}}
(out/'assembly-report.json').write_text(json.dumps(proof,indent=2)+'\n');print(filename,sha(full),packing)

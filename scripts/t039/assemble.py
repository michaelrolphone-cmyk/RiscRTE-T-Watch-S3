#!/usr/bin/env python3
"""Compose T039 from exact cumulative T046 images, preserving native firmware."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,zipfile
p=argparse.ArgumentParser()
for n in ['baseline','buttons','hid','runtime','watch-tools','product-repo','output']:p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--product',choices=['watch','wave','x4'],required=True);p.add_argument('--previous-sd',type=Path)
a=p.parse_args();sys.path[:0]=[str(a.runtime/'scripts'),str(a.watch_tools/'scripts')]
from spiffs_image import read_image
from paired_bank_images import initial_bank_state,parse_record
import current_bootfs
sha=lambda b:hashlib.sha256(b).hexdigest()
encode=lambda o:(json.dumps(o,separators=(',',':'))+'\n').encode()
spec={
 'watch':('TWatch','1.1.30','1.1.31','49ed4a8dd160950cfa23518093ce90968c2ac4509f28645ef505f57f1491438a'),
 'wave':('Waveshare','0.1.33','0.1.34','fe68fc15ff5e10edaa89d6d12cec10017fd968a0c868cd8a3d279473dc88aec6'),
 'x4':('X4','0.1.116','0.1.117','f08b1a9c956ebdb6a26bed066449c7980f325983acd8f85abdc961fbf459e667')}
name,oldversion,version,expected=spec[a.product];raw=a.baseline.read_bytes();assert sha(raw)==expected
size=0x510000 if a.product=='x4' else 0x550000
before=read_image(raw[0x2f0000:0x2f0000+size],size);store=dict(before)
packed,_=current_bootfs.build(before,size=size);assert packed==raw[0x2f0000:0x2f0000+size]
receipt=json.loads((a.buttons/'build.json').read_text());binary=(a.buttons/'ble_buttons.elf').read_bytes();assert sha(binary)==receipt['sha256']
meta=json.loads(before['ble_buttons.json']);assert meta['version']==('0.1.25' if a.product=='x4' else '0.1.23');meta['version']='0.1.26';store['ble_buttons.json']=encode(meta)
if a.product!='x4':store['ble_buttons.elf']=binary
hid=(a.hid/'driver.elf').read_bytes();assert sha(hid)=='6290d9cdfae051b9f2f2c83060f1c4000a62f727d47b680c67cd77b0d9e0c555'
key='hid' if a.product=='x4' else 'ble-hid'
hm=json.loads(before[key+'/manifest.json'])
if a.product=='wave':
 assert hm['version']=='0.1.2';new=json.loads((a.hid/'manifest.json').read_text());assert hm['id']==new['id'] and hm['requires']==new['requires'] and hm['provides']==new['provides'];hm['version']='0.1.4';store[key+'/manifest.json']=encode(hm);store[key+'/driver.elf']=hid
else:assert hm['version']=='0.1.4' and before[key+'/driver.elf']==hid
source=subprocess.check_output(['git','-C',str(a.product_repo),'rev-parse','HEAD'],text=True).strip();cohort=json.loads(before['cohort.json']);assert cohort['version']==oldversion;cohort.update(version=version,source_revision=source);store['cohort.json']=encode(cohort)
changed=sorted(n for n in store if store[n]!=before[n]);expected_changes=['ble_buttons.json','cohort.json']
if a.product!='x4':expected_changes+=['ble_buttons.elf']
if a.product=='wave':expected_changes+=['ble-hid/driver.elf','ble-hid/manifest.json']
assert changed==sorted(expected_changes)
image,packing=current_bootfs.build(store,size=size);repeat,_=current_bootfs.build(store,size=size);assert image==repeat and read_image(image,size)==store
fw=raw[0x10000:0x10000+cohort['firmware_size']];assert sha(fw)==cohort['firmware_sha256'];state=initial_bank_state(fw,image,True) if a.product=='x4' else initial_bank_state(fw,image,True,True);parse_record(state[:96],True) if a.product=='x4' else parse_record(state[:96],True,True)
full=bytearray(raw);full[0x2f0000:0x2f0000+size]=image;full[0xff2000:0xff2000+len(state)]=state
assert full[:0x2f0000]==raw[:0x2f0000] and full[0x2f0000+size:0xff2000]==raw[0x2f0000+size:0xff2000] and full[0xff3000:]==raw[0xff3000:]
out=a.output;out.mkdir(parents=True,exist_ok=True);filename=f'{name}-{version}-T039-BLE-Buttons-factory-erases-data-0x0.bin';(out/filename).write_bytes(full)
for n,b in store.items():f=out/'store'/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
proof={'file':filename,'version':version,'image_sha256':sha(full),'baseline_sha256':sha(raw),'source_revision':source,'changed_store_files':changed,'native_unchanged':True,'boot_and_grants_unchanged':True,'home_unchanged':True,'settings_partitions_unchanged':True,'baseline_store_reproduced':True,'packing_repeated_identically':True,'hardware_tested':False,'packing':packing,'buttons':receipt,'hid_sha256':sha(hid),'inventory':{n:sha(b) for n,b in store.items()}}
if a.product=='x4':
 assert a.previous_sd and sha(a.previous_sd.read_bytes())=='ad6aeed029d4c08ecdb0c0c75b8bb39dec413f08a04f734abc1454ec83a957c6'
 with zipfile.ZipFile(a.previous_sd) as z:previous={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
 sd=dict(previous);path='Apps/ble_buttons/ble_buttons.elf'
 boot=json.loads(before['boot.json']);row=next(r for r in boot['app_capabilities'] if r['manifest']=='ble_buttons.json');assert row['image_source']['path']==path
 assert path not in previous;sd[path]=binary
 sd['Apps/ble_buttons/manifest.json']=store['ble_buttons.json']
 sdname=f'X4-{version}-Cumulative-Changed-SD-Keep-Existing.zip'
 with zipfile.ZipFile(out/sdname,'w',zipfile.ZIP_DEFLATED) as z:
  for n,b in sorted(sd.items()):item=zipfile.ZipInfo(n,(2026,10,14,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;z.writestr(item,b)
 assert all(sd[n]==b for n,b in previous.items() if n!=path);proof.update(sd_file=sdname,sd_sha256=sha((out/sdname).read_bytes()),sd_inventory={n:sha(b) for n,b in sd.items()},added_overlay_files=[path,'Apps/ble_buttons/manifest.json'],other_sd_files_unchanged=True)
(out/'assembly-report.json').write_text(json.dumps(proof,indent=2)+'\n');print(name,version,sha(full),packing)

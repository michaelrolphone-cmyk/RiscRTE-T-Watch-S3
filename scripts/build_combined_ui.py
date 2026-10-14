#!/usr/bin/env python3
"""Compose the combined UI on a checksum-pinned Spectrum factory baseline."""
from pathlib import Path
import argparse,hashlib,json,sys,subprocess
p=argparse.ArgumentParser(description=__doc__)
for n in ('baseline','runtime','home','launcher','watch_product','output'):p.add_argument('--'+n.replace('_','-'),type=Path,required=True)
p.add_argument('--product',choices=['watch','waveshare'],required=True)
p.add_argument('--product-revision',required=True)
a=p.parse_args();sha=lambda b:hashlib.sha256(b).hexdigest()
sys.path.insert(0,str(a.runtime/'scripts'));from spiffs_image import read_image;from paired_bank_images import initial_bank_state,parse_record
sys.path.insert(0,str(a.watch_product/'scripts'));import current_bootfs
rows={'watch':('1.1.26','T-Watch-S3','e51161e0947d0d2507e33e789fcf0d0a8ae3c056cea6e9521b26ea830f944aa3','watch-expanded'),'waveshare':('0.1.25','Waveshare','79af497a35f9d1d1c512c6481f223bd285ac77e7f7cb41a7b7bdc446df2d7f77','esp32s3-16mb-waveshare-expanded')}
version,prefix,baseline_sha,env=rows[a.product];raw=a.baseline.read_bytes();assert len(raw)==0x1000000 and sha(raw)==baseline_sha
native=a.runtime/'.pio/build'/env;firmware=(native/'firmware.bin').read_bytes();assert len(firmware)<=0x260000
partitions=(native/'partitions.bin').read_bytes();assert raw[0x8000:0x8000+len(partitions)]==partitions
runtime_revision=subprocess.check_output(['git','-C',str(a.runtime),'rev-parse','HEAD'],text=True).strip();assert ('RTE_SOURCE='+runtime_revision).encode() in firmware
store=read_image(raw[0x2f0000:0x840000],0x550000);before=dict(store)
for name in ('default','clock'):store[name+'.elf']=(a.home/(name+'.elf')).read_bytes()
store['springboard.elf']=a.launcher.read_bytes()
boot=json.loads(store['boot.json'])
for name in ('default','springboard','bringup','file_browser'):
 m=json.loads(store[name+'.json'])
 if name in ('default','springboard','bringup'):m['launcher_visible']=False
 if name=='file_browser':m.update(display_name='Files',icon='solid:f07c')
 if name in ('default','springboard'):
  if name=='default':m['version']='0.15.2'
  else:m['version']='1.7.10'
  policy=next(row for row in boot['app_capabilities'] if row['manifest']==name+'.json')
  declaration={'capability':'storage.shared-data','api':1}
  if declaration not in m['requires']:m['requires'].append(declaration)
  for instance in (2,3,4):
   grant={**declaration,'instance_id':instance,'file':'context-rules.ctx' if instance==4 else 'context-fingerprints.cfp'}
   if grant not in policy['grants']:policy['grants'].append(grant)
  assert len(policy['grants'])<=32
 store[name+'.json']=(json.dumps(m,sort_keys=True,separators=(',',':'))+'\n').encode()
store['boot.json']=(json.dumps(boot,sort_keys=True,separators=(',',':'))+'\n').encode()
cohort=json.loads(store['cohort.json']);cohort.update(version=version,source_revision=a.product_revision,firmware_size=len(firmware),firmware_sha256=sha(firmware))
store['cohort.json']=(json.dumps(cohort,indent=2)+'\n').encode()
# Existing Spectrum corrections, providers and all other apps remain exact.
allowed={'default.elf','clock.elf','springboard.elf','default.json','springboard.json','bringup.json','file_browser.json','boot.json','cohort.json'}
changed=sorted(n for n in store if store[n]!=before[n]);assert set(changed)<=allowed
assert json.loads(before['boot.json'])['drivers']==boot['drivers']
a.output.mkdir(parents=True,exist_ok=True);root=a.output/(a.product+'-store');root.mkdir(exist_ok=True)
for n,b in store.items():q=root/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b)
image,packing=current_bootfs.build(store,size=0x550000);assert read_image(image,0x550000)==store
state=initial_bank_state(firmware,image,True,True);parse_record(state[:96],True,True)
full=bytearray(raw);full[0x10000:0x270000]=firmware+b'\xff'*(0x260000-len(firmware));full[0x2f0000:0x840000]=image;full[0xff2000:0xff2000+len(state)]=state
assert full[:0x10000]==raw[:0x10000] and full[0x270000:0x2f0000]==raw[0x270000:0x2f0000] and full[0x840000:0xff2000]==raw[0x840000:0xff2000]
name=f'{prefix}-{version}-combined-ui-spectrum-factory-erases-data-0x0.bin';(a.output/name).write_bytes(full)
proof={'product':a.product,'version':version,'file':name,'bytes':len(full),'sha256':sha(full),'baseline_sha256':baseline_sha,'runtime_revision':runtime_revision,'firmware_sha256':sha(firmware),'firmware_bytes':len(firmware),'product_revision':a.product_revision,'changed_store_files':changed,'packing':packing,'partition_table_unchanged':True,'app_data_region_unchanged':True,'spectrum_unchanged':True,'hardware_verified':False}
(a.output/(a.product+'-verification.json')).write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))

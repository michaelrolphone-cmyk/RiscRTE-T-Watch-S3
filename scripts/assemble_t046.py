#!/usr/bin/env python3
"""T046 exact-baseline component composition; never compiles native firmware."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,zipfile
p=argparse.ArgumentParser()
for n in ['baseline','components','runtime','watch-tools','product-repo','output']:p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--product',choices=['watch','wave','x4'],required=True);p.add_argument('--previous-sd',type=Path);p.add_argument('--watch-store',type=Path)
a=p.parse_args();sys.path[:0]=[str(a.runtime/'scripts'),str(a.watch_tools/'scripts')]
from spiffs_image import read_image
from paired_bank_images import initial_bank_state,parse_record
import current_bootfs
sha=lambda b:hashlib.sha256(b).hexdigest()
encode=lambda o:(json.dumps(o,separators=(',',':'))+'\n').encode()
spec={
 'watch':('TWatch','1.1.29','1.1.30','5426b4da443c243f11c80ec839d4d560497a6b9616bc78fe1544d7dc63cf3e9a'),
 'wave':('Waveshare','0.1.32','0.1.33','b67a3d50dfbd55f5177e43035452f14d2faa08fe0743fbbaa5921e0c1a31b276'),
 'x4':('X4','0.1.115','0.1.116','fb89e6d1457968f81e78dfb6cede94d8277ce47d4c9fb7bcbc40c0597a722251')}
name,oldversion,version,expected=spec[a.product];raw=a.baseline.read_bytes();assert sha(raw)==expected
size=0x510000 if a.product=='x4' else 0x550000
before=read_image(raw[0x2f0000:0x2f0000+size],size);store=dict(before)
packed,_=current_bootfs.build(before,size=size);assert packed==raw[0x2f0000:0x2f0000+size]
boot=json.loads(before['boot.json']);oldboot=json.loads(before['boot.json']);sd={};paths={};component_evidence={}
for target,source in [('ui-scene','presentation/scene-host'),('ui-text' if a.product=='x4' else 'text-input','text-input-host')]:
 d=a.components/source;binary=(d/'driver.elf').read_bytes();receipt=json.loads((d/'build.json').read_text());assert sha(binary)==receipt['sha256']
 meta=json.loads(before[target+'/manifest.json']);newmeta=json.loads((d/'manifest.json').read_text())
 assert meta['id']==newmeta['id'] and meta['provides']==newmeta['provides']
 meta['version']=newmeta['version'];store[target+'/manifest.json']=encode(meta);store[target+'/driver.elf']=binary
 component_evidence[target]=receipt
 if a.product=='x4':
  row=next(r for r in boot['drivers'] if r['manifest']==target+'/manifest.json');oldpath=row['image_source']['path'];newpath='Drivers/'+meta['id']+'/image-'+sha(binary)+'.elf';row['image_source']['path']=newpath;paths[target]=(oldpath,newpath);sd[newpath]=binary
if a.product=='wave':
 assert a.watch_store
 # These exact Watch shared-service callers were already delivered on Wave.
 # Correct only their missing declared dependency and app authority.
 for app,ver in [('ble_scanner','0.2.5'),('points_in_time','0.5.4')]:
  assert before[app+'.elf']==(a.watch_store/(app+'.elf')).read_bytes()
  old=json.loads(before[app+'.json']);watch=json.loads((a.watch_store/(app+'.json')).read_text());req={'api':1,'capability':'ui.text-input'}
  assert req in watch['requires'] and req not in old['requires'];old['requires'].append(req);old['version']=ver;store[app+'.json']=encode(old)
  row=next(r for r in boot['app_capabilities'] if r['manifest']==app+'.json');assert not any(g['capability']=='ui.text-input' for g in row['grants']);row['grants'].append({**req,'instance_id':0})
if boot!=oldboot:store['boot.json']=encode(boot)
# Verify boot differs only at the two explicitly listed repairs / SD paths.
restored=json.loads(json.dumps(boot))
for target,(oldpath,_) in paths.items():next(r for r in restored['drivers'] if r['manifest']==target+'/manifest.json')['image_source']['path']=oldpath
if a.product=='wave':
 for app in ['ble_scanner','points_in_time']:
  row=next(r for r in restored['app_capabilities'] if r['manifest']==app+'.json');row['grants']=[g for g in row['grants'] if g['capability']!='ui.text-input']
assert restored==oldboot
source=subprocess.check_output(['git','-C',str(a.product_repo),'rev-parse','HEAD'],text=True).strip();cohort=json.loads(before['cohort.json']);assert cohort['version']==oldversion;cohort.update(version=version,source_revision=source);store['cohort.json']=encode(cohort)
changed=sorted(n for n in store if store[n]!=before[n]);expected_changes=['cohort.json','ui-scene/driver.elf','ui-scene/manifest.json',('ui-text' if a.product=='x4' else 'text-input')+'/driver.elf',('ui-text' if a.product=='x4' else 'text-input')+'/manifest.json']
if a.product!='watch':expected_changes+=['boot.json']
if a.product=='wave':expected_changes+=['ble_scanner.json','points_in_time.json']
assert changed==sorted(expected_changes)
image,packing=current_bootfs.build(store,size=size);repeat,_=current_bootfs.build(store,size=size);assert image==repeat and read_image(image,size)==store
fw=raw[0x10000:0x10000+cohort['firmware_size']];assert sha(fw)==cohort['firmware_sha256'];state=initial_bank_state(fw,image,True) if a.product=='x4' else initial_bank_state(fw,image,True,True);parse_record(state[:96],True) if a.product=='x4' else parse_record(state[:96],True,True)
full=bytearray(raw);full[0x2f0000:0x2f0000+size]=image;full[0xff2000:0xff2000+len(state)]=state
assert full[:0x2f0000]==raw[:0x2f0000] and full[0x2f0000+size:0xff2000]==raw[0x2f0000+size:0xff2000] and full[0xff3000:]==raw[0xff3000:]
out=a.output;out.mkdir(parents=True,exist_ok=True);filename=f'{name}-{version}-T046-Shared-Keyboard-factory-erases-data-0x0.bin';(out/filename).write_bytes(full)
for n,b in store.items():f=out/'store'/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
proof={'file':filename,'version':version,'image_sha256':sha(full),'baseline_sha256':sha(raw),'source_revision':source,'changed_store_files':changed,'native_unchanged':True,'all_application_executables_unchanged':True,'home_unchanged':True,'baseline_store_reproduced':True,'packing_repeated_identically':True,'hardware_tested':False,'packing':packing,'components':component_evidence,'inventory':{n:sha(b) for n,b in store.items()}}
if a.product=='x4':
 assert a.previous_sd
 with zipfile.ZipFile(a.previous_sd) as z:previous={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
 sd={**previous,**sd};sdname=f'X4-{version}-Cumulative-Changed-SD-Keep-Existing.zip'
 with zipfile.ZipFile(out/sdname,'w',zipfile.ZIP_DEFLATED) as z:
  for n,b in sorted(sd.items()):item=zipfile.ZipInfo(n,(2026,10,14,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;z.writestr(item,b)
 assert all(sd[n]==b for n,b in previous.items());proof.update(sd_file=sdname,sd_sha256=sha((out/sdname).read_bytes()),sd_inventory={n:sha(b) for n,b in sd.items()},existing_sd_files_unchanged=True)
(out/'assembly-report.json').write_text(json.dumps(proof,indent=2)+'\n');print(name,version,sha(full),packing)

from pathlib import Path
import argparse,json,hashlib,subprocess,sys
p=argparse.ArgumentParser()
for n in ['product','artifacts','runtime','watch-product','sdr-store','output']:p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();root=a.product.resolve();lock=json.loads((root/'integration/ordered-input/sources.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
sys.path.insert(0,str(a.runtime/'scripts'));from spiffs_image import read_image
from paired_bank_images import initial_bank_state,parse_record
sys.path.insert(0,str(a.watch_product/'scripts'));import current_bootfs
raw=Path(lock['baseline']).read_bytes();assert sha(raw)==lock['baseline_sha256'];store=read_image(raw[0x2f0000:0x840000],0x550000);before=dict(store)
versions={}
for name,proof in lock['apps'].items():
 elf=(a.artifacts/(name+'.elf')).read_bytes();assert sha(elf)==proof['sha256'];assert name+'.elf' in store
 m=json.loads(store[name+'.json']);v=m['version'].split('.');v[-1]=str(int(v[-1])+1);m['version']='.'.join(v) if name!='springboard' else lock['springboard_version']
 if name=='springboard':
  # Preserve the exact restored launcher's capability contract for both native displays.
  m=json.loads((a.sdr_store/'springboard.json').read_text());m['version']=lock['springboard_version']
 store[name+'.elf']=elf;store[name+'.json']=(json.dumps(m,sort_keys=True,separators=(',',':'))+'\n').encode();versions[name]=m['version']
for name in ['audio_spectrum','waterfall']:
 for ext in ['elf','json']:
  n=name+'.'+ext
  if a.product.name.startswith('TWatch'):store[n]=(a.sdr_store/n).read_bytes()
  else:assert store[n]==(a.sdr_store/n).read_bytes()
 versions[name]=json.loads(store[name+'.json'])['version']
cohort=json.loads(store['cohort.json']);cohort['version']=lock['version'];cohort['source_revision']=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip();store['cohort.json']=(json.dumps(cohort,indent=2)+'\n').encode()
changed=sorted(n for n in store if store[n]!=before[n]);allow={n+'.'+e for n in [*lock['apps'],'audio_spectrum','waterfall'] for e in ['elf','json']}|{'cohort.json'};assert set(changed)<=allow
for n in ['default.elf','clock.elf','boot.json']:assert store[n]==before[n]
fw=raw[0x10000:0x10000+cohort['firmware_size']];assert sha(fw)==cohort['firmware_sha256']
image,packing=current_bootfs.build(store,size=0x550000);assert read_image(image,0x550000)==store
state=initial_bank_state(fw,image,True,True);parse_record(state[:96],True,True)
full=bytearray(raw);full[0x2f0000:0x840000]=image;full[0xff2000:0xff2000+len(state)]=state
assert full[:0x2f0000]==raw[:0x2f0000] and full[0x840000:0xff2000]==raw[0x840000:0xff2000] and full[0xff2000+len(state):]==raw[0xff2000+len(state):]
a.output.mkdir(parents=True,exist_ok=True)
for n,b in store.items():f=a.output/'store'/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
name=lock['product']+'-'+lock['version']+'-ordered-input-factory-erases-data-0x0.bin';(a.output/name).write_bytes(full)
proof={'version':lock['version'],'file':name,'bytes':len(full),'sha256':sha(full),'source_revision':cohort['source_revision'],'changed_files':changed,'component_versions':versions,'packing':packing,'native_firmware_unchanged':True,'home_clock_boot_unchanged':True,'hardware_verified':False,'inventory':{n:sha(b) for n,b in store.items()}}
(a.output/'verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:v for k,v in proof.items() if k!='inventory'},indent=2))

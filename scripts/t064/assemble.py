"""Compose only Home and its explicit grants over each exact cumulative baseline."""
from pathlib import Path
import sys,json,hashlib,subprocess,argparse
p=argparse.ArgumentParser();p.add_argument('device',choices=['x4','wave','watch']);a=p.parse_args();root=Path.cwd();sys.path[:0]=[str(root/'Runtime-wave-t054/scripts'),str(root/'Watch-t054/scripts')]
from spiffs_image import read_image
from paired_bank_images import initial_bank_state,parse_record
import current_bootfs
sha=lambda b:hashlib.sha256(b).hexdigest();enc=lambda d:(json.dumps(d,separators=(',',':'))+'\n').encode()
config={
'x4':('t060-build/x4','a70fd9b7b93193ab6702e8991176a608d4f1f6f3ef96fe29cd7c257ac81f695d','0.1.120','0.1.121','X4','X4-t054',0x510000,'t064-build/x4-home/home'),
'wave':('t063-startup/wave','ec294d37dcfaaf5fdac8ead5ded52e29a8eafa408de00d48d627bb284e564a32','0.1.37','0.1.38','Waveshare','Wave-t054',0x550000,'t064-build/wave-home'),
'watch':('t054-build/watch','cc37711c0df356ad28bf79b9e8a273111aa1239999b22f8780c63fb228fc0646','1.1.32','1.1.33','TWatch','Watch-t054',0x550000,'t064-build/watch-home')}
folder,expected,old,new,label,repo,size,home=config[a.device];baseline=next((root/folder).glob('*factory*bin'));raw=baseline.read_bytes();assert sha(raw)==expected
before=read_image(raw[0x2f0000:0x2f0000+size],size);store=dict(before);h=root/home
store['default.elf']=(h/'default.elf').read_bytes();manifest=json.loads(before['default.json']);manifest['version']='0.4.19' if a.device=='x4' else '0.15.4'
assert b'crash-spool.bin' in store['default.elf'];boot=json.loads(before['boot.json']);entry=next(x for x in boot['app_capabilities'] if x['manifest']=='default.json')
if a.device!='x4':
 assert all(x['capability']!='storage.app-data' for x in entry['grants'])
 entry['grants'].append(dict(capability='storage.app-data',api=1,instance_id=61));manifest['requires'].append(dict(capability='storage.app-data',api=1))
 if a.device=='wave':
  entry['grants'].append(dict(capability='storage.volume',api=1,instance_id=12));manifest['requires'].append(dict(capability='storage.volume',api=1))
 store['boot.json']=enc(boot)
store['default.json']=enc(manifest)
cohort=json.loads(before['cohort.json']);assert cohort['version']==old;cohort['version']=new;cohort['source_revision']=subprocess.check_output(['git','-C',repo,'rev-parse','HEAD'],text=True).strip();store['cohort.json']=enc(cohort)
image,packing=current_bootfs.build(store,size=size);assert read_image(image,size)==store
fw=raw[0x10000:0x10000+cohort['firmware_size']];assert sha(fw)==cohort['firmware_sha256'];state=initial_bank_state(fw,image,True,a.device!='x4');parse_record(state[:96],True,a.device!='x4')
full=bytearray(raw);full[0x2f0000:0x2f0000+size]=image;full[0xff2000:0xff2000+len(state)]=state
assert full[:0x2f0000]==raw[:0x2f0000] and full[0x2f0000+size:0xff2000]==raw[0x2f0000+size:0xff2000] and full[0xff3000:]==raw[0xff3000:]
changed=sorted(k for k in store if store[k]!=before[k]);assert changed==sorted(['default.elf','default.json','cohort.json']+([] if a.device=='x4' else ['boot.json']))
out=root/'t064-build'/a.device;out.mkdir(exist_ok=True);name=f'{label}-{new}-T064-Crash-Reports-factory-erases-data-0x0.bin';(out/name).write_bytes(full)
for k,v in store.items():p=out/'store'/k;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v)
proof=dict(file=name,version=new,image_sha256=sha(full),baseline_sha256=expected,baseline_file=str(baseline),native_sha256=sha(fw),native_unchanged=True,all_other_store_files_unchanged=True,changed_store_files=changed,packing=packing,crash_namespace=62 if a.device=='x4' else 61,crash_sd_instance={'x4':9,'wave':12,'watch':None}[a.device],hardware_tested=False)
if a.device=='x4':
 sd=next((root/folder).glob('*Changed-SD*.zip'));proof.update(sd_file=str(sd),sd_sha256=sha(sd.read_bytes()),sd_unchanged=True)
(out/'assembly-report.json').write_text(json.dumps(proof,indent=2)+'\n');print(name,sha(full),packing['empty_blocks'])

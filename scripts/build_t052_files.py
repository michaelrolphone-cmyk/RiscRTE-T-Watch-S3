from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'Runtime-wave-t051/scripts'),str(R/'TWatch-input-product/scripts')]
from spiffs_image import read_image
from paired_bank_images import initial_bank_state,parse_record
import current_bootfs
sha=lambda b:hashlib.sha256(b).hexdigest()
products={'watch':('TWatch','1.1.29'),'waveshare':('Waveshare','0.1.31'),'x4':('X4','0.1.114')}
for key in sys.argv[1:]:
 product,version=products[key];base=R/'t051-product-build'/key;old=json.loads((base/'verification.json').read_text()) if key!='x4' else json.loads((base/'assembly-report.json').read_text())
 fname=old.get('file','X4-0.1.113-T051-WiFi-factory-erases-data-0x0.bin');raw=(base/fname).read_bytes();expected=old.get('sha256',old.get('image_sha256'));assert sha(raw)==expected
 size=0x510000 if key=='x4' else 0x550000;before=read_image(raw[0x2f0000:0x2f0000+size],size);store=dict(before);d=R/'t052-build'/key
 elf=(d/'file_browser.elf').read_bytes();build=json.loads((d/'build.json').read_text());assert sha(elf)==build['sha256'];store['file_browser.elf']=elf
 m=json.loads(store['file_browser.json']);m['version']='1.5.38';store['file_browser.json']=(json.dumps(m,separators=(',',':'))+'\n').encode()
 source=R/(product+'-input-product');head=subprocess.check_output(['git','-C',source,'rev-parse','HEAD'],text=True).strip()
 cohort=json.loads(store['cohort.json']);cohort.update(version=version,source_revision=head);store['cohort.json']=(json.dumps(cohort,indent=2)+'\n').encode()
 changed=sorted(n for n in store if store[n]!=before[n]);assert changed==['cohort.json','file_browser.elf','file_browser.json']
 fw=raw[0x10000:0x10000+cohort['firmware_size']];assert sha(fw)==cohort['firmware_sha256']
 image,packing=current_bootfs.build(store,size=size);assert read_image(image,size)==store
 state=initial_bank_state(fw,image,True,key!='x4');parse_record(state[:96],True,key!='x4')
 full=bytearray(raw);full[0x2f0000:0x2f0000+size]=image;full[0xff2000:0xff2000+len(state)]=state
 assert full[:0x2f0000]==raw[:0x2f0000] and full[0x2f0000+size:0xff2000]==raw[0x2f0000+size:0xff2000]
 name=f'{product}-{version}-T052-Mounted-Files-factory-erases-data-0x0.bin';(d/name).write_bytes(full)
 for n,b in store.items():p=d/'store'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 proof=dict(file=name,version=version,sha256=sha(full),source_revision=head,system_source='503565c',changed_files=changed,native_unchanged=True,boot_grants_unchanged=True,all_other_apps_unchanged=True,packing=packing,hardware_verified=False,inventory={n:sha(b) for n,b in store.items()})
 if key=='x4':
  sd='X4-0.1.114-Cumulative-Changed-SD-Keep-Existing.zip';shutil.copyfile(base/'X4-0.1.113-Cumulative-Changed-SD-Keep-Existing.zip',d/sd);proof['sd_file']=sd;proof['sd_sha256']=sha((d/sd).read_bytes())
 (d/'verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(key,name,proof['sha256'])

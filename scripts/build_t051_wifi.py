from pathlib import Path
import argparse,json,sys,hashlib,subprocess
p=argparse.ArgumentParser(description="Compose T051 Wi-Fi over the exact published 1.1.27 baseline")
for name in ('baseline','wifi','runtime','output'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();root=Path(__file__).resolve().parents[1];O=a.output;O.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(a.runtime/'scripts'));from spiffs_image import read_image
from paired_bank_images import initial_bank_state,parse_record
sys.path.insert(0,str(root/'scripts'));import current_bootfs
raw=a.baseline.read_bytes();sha=lambda b:hashlib.sha256(b).hexdigest();assert sha(raw)=='eed208ec72d8f1fe420fe1b37ef851eda70e776f0cde94e23f05918b1fe07725'
s=read_image(raw[0x2f0000:0x840000],0x550000);before=dict(s)
s['wifi_settings.elf']=a.wifi.read_bytes();assert sha(s['wifi_settings.elf'])=='0260a6d8c39ede4ed4b5aebc2220c93141b6db800c0aebab464404e313a5af2a'
m=json.loads(s['wifi_settings.json']);m['version']='1.1.30';boot=json.loads(s['boot.json']);row=next(r for r in boot['app_capabilities'] if r['manifest']=='wifi_settings.json')
for cap in ('ui.text-input','app.catalog'):
 need={'api':1,'capability':cap};grant={**need,'instance_id':0}
 if need not in m['requires']:m['requires'].append(need)
 if grant not in row['grants']:row['grants'].append(grant)
assert {'api':1,'capability':'storage.key-value','instance_id':6} in row['grants']
assert not any('atomic' in g['capability'] for g in row['grants'])
cohort=json.loads(s['cohort.json']);cohort['version']='1.1.28';cohort['source_revision']=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
for n,v in [('wifi_settings.json',m),('boot.json',boot),('cohort.json',cohort)]:s[n]=(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()
changed=sorted(n for n in s if s[n]!=before[n]);assert changed==['boot.json','cohort.json','wifi_settings.elf','wifi_settings.json']
image,packing=current_bootfs.build(s,size=0x550000);assert read_image(image,0x550000)==s
fw=raw[0x10000:0x10000+cohort['firmware_size']];assert sha(fw)==cohort['firmware_sha256'];state=initial_bank_state(fw,image,True,True);parse_record(state[:96],True,True)
full=bytearray(raw);full[0x2f0000:0x840000]=image;full[0xff2000:0xff2000+len(state)]=state
for n,b in s.items():p=O/'store'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
(O/'TWatch-1.1.28-T051-WiFi-factory-erases-data-0x0.bin').write_bytes(full)
p={'status':'qualified host candidate','source_revision':cohort['source_revision'],'file':'TWatch-1.1.28-T051-WiFi-factory-erases-data-0x0.bin','sha256':sha(full),'wifi_elf':sha(s['wifi_settings.elf']),'changed_files':changed,'native_unchanged':True,'all_other_apps_unchanged':True,'shared_keyboard_grant':True,'saved_networks_namespace':6,'storage':'internal native key-value','packing':packing}
(O/'verification.json').write_text(json.dumps(p,indent=2)+'\n');print(p)

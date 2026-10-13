from pathlib import Path
import json,hashlib,sys
sys.path.insert(0,'/tmp/twatch-shared-cohort-0121/scripts')
from read_only_spiffs import read_image
R=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
paths={'watch':next((R/'watch-assembly-final').glob('*.bin')),'waveshare':next((R/'waveshare-assembly-final').glob('*full*bin'))}
raw={k:p.read_bytes() for k,p in paths.items()}; stores={k:read_image(v[0x2f0000:0x840000],0x550000) for k,v in raw.items()}
base_paths={'watch':R/'baseline/T-Watch-S3-1.1.22-full-0x0.bin','waveshare':R.parent/'cumulative-rf-0121/final-assembly/Waveshare-0.1.21-expanded-updates-full-initial-erases-data-0x0.bin'}
cohort={};appbytes={};counts={};preserved={}
for k,s in stores.items():
 assert len(raw[k])==0x1000000
 boot=json.loads(s['boot.json']); cohort[k]=json.loads(s['cohort.json']); appbytes[k]={}
 for row in boot['app_capabilities']:
  m=json.loads(s[row['manifest']]);name=m['file_name'];source=row.get('image_source')
  appbytes[k][name]=(R/'staged-final/card'/source['path']).read_bytes() if source else s[name]
  assert len(row['grants'])<=32 and len(m['requires'])+len(m.get('optional',[]))<=32
 assert len(appbytes[k])==26 and boot['default_app']=='default.elf'
 assert next(x for x in boot['app_capabilities'] if x['manifest']=='default.json').get('image_source') is None
 base=base_paths[k].read_bytes();old=read_image(base[0x2f0000:0x840000],0x550000);b=json.loads(old['boot.json'])
 assert raw[k][0x270000:0x2f0000]==base[0x270000:0x2f0000]
 assert raw[k][0x8000:0x9000]==base[0x8000:0x9000]
 assert boot['drivers']==b['drivers'] and s['board.json']==old['board.json']
 for n,data in old.items():
  if '/' in n:assert s[n]==data,n
 counts[k]={'apps':26,'internal_elfs':sum(n.endswith('.elf') for n in s),'providers':len(boot['drivers'])}
 preserved[k]={'appdata_512KiB_sha256':sha(raw[k][0x270000:0x2f0000]),'partition_table_unchanged':True,'all_original_provider_bytes_and_policy_unchanged':True,'board_unchanged':True,'home_internal':True}
assert appbytes['watch']==appbytes['waveshare']
common={n:{'bytes':len(b),'sha256':sha(b)} for n,b in sorted(appbytes['watch'].items())}
for n,b in appbytes['watch'].items():assert b==(R/'staged-final/common-apps'/n).read_bytes()
wb=json.loads(stores['waveshare']['boot.json']);external=[r for r in wb['app_capabilities'] if 'image_source' in r]
assert len(external)==1 and external[0]['manifest']=='lora_messages.json' and external[0]['image_source']=={'volume_instance':12,'path':'Apps/lora_messages/lora_messages.elf'}
card={p.relative_to(R/'staged-final/card').as_posix():{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted((R/'staged-final/card').rglob('*')) if p.is_file()}
result={'schema':1,'status':'Software-qualified factory images; delivery held','delivery_hold_until':'2026-10-13T23:30:00Z','images':{k:{'file':str(p.relative_to(R)),'bytes':len(raw[k]),'sha256':sha(raw[k])} for k,p in paths.items()},'cohorts':cohort,'counts':counts,'common_app_binary_parity':common,'card_contents':card,'preserved':preserved,'declaration_and_grant_rows':32,'live_handles_per_invocation':16,'hardware_qualified':False,'target_instructions_executed':False,'preserving_OTA':{'watch':'1.1.22 to 1.1.23 cohort admission passes; no OTA package or hardware update executed.','waveshare':'0.1.21 to 0.1.22 cohort admission rejects new LoRa ownership of previously shared namespaces without explicit migration; guard unchanged.','delivery':'Factory images only; factory use erases saved settings/AppData.'}}
(R/'final-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('images','counts')},indent=2))

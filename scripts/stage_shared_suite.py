#!/usr/bin/env python3
"""Stage the source-pinned common 26-app suite; never touch media or flash."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WATCH_SHA='d36b2d14d92e24278f2d3415235b32a454206038b5d460e18fb0d6ddf1b99916'
WAVE_SHA='032643ee90d63f4894dcdc8bacac8a5e067596aaeaa382c374efb53c6b49ae4d'
HOME_SHA='db647227a06c452721fe6789dceb58847f9e9dced36c0bc21b53265eccc96ba8'
LORA_SHA='0a0c9ed6d8c701af9af336fcbb067b6ece8fc304f4acf68722b627c04d96d785'
def sha(b):return hashlib.sha256(b).hexdigest()
def encode(v):return (json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()
def inventory(s):return {n:{'bytes':len(b),'sha256':sha(b)} for n,b in sorted(s.items())}
def check(p,h):
 b=Path(p).read_bytes()
 if sha(b)!=h:raise ValueError('Source-bound input mismatch: '+str(p))
 return b
def add_unique(rows,values):
 for r in values:
  if r not in rows:rows.append(copy.deepcopy(r))
def write_tree(root,store):
 root.mkdir(parents=True,exist_ok=False)
 for n,b in store.items():
  p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for k in ('runtime','watch-bin','wave-bin','home','lora','output'):p.add_argument('--'+k,type=Path,required=True)
 a=p.parse_args();sys.path.insert(0,str(a.runtime/'scripts'));from spiffs_image import read_image
 from shared_optional_hardware import provision
 old={}
 for product,path,digest in [('watch',a.watch_bin,WATCH_SHA),('waveshare',a.wave_bin,WAVE_SHA)]:
  raw=check(path,digest);assert len(raw)==0x1000000
  old[product]=read_image(raw[0x2f0000:0x840000],0x550000)
 home,lora=check(a.home,HOME_SHA),check(a.lora,LORA_SHA)
 boots={k:json.loads(v['boot.json']) for k,v in old.items()}
 rows={k:{r['manifest']:r for r in b['app_capabilities']} for k,b in boots.items()}
 assert len(rows['watch'])==len(rows['waveshare'])==25
 assert set(rows['watch'])-set(rows['waveshare'])=={'lora_messages.json'}
 assert set(rows['waveshare'])-set(rows['watch'])=={'bringup.json'}
 names=sorted(set(rows['watch'])|set(rows['waveshare']));common={}
 for n in names:
  origin='waveshare' if n in rows['waveshare'] else 'watch';m=json.loads(old[origin][n]);elf=m['file_name']
  common[elf]=home if elf=='default.elf' else lora if elf=='lora_messages.elf' else old[origin][elf]
 assert len(common)==26
 result={};records={}
 for product in ('watch','waveshare'):
  store=copy.deepcopy(old[product]);boot=copy.deepcopy(boots[product]);newrows=[]
  for n in names:
   origin='waveshare' if n in rows['waveshare'] else 'watch'
   manifest=json.loads(old[origin][n]);policy=copy.deepcopy(rows[product].get(n,rows[origin][n]))
   # Preserve Watch's explicit retained-wake and existing data namespace grants.
   if n in rows[product]:
    own=json.loads(old[product][n]);add_unique(manifest['requires'],own.get('requires',[]))
    add_unique(manifest.setdefault('optional',[]),own.get('optional',[]))
   # Existing product-local provider selection wins over another board's ID.
   # Persistent grants retain their explicit per-namespace rows.
   for grant in rows[origin][n]['grants']:
    persistent=grant['capability'] in ('storage.key-value','storage.shared-data')
    already=any(g['capability']==grant['capability'] and g['api']==grant['api'] for g in policy['grants'])
    if persistent or not already:add_unique(policy['grants'],[grant])
   if n=='default.json':manifest['version']='0.15.1'
   if n=='lora_messages.json':
    manifest['version']='0.1.16';manifest['display_name']='LoRa Messages';manifest['icon']='solid:f27a'
    add_unique(manifest['requires'],[{'capability':c,'api':1} for c in ('input.power-key','power.sleep','display.power','app.catalog')])
    add_unique(policy['grants'],[{'capability':c,'api':1,'instance_id':0} for c in ('input.power-key','power.sleep','display.power','app.catalog')])
   manifest,policy=provision(manifest,policy,{'radio.lora'} if product=='waveshare' and n=='lora_messages.json' else ())
   # Both apps already tolerate no removable-volume capability; internal files
   # and copied file-source handoffs remain available on a volume-less product.
   if n in ('file_browser.json','model_viewer.json'):
    volume=[r for r in manifest['requires'] if r['capability']=='storage.volume']
    manifest['requires']=[r for r in manifest['requires'] if r['capability']!='storage.volume']
    add_unique(manifest.setdefault('optional',[]),volume)
    if product=='watch':policy['grants']=[g for g in policy['grants'] if g['capability']!='storage.volume']
   required={(r['capability'],r['api']) for r in manifest['requires']}
   manifest['optional']=[r for r in manifest.get('optional',[]) if (r['capability'],r['api']) not in required]
   if not manifest['optional']:manifest.pop('optional')
   assert len(manifest['requires'])+len(manifest.get('optional',[]))<=32 and len(policy['grants'])<=32,n
   elf=manifest['file_name'];store[n]=encode(manifest)
   if product=='waveshare' and n=='lora_messages.json':
    policy['image_source']={'volume_instance':12,'path':'Apps/lora_messages/lora_messages.elf'}
    store.pop(elf,None)
   else:store[elf]=common[elf]
   newrows.append(policy)
  boot['app_capabilities']=newrows;store['boot.json']=encode(boot)
  assert boot['default_app']=='default.elf'
  assert all('image_source' not in r for r in newrows if r['manifest']!='lora_messages.json')
  # Physical providers, their policy, board, data backing and panel stay exact.
  assert boot['drivers']==boots[product]['drivers'] and store['board.json']==old[product]['board.json']
  for n,b in old[product].items():
   if '/' in n:assert store[n]==b,n
  assert {json.loads(store[r['manifest']])['file_name'] for r in newrows}==set(common)
  result[product]=store
  records[product]={'files':len(store),'elfs':sum(n.endswith('.elf') for n in store),'apps':26,'providers':len(boot['drivers']),'inventory':inventory(store),'inventory_sha256':sha(encode(inventory(store))),'max_grants':max(len(r['grants']) for r in newrows),'all_prior_provider_bytes_and_policies_preserved':True}
 assert len([r for r in json.loads(result['waveshare']['boot.json'])['app_capabilities'] if 'image_source' in r])==1
 card={'Apps/lora_messages/lora_messages.elf':lora,'Apps/lora_messages/manifest.json':result['waveshare']['lora_messages.json']}
 card['suite-card.json']=encode({'schema':'riscrte.provisioned-card-content','schema_version':1,'apps':[{'manifest':'Apps/lora_messages/manifest.json','image':'Apps/lora_messages/lora_messages.elf','sha256':sha(lora)}],'discovery':'explicit internal boot policy; catalog entry comes from admitted lora_messages.json'})
 assert not a.output.exists();a.output.mkdir(parents=True)
 for product,store in result.items():write_tree(a.output/product/'UNSEALED-STORE',store)
 write_tree(a.output/'card',card);write_tree(a.output/'common-apps',common)
 (a.output/'staging.json').write_bytes(encode({'schema':1,'baseline':{'watch':WATCH_SHA,'waveshare':WAVE_SHA},'products':records,'shared_elfs':inventory(common),'card':inventory(card),'hardware_qualified':False,'flashable':False}))
 print(json.dumps({k:{n:v for n,v in r.items() if n!='inventory'} for k,r in records.items()},indent=2))
if __name__=='__main__':main()

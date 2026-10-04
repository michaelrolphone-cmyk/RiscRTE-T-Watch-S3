#!/usr/bin/env python3
"""Independent exact authority/provenance checks for the Points in Time development store."""
import argparse,hashlib,json,struct,zipfile
from pathlib import Path,PurePosixPath
from check_twatch_drivers import check_board
if not __debug__:raise RuntimeError('Verification requires normal Python, never optimized mode')
ROOT=Path(__file__).resolve().parents[1]
APPS=('default','clock','springboard','battery','settings','calculator','stopwatch','alarms','countdown','points_in_time')
DEVICES={1,2,3,4,5,6,8,9,12}
KV=[{'key':'alarm_cfg','namespace':3,'access':'read'},{'key':'timer_cfg','namespace':3,'access':'read'},{'key':'alarm_occ','namespace':4,'access':'read-write'},{'key':'timer_occ','namespace':4,'access':'read-write'},{'key':'alert_mode','namespace':1,'access':'read'},{'key':'points_cfg','namespace':5,'access':'read'},{'key':'points_occ','namespace':4,'access':'read-write'}]
def sha(data):return hashlib.sha256(data).hexdigest()
def verify(path):
 with zipfile.ZipFile(path) as z:
  names=z.namelist();assert len(names)==len(set(names)) and all(not n.startswith('/') and '..' not in PurePosixPath(n).parts for n in names)
  record=json.loads(z.read('deployment-record.json'));entries=record['entries']
  assert record['schema']=='riscrte.watch-points-launcher-deployment' and record['app_version']=='0.7.0'
  assert len(entries)==len({e['path'] for e in entries}) and set(names)=={e['path'] for e in entries}|{'deployment-record.json'}
  for e in entries:
   data=z.read(e['path']);assert e['size_bytes']==len(data) and e['sha256']==sha(data),e['path']
  for notice in ('Orbitron-OFL.txt','Rajdhani-OFL.txt','ShareTechMono-OFL.txt','SOURCES.txt'):assert z.read('licenses/nova/'+notice)
  boot=json.loads(z.read('store/boot.json'));board=json.loads(z.read('store/board.json'));assert boot['default_app']=='default.elf'
  assert {d['instance_id'] for d in board['devices']}==DEVICES
  physical=[d for d in boot['drivers'] if 'instance_id' in d];services=[d for d in boot['drivers'] if 'instance_id' not in d]
  assert len(physical)==9 and {d['instance_id'] for d in physical}==DEVICES
  assert services==[{'manifest':'alarm-service/manifest.json','key_value':KV}]
  assert [p['manifest'] for p in boot['app_capabilities']]==[a+'.json' for a in APPS]
  expected_versions={'default':'0.7.0','clock':'0.7.0','springboard':'1.4.1','settings':'1.2.3','battery':'1.0.8','calculator':'0.1.3','stopwatch':'0.1.3','alarms':'0.1.2','countdown':'0.1.2','points_in_time':'0.1.0'}
  metadata=json.loads(z.read('shared-app-build.json'))
  for name,policy in zip(APPS,boot['app_capabilities']):
   grants=[{'capability':'display.output','api':1,'instance_id':5},{'capability':'input.touch.raw','api':1,'instance_id':6}]
   if name in ('default','clock','springboard','settings','stopwatch','alarms','countdown','points_in_time'):grants.append({'capability':'rtc.clock','api':2,'instance_id':8})
   grants.append({'capability':'board.battery','api':1,'instance_id':4})
   ns=1 if name in ('default','clock','settings') else 2 if name=='stopwatch' else 3 if name in ('alarms','countdown') else 0
   if ns:grants.append({'capability':'storage.key-value','api':1,'instance_id':ns})
   if name in ('default','clock','points_in_time'):grants.append({'capability':'storage.key-value','api':1,'instance_id':5})
   if name=='points_in_time':grants.append({'capability':'storage.key-value','api':1,'instance_id':1})
   grants.append({'capability':'alarm.service','api':1,'instance_id':0})
   assert policy['grants']==grants,name
   manifest=json.loads(z.read('store/'+name+'.json'))
   expected={'type':'application','id':'twatch-clock' if name=='default' else 'twatch-clock-return' if name=='clock' else name,'version':expected_versions[name],'architecture':'xtensa-esp32s3','file_name':name+'.elf','entry':'app_main','requires':[dict(capability=c,api=v) for c,v in dict.fromkeys((g['capability'],g['api']) for g in grants)]}
   assert manifest==expected,name
   elf=z.read('store/'+name+'.elf');assert elf[:7]==b'\x7fELF\x01\x01\x01' and struct.unpack_from('<HH',elf,16)==(3,94)
   assert metadata['apps'][name]['sha256']==sha(elf)
  assert [x['file_name'] for x in json.loads(z.read('shared/catalog.json'))]==[a+'.elf' for a in ('clock','battery','settings','calculator','stopwatch','alarms','countdown','points_in_time')]
  assert metadata['return_targets']=={'springboard':'clock.elf',**{a:'springboard.elf' for a in ('battery','settings','calculator','stopwatch','alarms','countdown','points_in_time')}}
  manifests=[]
  for d in boot['drivers']:
   manifest=json.loads(z.read('store/'+d['manifest']));
   if manifest not in manifests:manifests.append(manifest)
   elf=z.read('store/'+str(PurePosixPath(d['manifest']).parent/manifest['file_name']));assert elf[:7]==b'\x7fELF\x01\x01\x01' and struct.unpack_from('<HH',elf,16)==(3,94)
  check_board(board,manifests[:-1]);service=manifests[-1]
  for identity,version in {'twatch-panel':'0.4.1','twatch-gpio':'0.4.2','twatch-pmu':'0.5.2','twatch-speaker':'0.2.1','twatch-haptic':'0.2.1'}.items():assert next(m for m in manifests if m['id']==identity)['version']==version
  assert service=={'type':'driver','id':'alarm-service','version':'0.2.0','driver_abi':2,'architecture':'xtensa-esp32s3','file_name':'driver.elf','requires':[{'capability':c,'api':v} for c,v in [('storage.key-value.bound',1),('platform.clock',1),('rtc.clock',2),('haptic.effect',1),('audio.output',1)]],'provides':[{'capability':'alarm.service','api':1}],'physical_verification':'pending','status':'development-only-recurring-points'}
  assert service['requires']==[{'capability':c,'api':v} for c,v in [('storage.key-value.bound',1),('platform.clock',1),('rtc.clock',2),('haptic.effect',1),('audio.output',1)]]
  assert next(d for d in board['devices'] if d['instance_id']==4)['config']['rails']==[{'id':1,'millivolts':3300},{'id':2,'millivolts':3300},{'id':5,'millivolts':3300}]
  runtime=json.loads(z.read('runtime-requirements.json'));assert runtime==json.loads((ROOT/'apps/alarm-runtime-requirements.json').read_text()) and runtime['source_sha']=='8688f92069b99547f0d25ecbd12cfcad3bb52c53'
  assert json.loads(z.read('shared/alarm-sources.json'))==json.loads((ROOT/'apps/points-sources.json').read_text())
  service_build=json.loads(z.read('shared/alarm-service-build.json'));assert service_build['elf_sha256']==sha(z.read('store/alarm-service/driver.elf'))
  print(path.name,'verified ten app policies, exact seven keys, physical closure, native ELFs and source pins')
  return record
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('archives',nargs='+',type=Path);a=p.parse_args()
 for path in a.archives:verify(path)

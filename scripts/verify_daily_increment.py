#!/usr/bin/env python3
"""Preserve delivered 0.5.0 hardware/GUI bytes around two bounded shared apps."""
import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()
def verify(path):
 baseline=json.loads((ROOT/'docs/DAILY_APPS_BASELINE.json').read_text())
 for name,digest in baseline['unchanged_source_sha256'].items():
  assert sha((ROOT/name).read_bytes())==digest,name
 with zipfile.ZipFile(path) as z:
  names=z.namelist();assert len(names)==len(set(names))
  files={n.removeprefix('store/'):z.read(n) for n in names if n.startswith('store/')}
  source=json.loads(z.read('shared-app-build.json'))
  assert source['touch_rotation']==0 and source['full_frames'] is True and source['retained_handoff'] is True
  assert source['handoff_ms']==60 and source['return_targets']=={'springboard':'clock.elf','battery':'springboard.elf','settings':'springboard.elf','calculator':'springboard.elf','stopwatch':'springboard.elf'}
  assert source['crown_navigation']=='app-local-original-pmu'
  assert source['sleep_policy']=={'default':'light','choice':'storage.key-value@1','instance_id':1,'key':'sleep_mode','deep_wake':'fresh-default','ulp_program':False}
  assert source['shared_sources']==json.loads((ROOT/'apps/shared-sources.json').read_text())
  assert source['daily_apps']=={'stopwatch':{'storage_instance':2,'key':'stopwatch','awake_clock':'monotonic-ms','restored_clock':'raw-RTC-seconds','precision':'approximate-after-recovery'},'calculator':{'arithmetic':'fixed-decimal','fractional_digits':6}}
 expected=baseline['baseline_store_sha256'];assert set(files)==set(expected)|set(baseline['added_store_files']) and len(files)==28
 actual={n:sha(b) for n,b in sorted(files.items())}
 changed=sorted(n for n in expected if actual[n]!=expected[n]);assert changed==baseline['changed_store_files'],changed
 fixed=sorted(set(expected)-set(changed));assert len(fixed)==19
 boot=json.loads(files['boot.json']);assert boot['drivers']==baseline['baseline_boot']['drivers'] and len(boot['drivers'])==7
 assert boot['app_capabilities'][:5]==baseline['baseline_boot']['app_capabilities'] and len(boot['app_capabilities'])==7
 assert boot['default_app']=='default.elf' and boot['board']=='board.json'
 for name in ('default','clock'):
  manifest=json.loads(files[name+'.json']);previous=baseline['baseline_manifests'][name];previous={**previous,'version':'0.5.1'}
  assert manifest==previous
 for name in ('calculator','stopwatch'):
  assert source['apps'][name]['sha256']==sha(files[name+'.elf'])
  manifest=json.loads(files[name+'.json']);assert manifest['id']==name and manifest['version']=='0.1.0' and manifest['file_name']==name+'.elf'
  grants=[{'capability':'display.output','api':1,'instance_id':5},{'capability':'input.touch.raw','api':1,'instance_id':6}]
  if name=='stopwatch':grants.append({'capability':'rtc.clock','api':2,'instance_id':8})
  grants.append({'capability':'board.battery','api':1,'instance_id':4})
  if name=='stopwatch':grants.append({'capability':'storage.key-value','api':1,'instance_id':2})
  assert next(p for p in boot['app_capabilities'] if p['manifest']==name+'.json')=={'manifest':name+'.json','grants':grants}
  assert manifest=={'type':'application','id':name,'version':'0.1.0','architecture':'xtensa-esp32s3','file_name':name+'.elf','entry':'app_main','requires':[{'capability':g['capability'],'api':g['api']} for g in grants]}
 assert json.loads(files['springboard.json'])=={**baseline['baseline_manifests']['springboard'],'version':'1.3.8'}
 assert source['apps']['springboard']['sha256']==sha(files['springboard.elf'])
 record={**baseline,'variant_store_sha256':actual,'verified_changed_files':changed,'unchanged_file_count':len(fixed),'unchanged_store_files':fixed}
 (Path(path).parent/'daily-apps-increment-proof.json').write_text(json.dumps(record,indent=2)+'\n')
 print('Verified daily apps: 19 unchanged files, 5 catalog/version/grant changes and 4 new app files; all physical drivers and rendering source retained')
 return record
if __name__=='__main__':
 assert len(sys.argv)==2
 verify(sys.argv[1])

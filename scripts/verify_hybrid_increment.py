#!/usr/bin/env python3
"""Bound Hybrid/polish to delivered 0.5.1; preserve grants and physical transport."""
import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()
def verify(path):
 baseline=json.loads((ROOT/'docs/HYBRID_BASELINE.json').read_text())
 for name,digest in baseline['unchanged_source_sha256'].items():assert sha((ROOT/name).read_bytes())==digest,name
 with zipfile.ZipFile(path) as z:
  names=z.namelist();assert len(names)==len(set(names))
  files={n.removeprefix('store/'):z.read(n) for n in names if n.startswith('store/')}
  source=json.loads(z.read('shared-app-build.json'))
 assert source['touch_rotation']==0 and source['full_frames'] is True and source['retained_handoff'] is True and source['handoff_ms']==60
 assert source['return_targets']=={'springboard':'clock.elf','battery':'springboard.elf','settings':'springboard.elf','calculator':'springboard.elf','stopwatch':'springboard.elf'}
 assert source['crown_navigation']=='app-local-original-pmu'
 assert source['sleep_policy']=={'default':'hybrid','application_idle_ms':60000,'light_ms':300000,'scope':'saved Clock mode; other apps always hybrid','choice':'storage.key-value@1','instance_id':1,'key':'sleep_mode','deep_wake':'fresh-default','ulp_program':False}
 assert source['shared_sources']==json.loads((ROOT/'apps/shared-sources.json').read_text())
 assert source['daily_apps']=={'stopwatch':{'storage_instance':2,'key':'stopwatch','awake_clock':'monotonic-ms','restored_clock':'raw-RTC-seconds','precision':'approximate-after-recovery'},'calculator':{'arithmetic':'fixed-decimal','fractional_digits':6}}
 expected=baseline['baseline_store_sha256'];assert set(files)==set(expected) and len(files)==28
 actual={n:sha(b) for n,b in sorted(files.items())}
 changed=sorted(n for n in expected if actual[n]!=expected[n]);assert changed==baseline['changed_store_files'],changed
 fixed=sorted(set(expected)-set(changed));assert len(fixed)==10
 assert json.loads(files['boot.json'])==baseline['baseline_boot']
 versions={'default':'0.5.2','clock':'0.5.2','springboard':'1.3.9','battery':'1.0.6','settings':'1.1.1','calculator':'0.1.1','stopwatch':'0.1.1'}
 for name,version in versions.items():
  assert json.loads(files[name+'.json'])=={**baseline['baseline_manifests'][name],'version':version}
  assert source['apps'][name]['sha256']==sha(files[name+'.elf'])
 for name,version in [('gpio','0.4.1'),('pmu','0.5.1')]:assert json.loads(files[name+'/manifest.json'])['version']==version
 record={**baseline,'variant_store_sha256':actual,'verified_changed_files':changed,'unchanged_file_count':len(fixed),'unchanged_store_files':fixed}
 (Path(path).parent/'hybrid-increment-proof.json').write_text(json.dumps(record,indent=2)+'\n')
 print('Hybrid/polish custody: 10 unchanged store files; 18 scoped app/GPIO/PMU files; exact unchanged grants, rails, panel, touch and RTC')
 return record
if __name__=='__main__':
 assert len(sys.argv)==2
 verify(sys.argv[1])

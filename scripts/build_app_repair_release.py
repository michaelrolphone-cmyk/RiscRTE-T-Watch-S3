#!/usr/bin/env python3
"""Reproduce, admit and package the pinned 1.1.35 to 1.1.36 successor."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
from watch_app_repair import ROOT,PINS,clean,need,require_final,sha,verify_baseline,write

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('baseline','runtime','replay-source','compiler','output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--source-cache',type=Path);p.add_argument('--qualified-replay',type=Path);p.add_argument('--source-revision',required=True);a=p.parse_args()
 for name,value in vars(a).items():
  if isinstance(value,Path):setattr(a,name,value.resolve())
 require_final();clean(ROOT,a.source_revision);clean(a.replay_source,PINS['replay_source_revision']);need(not a.output.exists(),'Output must be new')
 baseline=a.baseline.read_bytes();need(sha(baseline)==PINS['baseline_sha256'],'Wrong official 1.1.35 baseline')
 from read_only_spiffs import read_image
 before=read_image(baseline[0x2f0000:0x840000],0x550000);verify_baseline(before)
 work=a.output/'qualification';write(work/'baseline-store',before)
 def run(script,*args,sanitize=False):
  env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0','SANITIZE':'1' if sanitize else '0'}
  subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args)],check=True,env=env)
 if a.qualified_replay:
  from package_app_repair import verify_replay
  manifest=json.loads((ROOT/'docs/shared-app-repair/app-manifest.json').read_text())
  verify_replay(a.qualified_replay,a.replay_source,manifest,a.compiler)
  (work/'replay').mkdir()
  names=['receipt.json']+[name+ext for name in PINS['expected_repaired_apps'] for ext in ('.elf','.log')]
  for name in names:shutil.copyfile(a.qualified_replay/name,work/'replay'/name)
 else:
  cmd=[sys.executable,str(a.replay_source/'scripts/replay_shared_crash_apps.py'),'--product','twatch','--compiler',str(a.compiler),'--output',str(work/'replay')]
  if a.source_cache:cmd+=['--source-cache',str(a.source_cache)]
  subprocess.run(cmd,check=True)
 native=a.runtime/'.pio/build/watch-native-ui'
 run('watch_app_repair.py','compose','--baseline-store',work/'baseline-store','--apps',work/'replay','--firmware',native/'firmware.bin','--source-revision',a.source_revision,'--output',work/'composition')
 for sanitize in (False,True):
  run('verify_app_repair_native.py','--runtime',a.runtime,'--compiler',a.compiler,'--store',work/'composition/store','--baseline-store',work/'baseline-store','--output',work/('admission-sanitized' if sanitize else 'admission'),sanitize=sanitize)
 run('test_app_repair_preservation.py','--runtime',a.runtime,'--baseline',a.baseline,'--firmware',native/'firmware.bin','--store',work/'composition/store.bin','--output',work/'preservation')
 run('package_app_repair.py','--baseline',a.baseline,'--runtime',a.runtime,'--composition',work/'composition','--admission',work/'admission','--admission-sanitized',work/'admission-sanitized','--preservation',work/'preservation','--replay',work/'replay','--replay-source',a.replay_source,'--compiler',a.compiler,'--source-revision',a.source_revision,'--output',a.output/'assets')
 print('Complete exact-source 1.1.36 package; no hardware or publication I/O')

if __name__=='__main__':main()

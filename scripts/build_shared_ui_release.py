#!/usr/bin/env python3
"""Rebuild and qualify an exact-source local release; no device or publishing I/O."""
import argparse,json,os,subprocess,sys
from pathlib import Path
from shared_native_ui import ROOT,PINS,clean,files,need,require_final,sha,verify_baseline,write

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('baseline','runtime','system','baseline-system','bridges','compiler','output'):
  p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--source-revision',required=True);a=p.parse_args()
 for name,value in vars(a).items():
  if isinstance(value,Path):setattr(a,name,value.resolve())
 require_final();clean(ROOT,a.source_revision);need(not a.output.exists(),'Output must be new')
 baseline=a.baseline.read_bytes();need(sha(baseline)==PINS['baseline_sha256'],'Exact released .33 factory required')
 from read_only_spiffs import read_image
 before=read_image(baseline[0x2f0000:0x840000],0x550000);verify_baseline(before)
 a.output.mkdir(parents=True);work=a.output/'qualification';write(work/'baseline-store',before)
 def run(script,*args,sanitize=False):
  env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0','SANITIZE':'1' if sanitize else '0'}
  subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args)],check=True,env=env)
 for label,system in [('baseline-target',a.baseline_system),('target',a.system)]:
  run('shared_native_ui.py','build','--system',system,'--bridges',a.bridges,'--compiler',a.compiler,'--output',work/label,*(['--baseline'] if label=='baseline-target' else []))
 run('qualify_shared_native_ui.py','--system',a.system,'--bridges',a.bridges,'--output',work/'shared-source')
 native=a.runtime/'.pio/build/watch-native-ui'
 run('shared_native_ui.py','compose','--baseline-store',work/'baseline-store','--springboard',work/'target','--firmware',native/'firmware.bin','--source-revision',a.source_revision,'--output',work/'composition')
 for sanitize in (False,True):
  run('verify_shared_native_ui.py','--runtime',a.runtime,'--store',work/'composition/store','--baseline-store',work/'baseline-store','--output',work/('admission-sanitized' if sanitize else 'admission'),sanitize=sanitize)
 run('test_shared_ui_preservation.py','--runtime',a.runtime,'--baseline',a.baseline,'--firmware',native/'firmware.bin','--store',work/'composition/store.bin','--output',work/'preservation')
 run('package_shared_native_ui.py','--baseline',a.baseline,'--baseline-store',work/'baseline-store','--runtime',a.runtime,'--system',a.system,'--bridges',a.bridges,'--compiler',a.compiler,'--target',work/'target','--composition',work/'composition','--admission',work/'admission','--admission-sanitized',work/'admission-sanitized','--qualification',work/'shared-source','--preservation',work/'preservation','--source-revision',a.source_revision,'--output',a.output/'assets')
 print('Exact-source release package and evidence complete; no assets published')
if __name__=='__main__':main()

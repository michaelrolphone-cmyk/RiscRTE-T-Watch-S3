#!/usr/bin/env python3
"""Build the existing scene host's supported raw-touch-only Watch profile."""
import argparse,json,os,subprocess,sys,tempfile
from pathlib import Path
W=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
for n in ('system','runtime','output'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--lists-manifest',type=Path,required=True,help='Existing Lists stage manifest to project into strict native metadata')
a=p.parse_args();S=a.system.resolve();R=a.runtime.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(S/'scripts'))
from scene_sdk import stage_sdk
from scene_build import build,compiler_path
with tempfile.TemporaryDirectory() as tmp:
 include=stage_sdk(R,S,Path(tmp));m=json.loads((S/'Services/scene_host/manifest.json').read_text())
 # host.c already supports four dependencies and no navigation table. Watch
 # uses raw touch, and has no independent input.navigation provider to grant.
 m['requires']=[q for q in m['requires'] if q['capability']!='input.navigation'];m['version']='0.3.1'
 r=build(compiler_path(),include,out,m,[S/'Services/scene_host/host.c']);r['selection']='Watch raw-touch-only; optional navigation omitted'
 (out/'build.json').write_text(json.dumps(r,indent=2)+'\n')
 test=out/'touch-only-test';subprocess.run(['cc','-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(include),'-I'+str(S/'test/scene'),str(W/'tests/canvas_scene_touch_test.c'),str(S/'Services/scene_host/host.c'),'-o',str(test)],check=True)
 subprocess.run([str(test)],env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'},check=True)

legacy=json.loads(a.lists_manifest.read_text())
required={'type','id','version','architecture','file_name','entry','requires'}
optional={'description','display_name','icon','supported_file_types'}
assert required<=set(legacy) and legacy['id']=='lists'
assert set(legacy)-required-optional <= {'category','runtime_profile','min_firmware_version'}
native={k:v for k,v in legacy.items() if k in required|optional}
(out/'lists-native.json').write_text(json.dumps(native,indent=2)+'\n')

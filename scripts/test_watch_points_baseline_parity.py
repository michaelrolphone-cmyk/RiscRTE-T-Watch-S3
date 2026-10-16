"""Replay source-bound delivered Points screens and compare migrated pixel prefixes."""
from pathlib import Path
import argparse
import json,os,subprocess,sys,hashlib,shlex
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));import test_watch_keyboard_points as test
p=argparse.ArgumentParser();p.add_argument('--predecessor-record',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--workflow',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=a.output.resolve();root.mkdir(exist_ok=False)
baseline=json.loads(a.predecessor_record.read_text())['points_in_time'];modern=json.loads((a.build/'points_in_time-build-record.json').read_text())
system=Path(modern['source_roots']['system-apps']);runtime=Path(modern['source_roots']['runtime'])
flags=[x for x in baseline['defines'] if x!='-flto'];inc=[x for x in baseline['command'] if x.startswith('-I')];src=[Path(x) for x in baseline['command'] if x.endswith('.c') and not x.endswith(('portable_navigation.c','portable_sleep.c'))]
# Bind the replay to the recorded, exact target dependency bytes, including
# translation units whose hardware boundary is copied by the host fixture.
baseline_cc=os.environ.get('NATIVE_APP_CC',baseline['command'][0]);dependency_hashes={}
for source in (Path(x) for x in baseline['command'] if x.endswith('.c')):
 dep=subprocess.check_output([baseline_cc,'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM',*flags,*inc,str(source)],text=True)
 for item in shlex.split(dep.replace('\\\n',' ').split(':',1)[1]):
  path=Path(item);dependency_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
assert set(dependency_hashes.values())=={x['sha256'] for x in baseline['target_dependencies'].values()}
(root/'baseline-dependencies.json').write_text(json.dumps(dependency_hashes,indent=2)+'\n')
svc=['-I'+str(system/'Services/text_input'),'-I'+str(system/'sdk/app'),'-I'+str(system/'lib/PortableApps/include'),'-I'+str(runtime/'sdk/driver'),'-I'+str(system/'Services/scene_profile')]
modern_inc=['-I'+str(system/'lib/PortableApps/include'),'-I'+str(system/'lib/NativeApps/include'),'-I'+str(system/'Apps')]
fixture=ROOT/'tests/shared_keyboard/watch_points_host.c'
stub=root/'text-unselected.c';stub.write_text('#include <stdbool.h>\nbool portable_text_adapter_retained(void){return false;}\n')
sources=[(system/'Services/scene_host/host.c',svc+['-DSCENE_HOST_TELEMETRY=0','-DSCENE_HOST_WATCH_240=1','-Dt5_driver_get=points_scene_driver_get']),(system/'Services/text_input/host.c',svc+['-Dt5_driver_get=points_text_driver_get']),(system/'Services/scene_profile/profile.c',svc+['-Dt5_driver_get=points_profile_driver_get']),(fixture,flags+modern_inc+inc+['-DPOINTS_WATCH_RENDER','-I'+str(system/'sdk/app'),'-I'+str(runtime/'sdk/driver'),'-I'+str(system/'Services/scene_profile')]),(stub,[]),*[(p,flags+inc) for p in src]]
objects=[]
for i,(p,f) in enumerate(sources):
 obj=root/(str(i)+'.o');subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',*f,'-c',str(p),'-o',str(obj)],check=True);objects.append(obj)
binary=root/'points';subprocess.run(['cc',*map(str,objects),'-o',str(binary)],check=True)
for mode in ('idle','edit','types','custom','schedule-save','schedule-cancel','delete-point'):
 out=root/mode;out.mkdir(exist_ok=True);actions=out/'actions.txt';actions.write_text(''.join(' '.join(map(str,x))+'\n' for x in test.scenarios()[mode]));p=subprocess.run([str(binary),str(out),str(actions)],capture_output=True,text=True,env={**os.environ,'POINTS_CASE':mode},timeout=30);(out/'run.log').write_text(p.stdout+p.stderr);print(mode,p.returncode,flush=True)
 if p.returncode:print((p.stdout+p.stderr)[-2000:]);raise RuntimeError(mode)

report=[]
def frames(folder):
 out=[]
 for f in sorted(folder.glob('frame-*.ppm')):
  h=hashlib.sha256(f.read_bytes()).hexdigest()
  if not out or h!=out[-1][1]:out.append((f.name,h))
 return out
for mode in ('idle','edit','types','custom','schedule-save','schedule-cancel','delete-point'):
 before=frames(root/mode);after=frames(a.workflow/'normal'/mode)
 equal=[v for k,v in before]==[v for k,v in after[:len(before)]]
 assert equal,mode
 report.append(dict(case=mode,baseline=before,migrated=after,matching_reference_prefix=equal))
(root/'pixel-parity.json').write_text(json.dumps(dict(cases=report,matched_frames=sum(len(x['baseline']) for x in report),note='Migrated shutdown fixture generates explicit Back events after the script; compare the complete delivered-scene prefix before that fixture-only shutdown.'),indent=2)+'\n')

#!/usr/bin/env python3
"""Replay the exact Watch Points target profile with its real shared hosts."""
import argparse, hashlib, json, os, re, shlex, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def tap(delay,x,y,gate='app',release=40):return [(delay,gate,'down',x,y),(release,gate,'up',x,y)]
def nav(delay,kind,gate='app'):return [(delay,gate,kind,0,0)]
def swipe(delay,x,y,to_y):return [(delay,'app','down',x,y),(40,'app','move',x,to_y),(40,'app','up',x,to_y)]
def scenarios():
 edit=tap(200,100,100);types=edit+tap(250,100,100)
 custom=types+swipe(250,120,195,85)+swipe(250,120,195,85)+tap(250,195,142)
 name=custom+tap(250,100,103)
 key=tap(250,47,97,'text');done=tap(250,194,188,'text');cancel=tap(250,28,20,'text')
 save=tap(250,180,220);back=nav(250,'back','text');home=tap(250,210,20,'text')
 schedule=edit+tap(250,100,142)+tap(250,60,180)+tap(250,180,180)+tap(250,120,220)+tap(250,100,182)+tap(250,60,180)+tap(250,180,180)+tap(250,120,220)+swipe(250,120,190,90)+tap(250,195,110)+tap(250,195,150)+tap(250,100,190)+tap(250,100,182)+swipe(250,120,190,90)+tap(250,55,172)+tap(250,185,194)
 result={'idle':[], 'schedule-save':schedule+tap(250,180,220), 'schedule-cancel':schedule+tap(250,60,220), 'delete-point':edit+swipe(250,120,190,85)*3+tap(250,100,178)*2, 'panel-wide':[], 'panel-mono':[], 'edit':edit, 'types':types, 'custom':custom,
 'save':name+key+done+save, 'done-draft':name+key+done,
 'cancel':name+key+cancel, 'navigation-back':name+key+back,
 'unavailable':name,'retained':name+key+cancel,
 'back-return':name+key+back+nav(250,'back')+nav(250,'back')+nav(250,'back')+nav(250,'back'),
 'repeat':name+key+done+tap(250,100,103)+key+cancel+tap(250,100,103)+key+done+save,
 'navigation-home':name+key+home,
 'save-delayed':name+key+done+save,
 'rapid-repeat':name+tap(10,47,97,'text',release=4)+tap(4,47,97,'text',release=4)+done+save,
 'color-save':name+key+done+tap(250,55,185)+save,
 'limit':name+key*20+done+save,
 'delete':name+tap(250,211,156,'text')+done+save,
 'empty':name+tap(250,211,156,'text')*5+done+save,
 'custom-back':name+key+done+tap(250,60,220),
 'quick':tap(250,200,15)+tap(250,30,20),
 }
 for boundary in ('acquire','open','poll','close','release','kv-get','kv-put','kv-release','acquire-fail'):
  result['loss-'+boundary]=name+key+done+save
 return result

def qualify(build,output,provider_system=None):
 record_path=build/'points_in_time-build-record.json';r=json.loads(record_path.read_text());roots={k:Path(v) for k,v in r['source_roots'].items()}
 for k,v in r['source_sha256'].items():
  owner,relative=k.split(':',1);assert sha(roots[owner]/relative)==v,k
 assert sha(build/'points_in_time.elf')==r['sha256'];output.mkdir(parents=True,exist_ok=False)
 system=provider_system or roots['system-apps'];runtime=roots['runtime']
 defines=[x for x in r['defines'] if x not in ('-flto','-mno-target-align')];includes=[x for x in r['command'] if x.startswith('-I')]
 app_sources=[Path(x) for x in r['command'] if x.endswith('.c') and not x.endswith(('portable_navigation.c','portable_sleep.c'))]
 fixture=ROOT/'tests/shared_keyboard/watch_points_host.c'
 fixture_flags=['-DPOINTS_WATCH_RENDER','-I'+str(system/'sdk/app'),'-I'+str(system/'Services/scene_profile'),'-I'+str(runtime/'sdk/driver')]
 svc_flags=['-I'+str(system/'Services/text_input'),'-I'+str(system/'sdk/app'),'-I'+str(system/'lib/PortableApps/include'),'-I'+str(runtime/'sdk/driver'),'-I'+str(system/'Services/scene_profile')]
 common=['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror']
 results=[];commands=[];dependencies={}
 for san in (False,True):
  out=output/('san' if san else 'normal');out.mkdir()
  extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie'] if san else []
  objects=[]
  sources=[(system/'Services/scene_host/host.c',svc_flags+['-DSCENE_HOST_TELEMETRY=0','-DSCENE_HOST_WATCH_240=1','-Dt5_driver_get=points_scene_driver_get']),
           (system/'Services/text_input/host.c',svc_flags+['-Dt5_driver_get=points_text_driver_get']),
           (system/'Services/scene_profile/profile.c',svc_flags+['-Dt5_driver_get=points_profile_driver_get']),
           (fixture,defines+includes+fixture_flags),*[(p,defines+includes) for p in app_sources]]
  for i,(source,flags) in enumerate(sources):
   obj=out/(str(i)+'.o');dep=out/(str(i)+'.d');objects.append(obj)
   cmd=[*common,*extra,*flags,'-MMD','-MF',str(dep),'-c',str(source),'-o',str(obj)];commands.append(cmd);subprocess.run(cmd,check=True)
   for path in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):dependencies[path]=sha(path)
  binary=out/'points';cmd=[*common,*extra,*map(str,objects),'-o',str(binary)];commands.append(cmd);subprocess.run(cmd,check=True)
  for name,actions in scenarios().items():
   folder=out/name;folder.mkdir();path=folder/'actions.txt';path.write_text(''.join(' '.join(map(str,row))+'\n' for row in actions))
   env={k:v for k,v in os.environ.items() if not k.startswith('POINTS_')};env.update(ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1',POINTS_CASE=name)
   if name=='back-return':env['POINTS_BACK']='1'
   if name=='navigation-home':env['POINTS_HOME']='1'
   if name in ('save-delayed','rapid-repeat'):env['POINTS_DELAY']='1'
   p=subprocess.run([str(binary),str(folder),str(path)],env=env,capture_output=True,text=True,timeout=30)
   (folder/'run.log').write_text(p.stdout+p.stderr)
   frames=list(folder.glob('frame-*.ppm'))
   results.append(dict(case=name,sanitized=san,passed=p.returncode==0,frames=len(frames),log_sha256=sha(folder/'run.log')))
   print('PASS' if p.returncode==0 else 'FAIL',san,name,flush=True)
   if p.returncode:print((p.stdout+p.stderr)[-2200:]);raise RuntimeError(str(folder/'run.log'))
 evidence=dict(schema=1,elf_sha256=r['sha256'],build_record_sha256=sha(record_path),actual_watch_defines=r['defines'],cases=results,commands=commands,source_sha256=dependencies,hardware_verified=False,scope='Production Watch Points, adapter, compact scene host, text host; copied hardware transports and local navigation/sleep bridge boundaries')
 rapid=[]
 for san in ('normal','san'):
  log=(output/san/'rapid-repeat/run.log').read_text();times=[int(x) for x in re.findall(r'input at (\d+) ms: text (?:down|up) 47 97',log)]
  assert len(times)==4 and times[-1]-times[0]==12 and 'rapid edges=4 writes=1 grants=1 name=FocusWW' in log
  rapid.append(dict(sanitized=san=='san',ordered_key_edges=4,elapsed_ms=times[-1]-times[0],intervening_frames=0,persisted_name='FocusWW'))
 evidence['rapid_input']=rapid
 evidence['target_only_flags_omitted_for_host']=['-flto','-mno-target-align']
 (output/'receipt.json').write_text(json.dumps(evidence,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--provider-system',type=Path);a=p.parse_args();qualify(a.build.resolve(),a.output.resolve(),a.provider_system.resolve() if a.provider_system else None)

#!/usr/bin/env python3
"""Replay the exact Watch Scanner target profile with its real shared hosts."""
import argparse, hashlib, json, os, shlex, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def tap(delay,x,y,gate='app',release=40):return [(delay,gate,'down',x,y),(release,gate,'up',x,y)]
def nav(delay,kind,gate='app'):return [(delay,gate,kind,0,0)]
def scenarios():
 scan=tap(200,50,218);detail=scan+tap(500,100,80,'scan');name=detail+tap(250,172,218)
 key=tap(250,47,97,'text');done=tap(250,194,188,'text');cancel=tap(250,28,20,'text')
 back=nav(250,'back','text');home=tap(250,210,20,'text')
 result={'idle':[], 'scan-stop':scan+tap(800,50,218,'scan'), 'nested-back':detail+tap(250,28,20)+tap(250,28,20),
 'name-save':name+key+done, 'name-cancel':name+key+cancel, 'name-navigation-back':name+key+back,
 'name-unavailable':name,'name-retained':name+key+cancel,
 'name-back-return':name+key+back+tap(250,28,20)+tap(250,28,20),
 'name-repeat':name+key+done+tap(250,172,218)+key+cancel+tap(250,172,218)+key+done,
 'name-navigation-home':name+key+home,
 'name-save-delayed':name+key+done,
 'name-rapid-repeat':name+tap(10,47,97,'text',release=4)+tap(4,47,97,'text',release=4)+done}
 for boundary in ('acquire','open','poll','close','release','kv-acquire','kv-get','kv-put','kv-release','acquire-fail'):
  result['name-loss-'+boundary]=name+key+done
 return result

def qualify(build,drivers,output,provider_system=None):
 record_path=build/'ble_scanner-build-record.json';r=json.loads(record_path.read_text());roots={k:Path(v) for k,v in r['source_roots'].items()}
 for k,v in r['source_sha256'].items():
  owner,relative=k.split(':',1);assert sha(roots[owner]/relative)==v,k
 assert sha(build/'ble_scanner.elf')==r['sha256'];output.mkdir(parents=True,exist_ok=False)
 system=provider_system or roots['system-apps'];runtime=roots['runtime']
 defines=[x for x in r['defines'] if x!='-flto'];includes=[x for x in r['command'] if x.startswith('-I')]
 app_sources=[Path(x) for x in r['command'] if x.endswith('.c') and not x.endswith(('portable_navigation.c','portable_sleep.c'))]
 fixture=ROOT/'tests/shared_keyboard/watch_scanner_host.c'
 fixture_sdk=output/'fixture-sdk';fixture_sdk.mkdir();shutil.copyfile(roots['utilities']/'lib/Bluetooth/include/RiscBluetoothSensorsV1.h',fixture_sdk/'RiscBluetoothSensorsV1.h')
 fixture_flags=['-I'+str(fixture_sdk),'-DBLE_WATCH_RENDER','-I'+str(system/'sdk/app'),'-I'+str(system/'Services/scene_profile'),'-I'+str(drivers/'sdk/driver')]
 svc_flags=['-I'+str(system/'Services/text_input'),'-I'+str(system/'sdk/app'),'-I'+str(system/'lib/PortableApps/include'),'-I'+str(runtime/'sdk/driver'),'-I'+str(system/'Services/scene_profile')]
 common=['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror']
 results=[];commands=[];dependencies={}
 for san in (False,True):
  out=output/('san' if san else 'normal');out.mkdir()
  extra=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie'] if san else []
  objects=[]
  sources=[(system/'Services/scene_host/host.c',svc_flags+['-DSCENE_HOST_TELEMETRY=0','-DSCENE_HOST_WATCH_240=1','-Dt5_driver_get=ble_scene_driver_get']),
           (system/'Services/text_input/host.c',svc_flags+['-Dt5_driver_get=ble_text_driver_get']),
           (system/'Services/scene_profile/profile.c',svc_flags+['-Dt5_driver_get=ble_profile_driver_get']),
           (drivers/'Drivers/ble_sensors/driver.c',['-I'+str(drivers/'sdk/driver'),'-I'+str(drivers/'Drivers/ble_sensors'),'-I'+str(runtime/'sdk/driver')]),
           (fixture,defines+[fixture_flags[0]]+includes+fixture_flags[1:]),*[(p,defines+includes) for p in app_sources]]
  for i,(source,flags) in enumerate(sources):
   obj=out/(str(i)+'.o');dep=out/(str(i)+'.d');objects.append(obj)
   cmd=[*common,*extra,*flags,'-MMD','-MF',str(dep),'-c',str(source),'-o',str(obj)];commands.append(cmd);subprocess.run(cmd,check=True)
   for path in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):dependencies[path]=sha(path)
  binary=out/'scanner';cmd=[*common,*extra,*map(str,objects),'-o',str(binary)];commands.append(cmd);subprocess.run(cmd,check=True)
  for name,actions in scenarios().items():
   folder=out/name;folder.mkdir();path=folder/'actions.txt';path.write_text(''.join(' '.join(map(str,row))+'\n' for row in actions))
   env={k:v for k,v in os.environ.items() if not k.startswith('BLE_RENDER_')};env.update(ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
   if name!='idle':env['BLE_RENDER_SCAN']='1'
   if name in ('nested-back','name-back-return'):env['BLE_RENDER_BACK']='1'
   if name=='name-navigation-home':env['BLE_RENDER_HOME']='1'
   if name.startswith('name-'):env['BLE_RENDER_NAME']=name[5:]
   if name in ('name-save-delayed','name-rapid-repeat'):env['BLE_RENDER_DELAY']='1'
   p=subprocess.run([str(binary),str(folder),str(path)],env=env,capture_output=True,text=True,timeout=30)
   (folder/'run.log').write_text(p.stdout+p.stderr)
   frames=list(folder.glob('frame-*.ppm'))
   results.append(dict(case=name,sanitized=san,passed=p.returncode==0,frames=len(frames),log_sha256=sha(folder/'run.log')))
   print('PASS' if p.returncode==0 else 'FAIL',san,name,flush=True)
   if p.returncode:print((p.stdout+p.stderr)[-2200:]);raise RuntimeError(str(folder/'run.log'))
 evidence=dict(schema=1,elf_sha256=r['sha256'],build_record_sha256=sha(record_path),actual_watch_defines=r['defines'],cases=results,commands=commands,source_sha256=dependencies,hardware_verified=False,scope='Production Watch Scanner, adapter, compact scene host, text host and BLE sensor driver; copied hardware transports and local navigation/sleep bridge boundaries')
 (output/'receipt.json').write_text(json.dumps(evidence,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--drivers',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--provider-system',type=Path);a=p.parse_args();qualify(a.build.resolve(),a.drivers.resolve(),a.output.resolve(),a.provider_system.resolve() if a.provider_system else None)

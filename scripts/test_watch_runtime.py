#!/usr/bin/env python3
"""Real Runtime/Graph, scene, exact Watch FT6336U; deterministic CPU and register cadence.

Only physical transports and display are modeled. No target latency claim.
"""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
from scene_sdk import stage_sdk
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['runtime','watch','utilities','output']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--touch-source',default='drivers/candidates/twatch_touch_022/driver.c');p.add_argument('--scene',type=Path,default=ROOT);p.add_argument('--sanitize',action='store_true');a=p.parse_args()
 runtime=a.runtime.resolve();watch=a.watch.resolve();utilities=a.utilities.resolve();out=a.output.resolve();scene=a.scene.resolve();out.mkdir(parents=True,exist_ok=True)
 source_files=[scene/'Services/scene_host/host.c',scene/'Services/scene_host/keyboard_paper.inc',watch/a.touch_source,utilities/'test/native_apps/hid_watch_touch_backend.c',runtime/'src/bootstrap/Runtime.cpp',runtime/'src/runtime/drivers/ProviderGraphV2.cpp',*[ROOT/'test'/name for name in ['runtime_test.cpp','watch_backend.c','runtime_app.c','provider.c']],Path(__file__).resolve()]
 source_hashes={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in source_files}
 (out/'compiled-source-hashes.json').write_text(json.dumps(source_hashes,indent=2)+'\n')
 inc=stage_sdk(runtime,scene,out/'sdk')
 for folder,names in [(watch/'sdk/driver',['RiscI2cBusV1.h','RiscGpioBankV1.h','RiscHardwareConfigV1.h'])]:
  for src in [folder/name for name in names]:
   dst=inc/src.name
   if dst.exists():assert dst.read_bytes()==src.read_bytes(),src
   else:shutil.copyfile(src,dst)
 flags=['-g','-O1','-Wall','-Wextra','-Werror'];san=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer'] if a.sanitize else []
 incs=['-I'+str(inc),'-I'+str(watch/'include')];cc=os.environ.get('CC','cc');env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'};commands=[]
 def command(args):
  commands.append(list(map(str,args)));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
  r=subprocess.run(args,capture_output=True,text=True,env=env)
  if r.returncode:
   (out/'failure.json').write_text(json.dumps({'args':commands[-1],'code':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n');raise RuntimeError(r.stderr)
  return r.stdout
 def build(src,name,extra=(),shared=True):command([cc,'-std=c11',*flags,*san,*incs,*extra,*(['-fPIC','-fvisibility=hidden','-shared'] if shared else ['-c']),str(src),'-o',str(out/name)])
 wrapper=out/'scene_instrumented.c';wrapper.write_text('#include '+json.dumps(str(scene/'Services/scene_host/host.c'))+'\nextern void scene_timing_cpu_pixel(void);\n__attribute__((no_instrument_function)) void __cyg_profile_func_enter(void*f,void*c){(void)c;if(f==(void*)pixel)scene_timing_cpu_pixel();}\n__attribute__((no_instrument_function)) void __cyg_profile_func_exit(void*f,void*c){(void)f;(void)c;}\n')
 build(wrapper,'scene.elf',['-finstrument-functions']);build(scene/'Services/scene_profile/profile.c','profile.elf',['-DSCENE_PROFILE_ID="profile"','-DSCENE_PROFILE_PAPER=0','-DSCENE_DISPLAY_ROTATION=0']);build(ROOT/'test/runtime_app.c','default.elf')
 providers=[('display','display.output'),('touch','input.touch.raw'),('nav','input.navigation')]
 for name,cap in providers:build(ROOT/'test/provider.c',name+'.elf',[f'-DTEST_ID="{name}"',f'-DTEST_CAP="{cap}"'])
 build(watch/a.touch_source,'watch.o',[],False)
 build(ROOT/'test/watch_backend.c','backend.o',['-I'+str(utilities/'test/native_apps')],False)
 def write(n,d):(out/n).write_text(json.dumps(d,indent=2)+'\n')
 def req(c):return {'capability':c,'api':1}
 def manifest(n,c):return {'type':'driver','id':n,'version':'0.1.0','driver_abi':2,'architecture':'xtensa-esp32s3','file_name':n+'.elf','requires':[],'provides':[req(c)]}
 for n,c in providers:write(n+'.json',manifest(n,c))
 m=json.loads((scene/'Services/scene_host/manifest.json').read_text());m['file_name']='scene.elf';write('scene.json',m);write('profile.json',manifest('profile','ui.presentation-profile'))
 write('board.json',{'schema':'riscrte.board-hardware','schema_version':1,'board_id':'test','revision':'unspecified','buses':[],'devices':[]})
 write('default.json',{'type':'application','id':'default','version':'0.1.0','architecture':'xtensa-esp32s3','file_name':'default.elf','entry':'app_main','requires':[req('ui.scene')]})
 write('boot.json',{'board':'board.json','default_app':'default.elf','provider_activation':'eager','drivers':[{'manifest':n+'.json'} for n in ['scene','profile',*[x[0] for x in providers]]],'app_capabilities':[{'manifest':'default.json','grants':[{**req('ui.scene'),'instance_id':0}]}]})
 sources=['bootstrap/Json.cpp','bootstrap/Board.cpp','bootstrap/Runtime.cpp','runtime/streams/AppStreamSessions.cpp','runtime/streams/ProviderQueueHost.cpp','runtime/drivers/ProviderGraphV2.cpp','runtime/drivers/ProviderModuleV2.cpp']
 command([os.environ.get('CXX','c++'),'-std=c++17',*flags,*san,'-Wno-missing-field-initializers','-O0','-fno-pie','-no-pie','-rdynamic',*incs,'-I'+str(runtime/'src'),'-I'+str(runtime/'lib/ArduinoJson/src'),'-I'+str(runtime/'test/drivers/stubs'),*[str(runtime/'src'/x) for x in sources],str(ROOT/'test/runtime_test.cpp'),str(out/'watch.o'),str(out/'backend.o'),'-ldl','-o',str(out/'test')])
 results=[]
 cases=[(200,600),(133,180),(80,180),(60,180)]
 for cost in [0,500]:
  for delay in [1,17,2300]:
   for period,count in cases:
    for same in [0,1,2]:
     expected=True
     output=command([str(out/'test'),str(out),str(delay),str(cost),str(period),str(count),str(same),str(int(expected)),str(5)]).strip();print(output,flush=True);results.append(output)
 if True:
  # Actual FT6336U reports split header DOWN/UP across multiple scene polls;
  # keyboard Back/Home and ordinary-scene Back/Home keep their own contacts.
  for cost in [0,500]:
   for delay in [1,17,2300]:
    for mode in [3,4,5,6]:
     output=command([str(out/'test'),str(out),str(delay),str(cost),'200','12',str(mode),'1',str(5)]).strip();print(output,flush=True);results.append(output)
 proof={'cases':results,'sanitized':a.sanitize,'source_sha256':source_hashes,'limits':['Physical Watch FT6336U reports are simulated: latest state refreshed by an independent 5ms controller scan, read coherently as 13 register bytes; no physical device used.','Per-pixel virtual CPU cost and display transfer slices are explicit test loads, not measurements.','Real Runtime/Graph controls app/scene/profile lifetimes; thin touch fixture owns exact FT6336U start/quiesce and its strict GPIO/I2C dependencies. Current shared Runtime qualification, not a rebuilt selected Watch product.']}
 assert source_hashes=={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in source_files},'Source changed during qualification'
 (out/'qualification.json').write_text(json.dumps(proof,indent=2)+'\n')
if __name__=='__main__':main()

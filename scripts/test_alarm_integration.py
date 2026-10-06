#!/usr/bin/env python3
"""Focused production Clock/adapter/retained-app host checks for explicit alarms."""
import argparse,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--system-apps',type=Path,required=True);p.add_argument('--utilities',type=Path,required=True);a=p.parse_args()
system,utilities=a.system_apps.resolve(),a.utilities.resolve()
out=ROOT/'dist/alarm-tests';out.mkdir(parents=True,exist_ok=True)
incs=['-I'+str(x) for x in [system/'lib/PortableApps/include',system/'lib/NativeApps/include',ROOT,ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include']]
for mode,sanitize in [('plain',[]),('san',['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie'])]:
 for name in ('alarm_sleep','motion_client','alarm_clock','retained_calculator','retained_stopwatch'):
  sources=[ROOT/'tests'/(name+'_test.c')];defines=[]
  if name.startswith('retained_'):
   app=name.removeprefix('retained_');sources=[system/'Apps/settings.c',ROOT/'tests/retained_alarm_apps_test.c']
   defines=['-DPORTABLE_SETTINGS_FIXTURE="'+str(system/'test/native_apps/portable_settings_test.c')+'"','-DUTILITIES_APP_SOURCE="'+str(utilities/'Apps'/f'{app}.c')+'"']
   if app=='calculator':defines.append('-DTEST_CALCULATOR')
  exe=out/(name+'-'+mode)
  subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O1','-Wall','-Wextra','-Werror',*sanitize,*incs,*defines,*map(str,sources),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True,timeout=30)
print('Alarm production foreground models and owned sleep controls passed; hardware remains unqualified')

exe=out/'alarm-render';frames=out/'frames';frames.mkdir(exist_ok=True)
subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O1','-Wall','-Wextra','-Werror','-fsanitize=undefined',*incs,str(ROOT/'tests/alarm_render_test.c'),str(ROOT/'apps/clock/nova/nova.c'),'-o',str(exe)],check=True)
subprocess.run([str(exe),str(frames)],check=True)

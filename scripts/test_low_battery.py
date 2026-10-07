#!/usr/bin/env python3
"""Real Clock/Hybrid adapter regressions, with the staged shared policy source."""
from pathlib import Path
import argparse,os,subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--system-apps',type=Path,required=True);a=p.parse_args();system=a.system_apps.resolve()
assert (ROOT/'apps/clock/PortableSleepPolicy.h').read_bytes()==(system/'lib/PortableApps/include/PortableSleepPolicy.h').read_bytes()
out=ROOT/'dist/low-battery-tests';out.mkdir(parents=True,exist_ok=True)
for san in (False,True):
 flags=['-O1','-g','-Wall','-Wextra','-Werror','-DPORTABLE_LOW_BATTERY','-DWATCH_QUICK_RADIOS',*['-I'+str(p) for p in (system/'lib/PortableApps/include',ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include',ROOT)]]
 if san:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
 objects=[]
 for i,source in enumerate([ROOT/'tests/low_battery_clock_test.c',ROOT/'apps/clock/nova/nova.c',*[system/'lib/PortableApps/src'/n for n in ('quick_actions.c','quick_render.c','quick_session.c','quick_radios.c')]]):
  obj=out/f'{int(san)}-{i}.o';subprocess.run([os.environ.get('CC','cc'),'-std=c11',*flags,'-c',str(source),'-o',str(obj)],check=True);objects.append(str(obj))
 exe=out/f'clock-{int(san)}';subprocess.run([os.environ.get('CXX','c++'),'-std=c++11',*flags,str(ROOT/'apps/clock/effects/boot.cpp'),*objects,'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
for san in (False,True):
 flags=['-std=c11','-O1','-Wall','-Wextra','-Werror','-DPORTABLE_LOW_BATTERY',*['-I'+str(p) for p in (ROOT,ROOT/'include',ROOT/'sdk/app',ROOT/'sdk/driver',system/'lib/PortableApps/include')]]
 if san:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
 exe=out/f'alarm-{int(san)}'
 subprocess.run([os.environ.get('CC','cc'),*flags,str(ROOT/'tests/low_battery_alarm_test.c'),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))

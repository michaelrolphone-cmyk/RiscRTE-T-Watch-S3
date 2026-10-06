#!/usr/bin/env python3
from pathlib import Path
import argparse,os,subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--system-apps',type=Path,required=True);a=p.parse_args();system=a.system_apps.resolve();out=ROOT/'dist/quick-clock';out.mkdir(parents=True,exist_ok=True)
for radios in (False,True):
 for san in (False,True):
  flags=['-O1','-g','-Wall','-Wextra','-Werror',*['-I'+str(p) for p in (system/'lib/PortableApps/include',ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include',ROOT)]]
  if radios:flags+=['-DWATCH_QUICK_RADIOS']
  if san:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
  objects=[]
  for i,src in enumerate([ROOT/'tests/quick_clock_test.c',ROOT/'apps/clock/nova/nova.c',*[system/'lib/PortableApps/src'/n for n in ('quick_actions.c','quick_render.c','quick_session.c','quick_radios.c')]]):
   obj=out/f'{int(san)}-{i}.o';subprocess.run([os.environ.get('CC','cc'),'-std=c11',*flags,'-c',str(src),'-o',str(obj)],check=True);objects.append(str(obj))
  exe=out/f'quick-clock-{int(san)}-{int(radios)}';subprocess.run([os.environ.get('CXX','c++'),'-std=c++11',*flags,str(ROOT/'apps/clock/effects/boot.cpp'),*objects,'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True,timeout=30,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))

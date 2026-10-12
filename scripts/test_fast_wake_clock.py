#!/usr/bin/env python3
"""Exercise actual opt-in Watch Clock with modeled peripheral boundaries."""
from pathlib import Path
import argparse, os, subprocess
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--system-apps',type=Path,required=True);p.add_argument('--utilities',type=Path,required=True);a=p.parse_args()
out=root/'dist/fast-wake-clock';out.mkdir(parents=True,exist_ok=True)
for sanitize in (False,True):
 flags=['-DWATCH_FAST_WAKE','-O1','-g','-Wall','-Wextra','-Werror',*['-I'+str(x) for x in (a.system_apps/'lib/PortableApps/include',a.utilities/'lib/Contexts/include',a.utilities/'lib/Alarm/include',root/'sdk/app',root/'sdk/driver',root/'include',root)]]
 if sanitize:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
 objects=[]
 for i,source in enumerate([root/'tests/fast_wake_clock_test.c',root/'apps/clock/nova/nova.c',*[a.system_apps/'lib/PortableApps/src'/n for n in ('quick_actions.c','quick_render.c','quick_session.c','quick_radios.c')]]):
  obj=out/f'{int(sanitize)}-{i}.o';subprocess.run([os.environ.get('CC','cc'),'-std=c11',*flags,'-c',str(source),'-o',str(obj)],check=True);objects.append(str(obj))
 binary=out/f'test-{int(sanitize)}';subprocess.run([os.environ.get('CXX','c++'),'-std=c++11',*flags,str(root/'apps/clock/effects/boot.cpp'),*objects,'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True,timeout=60,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

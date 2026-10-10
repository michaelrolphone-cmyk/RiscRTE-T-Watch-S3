#!/usr/bin/env python3
from pathlib import Path
import argparse,os,subprocess
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--system-apps',type=Path,required=True);a=p.parse_args();system=a.system_apps.resolve()
out=root/'dist/contexts-clock';out.mkdir(parents=True,exist_ok=True)
for san in (False,True):
 flags=['-DWATCH_CONTEXTS_CLIENT','-O1','-g','-Wall','-Wextra','-Werror',*['-I'+str(x) for x in (system/'lib/PortableApps/include',root/'sdk/app',root/'sdk/driver',root/'include',root)]]
 if san:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
 objects=[]
 for i,src in enumerate([root/'tests/contexts_clock_test.c',root/'apps/clock/nova/nova.c',*[system/'lib/PortableApps/src'/n for n in ('quick_actions.c','quick_render.c','quick_session.c','quick_radios.c')]]):
  obj=out/f'{int(san)}-{i}.o';subprocess.run([os.environ.get('CC','cc'),'-std=c11',*flags,'-c',str(src),'-o',str(obj)],check=True);objects.append(str(obj))
 binary=out/f'test-{int(san)}';subprocess.run([os.environ.get('CXX','c++'),'-std=c++11',*flags,str(root/'apps/clock/effects/boot.cpp'),*objects,'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True,timeout=30)

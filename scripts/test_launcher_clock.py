#!/usr/bin/env python3
from pathlib import Path
import os,subprocess
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'dist/launcher-tests';out.mkdir(parents=True,exist_ok=True)
flags=['-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',*['-I'+str(ROOT/p) for p in ('sdk/app','sdk/driver','include','.')]]
objects=[]
for src in ('tests/launcher_app_test.c','apps/clock/nova/nova.c'):
 obj=out/(Path(src).stem+'.o');subprocess.run([os.environ.get('CC','cc'),'-std=c11',*flags,'-c',str(ROOT/src),'-o',str(obj)],check=True);objects.append(str(obj))
exe=out/'launcher-clock'
subprocess.run([os.environ.get('CXX','c++'),'-std=c++11',*flags,str(ROOT/'apps/clock/effects/boot.cpp'),*objects,'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True,timeout=30)

for test in ('launcher-return','clock-touch-latency'):
 source='tests/launcher_app_test.c' if test=='launcher-return' else 'tests/clock_touch_latency_test.c'
 obj=out/(test+'.o')
 subprocess.run([os.environ.get('CC','cc'),'-std=c11',*flags,'-DWATCH_CLOCK_RETURN','-c',str(ROOT/source),'-o',str(obj)],check=True)
 exe=out/test
 subprocess.run([os.environ.get('CXX','c++'),'-std=c++11',*flags,str(ROOT/'apps/clock/effects/boot.cpp'),str(out/'nova.o'),str(obj),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,timeout=30)

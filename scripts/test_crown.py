#!/usr/bin/env python3
"""Real copied effects and crown app lifecycle under UBSan; no device access."""
from pathlib import Path
import subprocess,os
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'dist/crown-tests';out.mkdir(parents=True,exist_ok=True)
common=['-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',*['-I'+str(ROOT/p) for p in ('sdk/app','sdk/driver','include','.')]]
objects=[]
for src in ('apps/clock/crown.c','apps/clock/render.c','apps/clock/effects/ripple.c','tests/crown_app_test.c'):
 obj=out/(Path(src).stem+'.o');subprocess.run([os.environ.get('CC','cc'),'-std=c11',*common,'-c',str(ROOT/src),'-o',str(obj)],check=True);objects.append(str(obj))
for name,sources in [('crown',objects),('effects',[str(ROOT/'tests/clock_effects_test.cpp'),str(out/'ripple.o')])]:
 exe=out/name
 subprocess.run([os.environ.get('CXX','c++'),'-std=c++11',*common,str(ROOT/'apps/clock/effects/boot.cpp'),*sources,'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,timeout=30)

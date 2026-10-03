#!/usr/bin/env python3
"""Real copied effects and crown app lifecycle under UBSan; no device access."""
from pathlib import Path
import subprocess,os
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'dist/crown-tests';out.mkdir(parents=True,exist_ok=True)
common=['-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',*['-I'+str(ROOT/p) for p in ('sdk/app','sdk/driver','include','.')]]
objects=[]
for src in ('apps/clock/crown.c','apps/clock/nova/nova.c','apps/clock/effects/ripple.c','tests/crown_app_test.c'):
 obj=out/(Path(src).stem+'.o');subprocess.run([os.environ.get('CC','cc'),'-std=c11',*common,*(['-Dnova_watch_render=test_nova_watch_render','-Dwatch_boot_render=test_watch_boot_render','-Dwatch_ripple_render=test_watch_ripple_render','-Dmalloc=test_clock_malloc','-Dfree=test_clock_free'] if src=='apps/clock/crown.c' else []),'-c',str(ROOT/src),'-o',str(obj)],check=True);objects.append(str(obj))
for name,sources in [('crown',objects),('effects',[str(ROOT/'tests/clock_effects_test.cpp'),str(out/'ripple.o')])]:
 exe=out/name
 subprocess.run([os.environ.get('CXX','c++'),'-std=c++11',*common,str(ROOT/'apps/clock/effects/boot.cpp'),*sources,'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,timeout=30)

exe=out/'division'
subprocess.run([os.environ.get('CC','cc'),'-std=c11',*common,str(ROOT/'apps/clock/effects/divdi3.c'),str(ROOT/'tests/effects_division_test.c'),'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True,timeout=10)

exe=out/'display-time'
subprocess.run([os.environ.get('CC','cc'),'-std=c11',*common,str(ROOT/'tests/clock_display_time_test.c'),'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True,timeout=10)

subprocess.run([os.environ.get('PYTHON','python3'),str(ROOT/'scripts/test_clock_timezone.py')],check=True,timeout=30)

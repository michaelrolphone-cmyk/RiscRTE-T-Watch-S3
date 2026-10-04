#!/usr/bin/env python3
"""Exercise shared recurrence projection and actual Clock loading/lifecycle."""
import argparse,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--system-apps',type=Path,required=True);p.add_argument('--utilities',type=Path,required=True);a=p.parse_args()
s,u=a.system_apps.resolve(),a.utilities.resolve();out=ROOT/'dist/points-integration-tests';out.mkdir(parents=True,exist_ok=True)
incs=['-I'+str(x) for x in [s/'lib/PortableApps/include',s/'lib/NativeApps/include',u/'lib/Alarm/include',ROOT,ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include']]
for mode,flags in [('normal',[]),('san',['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie'])]:
 for denver in [False,True]:
  exe=out/('projection-'+mode+str(int(denver)))
  subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O1','-Wall','-Wextra','-Werror',*flags,*incs,*(['-DPORTABLE_RTC_UTC8_DENVER'] if denver else []),str(ROOT/'tests/points_projection_test.c'),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True,timeout=30)
 exe=out/('clock-'+mode)
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O1','-Wall','-Wextra','-Werror',*flags,*incs,'-DWATCH_CLOCK_POINTS','-DPORTABLE_RTC_UTC8_DENVER',str(ROOT/'tests/alarm_clock_test.c'),str(ROOT/'apps/clock/points_projection.c'),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,timeout=45)
print('Points projection and real Clock configuration reads/hold/retained/picker regressions passed')

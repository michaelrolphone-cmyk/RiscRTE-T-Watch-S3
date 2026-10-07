#!/usr/bin/env python3
"""Current Watch/service sleep boundary with two independent clocks."""
import argparse,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument('--system-apps',type=Path,required=True)
p.add_argument('--utilities',type=Path,required=True)
p.add_argument('--runtime',type=Path,required=True)
a=p.parse_args();system=a.system_apps.resolve();utilities=a.utilities.resolve();runtime=a.runtime.resolve()
out=ROOT/'dist/alarm-sleep-resume';out.mkdir(parents=True,exist_ok=True)
headers=[system/'lib/PortableApps/include/AlarmServiceV1.h',utilities/'lib/Alarm/include/AlarmServiceV1.h']
assert headers[0].read_bytes()==headers[1].read_bytes(),'Alarm API copies differ'
assert b'ALARM_SERVICE_SLEEP_RESUME_SUPPORTED' in headers[0].read_bytes(),'Current sleep boundary header missing'
includes=[ROOT,ROOT/'include',ROOT/'sdk/app',ROOT/'sdk/driver',runtime/'sdk/driver',runtime/'sdk/hardware',utilities/'lib/Alarm/include',system/'lib/PortableApps/include']
for mode,sanitize in [('plain',[]),('san',['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie'])]:
 for name in ('alarm_resume_client','alarm_resume_service'):
  defines=[];objects=[]
  if name.endswith('service'):
   defines=['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER','-DALARM_VOLUME_CONTROL','-DALARM_DND_CONTROL']
   obj=out/('service-'+mode+'.o')
   subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O1','-Wall','-Wextra','-Werror',*sanitize,*defines,*['-I'+str(d) for d in includes],'-c',str(utilities/'Services/alarm_service/service.c'),'-o',str(obj)],check=True)
   objects=[str(obj)]
  exe=out/(name+'-'+mode)
  subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O1','-Wall','-Wextra','-Werror',*sanitize,*defines,*['-I'+str(d) for d in includes],str(ROOT/'tests'/(name+'_test.c')),*objects,'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True,timeout=30)
print('Current Watch + real alarm service resume boundary passed; physical qualification remains pending')

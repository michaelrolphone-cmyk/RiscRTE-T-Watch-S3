#!/usr/bin/env python3
"""Build explicit Wi-Fi Settings plus the complete Points development baseline."""
import argparse,json,hashlib
from pathlib import Path
from build_launcher_apps import build,ROOT
from build_alarm_apps import build_service
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for name in ('system-apps','utilities','runtime','productivity'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();s,u,r,p=(getattr(a,n).resolve() for n in ('system_apps','utilities','runtime','productivity'))
 build(s,u,alarms=True,runtime=r,productivity=p,wifi=True)
 build_service(s,u,r,points=True,wifi=True)

 baseline=json.loads((ROOT/'apps/wifi-preserved-elf-baseline.json').read_text())
 for name,expected in baseline['apps'].items():
  data=(ROOT/'dist/wifi-launcher'/name).read_bytes()
  if len(data)!=expected['size_bytes'] or hashlib.sha256(data).hexdigest()!=expected['sha256']:
   raise ValueError('Wi-Fi unexpectedly changed a delivered executable: '+name)
 print('Ten unrelated delivered app/service ELF files remain byte-identical')

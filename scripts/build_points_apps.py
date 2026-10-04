#!/usr/bin/env python3
"""Explicit Points in Time development deployment; no device operations."""
import argparse
from pathlib import Path
from build_launcher_apps import build
from build_alarm_apps import build_service
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for name in ('system-apps','utilities','runtime','productivity'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();system,utilities,runtime,productivity=(getattr(a,n).resolve() for n in ('system_apps','utilities','runtime','productivity'))
 build(system,utilities,alarms=True,runtime=runtime,productivity=productivity)
 build_service(system,utilities,runtime,points=True)

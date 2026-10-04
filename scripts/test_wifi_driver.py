#!/usr/bin/env python3
"""Production station driver failure/cancellation tests; never opens a network."""
import os, subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'dist/wifi-tests';out.mkdir(parents=True,exist_ok=True)
for mode,flags in [('normal',[]),('san',['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie'])]:
 target=out/('wifi-driver-'+mode)
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',*flags,'-I'+str(root/'sdk/driver'),'-I'+str(root/'include'),str(root/'tests/wifi_driver_test.c'),'-o',str(target)],check=True)
 subprocess.run([str(target)],check=True,timeout=30)

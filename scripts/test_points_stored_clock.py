#!/usr/bin/env python3
"""Prove legacy final-image failure and current Clock compatibility, no migration."""
import argparse, os, subprocess, tempfile, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
for n in ('system-apps','utilities','productivity','legacy-utilities'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();s,u,prod,old=[getattr(a,n).resolve() for n in ('system_apps','utilities','productivity','legacy_utilities')]
def run(cmd):subprocess.run(list(map(str,cmd)),check=True)
with tempfile.TemporaryDirectory(prefix='points-stored-clock-') as temp:
    out=Path(temp);cc=os.environ.get('CC','cc')
    common=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie','-DPORTABLE_RTC_UTC8_DENVER']
    inc=['-I'+str(x) for x in (s/'lib/PortableApps/include',s/'lib/NativeApps/include',ROOT,ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include',prod/'Apps')]
    run([cc,*common,*inc,'-I'+str(u/'lib/Alarm/include'),ROOT/'tests/points_store_fixture.c','-o',out/'writer'])
    for label,path in [('old',old),('current',u)]:
        run([cc,*common,*inc,'-I'+str(path/'lib/Alarm/include'),ROOT/'tests/points_stored_clock_test.c',ROOT/'apps/clock/points_projection.c','-o',out/label])
    for mode in ('legacy','flags','custom'):
        directory=out/mode;directory.mkdir();run([out/'writer',directory,mode])
        before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in directory.iterdir()}
        run([out/'old',directory,'ready' if mode=='legacy' else 'error'])
        run([out/'current',directory,'ready'])
        assert before=={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in directory.iterdir()},'Clock rewrote saved data'
print('Old Clock rejects new flags/custom records; current Clock reads all records without changing saved bytes (ASan/UBSan).')

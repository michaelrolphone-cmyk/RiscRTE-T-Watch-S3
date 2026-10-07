#!/usr/bin/env python3
"""Link real Waterfall source to the actual Runtime logger and existing USB shim."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument('--utilities',type=Path,default=ROOT)
p.add_argument('--system-apps',type=Path,required=True)
p.add_argument('--runtime',type=Path,required=True)
p.add_argument('--output',type=Path,default=ROOT/'build'/'waterfall-serial')
a=p.parse_args()
utilities=a.utilities.resolve();system=a.system_apps.resolve();runtime=a.runtime.resolve()
for sanitizer in (False,True):
    out=a.output.resolve()/('sanitized' if sanitizer else 'normal');out.mkdir(parents=True,exist_ok=True)
    flags=['-O1','-g','-Wall','-Wextra','-Werror']
    if sanitizer:
        flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
    objects=[]
    for index,source in enumerate((ROOT/'tests/waterfall_runtime_diagnostics.cpp',runtime/'src/ports/esp32s3/SleepDiagnostics.cpp')):
        obj=out/f'diagnostics-{index}.o';objects.append(obj)
        subprocess.run([os.environ.get('CXX','c++'),'-std=c++17',*flags,'-DRISC_SLEEP_DIAGNOSTICS=1',
            '-I'+str(runtime/'src'),'-I'+str(runtime/'test/diagnostic_shim'),'-c',str(source),'-o',str(obj)],check=True)
    exe=out/'waterfall-serial'
    subprocess.run([os.environ.get('CC','cc'),'-std=c11',*flags,'-DPORTABLE_RETURN_APP="springboard.elf"',
        '-I'+str(utilities/'Apps'),'-I'+str(utilities/'lib/NativeApps/include'),
        '-I'+str(system/'lib/PortableApps/include'),str(ROOT/'tests/waterfall_serial_test.c'),
        *map(str,objects),'-lstdc++','-o',str(exe)],check=True)
    for mode in ('connected','absent','full'):
        for exit_mode in ('return','back'):
            folder=out/f'{mode}-{exit_mode}';folder.mkdir(exist_ok=True)
            result=subprocess.run([str(exe),str(folder),mode,exit_mode],check=True,capture_output=True,text=True,
                env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'),timeout=30)
            (folder/'result.txt').write_text(result.stdout+result.stderr)
            print(('ASAN+UBSAN' if sanitizer else 'normal')+': '+result.stdout,end='')
print('Waterfall Runtime serial path: 12 scenarios passed; no physical USB/hardware qualification claimed.')

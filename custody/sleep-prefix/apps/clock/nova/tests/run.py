#!/usr/bin/env python3
"""Portable renderer checks. Run from any directory; writes only dist/nova-tests."""
from pathlib import Path
import subprocess, os
ROOT=Path(__file__).resolve().parents[4]
NOVA=ROOT/'apps/clock/nova'
OUT=ROOT/'dist/nova-tests';OUT.mkdir(parents=True,exist_ok=True)
flags=['-std=c11','-O2','-Wall','-Wextra','-Werror']
includes=[f'-I{ROOT/p}' for p in ['sdk/app','sdk/driver','include','apps/clock/nova']]
for name in ['test','frame']:
    subprocess.run([os.environ.get('CC','cc'),*flags,*includes,str(NOVA/'nova.c'),str(NOVA/'tests'/f'{name}.c'),'-o',str(OUT/name)],check=True)
subprocess.run([str(OUT/'test')],check=True)
# ASan/UBSan cover shifts, narrow buffers and all animation paths exercised above.
subprocess.run([os.environ.get('CC','cc'),*flags,'-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',*includes,str(NOVA/'nova.c'),str(NOVA/'tests/test.c'),'-o',str(OUT/'sanitized')],check=True)
# This hosted runner is traced; LeakSanitizer cannot run under ptrace. The
# renderer allocates nothing; retain AddressSanitizer and UB checks.
subprocess.run([str(OUT/'sanitized')],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))

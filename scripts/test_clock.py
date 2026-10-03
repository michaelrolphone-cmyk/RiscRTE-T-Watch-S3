#!/usr/bin/env python3
"""Actual clock source against bounded host services; UBSan, no hardware."""
import os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
common=[os.environ.get('CC','clang'),'-std=c11','-Wall','-Wextra','-Werror',
        '-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'sdk/app'),
        '-I'+str(ROOT/'sdk/driver'),'-I'+str(ROOT/'include'),'-I'+str(ROOT)]
(ROOT/'dist').mkdir(exist_ok=True)
for test in ('render','app'):
    sources=[str(ROOT/'apps/clock/render.c'),str(ROOT/f'tests/clock_{test}_test.c')]
    if test=='app':sources.append(str(ROOT/'apps/clock/main.c'))
    out=ROOT/'dist'/f'test-clock-{test}'
    subprocess.run(common+sources+['-o',str(out)],check=True)
    subprocess.run([str(out)],check=True)
print('Clock render/calendar/bounds and app grant/frame/error/timeout tests passed (UBSan)')

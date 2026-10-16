#!/usr/bin/env python3
"""Regress real Home gestures during modeled raster work and at input boundaries.

The target is actual production Clock and NOVA code, with fake device APIs.
No modeled duration is a hardware timing claim. --source-root permits running
this test against a preserved predecessor without modifying that source tree.
"""
from pathlib import Path
import argparse
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--system-apps', type=Path, required=True)
p.add_argument('--utilities', type=Path, required=True)
p.add_argument('--source-root', type=Path, default=ROOT)
p.add_argument('--output', type=Path, default=ROOT / 'dist/clock-raster-gestures')
p.add_argument('--expect-loss', action='store_true')
p.add_argument('--mode', choices=('normal', 'sanitized', 'both'), default='both')
a = p.parse_args()
source_root = a.source_root.resolve()
a.output.mkdir(parents=True, exist_ok=True)
for sanitize in ((False, True) if a.mode == 'both' else (a.mode == 'sanitized',)):
    label = 'sanitized' if sanitize else 'normal'
    out = a.output / label
    out.mkdir(parents=True, exist_ok=True)
    flags = ['-DWATCH_FAST_WAKE', '-DPORTABLE_RTC_UTC8_DENVER', '-O1', '-g',
             '-Wall', '-Wextra', '-Werror']
    if a.expect_loss:
        flags += ['-DWATCH_RASTER_EXPECT_LOSS']
    for include in (a.system_apps / 'lib/PortableApps/include',
                    a.utilities / 'lib/Contexts/include',
                    a.utilities / 'lib/Alarm/include', source_root / 'sdk/app',
                    source_root / 'sdk/driver', source_root / 'include', source_root):
        flags += ['-I' + str(include)]
    if sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                  '-fno-omit-frame-pointer', '-no-pie']
    sources = [ROOT / 'tests/clock_raster_gesture_test.c',
               source_root / 'apps/clock/nova/nova.c',
               source_root / 'apps/clock/points_projection.c']
    sources += [a.system_apps / 'lib/PortableApps/src' / name for name in
                ('quick_actions.c', 'quick_render.c', 'quick_session.c', 'quick_radios.c')]
    objects = []
    for i, source in enumerate(sources):
        obj = out / f'{i}.o'
        # The test defines its feature flags internally. Other translation units
        # must retain the target's Contexts callback layout and quick UI profile.
        extra = ['-DWATCH_CONTEXTS_CLIENT'] if i else []
        subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', *flags, *extra,
                        '-c', str(source), '-o', str(obj)], check=True)
        objects.append(str(obj))
    binary = out / 'test'
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++11', *flags,
                    str(source_root / 'apps/clock/effects/boot.cpp'), *objects,
                    '-o', str(binary)], check=True)
    result = subprocess.run([str(binary)], text=True, capture_output=True,
                            env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'}, timeout=120)
    (out / 'stdout.txt').write_text(result.stdout)
    (out / 'stderr.txt').write_text(result.stderr)
    print(result.stdout, end='')
    print(result.stderr, end='')
    result.check_returncode()
    print(f'{label}: PASS')

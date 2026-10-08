#!/usr/bin/env python3
"""Production local sleep adapter in legacy/current/low-battery build modes."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--system-apps', type=Path, required=True)
    args = parser.parse_args()
    includes = [args.system_apps.resolve() / 'lib/PortableApps/include',
                ROOT / 'sdk/app', ROOT / 'sdk/driver', ROOT / 'include', ROOT]
    out = ROOT / 'dist/portable-sleep-lifecycle'
    out.mkdir(parents=True, exist_ok=True)
    for alarm in (False, True):
        for low_battery in (False, True):
            flags = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                     '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                     '-fno-omit-frame-pointer', '-no-pie']
            if alarm:
                flags += ['-DPORTABLE_ALARM_CLIENT', '-DWATCH_ALARM_SLEEP_RESUME']
            if low_battery:
                flags += ['-DPORTABLE_LOW_BATTERY', '-DPORTABLE_QUICK_ACTIONS']
            exe = out / f'adapter-{int(alarm)}-{int(low_battery)}'
            subprocess.run([os.environ.get('CC', 'cc'), *flags,
                            *['-I' + str(path) for path in includes],
                            str(ROOT / 'tests/portable_sleep_lifecycle_test.c'),
                            '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=30,
                           env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'))

if __name__ == '__main__':
    main()

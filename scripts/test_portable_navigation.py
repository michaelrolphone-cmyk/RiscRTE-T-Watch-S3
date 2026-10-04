#!/usr/bin/env python3
"""Test Watch app-local key navigation using the existing PMU ABI prefix."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--system-apps', required=True, type=Path)
args = parser.parse_args()
system = args.system_apps.resolve()
binary = ROOT / 'dist/launcher-tests/portable-navigation'
binary.parent.mkdir(parents=True, exist_ok=True)
subprocess.run([
    os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
    '-fsanitize=undefined', '-fno-sanitize-recover=all',
    '-DPORTABLE_INPUT_NAVIGATION_LOCAL',
    '-I' + str(system / 'lib/PortableApps/include'),
    '-I' + str(ROOT / 'sdk/driver'), '-I' + str(ROOT / 'include'),
    str(ROOT / 'apps/clock/portable_navigation.c'),
    str(ROOT / 'tests/portable_navigation_test.c'), '-o', str(binary)
], check=True, timeout=60)
subprocess.run([str(binary)], check=True, timeout=10)

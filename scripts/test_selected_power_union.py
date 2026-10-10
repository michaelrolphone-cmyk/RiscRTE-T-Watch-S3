#!/usr/bin/env python3
"""Requalify recovered Watch power source with one explicit current SDK.

This source-only host proof does not select a product profile or change frozen
Watch pins. The canonical policy is included before the legacy local copy;
the existing guard then suppresses only that duplicate. Alarm sleep uses the
completed resume-suffix header, never the System checkout's legacy copy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
for name in ('system', 'runtime', 'alarm-source', 'output'):
    p.add_argument('--' + name, type=Path, required=True)
p.add_argument('--watch', type=Path, help='Explicit recovered Watch checkout; defaults to this repository')
a = p.parse_args()
watch = (a.watch or Path(__file__).resolve().parents[1]).resolve()
system, runtime, alarm = a.system.resolve(), a.runtime.resolve(), a.alarm_source.resolve()
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
sdk = out / 'sdk'
shutil.copytree(system / 'lib/PortableApps/include', sdk)
alarm_header = alarm / 'lib/Alarm/include/AlarmServiceV1.h'
assert b'ALARM_SERVICE_SLEEP_RESUME_SUPPORTED' in alarm_header.read_bytes()
shutil.copy2(alarm_header, sdk / 'AlarmServiceV1.h')
for name in ('RiscRuntimeV1.h', 'RiscKeyValueV1.h'):
    assert (sdk / name).read_bytes() == (runtime / 'sdk/app' / name).read_bytes(), name
policy = sdk / 'PortableSleepPolicy.h'
assert b'portable_sleep_load_profile' in policy.read_bytes()
prefix = sdk / 'WatchSelectedSleepPolicy.h'
prefix.write_text('#include "PortableSleepPolicy.h"\n'
                  '#ifndef PORTABLE_SLEEP_POLICY_H\n#define PORTABLE_SLEEP_POLICY_H\n#endif\n')
commands, results = [], []
env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1')
cc, cxx = os.environ.get('CC', 'cc'), os.environ.get('CXX', 'c++')
includes = [sdk, watch / 'sdk/app', watch / 'sdk/driver', watch / 'include', watch,
            runtime / 'sdk/driver', runtime / 'sdk/hardware']
base = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-include', str(prefix),
        *['-I' + str(x) for x in includes]]

def command(args):
    commands.append(args)
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    (out / ('command-%03d.log' % len(commands))).write_text(r.stdout + r.stderr)
    if r.returncode:
        raise RuntimeError((args, r.returncode, r.stdout, r.stderr))
    return r

for sanitized in (False, True):
    flags = base + (['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-fno-omit-frame-pointer', '-no-pie'] if sanitized else [])
    for alarms in (False, True):
        for battery in (False, True):
            name = f'sleep-{int(sanitized)}-{int(alarms)}-{int(battery)}'
            defines = (['-DPORTABLE_ALARM_CLIENT', '-DWATCH_ALARM_SLEEP_RESUME'] if alarms else [])
            defines += ['-DPORTABLE_LOW_BATTERY', '-DPORTABLE_QUICK_ACTIONS'] if battery else []
            exe = out / name
            command([cc, '-std=c11', *flags, *defines,
                     str(watch / 'tests/portable_sleep_lifecycle_test.c'), '-o', str(exe)])
            r = command([str(exe)])
            results.append({'name': name, 'passed': True, 'output': r.stdout})
    # The recovered test's positional Runtime table predates additive suffixes.
    # C zero-initializes those trailing fields; no application warning is hidden.
    defs = ['-DPORTABLE_LOW_BATTERY', '-DWATCH_QUICK_RADIOS']
    sources = [watch / 'tests/low_battery_clock_test.c', watch / 'apps/clock/nova/nova.c',
               *[system / 'lib/PortableApps/src' / n for n in
                 ('quick_actions.c', 'quick_render.c', 'quick_session.c', 'quick_radios.c')]]
    objects = []
    for i, source in enumerate(sources):
        obj = out / f'clock-{int(sanitized)}-{i}.o'
        fixture_flags = ['-Wno-missing-field-initializers'] if i == 0 else []
        command([cc, '-std=c11', *flags, *defs, *fixture_flags,
                 '-c', str(source), '-o', str(obj)])
        objects.append(str(obj))
    exe = out / f'clock-{int(sanitized)}'
    command([cxx, '-std=c++11', *flags, *defs, str(watch / 'apps/clock/effects/boot.cpp'),
             *objects, '-o', str(exe)])
    r = command([str(exe)])
    results.append({'name': exe.name, 'passed': True, 'output': r.stdout})

inputs = [Path(__file__).resolve(), alarm_header]
for root in (watch / 'apps/clock', watch / 'include', watch / 'sdk',
             system / 'lib/PortableApps/include', system / 'lib/PortableApps/src'):
    inputs.extend(x for x in root.rglob('*') if x.is_file())
inputs.extend(watch / 'tests' / n for n in ('portable_sleep_lifecycle_test.c', 'low_battery_clock_test.c'))
def pin(root):
    return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
receipt = {'watch': pin(watch), 'system': pin(system), 'runtime': pin(runtime),
           'commands': commands, 'results': results,
           'source_sha256': {str(x): hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs},
           'hardware_tested': False, 'leak_sanitizer': False,
           'product_profile_changed': False, 'policy_selection': prefix.read_text()}
(out / 'qualification.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('Canonical Watch power union:', len(results), 'normal/sanitized programs passed')

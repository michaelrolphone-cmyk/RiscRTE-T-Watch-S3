#!/usr/bin/env python3
"""Rebuild native Home twice and run source-owned cross-display regressions."""
import argparse, json, os, subprocess, sys
from pathlib import Path
from watch_native_faces import ROOT, PINS, clean, need, sha, encoded, require_final
EXPECTED_REPORTS = {'build-1', 'build-2', 'test_native_faces', 'test_native_effects', 'test_home_native_height', 'test_watch_layout', 'test_viewport', 'test_crown_native_lifecycle', 'test_fast_wake_clock', 'test_clock_raster_gestures', 'test_quick_native', 'test_packed_alpha', 'test_packed_calendar', 'test_packed_atlas_codec', 'test_packed_atlas_render'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('shared', 'system', 'utilities', 'compiler', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    for name, value in vars(a).items(): setattr(a, name, value.resolve())
    require_final()
    need(sha(a.compiler.read_bytes()) == PINS['compiler_sha256'], 'Pinned compiler differs')
    for name in ('shared', 'system', 'utilities'): clean(getattr(a, name), PINS[name+'_revision'])
    need(not a.output.exists(), 'Output must be new'); a.output.mkdir(parents=True)
    # Other qualified product builds may use the same checkouts. Immutable
    # snapshots prevent concurrent host generators from changing our inputs.
    for name in ('shared', 'system', 'utilities'):
        snapshot = a.output/'sources'/name
        subprocess.run(['git', 'clone', '--no-checkout', '--no-hardlinks', str(getattr(a, name)), str(snapshot)], check=True)
        subprocess.run(['git', '-C', str(snapshot), 'checkout', '--detach', PINS[name+'_revision']], check=True)
        setattr(a, name, snapshot)
    lock = json.loads((a.shared / 'dependencies.lock.json').read_text())
    need(all(lock[k]['commit'] == PINS[k+'_revision'] for k in ('system', 'utilities')), 'Shared dependency pins differ')
    reports = {}
    def run(name, command):
        with (a.output / (name+'.log')).open('wb') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
        if result.returncode: print((a.output / (name+'.log')).read_text(), file=sys.stderr)
        need(result.returncode == 0, 'Qualification failed: '+name)
        reports[name] = sha((a.output / (name+'.log')).read_bytes())
    for index in (1, 2):
        run('build-'+str(index), [sys.executable, str(a.shared/'scripts/build.py'), '--system', str(a.system),
                                 '--utilities', str(a.utilities), '--cc', str(a.compiler), '--preferences', 'nvs',
                                 '--role', 'default', '--output', str(a.output/('build-'+str(index)))])
        artifact = a.output / ('build-'+str(index)) / 'default.elf'
        need(sha(artifact.read_bytes()) == PINS['home_sha256'] and artifact.stat().st_size == PINS['home_bytes'], 'Home does not reproduce')
        report = json.loads((artifact.parent/'build.json').read_text())
        need(report['preferences'] == 'nvs' and report['artifacts']['default']['sha256'] == PINS['home_sha256'], 'Home recipe differs')
        need(report['compiler_sha256'] == sha(a.compiler.read_bytes()), 'Compiler differs')
        defines = report['artifacts']['default']['defines']
        need('-DPORTABLE_WATCH_NATIVE_HEIGHT' in defines and '-DWATCH_ATOMIC_PREFERENCES' not in defines, 'Wrong display/preferences selection')
    for script in ('test_native_faces.py', 'test_native_effects.py', 'test_home_native_height.py', 'test_watch_layout.py', 'test_viewport.py',
                   'test_packed_alpha.py', 'test_packed_calendar.py', 'test_packed_atlas_codec.py', 'test_packed_atlas_render.py'):
        run(script[:-3], [sys.executable, str(a.shared/'scripts'/script)])
    for script in ('test_crown_native_lifecycle.py', 'test_fast_wake_clock.py', 'test_clock_raster_gestures.py'):
        command = [sys.executable, str(a.shared/'scripts'/script), '--system-apps', str(a.system), '--utilities', str(a.utilities)]
        if script != 'test_crown_native_lifecycle.py': command += ['--native']
        if script == 'test_clock_raster_gestures.py': command += ['--output', str(a.output/script[:-3])]
        run(script[:-3], command)
    run('test_quick_native', [sys.executable, str(a.system/'scripts/test_quick_native.py')])
    for name in ('shared', 'system', 'utilities'): clean(getattr(a, name), PINS[name+'_revision'])
    need(set(reports) == EXPECTED_REPORTS, 'Incomplete regression suite')
    result = dict(home_sha256=PINS['home_sha256'], home_bytes=PINS['home_bytes'], twice_reproduced=True,
                  shared_revision=PINS['shared_revision'], system_revision=PINS['system_revision'], utilities_revision=PINS['utilities_revision'],
                  compiler_sha256=sha(a.compiler.read_bytes()), reports=reports, producer_sha256=sha(Path(__file__).read_bytes()), hardware_tested=False)
    (a.output/'qualification.json').write_bytes(encoded(result)); print(json.dumps(result, indent=2))


if __name__ == '__main__': main()

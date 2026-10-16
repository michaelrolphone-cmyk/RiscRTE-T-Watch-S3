#!/usr/bin/env python3
"""Qualify and package the pinned native Home successor from immutable sources."""
import argparse, os, subprocess, sys
from pathlib import Path
from watch_native_faces import ROOT, PINS, clean, need, require_final, sha, write, compose, native_stage


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'evidence', 'runtime', 'shared', 'system', 'utilities', 'compiler', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--source-revision', required=True)
    p.add_argument('--qualified-home', type=Path)
    a = p.parse_args()
    for name, value in vars(a).items():
        if isinstance(value, Path): setattr(a, name, value.resolve())
    require_final(); clean(ROOT, a.source_revision); need(not a.output.exists(), 'Output must be new')
    for name in ('shared', 'system', 'utilities'): clean(getattr(a, name), PINS[name+'_revision'])
    native_stage(a.runtime)
    from stage_native_faces import stage
    stage(a.baseline.read_bytes(), a.evidence.read_bytes(), a.runtime)
    from read_only_spiffs import read_image
    baseline = a.baseline.read_bytes(); need(sha(baseline) == PINS['baseline_sha256'], 'Wrong official baseline')
    work = a.output/'qualification'; write(work/'baseline-store', read_image(baseline[0x2f0000:0x840000], 0x550000))
    def run(script, *args, sanitize=False):
        subprocess.run([sys.executable, str(ROOT/'scripts'/script), *map(str, args)], check=True,
                       env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0', 'SANITIZE': '1' if sanitize else '0'})
    qualified = a.qualified_home or work/'home'
    if not a.qualified_home:
        run('qualify_native_faces.py', '--shared', a.shared, '--system', a.system, '--utilities', a.utilities,
            '--compiler', a.compiler, '--output', qualified)
    native = a.runtime/'.pio/build/watch-native-ui'
    compose(work/'baseline-store', qualified/'build-1', (native/'firmware.bin').read_bytes(), a.source_revision, work/'composition')
    run('test_native_faces_contract.py', '--baseline-store', work/'baseline-store', '--store', work/'composition/store',
        '--firmware', native/'firmware.bin', '--source-revision', a.source_revision)
    for sanitize in (False, True):
        run('verify_native_faces.py', '--runtime', a.runtime, '--compiler', a.compiler, '--store', work/'composition/store',
            '--baseline-store', work/'baseline-store', '--output', work/('admission-sanitized' if sanitize else 'admission'), sanitize=sanitize)
    run('test_native_faces_preservation.py', '--runtime', a.runtime, '--baseline', a.baseline, '--firmware', native/'firmware.bin',
        '--store', work/'composition/store.bin', '--output', work/'preservation')
    run('package_native_faces.py', '--baseline', a.baseline, '--runtime', a.runtime, '--composition', work/'composition',
        '--admission', work/'admission', '--admission-sanitized', work/'admission-sanitized', '--preservation', work/'preservation',
        '--qualification', qualified, '--source-revision', a.source_revision, '--output', a.output/'assets')
    run('verify_native_faces_assets.py', '--assets', a.output/'assets', '--baseline', a.baseline,
        '--runtime', a.runtime, '--source-revision', a.source_revision)
    print('Complete exact-source 1.1.38 package; no hardware or publication I/O')


if __name__ == '__main__': main()

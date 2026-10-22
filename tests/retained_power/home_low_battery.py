#!/usr/bin/env python3
"""Additive exact retained Home low-battery composition qualification (host only)."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile
import home_profile
import qualify

PINS = home_profile.PINS
CASES = [(name, mode) for name in ('schedule', 'overrides') for mode in range(3)]
CASES += [('invalid-charging', 2), ('partial', 2), ('retained', 2)]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (*PINS, 'assets', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    repos = {name: getattr(args, name).resolve() for name in PINS}
    for name, repo in repos.items():
        qualify.source(repo, PINS[name])
    raw = qualify.assets(args.assets)
    with zipfile.ZipFile(io.BytesIO(raw['TWatch-1.1.46-Provisioning-Evidence.zip'])) as archive:
        canonical = archive.read('canonical-a.json')
        artifact = json.loads(canonical)['artifacts']['default']
    assert (artifact['bytes'], artifact['sha256']) == qualify.HOME
    flags = [flag for flag in artifact['defines'] if flag.startswith('-D')]
    required = ['-DWATCH_CRASH_REPORT_NAMESPACE=61', '-DPORTABLE_LOW_BATTERY',
                '-DWATCH_ATOMIC_PREFERENCES', '-DPORTABLE_QUICK_ATOMIC_PREFERENCES',
                '-DPORTABLE_PREFERENCE_STORE']
    assert all(flag in flags for flag in required)
    negative = []
    try:
        qualify.source(repos['system'], PINS['watch'])
    except ValueError:
        negative.append('wrong selected source rejected')
    else:
        raise AssertionError('wrong source accepted')
    receipt = {'status': 'running', 'source_pins': PINS,
               'canonical_receipt_sha256': digest(canonical), 'production_defines': flags,
               'preference_flags': 4, 'namespace': 1, 'commands': [], 'runs': [],
               'runner_sha256': digest(Path(__file__).read_bytes()),
               'fixture_sha256': digest(Path(__file__).with_suffix('.c').read_bytes())}
    receipt_path = output / 'home-low-battery.json'
    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    def run(name, command):
        result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=180,
            env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0:halt_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1'})
        log = output / (name + '.log')
        log.write_text(result.stdout + result.stderr)
        receipt['commands'].append({'name': name, 'command': list(map(str, command)),
            'returncode': result.returncode, 'log': log.name, 'log_sha256': digest(log.read_bytes())})
        if result.returncode:
            receipt['status'] = 'failed'
        save()
        result.check_returncode()
        return result.stdout
    with tempfile.TemporaryDirectory(prefix='retained-home-low-battery-') as temporary:
        work = Path(temporary)
        watch, system, utilities = [repos[name] for name in ('watch', 'system', 'utilities')]
        sys.path.insert(0, str(watch / 'scripts'))
        from merged_sdk import headers
        sdk = headers(work, system, utilities, watch)
        # Adapt only the pre-existing HOST FIXTURE to expose its runtime table
        # and replace its main. No production source is rewritten or copied.
        original = (watch / 'tests/fast_wake_clock_test.c').read_text()
        assert original.count('static const risc_runtime_api_v1 fast_runtime=') == 1
        original = original.replace('static const risc_runtime_api_v1 fast_runtime=', 'static risc_runtime_api_v1 fast_runtime=')
        assert original.count('int main(void){') == 1
        original = original.replace('int main(void){', 'static int __attribute__((unused)) inherited_fast_main(void){')
        for flag in flags:
            name = flag[2:].split('=')[0]
            original = re.sub(r'^#define ' + re.escape(name) + r'\s*$',
                lambda match: '#ifndef ' + name + '\n' + match.group(0) + '\n#endif', original, flags=re.M)
        (work / 'home_fixture.inc').write_text(original)
        sources = [Path(__file__).with_suffix('.c').resolve(),
            *[watch / 'apps/clock' / name for name in ('nova/nova.c', 'points_projection.c', 'viewport.c', 'capability_clients.c', 'quick_radios.c')],
            *[system / 'lib/PortableApps/src' / name for name in ('quick_actions.c', 'quick_render.c', 'quick_session.c', 'PortableAutomaticProvision.c', 'PortableNetworkSession.c')]]
        for sanitized in (False, True):
            variant = 'asan-ubsan' if sanitized else 'plain'
            common = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', *flags,
                *['-I' + str(path) for path in (work, sdk, watch / 'include', watch, watch / 'tests', system / 'lib/PortableApps/src')]]
            if sanitized:
                common += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', '-no-pie']
            objects = []
            for index, source in enumerate(sources):
                obj = work / f'{variant}-{index}.o'
                run(f'compile-{variant}-{index}', ['cc', '-std=c11', *common, '-c', source, '-o', obj])
                objects.append(obj)
            executable = work / variant
            run(f'link-{variant}', ['c++', '-std=c++11', *common, watch / 'apps/clock/effects/boot.cpp', *objects, '-o', executable])
            for case, mode in CASES:
                result = run(f'{variant}-{case}-{mode}', [executable, case, mode])
                receipt['runs'].append({'variant': variant, 'case': case, 'mode': mode, 'result': json.loads(result)})
                save()
        for missing in required:
            bad = subprocess.run(['cc', '-std=c11', *[f for f in common if f != missing], '-fsyntax-only', sources[0]], capture_output=True, text=True)
            assert bad.returncode and 'Exact retained Home' in bad.stderr
            negative.append('missing ' + missing + ' rejected')
    receipt.update(status='passed', negative_controls=negative,
        host_compiler=subprocess.check_output(['cc', '--version'], text=True).splitlines()[0],
        limits=['Host execution of pinned crown.c, home_automatic.inc and quick_session.c, not Xtensa ELF execution.',
                'Synthetic clock and provider mocks, not physical timing, radio, display, sleep/wake, current or live-memory acceptance.',
                'COPIED_INPUT-only Runtime preference contract; no atomic-group or real NVS durability claim.',
                'Override records use real production serializers at an explicit inter-invocation user-save boundary, not a Settings/Quick UI event replay.',
                'Deep sleep request returns a modeled refusal to inspect cleanup; no device action.',
                'LeakSanitizer disabled; ASan and UBSan enabled in the sanitized variant.'])
    save()
    print(json.dumps({'status': 'passed', 'runs': len(receipt['runs']), 'receipt': str(receipt_path)}))

if __name__ == '__main__':
    main()

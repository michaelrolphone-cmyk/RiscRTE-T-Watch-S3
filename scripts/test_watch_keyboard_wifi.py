#!/usr/bin/env python3
"""Qualify the exact built Watch Wi-Fi profile with copied host providers.

Compiles the unchanged production controller/adapter under the target's actual
feature defines. Only target optimization flags are omitted on the host.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CASES = ['masked-accept-delayed-close', 'ssid-accept', 'cancel', 'home-cancel',
         'reject-unmasked-provider', 'busy-recovery', 'repeated-open-close',
         'close-pending', 'terminal-retention', 'watch-idle',
         'unsubmitted-raster-handoff', 'pending-raster-handoff', 'watch-app-main-home-return', 'watch-local-back-neutral-reopen', 'watch-local-back-failure']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify(build_dir, output):
    record_path = build_dir / 'wifi_settings-build-record.json'
    record = json.loads(record_path.read_text())
    roots = {k: Path(v) for k, v in record['source_roots'].items()}
    for name, wanted in record['source_sha256'].items():
        owner, relative = name.split(':', 1)
        if sha(roots[owner] / relative) != wanted:
            raise ValueError('Built source changed: ' + name)
    if sha(build_dir / 'wifi_settings.elf') != record['sha256']:
        raise ValueError('Built Wi-Fi ELF changed')
    runtime_source = roots['runtime'] / 'src/bootstrap/Runtime.cpp'
    if sha(runtime_source) != record['home_return']['runtime_source_sha256']:
        raise ValueError('Home-return Runtime source changed')
    assert record['home_return']['default_app'] == 'default.elf'
    assert 'else if(!isDefault) strcpy(invocation_->current_,default_);' in runtime_source.read_text()
    output.mkdir(parents=True, exist_ok=False)
    system = roots['system-apps']
    includes = [x for x in record['command'] if x.startswith('-I')]
    # The fixture redefines five selectors itself with equivalent values. It
    # does not remove any selected feature and does not use TEST_IDLE_ELIGIBILITY.
    flags = [x for x in record['defines'] if x != '-flto']
    assert '-DPORTABLE_RASTER_SNAPSHOT' in flags and '-DPORTABLE_TEXT_INPUT_CLIENT' in flags
    assert not any('TEST_IDLE_ELIGIBILITY' in x for x in flags)
    sources = [ROOT / 'tests/shared_keyboard/watch_wifi_host.c',
        *[system / 'lib/PortableApps/src' / n for n in ('quick_actions.c', 'quick_render.c', 'quick_session.c', 'quick_radios.c')]]
    common = [os.environ.get('CC', 'cc'), '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
              '-Wno-unused-function', *flags, *includes, '-I' + str(system / 'test/native_apps')]
    commands, results, dependencies = [], [], {}
    for source in sources:
        text = subprocess.check_output([*common, '-MM', str(source)], text=True)
        for name in shlex.split(text.replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(name).resolve()
            dependencies[str(path)] = sha(path)
    for sanitized in (False, True):
        binary = output / ('watch-wifi-san' if sanitized else 'watch-wifi')
        command = [*common, *(['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', '-no-pie'] if sanitized else []),
                   *map(str, sources), '-o', str(binary)]
        commands.append(command)
        subprocess.run(command, check=True, timeout=120)
        for case, name in enumerate(CASES):
            command = [str(binary), str(case)];commands.append(command)
            result = subprocess.run(command, text=True, capture_output=True, timeout=20,
                env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0', 'UBSAN_OPTIONS': 'halt_on_error=1'})
            log = output / (('san-' if sanitized else 'normal-') + name + '.log')
            log.write_text(result.stdout + result.stderr)
            print(result.stdout + result.stderr, end='')
            result.check_returncode()
            results.append({'case': name, 'sanitized': sanitized, 'log_sha256': sha(log), 'passed': True})
    evidence = {'schema': 1, 'build_record_sha256': sha(record_path), 'elf_sha256': record['sha256'],
        'actual_watch_defines': record['defines'], 'cases': results, 'commands': commands,
        'home_return_contract': record['home_return'],
        'source_sha256': dependencies, 'hardware_verified': False,
        'boundary': 'Production Wi-Fi controller/adapter; copied display, text-host, radio, alarm, BLE, battery, RTC, navigation and sleep providers; no real credentials or network',
        'sanitizer_note': 'ASan and UBSan enabled; LeakSanitizer disabled because ptrace environment does not support it'}
    (output / 'receipt.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    qualify(args.build_dir.resolve(), args.output.resolve())

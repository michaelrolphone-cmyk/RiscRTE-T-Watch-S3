#!/usr/bin/env python3
"""Run existing exact-source Home, Runtime and capability-adapter host suites."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import qualify

PINS = {
    'system': 'bb0cadf3cec3445a64e11513b47b2676f3fdd92d',
    'watch': '416fa9f144fa5bd5471e6f4c9cefff21455c8361',
    'utilities': '4fdcad2495c33fe63f5f6faca9b11ced3c739a5b',
    'runtime': '48229bd1593a2e24e95bf4537b495ee615990fd3',
    'drivers': '5890721073ebabd781d5d278e447c761947a5c58',
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in PINS: parser.add_argument('--' + role, type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = {role: getattr(args, role).resolve() for role in PINS}
    for role, path in paths.items(): qualify.source(path, PINS[role])
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    w, s, u, r, d = [paths[n] for n in ('watch', 'system', 'utilities', 'runtime', 'drivers')]
    commands = [
        ('home-runtime-sleep', [sys.executable, w / 'scripts/test_runtime_sleep.py', '--system', s, '--utilities', u, '--output', out / 'home-runtime-sleep']),
        ('runtime-light-sleep', ['bash', r / 'test/run_light_sleep_test.sh']),
        ('runtime-deep-timed-wake-set', ['bash', r / 'test/run_deep_sleep_test.sh']),
        ('native-nvs', ['bash', r / 'test/native_nvs_shim/run_test.sh']),
        ('legacy-power-adapters', [sys.executable, d / 'scripts/test_legacy_power_bridge.py', '--sdk', r / 'sdk/driver', '--sanitize']),
    ]
    runs = []
    for name, command in commands:
        command = list(map(str, command))
        result = subprocess.run(command, capture_output=True, text=True, timeout=600,
                                env={**os.environ, 'SANITIZE': '1', 'ASAN_OPTIONS': 'detect_leaks=0', 'UBSAN_OPTIONS': 'halt_on_error=1'})
        log = out / (name + '.log'); log.write_text(result.stdout + result.stderr)
        runs.append({'name': name, 'command': command, 'returncode': result.returncode,
                     'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
        print(name, result.returncode, flush=True)
        result.check_returncode()
    for role, path in paths.items(): qualify.source(path, PINS[role])
    receipt = {'status': 'passed', 'source_pins': PINS, 'runs': runs,
               'scope': 'Original host suites against exact selected sources, not full production flags or retained Xtensa ELF execution. SDK/board operations use host shims.',
               'asan_ubsan': 'Home normal and sanitized; deep/timed/wake/NVS/adapters sanitized where original runners honor SANITIZE; Light original runner not sanitized.',
               'leak_detection': False, 'physical_tested': False, 'live_memory_fit_tested': False}
    (out / 'boundaries.json').write_text(json.dumps(receipt, indent=2) + '\n')

if __name__ == '__main__': main()

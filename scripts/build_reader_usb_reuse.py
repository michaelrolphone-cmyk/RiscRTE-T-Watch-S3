#!/usr/bin/env python3
"""Audit/build unchanged pinned Reader USB input sources; never activate hardware.

No download, source mutation, package installation, VBUS operation or flashing.
The output is compatibility evidence, not a runnable Watch deployment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / 'tests/usb-reuse-sources.json'
MAX_FILES = 128
MAX_BYTES = 4 * 1024 * 1024
TIMEOUT = 180


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, timeout=TIMEOUT, **kwargs)


def git(repo, *args):
    return run(['git', '-C', repo, *args], stdout=subprocess.PIPE).stdout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_source(repo, sha, paths):
    if git(repo, 'rev-parse', 'HEAD').decode().strip() != sha:
        raise ValueError(f'{repo}: expected pinned commit {sha}')
    # Compile only bytes from the pin. Never silently use modified local files.
    changed = git(repo, 'diff', '--name-only', 'HEAD', '--', *paths)
    if changed:
        raise ValueError(f'{repo}: selected source has uncommitted changes')


def source_files(repo, scopes):
    names = git(repo, 'ls-tree', '-r', '--name-only', 'HEAD', '--', *scopes).decode().splitlines()
    if not names or len(names) > MAX_FILES:
        raise ValueError('source snapshot file-count bound')
    return sorted(names)


def stage(repo, paths, destination):
    rows, total = [], 0
    for name in paths:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('unsafe source path')
        data = git(repo, 'show', f'HEAD:{name}')
        total += len(data)
        if total > MAX_BYTES:
            raise ValueError('source snapshot byte bound')
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rows.append({'path': name, 'size': len(data), 'sha256': digest(data)})
    return rows


def imports(elf, readelf):
    listing = run([readelf, '--dyn-syms', '--wide', elf], stdout=subprocess.PIPE, text=True).stdout
    exports, needed = set(), set()
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) < 8 or fields[4] not in ('GLOBAL', 'WEAK'):
            continue
        if fields[6] == 'UND':
            needed.add(fields[7])
        elif fields[3] == 'FUNC' and fields[4] == 'GLOBAL':
            exports.add(fields[7])
    if exports != {'t5_driver_get'}:
        raise ValueError(f'{elf}: unexpected function exports {exports}')
    return sorted(needed)


def runtime_exports(runtime):
    source = (runtime / 'lib/elf_loader/src/esp_elf_symbol.c').read_text()
    match = re.search(r'\bg_esp_libc_elfsyms\s*\[\s*\]\s*=\s*\{(.*?)\n\s*\};', source, re.S)
    if not match:
        raise ValueError('minimal runtime libc export inventory unavailable')
    return set(re.findall(r'ESP_ELFSYM_EXPORT\(\s*(\w+)\s*\)', match[1]))


def host_test(reader, runtime, modules, output, sanitize):
    host = output / 'host'
    host.mkdir()
    flags = ['-g', '-fsanitize=undefined', '-fno-sanitize-recover=all'] if sanitize else []
    rows = []
    for item in modules:
        source = reader / 'Drivers' / item['source']
        metadata = json.loads((source / 'manifest.json').read_text())
        run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fPIC', '-fvisibility=hidden',
             '-shared', *flags, '-I' + str(reader / 'sdk/driver'), source / 'driver.c',
             '-o', host / (metadata['id'] + '.so')])
        names = [row['capability'] for row in metadata['requires']]
        rows.append('  {' + ', '.join((json.dumps(metadata['id']), json.dumps(metadata['provides'][0]['capability']),
                    '{' + ', '.join(json.dumps(n) for n in names) + '}', str(len(names)))) + '},')
    (host / 'usb_reuse_inputs.inc').write_text(
        'struct Source { const char* id; const char* capability; const char* requirements[16]; size_t count; };\n'
        'static const Source sources[] = {\n' + '\n'.join(rows) + '\n};\n')
    run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', *flags,
         '-I' + str(reader / 'sdk/driver'), '-I' + str(runtime / 'sdk/hardware'),
         '-I' + str(runtime / 'src'), '-I' + str(runtime / 'test/drivers/stubs'), '-I' + str(host),
         runtime / 'src/runtime/drivers/ProviderModuleV2.cpp',
         runtime / 'src/runtime/drivers/ProviderGraphV2.cpp',
         ROOT / 'tests/usb_reuse_graph_test.cpp', '-ldl', '-o', host / 'graph-test'])
    run([host / 'graph-test', host])
    return {'runtime_graph': 'passed', 'physical_controller': 'test double only',
            'undefined_behavior_sanitizer': sanitize}


def build(reader, runtime, output, cc=None, sanitize=True):
    pin = json.loads(PIN.read_text())
    modules = pin['modules']
    scopes = ['Drivers/' + item['source'] for item in modules]
    scopes += ['Drivers/usb_controller_esp32s3', 'sdk/driver', 'platformio.ini', 'LICENSE',
               'scripts/build_usb_host_v2.py', 'scripts/build_usb_hid_common.py',
               'scripts/native_app_symbols.py', 'src/native/NativeHardwareCompat.cpp',
               'lib/NativeApps/src/NativeAppLauncher.c', 'lib/NativeApps/include/NativeHardwareCompatSymbols.def',
               'lib/elf_loader/src/esp_elf_symbol.c']
    validate_source(reader, pin['reader_commit'], scopes)
    runtime_scopes = ['src/runtime/drivers', 'sdk/driver', 'sdk/hardware',
                      'lib/elf_loader', 'lib/hal/RuntimeFaultRetention.h', 'test/drivers/stubs',
                      'test/native_apps/validate_test.c', 'test/native_apps/stubs']
    validate_source(runtime, pin['runtime_commit'], runtime_scopes)
    if output.exists():
        raise ValueError('output must be a new directory; preserve previous evidence')
    output.mkdir(parents=True)
    snapshot = output / 'reader-source'
    source_rows = stage(reader, source_files(reader, scopes), snapshot)
    for header in ('RiscProviderV2.h', 'RiscPlatformClockV1.h'):
        if (snapshot / 'sdk/driver' / header).read_bytes() != (runtime / 'sdk/driver' / header).read_bytes():
            raise ValueError(f'canonical runtime contract mismatch: {header}')
    report = {'schema': 1, 'reader_commit': pin['reader_commit'], 'runtime_commit': pin['runtime_commit'],
              'sources': source_rows, 'activatable_watch_deployment': False,
              'remaining': ['verified privileged admission', 'explicit external VBUS qualification',
                            'single USB role ownership and console handback', 'external app input/sleep integration'],
              'tests': host_test(snapshot, runtime, modules, output, sanitize), 'target': []}
    if cc:
        compiler = Path(cc).resolve()
        report['compiler'] = run([compiler, '--version'], stdout=subprocess.PIPE, text=True).stdout.splitlines()[0]
        # Execute the exact existing builders from the read-only source snapshot.
        # Only their documented compiler argument and output-root globals differ.
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(snapshot / 'scripts'))
        import build_usb_host_v2
        import build_usb_hid_common
        readelf = compiler.with_name(compiler.name.replace('gcc', 'readelf'))
        allowed = runtime_exports(runtime)
        validator = output / 'validate-elf'
        run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
             '-I' + str(runtime / 'test/native_apps/stubs'),
             '-I' + str(runtime / 'lib/elf_loader/include'),
             runtime / 'lib/elf_loader/src/esp_elf_validate.c',
             runtime / 'test/native_apps/validate_test.c', '-o', validator])
        for item in modules:
            metadata = json.loads((snapshot / 'Drivers' / item['source'] / 'manifest.json').read_text())
            if item['source'] == 'usb_host_v2':
                elf = build_usb_host_v2.build(str(compiler))
            else:
                elf = build_usb_hid_common.build(item['source'], metadata['id'],
                    tuple(row['capability'] for row in metadata['requires']),
                    metadata['provides'][0]['capability'], str(compiler))
            required = imports(elf, readelf)
            if set(required) - allowed:
                raise ValueError(f"{metadata['id']}: imports absent from minimal runtime: {set(required)-allowed}")
            run([validator, elf])
            report['target'].append({'id': metadata['id'], 'version': metadata['version'],
                'sha256': digest(elf.read_bytes()), 'bytes': elf.stat().st_size, 'imports': required,
                'runtime_structural_validator_and_corruption_negatives': 'passed'})
    (output / 'reuse-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Compatibility evidence:', output / 'reuse-report.json')
    print('No Watch activation, controller target build or physical operation claimed.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', required=True, type=Path)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cc', help='Optional Xtensa compiler; omitted runs host integration only')
    parser.add_argument('--no-sanitize', action='store_true')
    args = parser.parse_args()
    build(args.reader.resolve(), args.runtime.resolve(), args.output.resolve(), args.cc, not args.no_sanitize)


if __name__ == '__main__':
    main()

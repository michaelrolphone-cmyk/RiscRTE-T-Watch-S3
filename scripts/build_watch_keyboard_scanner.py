#!/usr/bin/env python3
"""Rebuild only Watch BLE Scanner with shared plaintext input and frozen app features.

No firmware, SD checkpoint, baseline store, or external source tree is changed.
The exact predecessor receipt must match the supplied frozen BLE Scanner ELF.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from build_contexts_cohort import definitions
from build_current_apps import application_inputs
from compact_current_elf import compact

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.2.18'
SYSTEM_COMMIT = '9c0ad2faa4b3aa73daf1c92cc343e0f83c2a5af3'
UTILITIES_COMMIT = '3385d634db829066e3f7f0d84474df5ed54bf143'
RUNTIME_COMMIT = '267aab6d9382ce4921a1536fab1620749b2f5301'
BASELINE_SCANNER_SHA256 = '1c715efe199f01f16caa38b98602ec81a1bb0a1f2177bdefffcb47b03ebb7aba'
TEXT_GRANT = {'capability': 'ui.text-input', 'api': 1, 'instance_id': 0}
EXPORTS = {'app_main', 'app_module_init', 'app_module_fini'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def normalized_flags(flags):
    result = []
    for flag in flags:
        if flag.endswith(('ContextsFaces.h', 'watch-alarm-profile.h')):
            result.append(Path(flag).name)
        else:
            result.append(flag)
    return result


def watch_flags(root, alarm):
    return definitions('ble_scanner', VERSION, root) + [
        '-DPORTABLE_ASYNC_RGB565', '-include', str(alarm), '-flto',
        '-DPORTABLE_TEXT_INPUT_CLIENT', '-DPORTABLE_CHECKED_STORAGE_RUNTIME',
        '-DPORTABLE_NATIVE_CUSTODY_FENCE', '-DPORTABLE_ALARM_TERMINAL_RETENTION',
        '-DBLE_SCANNER_COMPACT_COLOR_ONLY',
    ]


def admission(baseline):
    manifest = json.loads((baseline / 'ble_scanner.json').read_text())
    require(manifest['id'] == 'ble_scanner' and manifest['version'] == '0.2.17',
            'Expected frozen Watch BLE Scanner 0.2.17')
    require(sha(baseline / 'ble_scanner.elf') == BASELINE_SCANNER_SHA256,
            'Frozen Watch BLE Scanner bytes differ')
    requirement = {'capability': 'ui.text-input', 'api': 1}
    require(requirement not in manifest['requires'], 'Baseline already has shared text input')
    manifest['version'] = VERSION
    manifest['requires'].append(requirement)
    boot = json.loads((baseline / 'boot.json').read_text())
    rows = [r for r in boot['app_capabilities'] if r['manifest'] == 'ble_scanner.json']
    require(len(rows) == 1, 'Expected one frozen BLE Scanner policy row')
    grants = rows[0]['grants']
    require(TEXT_GRANT not in grants, 'Baseline already has text input authority')
    return manifest, [*grants, TEXT_GRANT]


def build(args):
    root = args.watch_profile.resolve()
    system, utilities, runtime, baseline, out, predecessor = [Path(x).resolve() for x in
        (args.system, args.utilities, args.runtime, args.baseline, args.output, args.predecessor_record)]
    repos = {'system-apps': system, 'utilities': utilities, 'runtime': runtime, 'watch': root}
    for key, commit in [('system-apps', args.system_commit), ('utilities', args.utilities_commit), ('runtime', RUNTIME_COMMIT)]:
        require(git(repos[key], 'rev-parse', 'HEAD') == commit, 'Wrong source pin: ' + key)
        require(not git(repos[key], 'status', '--porcelain', '--untracked-files=no'), 'Dirty source: ' + key)
    source_pins = {k: git(p, 'rev-parse', 'HEAD') for k, p in repos.items()}
    recipe_pin = git(ROOT, 'rev-parse', 'HEAD')
    recipe_hash = sha(__file__)
    manifest, grants = admission(baseline)
    prior = json.loads(predecessor.read_text())['ble_scanner']
    require(prior['sha256'] == sha(baseline / 'ble_scanner.elf'), 'Predecessor receipt does not identify baseline ELF')
    require(not out.exists(), 'Output must be new; stale build files are rejected')
    out.mkdir(parents=True)
    catalog = predecessor.parent / 'build/empty_catalog.c'
    require(sha(catalog) == prior['target_dependencies']['generated:empty_catalog.c']['sha256'],
            'Frozen full Contexts catalog differs')
    shutil.copyfile(catalog, out / 'empty_catalog.c')
    # Preserve the exact Watch sleep suffix ABI. The shared X4 outputs suffix
    # occupies the same extension location and must never be used for Watch.
    alarm = out / 'watch-alarm-profile.h'
    alarm.write_text('#include "' + str(utilities / 'lib/Alarm/include/AlarmServiceV1.h') + '"\n'
                     '#define ALARM_MODE_VISUAL 0u\n'
                     'static inline uint32_t alarm_service_output_modes(const alarm_service_v1*s)'
                     '{return s?ALARM_MODE_BOTH:ALARM_MODE_VISUAL;}\n')
    flags = watch_flags(root, alarm)
    require(normalized_flags(flags[:-5]) == normalized_flags(prior['defines']),
            'Inherited Watch build features differ from the exact predecessor')
    for name, row in prior['target_dependencies'].items():
        if name.startswith('watch:'):
            require(sha(root / name.split(':', 1)[1]) == row['sha256'], 'Inherited Watch app input changed: ' + name)
    cc = os.environ.get('NATIVE_APP_CC') or shutil.which('xtensa-esp32s3-elf-gcc')
    require(cc, 'Set NATIVE_APP_CC to the pinned target compiler')
    compiler = subprocess.check_output([cc, '--version'], text=True).splitlines()[0]
    require('8.4.0' in compiler and '2021r2-patch5' in compiler, 'Wrong target compiler')
    sources, includes, allowed = application_inputs('ble_scanner', utilities / 'Apps/ble_scanner.c', repos, root, out, 'runtime-features')
    includes += [utilities / 'lib/Contexts/include', runtime / 'sdk/app']
    allowed |= {'memchr'}
    dependencies = {}
    owners = {**repos, 'generated': out}
    for source in sources:
        dep = subprocess.check_output([cc, '-std=c11', '-Os', '-fPIC', '-ffreestanding', '-fno-builtin',
            '-MM', *flags, *['-I' + str(p) for p in includes], str(source)], text=True)
        for item in shlex.split(dep.replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(item).resolve()
            require(path.is_file() and not {'test', 'tests', 'fixtures'} & set(path.parts),
                    'Invalid target dependency: ' + item)
            owner = [(k, path.relative_to(p)) for k, p in owners.items() if path.is_relative_to(p)]
            require(owner, 'Unowned target dependency: ' + item)
            key, relative = owner[-1]
            dependencies[key + ':' + relative.as_posix()] = {'sha256': sha(path), 'size_bytes': path.stat().st_size}
    require('utilities:Apps/ble_scanner.c' in dependencies, 'Scanner controller absent from target closure')
    for name in ['lib/PortableApps/include/PortableTextInputClient.h',
                 'lib/PortableApps/include/RiscTextEntryV1.h']:
        require('system-apps:' + name in dependencies, 'Shared text consumer absent from target closure: ' + name)
    mapping = out / 'exports.map'
    mapping.write_text('{global:' + ';'.join(sorted(EXPORTS)) + ';local:*;};\n')
    elf = out / 'ble_scanner.elf'
    command = [cc, '-std=c11', '-Os', '-fPIC', '-mtext-section-literals', '-mlongcalls',
        '-fvisibility=hidden', '-ffreestanding', '-fno-builtin', '-nostdlib', '-nostartfiles', '-shared',
        '-Wl,--no-relax', '-Wl,--hash-style=sysv', '-Wl,--version-script=' + str(mapping),
        '-Wall', '-Wextra', '-Werror', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
        *flags, *['-I' + str(i) for i in includes], *map(str, sources), '-lgcc', '-o', str(elf)]
    subprocess.run(command, check=True)
    validator = out / 'validate-elf'
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
        '-I' + str(system / 'test/native_apps/stubs'), '-I' + str(system / 'lib/elf_loader/include'),
        str(system / 'lib/elf_loader/src/esp_elf_validate.c'), str(system / 'test/native_apps/validate_test.c'),
        '-o', str(validator)], check=True)
    subprocess.run([str(validator), str(elf)], check=True)
    compaction = compact(elf, cc, debug_path=out / 'debug/ble_scanner.elf')
    subprocess.run([str(validator), str(elf)], check=True)
    symbols = subprocess.check_output([cc.removesuffix('gcc') + 'nm', '-D', str(elf)], text=True)
    imports = {r.split()[-1] for r in symbols.splitlines() if ' U ' in ' ' + r}
    exports = {r.split()[-1] for r in symbols.splitlines() if len(r.split()) >= 3 and r.split()[-2] in ('T', 'D', 'B', 'R')}
    require(imports <= allowed and exports == EXPORTS, 'Target imports/exports differ: ' + repr(imports - allowed))
    raw = elf.read_bytes()
    require(raw[:7] == b'\x7fELF\x01\x01\x01' and raw[16:20] == b'\x03\x00\x5e\x00', 'Wrong target architecture')
    require(len(raw) <= 148000, 'Scanner exceeds the component budget')
    require(b'ui.text-input\0' in raw and b'Sensor name\0' in raw, 'Shared text consumer strings missing from ELF')
    (out / 'ble_scanner.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for owner, source_root in repos.items():
        require(git(source_root, 'rev-parse', 'HEAD') == source_pins[owner], 'Source commit changed during build: ' + owner)
    for name, proof in dependencies.items():
        owner, relative = name.split(':', 1)
        require(sha(owners[owner] / relative) == proof['sha256'], 'Compiled source changed during build: ' + name)
    require(git(ROOT, 'rev-parse', 'HEAD') == recipe_pin and sha(__file__) == recipe_hash, 'Product recipe changed during build')
    record = {
        'schema': 1, 'purpose': 'Watch shared-keyboard BLE Scanner component; no native or SD changes',
        'version': VERSION, 'sha256': sha(elf), 'bytes': len(raw), 'compiler': compiler,
        'sources': {**source_pins, 'product-recipe': recipe_pin},
        'source_sha256': {k: v['sha256'] for k, v in dependencies.items()}, 'target_dependencies': dependencies,
        'source_roots': {k: str(p) for k, p in owners.items()},
        'build_recipe_sha256': recipe_hash, 'required_grants': grants, 'defines': flags,
        'command': command, 'imports': sorted(imports), 'exports': sorted(exports), 'compaction': compaction,
        'predecessor_receipt': {'path': str(predecessor), 'sha256': sha(predecessor), 'scanner_sha256': prior['sha256']},
        'baseline_files': {name: sha(baseline / name) for name in ('boot.json', 'ble_scanner.json', 'ble_scanner.elf')},
        'manifest_sha256': sha(out / 'ble_scanner.json'),
        'baseline_grants_preserved': True, 'baseline_feature_flags_preserved': True, 'component_budget_bytes': 148000,
        'home_return': {'default_app': json.loads((baseline / 'boot.json').read_text())['default_app'],
                        'runtime_source_sha256': sha(runtime / 'src/bootstrap/Runtime.cpp'),
                        'policy': 'Non-resident child return without queued launch reloads configured default'},
        'full_contexts_catalog_preserved': True, 'shared_text_input': True,
        'cooperative_renderer': 'Checked direct-render profile retains bounded capture checkpoints; shared keyboard capture is serviced independently of presentation', 'masked_input': False,
        'shared_consumer_in_target_closure_and_elf': True, 'host_fixture_excluded': True,
        'native_changed': False, 'sd_persistence_changed': False, 'hardware_verified': False,
    }
    (out / 'ble_scanner-build-record.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Watch BLE Scanner', VERSION, sha(elf), len(raw), 'bytes; frozen features/grants and shared plaintext input validated')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'utilities', 'runtime', 'baseline', 'output', 'predecessor-record', 'watch-profile'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--utilities-commit', default=UTILITIES_COMMIT, help='Exact clean Utilities source commit')
    parser.add_argument('--system-commit', default=SYSTEM_COMMIT, help='Exact clean, qualified System source commit')
    build(parser.parse_args())


if __name__ == '__main__':
    main()

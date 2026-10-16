#!/usr/bin/env python3
"""Rebuild only Watch Points in Time with shared plaintext input and frozen app features.

No firmware, SD checkpoint, baseline store, or external source tree is changed.
The exact predecessor receipt must match the supplied frozen Points in Time ELF.
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
VERSION = '0.6.13'
SYSTEM_COMMIT = '9550949bab67e820aa19984ef7bc20322756feb3'
UTILITIES_COMMIT = '3385d634db829066e3f7f0d84474df5ed54bf143'
PRODUCTIVITY_COMMIT = '519dba53fbfd498da0443f516445450e864c7bc3'
RUNTIME_COMMIT = '267aab6d9382ce4921a1536fab1620749b2f5301'
BASELINE_POINTS_SHA256 = 'ef04091c3ff1a429e1968c8bfe38ed7c6dd510f651e3600ff8646df3d594bc36'
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
    return definitions('points_in_time', VERSION, root) + [
        '-DPORTABLE_ASYNC_RGB565', '-include', str(alarm), '-flto',
        '-DPORTABLE_TEXT_INPUT_CLIENT', '-DPORTABLE_CHECKED_STORAGE_RUNTIME',
        '-DPORTABLE_NATIVE_CUSTODY_FENCE', '-DPORTABLE_ALARM_TERMINAL_RETENTION',
        '-mno-target-align', '-DWATCH_POINTS_SHARED_INPUT', '-DPORTABLE_WATCH_COLOR_ONLY', '-DPORTABLE_WATCH_FROZEN_ICONS',
    ]


def admission(baseline):
    manifest = json.loads((baseline / 'points_in_time.json').read_text())
    require(manifest['id'] == 'points_in_time' and manifest['version'] == '0.6.12',
            'Expected frozen Watch Points in Time 0.6.12')
    require(sha(baseline / 'points_in_time.elf') == BASELINE_POINTS_SHA256,
            'Frozen Watch Points in Time bytes differ')
    requirement = {'capability': 'ui.text-input', 'api': 1}
    require(requirement not in manifest['requires'], 'Baseline already has shared text input')
    manifest['version'] = VERSION
    manifest['requires'].append(requirement)
    boot = json.loads((baseline / 'boot.json').read_text())
    rows = [r for r in boot['app_capabilities'] if r['manifest'] == 'points_in_time.json']
    require(len(rows) == 1, 'Expected one frozen Points in Time policy row')
    grants = rows[0]['grants']
    require(TEXT_GRANT not in grants, 'Baseline already has text input authority')
    return manifest, [*grants, TEXT_GRANT]


def build(args):
    root = args.watch_profile.resolve()
    system, utilities, productivity, runtime, baseline, out, predecessor = [Path(x).resolve() for x in
        (args.system, args.utilities, args.productivity, args.runtime, args.baseline, args.output, args.predecessor_record)]
    repos = {'system-apps': system, 'utilities': utilities, 'productivity': productivity, 'runtime': runtime, 'watch': root}
    for key, commit in [('system-apps', args.system_commit), ('utilities', args.utilities_commit), ('runtime', RUNTIME_COMMIT), ('productivity', args.productivity_commit)]:
        require(git(repos[key], 'rev-parse', 'HEAD') == commit, 'Wrong source pin: ' + key)
        require(not git(repos[key], 'status', '--porcelain', '--untracked-files=no'), 'Dirty source: ' + key)
    source_pins = {k: git(p, 'rev-parse', 'HEAD') for k, p in repos.items()}
    recipe_pin = git(ROOT, 'rev-parse', 'HEAD')
    recipe_hash = sha(__file__)
    manifest, grants = admission(baseline)
    prior = json.loads(predecessor.read_text())['points_in_time']
    require(prior['sha256'] == sha(baseline / 'points_in_time.elf'), 'Predecessor receipt does not identify baseline ELF')
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
    require(normalized_flags(flags[:-8]) == normalized_flags(prior['defines']),
            'Inherited Watch build features differ from the exact predecessor')
    for name, row in prior['target_dependencies'].items():
        if name.startswith('watch:'):
            require(sha(root / name.split(':', 1)[1]) == row['sha256'], 'Inherited Watch app input changed: ' + name)
    for name in ('points_nova7_picker.inc', 'points_writer.h', 'points_paper.inc'):
        require(sha(productivity / 'Apps' / name) == prior['target_dependencies']['productivity:Apps/' + name]['sha256'],
                'Unchanged Points feature source differs: ' + name)
    require(sha(system / 'lib/PortableApps/fonts/watch-240-icons.inc') ==
            prior['target_dependencies']['system-apps:lib/PortableApps/fonts/icons.inc']['sha256'],
            'Delivered Watch icon bytes differ')
    cc = os.environ.get('NATIVE_APP_CC') or shutil.which('xtensa-esp32s3-elf-gcc')
    require(cc, 'Set NATIVE_APP_CC to the pinned target compiler')
    compiler = subprocess.check_output([cc, '--version'], text=True).splitlines()[0]
    require('8.4.0' in compiler and '2021r2-patch5' in compiler, 'Wrong target compiler')
    sources, includes, allowed = application_inputs('points_in_time', productivity / 'Apps/points_in_time.c', repos, root, out, 'runtime-features')
    includes += [utilities / 'lib/Contexts/include', runtime / 'sdk/app']
    allowed |= {'memchr', 'strncmp'}
    paper_absent = predecessor.parent / 'build/watch-paper-absent.c'
    require(sha(paper_absent) == prior['target_dependencies']['generated:watch-paper-absent.c']['sha256'], 'Frozen Watch presentation selection differs')
    shutil.copyfile(paper_absent, out / 'watch-paper-absent.c')
    # Frozen presentation selection is now explicit in the Watch app branch.
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
    require('productivity:Apps/points_in_time.c' in dependencies, 'Points controller absent from target closure')
    require('productivity:Apps/points_watch_shared_input.h' in dependencies and
            'productivity:Apps/points_watch_keyboard.h' not in dependencies,
            'Selected Points input must use the shared host, without the legacy keyboard')
    for name in ['lib/PortableApps/include/PortableTextInputClient.h',
                 'lib/PortableApps/include/RiscTextEntryV1.h']:
        require('system-apps:' + name in dependencies, 'Shared text consumer absent from target closure: ' + name)
    mapping = out / 'exports.map'
    mapping.write_text('{global:' + ';'.join(sorted(EXPORTS)) + ';local:*;};\n')
    elf = out / 'points_in_time.elf'
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
    compaction = compact(elf, cc, debug_path=out / 'debug/points_in_time.elf')
    subprocess.run([str(validator), str(elf)], check=True)
    symbols = subprocess.check_output([cc.removesuffix('gcc') + 'nm', '-D', str(elf)], text=True)
    imports = {r.split()[-1] for r in symbols.splitlines() if ' U ' in ' ' + r}
    exports = {r.split()[-1] for r in symbols.splitlines() if len(r.split()) >= 3 and r.split()[-2] in ('T', 'D', 'B', 'R')}
    require(imports <= allowed and exports == EXPORTS, 'Target imports/exports differ: ' + repr(imports - allowed))
    raw = elf.read_bytes()
    require(raw[:7] == b'\x7fELF\x01\x01\x01' and raw[16:20] == b'\x03\x00\x5e\x00', 'Wrong target architecture')
    require(len(raw) <= 155144, 'Points exceeds the component budget')
    require(b'ui.text-input\0' in raw and b'Custom type\0' in raw, 'Shared text consumer strings missing from ELF')
    (out / 'points_in_time.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for owner, source_root in repos.items():
        require(git(source_root, 'rev-parse', 'HEAD') == source_pins[owner], 'Source commit changed during build: ' + owner)
    for name, proof in dependencies.items():
        owner, relative = name.split(':', 1)
        require(sha(owners[owner] / relative) == proof['sha256'], 'Compiled source changed during build: ' + name)
    require(git(ROOT, 'rev-parse', 'HEAD') == recipe_pin and sha(__file__) == recipe_hash, 'Product recipe changed during build')
    record = {
        'schema': 1, 'purpose': 'Watch shared-keyboard Points in Time component; no native or SD changes',
        'version': VERSION, 'sha256': sha(elf), 'bytes': len(raw), 'compiler': compiler,
        'sources': {**source_pins, 'product-recipe': recipe_pin},
        'source_sha256': {k: v['sha256'] for k, v in dependencies.items()}, 'target_dependencies': dependencies,
        'source_roots': {k: str(p) for k, p in owners.items()},
        'build_recipe_sha256': recipe_hash, 'required_grants': grants, 'defines': flags,
        'command': command, 'imports': sorted(imports), 'exports': sorted(exports), 'compaction': compaction,
        'predecessor_receipt': {'path': str(predecessor), 'sha256': sha(predecessor), 'points_sha256': prior['sha256']},
        'baseline_files': {name: sha(baseline / name) for name in ('boot.json', 'points_in_time.json', 'points_in_time.elf')},
        'manifest_sha256': sha(out / 'points_in_time.json'),
        'baseline_grants_preserved': True, 'baseline_feature_flags_preserved': True, 'component_budget_bytes': 155144,
        'home_return': {'default_app': json.loads((baseline / 'boot.json').read_text())['default_app'],
                        'runtime_source_sha256': sha(runtime / 'src/bootstrap/Runtime.cpp'),
                        'policy': 'Non-resident child return without queued launch reloads configured default'},
        'full_contexts_catalog_preserved': True, 'shared_text_input': True,
        'cooperative_renderer': 'Checked direct-render profile retains bounded capture checkpoints; shared keyboard capture is serviced independently of presentation', 'masked_input': False,
        'shared_consumer_in_target_closure_and_elf': True, 'host_fixture_excluded': True,
        'native_changed': False, 'sd_persistence_changed': False, 'hardware_verified': False,
    }
    (out / 'points_in_time-build-record.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Watch Points in Time', VERSION, sha(elf), len(raw), 'bytes; frozen features/grants and shared plaintext input validated')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'utilities', 'productivity', 'runtime', 'baseline', 'output', 'predecessor-record', 'watch-profile'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--productivity-commit', default=PRODUCTIVITY_COMMIT, help='Exact clean Productivity source commit')
    parser.add_argument('--utilities-commit', default=UTILITIES_COMMIT, help='Exact clean Utilities source commit')
    parser.add_argument('--system-commit', default=SYSTEM_COMMIT, help='Exact clean, qualified System source commit')
    build(parser.parse_args())


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Rebuild the retained Watch Files 1.5.35 ELF using only pinned public sources.

Requires Python 3.11+, pyelftools==0.32, a host C compiler, and Xtensa ESP32-S3
GCC 8.4.0 (esp-2021r2-patch5). Clone each repository below and check out its
PINS value; pass those clean checkouts and the compiler explicitly, for example:

  python scripts/rebuild_watch_files_from_source.py \
    --system-predecessor SRC/System-old --system SRC/System \
    --watch SRC/T-Watch --utilities SRC/Utilities --runtime SRC/RiscRTE \
    --cc TOOLCHAIN/bin/xtensa-esp32s3-elf-gcc --output NEW-OUTPUT

System checkouts: michaelrolphone-cmyk/RiscRTE-System-Apps
Watch checkout: michaelrolphone-cmyk/RiscRTE-T-Watch-S3
Utilities checkout: michaelrolphone-cmyk/RiscRTE-Utilities
Runtime checkout: michaelrolphone-cmyk/RiscRTE

No baseline store, prior build record, binary input, or prebuilt object is used.
The predecessor's public source recipe generates every sharing object, then the
final System source adds only the modal text-input policy flag. Both resulting
ELFs must match the retained hashes. This component-only operation does not
create manifests/grants, compose firmware, or establish hardware qualification.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

from compact_current_elf import compact

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    'system_predecessor': 'e3fd26c2257cef91c8f6a7b98065b52f1db7a54d',
    'system': '66282802bb498590fcbab4eba871ff40cc3ddafd',
    'watch': 'e0b43ef70f312cc512861926109ebe99f41c964d',
    'utilities': 'fc0bdbbbc600ce891e60c44d091fce0586ade7d8',
    'runtime': '3b90cd11cf0ff4e8116bb54d2d9eb9c7c67a148b',
}
TARGETS = {
    'predecessor': (289312, '2265a75e0f1226f9b885207dfd176d335593703aa5721f1581dee08dfa87c583'),
    'final': (291468, '915779e0a7098a8df3238b33648a6703e3958eddf736a1acd20169eb01062c47'),
}
POLICY = '-DPORTABLE_TEXT_INPUT_POLICY'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def check_source(root, pin):
    require(git(root, 'rev-parse', 'HEAD') == pin, 'Wrong source pin: ' + str(root))
    require(not git(root, 'status', '--porcelain', '--untracked-files=all'),
            'Source checkout is not clean: ' + str(root))


def check_output(output, roots):
    require(not output.exists(), 'Output must be a fresh directory')
    require(not any(output.is_relative_to(root) or root.is_relative_to(output)
                    for root in roots), 'Output must be outside every source checkout')


def check_compiler(cc):
    require(cc.name == 'xtensa-esp32s3-elf-gcc', 'Wrong target compiler executable')
    version = subprocess.check_output([str(cc), '--version'], text=True).splitlines()[0]
    machine = subprocess.check_output([str(cc), '-dumpmachine'], text=True).strip()
    require('8.4.0' in version and '2021r2-patch5' in version and
            machine == 'xtensa-esp32s3-elf', 'Wrong target compiler version or target')
    return version


def selected_inputs():
    selection = json.loads((ROOT / 'docs/files-input-policy/selection.json').read_text())
    require(selection['sources']['system-apps'] == PINS['system'] and
            selection['finalized'] is True and
            selection['source_publication'] == 'public-exact-commit' and
            selection['schema'] == 'files.modal-policy.selection.v1' and
            selection['version'] == '1.5.35', 'Public Files selection differs')
    return selection['predecessor_input_sha256']['watch']


def verify_generated(out):
    selected = selected_inputs()
    expected = {name: value for name, value in selected.items()
                if name.startswith('sharing-objects/')}
    actual = {p.relative_to(out).as_posix(): sha(p)
              for p in (out / 'sharing-objects').glob('*') if p.is_file()}
    require(len(expected) == 11 and actual == expected,
            'Fresh sharing objects differ from the selected source build')
    for name in ('empty_catalog.c', 'exports.map'):
        require(sha(out / name) == selected[name], 'Generated input differs: ' + name)
    # The alarm header includes the caller's Utilities path, not a historical
    # machine path. Its included source is pinned, and both ELF hashes are gated.
    return actual


def predecessor_command(roots, out, cc):
    # Reuse the actual source/feature functions from the pinned public recipe.
    # Disable bytecode writes so even clean source checkouts remain untouched.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(roots['watch'] / 'scripts'))
    current = importlib.import_module('build_current_apps')
    contexts = importlib.import_module('build_contexts_cohort')
    sys.path.insert(0, str(roots['system_predecessor'] / 'scripts'))
    sharing = importlib.import_module('portable_file_sharing_build')
    system, utilities, runtime, watch = (roots[name] for name in
                                        ('system_predecessor', 'utilities', 'runtime', 'watch'))
    flags = contexts.definitions('file_browser', '1.5.34', watch)
    flags += ['-DPORTABLE_CHECKED_STORAGE_RUNTIME']
    alarm = out / 'watch-alarm-profile.h'
    alarm.write_text('#include "' + str(utilities / 'lib/Alarm/include/AlarmServiceV1.h') +
                     '"\n#define ALARM_MODE_VISUAL 0u\nstatic inline uint32_t '
                     'alarm_service_output_modes(const alarm_service_v1 *s)'
                     '{return s?ALARM_MODE_BOTH:ALARM_MODE_VISUAL;}\n')
    flags += ['-include', str(alarm), '-DPORTABLE_FILE_BROWSER_RGB_ONLY',
              '-DPORTABLE_DISPLAY_ROTATION=0', '-DPORTABLE_WIFI_INSTANCE=15',
              '-DPORTABLE_FILE_BROWSER_HANDLERS',
              '-DPORTABLE_FILE_BROWSER_SECONDARY_CAPABILITY="storage.app-data.export"',
              '-DPORTABLE_FILE_BROWSER_SECONDARY_INSTANCE=0',
              '-DPORTABLE_FILE_BROWSER_SOURCE_HANDOFF',
              '-DPORTABLE_FILE_BROWSER_SHARED_INPUT', '-DPORTABLE_TEXT_INPUT_CLIENT',
              '-flto', '-mno-target-align']
    sources, includes, _ = current.application_inputs(
        'file_browser', system / 'Apps/file_browser.c',
        {'system-apps': system, 'utilities': utilities, 'runtime': runtime},
        watch, out, 'runtime-features')
    includes += [utilities / 'lib/Contexts/include', runtime / 'sdk/app']
    (out / 'empty_catalog.c').write_text(
        '#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[1]={{.compatible=false}};\n'
        'const unsigned portable_catalog_count=0;\n')
    profile = SimpleNamespace(peer_files=True, webdav_sharing=True, sharing_export_instance=0,
                              sharing_tcp_instance=0, sharing_entropy_instance=0, sharing_setup_instance=0)
    more_flags, more_sources, _ = sharing.configure(profile, system, out, includes[0], str(cc))
    flags += more_flags
    sources += more_sources
    mapping = out / 'exports.map'
    mapping.write_text('{global:app_main;app_module_init;app_module_fini;local:*;};\n')
    return [str(cc), '-std=c11', '-Os', '-fPIC', '-mtext-section-literals', '-mlongcalls',
            '-fvisibility=hidden', '-ffreestanding', '-fno-builtin', '-nostdlib', '-nostartfiles',
            '-shared', '-Wl,--no-relax', '-Wl,--hash-style=sysv',
            '-Wl,--version-script=' + str(mapping), '-Wall', '-Wextra', '-Werror',
            *flags, *['-I' + str(path) for path in includes], *map(str, sources),
            '-lgcc', '-o', str(out / 'file_browser.elf')]


def final_command(command, old_system, system, old_out, out):
    require(POLICY not in command and command.count('-o') == 1, 'Unexpected predecessor command')
    # Paths are complete directory prefixes; do not rewrite similarly named paths.
    result = [value.replace(str(old_system) + '/', str(system) + '/')
              .replace(str(old_out) + '/', str(out) + '/') for value in command]
    result.insert(result.index('-o'), POLICY)
    return result


def compile_target(command, out):
    # This pinned historical linker occasionally aborts on double-free. Retry
    # only that known failure, with exactly the same command and inputs.
    for attempt in range(1, 7):
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (out / ('link-' + str(attempt) + '.log')).write_text(process.stdout)
        if process.returncode == 0:
            return
        elf = out / 'file_browser.elf'
        if elf.exists():
            elf.rename(out / ('rejected-link-' + str(attempt) + '.elf'))
        require('ld terminated with signal 6' in process.stdout and
                'double free or corruption' in process.stdout, 'Target compilation failed: ' + process.stdout)
    raise ValueError('Pinned linker abort persisted; no component was accepted')


def verify_target(path, stage):
    require((path.stat().st_size, sha(path)) == TARGETS[stage],
            'Rebuilt ' + stage + ' Files ELF differs from the retained component')


def build(args):
    roots = {name: getattr(args, name).resolve() for name in PINS}
    out, cc = args.output.resolve(), args.cc.resolve()
    for name, root in roots.items():
        check_source(root, PINS[name])
    check_output(out, [ROOT, *roots.values()])
    compiler = check_compiler(cc)
    out.mkdir(parents=True)
    old_out, final_out = out / 'predecessor', out / 'final'
    old_out.mkdir()
    final_out.mkdir()
    command = predecessor_command(roots, old_out, cc)
    objects = verify_generated(old_out)
    validator = out / 'validate-elf'
    system = roots['system']
    subprocess.run([args.host_cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-I' + str(system / 'test/native_apps/stubs'),
                    '-I' + str(system / 'lib/elf_loader/include'),
                    str(system / 'lib/elf_loader/src/esp_elf_validate.c'),
                    str(system / 'test/native_apps/validate_test.c'), '-o', str(validator)], check=True)
    records = {}
    for stage, directory, cmd in (
            ('predecessor', old_out, command),
            ('final', final_out, final_command(command, roots['system_predecessor'],
                                               system, old_out, final_out))):
        if stage == 'final':
            for name in ('empty_catalog.c', 'exports.map', 'watch-alarm-profile.h'):
                shutil.copyfile(old_out / name, final_out / name)
            shutil.copytree(old_out / 'sharing-objects', final_out / 'sharing-objects')
        verify_generated(directory)
        compile_target(cmd, directory)
        elf = directory / 'file_browser.elf'
        subprocess.run([str(validator), str(elf)], check=True)
        proof = compact(elf, str(cc), debug_path=directory / 'file_browser.debug.elf')
        subprocess.run([str(validator), str(elf)], check=True)
        verify_target(elf, stage)
        verify_generated(directory)
        records[stage] = {'bytes': elf.stat().st_size, 'sha256': sha(elf),
                          'command': cmd, 'compaction': proof}
    for name, root in roots.items():
        check_source(root, PINS[name])
    result = {'schema': 'watch.files.source-only-replay.v1', 'sources': PINS,
              'compiler': compiler, 'sharing_objects_sha256': objects, 'targets': records,
              'binary_inputs': [], 'hardware_verified': False}
    (out / 'source-replay.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Files 1.5.35:', records['final']['bytes'], records['final']['sha256'])
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in PINS:
        result.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
    result.add_argument('--cc', type=Path, required=True)
    result.add_argument('--host-cc', default='cc')
    result.add_argument('--output', type=Path, required=True)
    return result


if __name__ == '__main__':
    build(parser().parse_args())

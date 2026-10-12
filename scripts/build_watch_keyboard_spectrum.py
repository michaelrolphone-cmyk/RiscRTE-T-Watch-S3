#!/usr/bin/env python3
"""Rebuild only Watch Audio Spectrum with shared plaintext input and frozen app features.

No firmware, SD checkpoint, baseline store, or external source tree is changed.
The exact predecessor receipt must match the supplied frozen Audio Spectrum ELF.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from build_contexts_cohort import definitions
from build_current_apps import application_inputs
from compact_current_elf import compact
from check_runtime_store_admission import store_digest

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.5.4'
RUNTIME_COMMIT = '64c8e52e46fd91e8fdafd636db04eed88f0c51a9'
BASELINE_STORE_SHA256 = '6b82cf31e572210a26153659c38b6f22ce985cf6248bae6f337a7071e046de8c'
BASELINE_SPECTRUM_SHA256 = 'dc9c242b385f0a38e6c80d4688935b8975404d635aa8ecf7d5b3bf227e502635'
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


FEATURE_ADDITIONS = [
    '-flto', '-Wl,--undefined=__divsf3', '-DPORTABLE_TEXT_INPUT_CLIENT', '-DPORTABLE_CHECKED_STORAGE_RUNTIME',
    '-DPORTABLE_NATIVE_CUSTODY_FENCE', '-DPORTABLE_ALARM_TERMINAL_RETENTION',
    '-DPORTABLE_SPECTRUM_SHARED_TEXT_INPUT', '-DPORTABLE_APP_LAUNCH_GUARD',
    '-DPORTABLE_WATCH_COLOR_ONLY', '-DPORTABLE_WATCH_FROZEN_ICONS', '-mno-target-align',
]
COMPONENT_BUDGET_BYTES = 238000


def inherited_flags(root, alarm):
    # The exact deployed Spectrum recipe explicitly omitted Contexts LTO.
    return [f for f in definitions('audio_spectrum', VERSION, root) if f != '-flto'] + [
        '-DPORTABLE_ASYNC_RGB565', '-include', str(alarm),
    ]


def watch_flags(root, alarm):
    return inherited_flags(root, alarm) + FEATURE_ADDITIONS


def admission(baseline):
    manifest = json.loads((baseline / 'audio_spectrum.json').read_text())
    require(manifest['id'] == 'audio_spectrum' and manifest['version'] == '0.5.3',
            'Expected frozen Watch Audio Spectrum 0.5.3')
    require(sha(baseline / 'audio_spectrum.elf') == BASELINE_SPECTRUM_SHA256,
            'Frozen Watch Audio Spectrum bytes differ')
    requirement = {'capability': 'ui.text-input', 'api': 1}
    require(requirement not in manifest['requires'], 'Baseline already has shared text input')
    manifest['version'] = VERSION
    manifest['requires'].append(requirement)
    boot = json.loads((baseline / 'boot.json').read_text())
    rows = [r for r in boot['app_capabilities'] if r['manifest'] == 'audio_spectrum.json']
    require(len(rows) == 1, 'Expected one frozen Audio Spectrum policy row')
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
    require(not git(root, 'status', '--porcelain', '--untracked-files=no'), 'Dirty Watch profile source')
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty product source')
    recipe_pin = git(ROOT, 'rev-parse', 'HEAD')
    recipe_hash = sha(__file__)
    baseline_store = {p.relative_to(baseline).as_posix(): p.read_bytes() for p in baseline.rglob('*') if p.is_file()}
    require(len(baseline_store) == 113 and store_digest(baseline_store) == BASELINE_STORE_SHA256,
            'Expected complete qualified LoRa baseline store')
    manifest, grants = admission(baseline)
    prior = json.loads(predecessor.read_text())['audio_spectrum']
    require(prior['sha256'] == sha(baseline / 'audio_spectrum.elf'), 'Predecessor receipt does not identify baseline ELF')
    require(not out.exists(), 'Output must be new; stale build files are rejected')
    out.mkdir(parents=True)
    catalog = predecessor.parent / 'empty_catalog.c'
    if not catalog.is_file():catalog = predecessor.parent / 'build/empty_catalog.c'
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
    require(normalized_flags(inherited_flags(root, alarm)) == normalized_flags(prior['defines']),
            'Inherited Watch build features differ from the exact predecessor')
    changed_app_sources = {'Apps/audio_spectrum.c', 'Apps/spectrum_signature_app.inc',
                           'Apps/spectrum_temporal_app.inc', 'Apps/context_fingerprint_app.inc',
                           'Apps/context_signal_library.inc'}
    for name, row in prior['target_dependencies'].items():
        owner, relative = name.split(':', 1)
        if owner == 'watch' or (owner == 'utilities' and relative not in changed_app_sources):
            require(sha(repos[owner] / relative) == row['sha256'], 'Inherited app input changed: ' + name)
        if owner == 'system-apps' and relative.startswith(('lib/PortableApps/fonts/', 'lib/PortableApps/settings_fonts/')) and not relative.endswith('/icons.inc'):
            require(sha(system / relative) == row['sha256'], 'Original font bytes differ: ' + name)
    require(sha(system / 'lib/PortableApps/fonts/watch-240-icons.inc') ==
            prior['target_dependencies']['system-apps:lib/PortableApps/fonts/icons.inc']['sha256'],
            'Delivered Watch icon bytes differ')
    cc = os.environ.get('NATIVE_APP_CC') or shutil.which('xtensa-esp32s3-elf-gcc')
    require(cc, 'Set NATIVE_APP_CC to the pinned target compiler')
    compiler = subprocess.check_output([cc, '--version'], text=True).splitlines()[0]
    require('8.4.0' in compiler and '2021r2-patch5' in compiler, 'Wrong target compiler')
    sources, includes, allowed = application_inputs('audio_spectrum', utilities / 'Apps/audio_spectrum.c', repos, root, out, 'runtime-features')
    sources += [system / 'lib/NativeApps/src/SingleFloatDivisionCompat.c']
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
    require('utilities:Apps/audio_spectrum.c' in dependencies, 'Audio Spectrum controller absent from target closure')
    require('system-apps:lib/PortableApps/settings_fonts/text.inc' in dependencies and
            not any('text-faces-012.inc' in name for name in dependencies), 'Full original NOVA font closure differs')
    for name in ['lib/PortableApps/include/PortableTextInputClient.h',
                 'lib/PortableApps/include/RiscTextEntryV1.h']:
        require('system-apps:' + name in dependencies, 'Shared text consumer absent from target closure: ' + name)
    mapping = out / 'exports.map'
    mapping.write_text('{global:' + ';'.join(sorted(EXPORTS)) + ';local:*;};\n')
    elf = out / 'audio_spectrum.elf'
    command = [cc, '-std=c11', '-Os', '-fPIC', '-mtext-section-literals', '-mlongcalls',
        '-fvisibility=hidden', '-ffreestanding', '-fno-builtin', '-nostdlib', '-nostartfiles', '-shared',
        '-Wl,--no-relax', '-Wl,--hash-style=sysv', '-Wl,--version-script=' + str(mapping),
        '-Wall', '-Wextra', '-Werror',
        *flags, *['-I' + str(i) for i in includes], *map(str, sources), '-lgcc', '-o', str(elf)]
    subprocess.run(command, check=True)
    normalizer = utilities / 'scripts/normalize_xtensa_relocations.py'
    require(sha(normalizer) == 'f71d9ca3b267166bc69d0e4853463774a8dde5384924132e1aca0e0c2f3a965f',
            'Canonical relocation normalizer differs')
    spec = importlib.util.spec_from_file_location('spectrum_relocation_normalizer', normalizer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    linker_sha256 = sha(elf)
    (out / 'debug').mkdir()
    shutil.copyfile(elf, out / 'debug/audio_spectrum-linker.elf')
    normalization = module.normalize(elf)
    normalized_sha256 = sha(elf)
    validator = out / 'validate-elf'
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
        '-I' + str(system / 'test/native_apps/stubs'), '-I' + str(system / 'lib/elf_loader/include'),
        str(system / 'lib/elf_loader/src/esp_elf_validate.c'), str(system / 'test/native_apps/validate_test.c'),
        '-o', str(validator)], check=True)
    subprocess.run([str(validator), str(elf)], check=True)
    compaction = compact(elf, cc, debug_path=out / 'debug/audio_spectrum.elf')
    subprocess.run([str(validator), str(elf)], check=True)
    symbols = subprocess.check_output([cc.removesuffix('gcc') + 'nm', '-D', str(elf)], text=True)
    imports = {r.split()[-1] for r in symbols.splitlines() if ' U ' in ' ' + r}
    exports = {r.split()[-1] for r in symbols.splitlines() if len(r.split()) >= 3 and r.split()[-2] in ('T', 'D', 'B', 'R')}
    require(imports <= allowed and exports == EXPORTS, 'Target imports/exports differ: ' + repr(imports - allowed))
    raw = elf.read_bytes()
    require(raw[:7] == b'\x7fELF\x01\x01\x01' and raw[16:20] == b'\x03\x00\x5e\x00', 'Wrong target architecture')
    require(len(raw) <= COMPONENT_BUDGET_BYTES, 'Audio Spectrum exceeds the component budget')
    require(b'ui.text-input\0' in raw, 'Shared text consumer strings missing from ELF')
    (out / 'audio_spectrum.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for owner, source_root in repos.items():
        require(git(source_root, 'rev-parse', 'HEAD') == source_pins[owner], 'Source commit changed during build: ' + owner)
    for name, proof in dependencies.items():
        owner, relative = name.split(':', 1)
        require(sha(owners[owner] / relative) == proof['sha256'], 'Compiled source changed during build: ' + name)
    require(git(ROOT, 'rev-parse', 'HEAD') == recipe_pin and sha(__file__) == recipe_hash, 'Product recipe changed during build')
    record = {
        'schema': 1, 'purpose': 'Watch shared-keyboard Audio Spectrum component; no native or SD changes',
        'version': VERSION, 'sha256': sha(elf), 'bytes': len(raw), 'compiler': compiler,
        'sources': {**source_pins, 'product-recipe': recipe_pin},
        'source_sha256': {k: v['sha256'] for k, v in dependencies.items()}, 'target_dependencies': dependencies,
        'source_roots': {k: str(p) for k, p in owners.items()},
        'build_recipe_sha256': recipe_hash, 'required_grants': grants, 'defines': flags,
        'command': command, 'imports': sorted(imports), 'exports': sorted(exports), 'compaction': compaction,
        'relocation_normalization': normalization, 'relocation_normalizer_sha256': sha(normalizer),
        'relocation_normalization_proof': {'before_sha256': linker_sha256, 'after_sha256': normalized_sha256,
            'operation': 'Remove only trailing all-zero R_XTENSA_NONE linker padding; no actionable relocations changed'},
        'baseline_store_sha256': BASELINE_STORE_SHA256,
        'predecessor_receipt': {'path': str(predecessor), 'sha256': sha(predecessor), 'spectrum_sha256': prior['sha256']},
        'baseline_files': {name: sha(baseline / name) for name in ('boot.json', 'audio_spectrum.json', 'audio_spectrum.elf')},
        'manifest_sha256': sha(out / 'audio_spectrum.json'),
        'baseline_grants_preserved': True, 'baseline_feature_flags_preserved': True, 'component_budget_bytes': COMPONENT_BUDGET_BYTES,
        'home_return': {'default_app': json.loads((baseline / 'boot.json').read_text())['default_app'],
                        'runtime_source_sha256': sha(runtime / 'src/bootstrap/Runtime.cpp'),
                        'policy': 'Non-resident child return without queued launch reloads configured default'},
        'full_contexts_catalog_preserved': True, 'shared_text_input': True,
        'cooperative_renderer': 'Checked direct-render profile retains bounded capture checkpoints; shared keyboard capture is serviced independently of presentation', 'masked_input': False,
        'shared_consumer_in_target_closure_and_elf': True, 'host_fixture_excluded': True,
        'native_changed': False, 'sd_persistence_changed': False, 'hardware_verified': False,
        'original_fonts_retained': True,
        'unchanged_spectrum_model_sources': {name: sha(utilities / 'Apps' / name) for name in
            ['spectrum_dsp.h', 'spectrum_neural.h', 'spectrum_neural_store.h', 'spectrum_signatures.h',
             'spectrum_signature_store.h', 'spectrum_temporal.h', 'spectrum_temporal_files.h',
             'spectrum_temporal_store.h', 'spectrum_store.h']},
    }
    (out / 'audio_spectrum-build-record.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Watch Audio Spectrum', VERSION, sha(elf), len(raw), 'bytes; frozen features/grants and shared plaintext input validated')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'utilities', 'runtime', 'baseline', 'output', 'predecessor-record', 'watch-profile'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--utilities-commit', required=True, help='Exact clean Utilities source commit')
    parser.add_argument('--system-commit', required=True, help='Exact clean, qualified System source commit')
    build(parser.parse_args())


if __name__ == '__main__':
    main()

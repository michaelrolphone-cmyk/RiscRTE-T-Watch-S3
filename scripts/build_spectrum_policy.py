#!/usr/bin/env python3
"""Build only Watch Audio Spectrum 0.5.5 with one optional modal-policy flag.

Replay every selected 0.5.4 target option, preserve original fonts and models,
then validate and compact the Xtensa ELF. No firmware or full image is built.
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

from compact_current_elf import compact
from current_bootfs import read_image
from check_runtime_store_admission import store_digest

ROOT = Path(__file__).resolve().parents[1]
SELECTION = json.loads((ROOT / 'docs/spectrum-input-policy/selection.json').read_text())
VERSION = '0.5.5'
SYSTEM = 'fd4b1e52fe2a49c3c4c22f9ccd4c98a91f88afa0'
RUNTIME = '64c8e52e46fd91e8fdafd636db04eed88f0c51a9'
PROFILE = '089868395268b696c05651c33816345bfe0425df'
PRIOR_SHA = '2c84ebdf52aa1affd4d6fd7034daef2f0a86111e795d99fbef0a0a700bffa04a'
COMPONENT_BUDGET_BYTES = 238000
FEATURE_ADDITIONS = ['-DPORTABLE_TEXT_INPUT_POLICY']
EXPORTS = {'app_main', 'app_module_init', 'app_module_fini'}
ALLOWED = {'risc_runtime_get_api', 'memcpy', 'memset', 'memcmp', 'memmove', 'strcmp',
           'strncmp', 'strlen', 'snprintf', 'malloc', 'calloc', 'free', 'strcpy', 'memchr', 'strrchr'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def clean(root, pin):
    require(git(root, 'rev-parse', 'HEAD') == pin and
            not git(root, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty source: ' + str(root))


def relocate(value, oldroots, roots):
    for owner, path in oldroots.items():
        value = value.replace(path, str(roots[owner]))
    return value


def compile_exact(command, elf, evidence, attempts=6):
    """Retry only the established pinned-linker abort, without changing inputs."""
    evidence.mkdir(parents=True, exist_ok=True)
    history = []
    for attempt in range(1, attempts + 1):
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        log = evidence / ('link-attempt-' + str(attempt) + '.log')
        log.write_text(process.stdout)
        row = {'attempt': attempt, 'returncode': process.returncode, 'log_sha256': sha(log)}
        history.append(row)
        if process.returncode == 0:
            return history
        if elf.exists():
            failed = evidence / ('rejected-link-attempt-' + str(attempt) + '.elf')
            shutil.move(elf, failed)
            row['rejected_elf_sha256'] = sha(failed)
        recognized = 'ld terminated with signal 6' in process.stdout and 'double free or corruption' in process.stdout
        if not recognized:
            raise RuntimeError('Target link failed: ' + process.stdout)
    raise RuntimeError('Pinned linker double-free persisted across unchanged-command retries; all failed outputs rejected')


def build(args):
    system, utilities, runtime, profile, out, predecessor, baseline = [getattr(args, name).resolve()
        for name in ('system', 'utilities', 'runtime', 'watch_profile', 'output', 'predecessor_record', 'selected_baseline')]
    require(SELECTION['finalized'] and args.utilities_commit == SELECTION['sources']['utilities'],
            'Spectrum source selection is not finalized')
    roots = {'system-apps': system, 'utilities': utilities, 'runtime': runtime, 'watch': profile, 'generated': out}
    pins = {'system-apps': SYSTEM, 'utilities': args.utilities_commit, 'runtime': RUNTIME, 'watch': PROFILE}
    for owner, pin in pins.items():
        clean(roots[owner], pin)
    recipe = git(ROOT, 'rev-parse', 'HEAD')
    clean(ROOT, recipe)
    require(not out.exists(), 'Use a fresh output directory')
    require(sha(predecessor) == SELECTION['baseline']['spectrum_predecessor_record_sha256'], 'Wrong predecessor receipt')
    prior = json.loads(predecessor.read_text())
    require(prior['version'] == '0.5.4' and prior['sha256'] == PRIOR_SHA, 'Wrong selected Spectrum predecessor')
    require(sha(predecessor.parent / 'audio_spectrum.elf') == PRIOR_SHA and
            sha(predecessor.parent / 'audio_spectrum.json') == prior['manifest_sha256'], 'Predecessor artifact custody differs')
    selected = read_image((baseline / 'components/bootfs.bin').read_bytes(), 0x510000)
    require(store_digest(selected) == SELECTION['baseline']['candidate_store_sha256'], 'Wrong complete selected union')
    manifest = json.loads((predecessor.parent / 'audio_spectrum.json').read_text())
    require(hashlib.sha256(selected['audio_spectrum.elf']).hexdigest() == PRIOR_SHA and
            json.loads(selected['audio_spectrum.json']) == manifest, 'Selected Spectrum artifact differs')
    require(manifest['version'] == '0.5.4' and
            manifest['requires'].count({'capability': 'ui.text-input', 'api': 1}) == 1, 'Wrong inherited Spectrum authority')
    grants = next(r['grants'] for r in json.loads(selected['boot.json'])['app_capabilities']
                  if r['manifest'] == 'audio_spectrum.json')
    require(grants == prior['required_grants'], 'Selected Spectrum grants differ')
    manifest['version'] = VERSION
    models = {name: sha(utilities / 'Apps' / name) for name in prior['unchanged_spectrum_model_sources']}
    require(models == prior['unchanged_spectrum_model_sources'], 'Spectrum model or storage format changed')
    out.mkdir(parents=True)
    (out / 'debug').mkdir()
    mapped = lambda value: relocate(value, prior['source_roots'], roots)
    generated_provenance = {}
    for name, row in prior['target_dependencies'].items():
        owner, relative = name.split(':', 1)
        if owner == 'generated':
            source = predecessor.parent / relative
            require(sha(source) == row['sha256'], 'Changed generated predecessor input: ' + relative)
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(mapped(source.read_text()))
            generated_provenance[relative] = {'baseline_sha256': row['sha256'], 'selected_sha256': sha(target),
                                              'operation': 'source-root relocation only'}
        if owner == 'watch' or (owner == 'system-apps' and
                any(part in relative for part in ('/fonts/', '/settings_fonts/', '/paper_fonts/'))):
            require(sha(roots[owner] / relative) == row['sha256'], 'Original Watch source or font changed: ' + name)
    inherited = [mapped(flag) for flag in prior['defines']]
    require(all(flag not in inherited for flag in FEATURE_ADDITIONS), 'Predecessor already enables modal policy')
    flags = inherited + FEATURE_ADDITIONS
    command = [mapped(value) for value in prior['command']]
    cc = os.environ.get('NATIVE_APP_CC') or command[0]
    command[0] = cc
    before = list(command)
    command[command.index('-o'):command.index('-o')] = FEATURE_ADDITIONS
    require([value for value in command if value not in FEATURE_ADDITIONS] == before,
            'An inherited target command option changed')
    compiler = subprocess.check_output([cc, '--version'], text=True).splitlines()[0]
    require('8.4.0' in compiler and '2021r2-patch5' in compiler, 'Wrong target compiler')
    (out / 'exports.map').write_text('{global:' + ';'.join(sorted(EXPORTS)) + ';local:*;};\n')
    sources = [Path(value) for value in command if value.endswith('.c')]
    includes = [value for value in command if value.startswith('-I')]
    dependencies = {}
    for source in sources:
        closure = subprocess.check_output([cc, '-std=c11', '-Os', '-fPIC', '-ffreestanding', '-fno-builtin',
                                          '-MM', *flags, *includes, str(source)], text=True)
        for token in shlex.split(closure.replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(token).resolve()
            require(path.is_file() and not {'test', 'tests', 'fixtures'} & set(path.parts), 'Invalid target input: ' + token)
            owners = [(owner, path.relative_to(root)) for owner, root in roots.items() if path.is_relative_to(root)]
            require(owners, 'Unowned target source: ' + str(path))
            owner, relative = owners[-1]
            dependencies[owner + ':' + relative.as_posix()] = {'sha256': sha(path), 'bytes': path.stat().st_size}
    for name in ('PortableTextInputClient.h', 'PortableTextInputPolicy.h', 'PortableTextInputCheckpointClient.h'):
        require(any(key.endswith('/' + name) for key in dependencies), 'Missing modal policy target dependency: ' + name)
    require(not any('text-faces-' in name for name in dependencies), 'A font subset was selected')
    require('system-apps:lib/PortableApps/settings_fonts/text.inc' in dependencies, 'Full NOVA fonts missing')
    elf = out / 'audio_spectrum.elf'
    linker_attempts = compile_exact(command, elf, out / 'debug/linker-attempts')
    normalizer_path = utilities / 'scripts/normalize_xtensa_relocations.py'
    require(sha(normalizer_path) == 'f71d9ca3b267166bc69d0e4853463774a8dde5384924132e1aca0e0c2f3a965f', 'Normalizer changed')
    spec = importlib.util.spec_from_file_location('spectrum_policy_normalizer', normalizer_path)
    normalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(normalizer)
    shutil.copyfile(elf, out / 'debug/audio_spectrum-linker.elf')
    normalization = normalizer.normalize(elf)
    validator = out / 'validate-elf'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
        '-I' + str(system / 'test/native_apps/stubs'), '-I' + str(system / 'lib/elf_loader/include'),
        str(system / 'lib/elf_loader/src/esp_elf_validate.c'), str(system / 'test/native_apps/validate_test.c'),
        '-o', str(validator)], check=True)
    subprocess.run([str(validator), str(elf)], check=True)
    compaction = compact(elf, cc, debug_path=out / 'debug/audio_spectrum.elf')
    subprocess.run([str(validator), str(elf)], check=True)
    nm = subprocess.check_output([cc.removesuffix('gcc') + 'nm', '-D', str(elf)], text=True)
    imports = {line.split()[-1] for line in nm.splitlines() if ' U ' in ' ' + line}
    exports = {line.split()[-1] for line in nm.splitlines() if len(line.split()) >= 3 and line.split()[-2] in ('T', 'D', 'B', 'R')}
    require(imports <= ALLOWED and exports == EXPORTS, 'Unexpected Spectrum ABI')
    require(b'ui.text-input\0' in elf.read_bytes(), 'Shared input service missing')
    require(elf.stat().st_size <= COMPONENT_BUDGET_BYTES, 'Spectrum component budget exceeded')
    for name, row in dependencies.items():
        owner, relative = name.split(':', 1)
        require(sha(roots[owner] / relative) == row['sha256'], 'Source changed during build: ' + name)
    for owner, pin in pins.items():
        clean(roots[owner], pin)
    clean(ROOT, recipe)
    (out / 'audio_spectrum.json').write_text(json.dumps(manifest, indent=2) + '\n')
    record = dict(schema='spectrum.modal-policy.component.v1', device='watch', version=VERSION,
        sha256=sha(elf), bytes=elf.stat().st_size, manifest_sha256=sha(out / 'audio_spectrum.json'),
        compiler=compiler, command=command, defines=flags, inherited_defines=inherited, linker_attempts=linker_attempts,
        feature_additions=FEATURE_ADDITIONS, sources=pins, source_roots={k: str(v) for k, v in roots.items()},
        product_recipe=recipe, source_publication=SELECTION['source_publication'], build_recipe_sha256=sha(__file__), target_dependencies=dependencies,
        generated_provenance=generated_provenance, original_fonts_retained=True, baseline_features_preserved=True,
        unchanged_spectrum_model_sources=models, predecessor_receipt_sha256=sha(predecessor),
        predecessor_elf_sha256=PRIOR_SHA, required_grants=grants, imports=sorted(imports), exports=sorted(exports),
        compaction=compaction, relocation_normalization=normalization, component_budget_bytes=COMPONENT_BUDGET_BYTES,
        shared_text_input=True, modal_policy=True, native_changed=False, hardware_verified=False)
    (out / 'audio_spectrum-build-record.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Watch Audio Spectrum', VERSION, record['bytes'], record['sha256'])
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'utilities', 'runtime', 'watch-profile', 'selected-baseline', 'predecessor-record', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--utilities-commit', required=True)
    build(parser.parse_args())


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Reproduce the preserving T023 Springboard from exact public RGB/bridge pins."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compose_manifest(baseline):
    result = copy.deepcopy(baseline)
    declarations = result.get('requires', []) + result.get('optional', [])
    for capability in ['software.installed-apps', 'storage.volume']:
        entry = {'capability': capability, 'api': 1}
        if entry not in declarations:
            result.setdefault('optional', []).append(entry)
    return result


def build_command(profile, compiler, system, output, bridge, atomic):
    substitutions = {'system': str(system), 'output': str(output), 'bridge': str(bridge)}
    arguments = [arg.format(**substitutions) for arg in profile['arguments']]
    arguments += ['-DPORTABLE_PACKAGE_DISCOVERY', '-DPORTABLE_PACKAGE_VOLUME=12',
                  str(system / 'lib/PortableApps/src/PortableInstalledCatalog.c')]
    if atomic:
        arguments.append('-DPORTABLE_QUICK_ATOMIC_PREFERENCES')
    return [str(compiler), *arguments, '-o', str(output / 'springboard.elf')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['baseline-store', 'rgb-system', 'bridges', 'compiler', 'validator', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    recipe = json.loads((ROOT / 'profiles/t023-reproduction.json').read_text())
    selected = recipe['springboard']
    system, out = args.rgb_system.resolve(), args.output.resolve()
    if out.exists():
        parser.error('--output must be a new directory; preserve prior evidence')
    actual = subprocess.check_output(['git', '-C', str(system), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != recipe['source_pins']['rgb_system']['commit']:
        parser.error('RGB checkout must be the exact pinned public commit')
    if subprocess.check_output(['git', '-C', str(system), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
        parser.error('RGB tracked source must be clean')
    source_recipe = system / 'test/native_apps/fixtures/catalog_target/recipes.json'
    if digest(source_recipe) != selected['source_recipe_sha256']:
        parser.error('RGB compiler recipe differs from the selected source')
    baseline_manifest = args.baseline_store / 'springboard.json'
    if digest(baseline_manifest) != recipe['baseline']['files']['springboard.json']:
        parser.error('Springboard baseline manifest differs from the exact released store')
    version = subprocess.check_output([str(args.compiler), '--version'], text=True).splitlines()[0]
    if version != recipe['compiler']['version'] or digest(args.compiler) != recipe['compiler']['sha256']:
        parser.error('Compiler does not match the selected toolchain')
    recipes = json.loads(source_recipe.read_text())
    if recipes['shared_bridge']['revision'] != recipe['source_pins']['bridges']['commit']:
        parser.error('Shared RGB bridge pin differs from the selected source')
    out.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location('pinned_rgb_proof', system / 'scripts/prove_shared_catalog_target.py')
    proof = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proof)
    bridge = out / 'bridges'
    proof.materialize(args.bridges.resolve(), recipes['shared_bridge']['revision'], bridge)
    (out / 'springboard.map').write_text('{ global: app_main; app_module_init; app_module_fini; local: *; };\n')
    profile = recipes['profiles']['springboard']
    command = build_command(profile, args.compiler, system, out, bridge, selected['atomic_preferences'])
    subprocess.run(command, check=True)
    subprocess.run([str(args.validator), str(out / 'springboard.elf')], check=True)
    elf = out / 'springboard.elf'
    if digest(elf) != selected['elf_sha256'] or elf.stat().st_size != selected['elf_bytes']:
        raise ValueError('Springboard bytes differ from the qualified exact component recipe')
    symbols = subprocess.check_output([str(args.compiler).removesuffix('gcc') + 'nm', '-D', str(elf)], text=True)
    imports = sorted({r.split()[-1] for r in symbols.splitlines() if ' U ' in ' ' + r})
    exports = sorted({r.split()[-1] for r in symbols.splitlines() if len(r.split()) >= 3 and r.split()[-2] in ('T', 'D', 'B', 'R')})
    if imports != profile['expected_imports'] or exports != profile['expected_exports']:
        raise ValueError('Springboard import/export boundary changed')
    manifest = compose_manifest(json.loads(baseline_manifest.read_text()))
    (out / 'springboard.json').write_text(json.dumps(manifest, indent=2) + '\n')
    record = {'source_commit': actual, 'bridge_commit': recipes['shared_bridge']['revision'],
              'command': command, 'sha256': digest(elf), 'bytes': elf.stat().st_size,
              'imports': imports, 'exports': exports, 'atomic_preferences': selected['atomic_preferences'],
              'manifest_sha256': digest(out / 'springboard.json'), 'baseline_manifest_sha256': digest(baseline_manifest),
              'source_recipe_sha256': digest(source_recipe), 'compiler': version,
              'compiler_sha256': digest(args.compiler), 'hardware_qualified': False}
    (out / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({key: record[key] for key in ['sha256', 'bytes', 'atomic_preferences']}))


if __name__ == '__main__':
    main()

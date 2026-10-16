#!/usr/bin/env python3
"""Replay retained Home 0.11.5; allow only explicitly named patch dependencies.

No flashing, filesystem-image assembly, publication, or source modification.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys

sys.dont_write_bytecode = True
P = pathlib.Path
ROOT = P(__file__).resolve().parents[1]
PYELFTOOLS = P('/workspace/scratch/c744abbbbd60/watch-build-tools/python/lib/python3.12/site-packages')
sys.path.insert(0, str(PYELFTOOLS))
BASE = P('/workspace/shared/watch-evening-1119-20261012/product')
SYSTEM = P('/workspace/shared/watch-fast-wake-20261012/system-clock')
UTILITIES = P('/workspace/shared/watch-fast-wake-20261012/utilities-clock')
RETAINED = P('/workspace/shared/watch-sleep-failure-clock-build-0115')
CC = P('/workspace/scratch/c744abbbbd60/watch-build-tools/platformio-core/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc')
EXPECTED_ELF = '90388f2269badefae66d8ba7fc844fd7d7af481392e55bb79f9e898e4ff81875'
EXPECTED_RECEIPT = 'c8c4c6bd89291769cbecee8488a0ad036695f7d77154653765bac995dd21053f'
TOOLCHAIN_PINS = ROOT / 'docs/home-swipe/toolchain-pins.json'
EXPECTED_TOOLCHAIN_PINS = '83ec949f5c1b81fbf73c89ee7ef8975ae7821f02318fe9beddc3fe6eefab58a1'
EXPECTED_COMPILER_HASHES = {
    'gcc': '732bebd44b70a21687ffa3ac5da55edc9b555080ad21cfd74503b2288a143d3f',
    'g++': '5b30f4eb7c41b7954acd4f183895f03abdb612d8470346436d850208b8be2c98',
    'objcopy': 'e366061dda019ed36a3cf902f7abf5b48a0ac2f8c47ae7ad4794f5e4c0658203',
    'nm': 'af632d7578c77d53fe9767298b0fc0b46763f855df5cab7d40343f51e9b2f0bf',
}
PINNED_HELPERS = {
    BASE / 'scripts/compact_current_elf.py': '07936b7ccbc53809ef8d907b19d434b047e4b7e4a2a8501bd32bd9465f691d55',
    UTILITIES / 'scripts/normalize_xtensa_relocations.py': 'f71d9ca3b267166bc69d0e4853463774a8dde5384924132e1aca0e0c2f3a965f',
}


def sha(path):
    return hashlib.sha256(P(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    global BASE, SYSTEM, UTILITIES, RETAINED, CC, PINNED_HELPERS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product', type=P, default=ROOT)
    for name in ('baseline-product', 'baseline-clock', 'system', 'utilities', 'compiler'):
        parser.add_argument('--' + name, type=P, required=True)
    parser.add_argument('--output', type=P, required=True)
    parser.add_argument('--allow-change', action='append', default=[], help='Exact receipt key, repeat for each expected change')
    parser.add_argument('--version', choices=('0.11.5', '0.11.6'), default='0.11.6')
    args = parser.parse_args()
    BASE, RETAINED, SYSTEM, UTILITIES, CC = (getattr(args, key).resolve() for key in ('baseline_product', 'baseline_clock', 'system', 'utilities', 'compiler'))
    PINNED_HELPERS = {BASE / 'scripts/compact_current_elf.py': '07936b7ccbc53809ef8d907b19d434b047e4b7e4a2a8501bd32bd9465f691d55', UTILITIES / 'scripts/normalize_xtensa_relocations.py': 'f71d9ca3b267166bc69d0e4853463774a8dde5384924132e1aca0e0c2f3a965f'}
    product, output = args.product.resolve(), args.output.resolve()
    product_source = subprocess.check_output(['git', '-C', str(product), 'rev-parse', 'HEAD'], text=True).strip()
    product_tree = subprocess.check_output(['git', '-C', str(product), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    assert not subprocess.check_output(['git', '-C', str(product), 'status', '--porcelain', '--untracked-files=no'], text=True).strip(), 'Commit tracked source edits before target build'
    assert not output.exists(), f'Output already exists: {output}'
    assert sha(RETAINED / 'build.json') == EXPECTED_RECEIPT
    assert sha(RETAINED / 'default.elf') == EXPECTED_ELF
    receipt = json.loads((RETAINED / 'build.json').read_text())
    assert sha(RETAINED / 'default.json') == receipt['manifest']['sha256']
    assert sha(TOOLCHAIN_PINS) == EXPECTED_TOOLCHAIN_PINS
    toolchain = json.loads(TOOLCHAIN_PINS.read_text())
    for relative, digest in toolchain['files'].items():
        assert sha(CC.parent.parent / relative) == digest, relative
    for helper, digest in PINNED_HELPERS.items():
        assert sha(helper) == digest, str(helper)
    for root, commit in [(BASE, '6260a9d01d409a21b49d600176d591ab919b79d7'), (SYSTEM, '63532e4611749acad2060d0437a883b7c4ac8fd5'), (UTILITIES, '814502e51125d799a7ca625b78707753ca12d4e5')]:
        assert subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip() == commit
    roots = {'watch': product, 'system': SYSTEM, 'utilities': UTILITIES}
    baseline_roots = {'watch': BASE, 'system': SYSTEM, 'utilities': UTILITIES}
    dependencies, changed = {}, []
    for key, prior in receipt['dependencies'].items():
        owner, relative = key.split(':', 1)
        assert sha(baseline_roots[owner] / relative) == prior['sha256'], f'Pinned baseline changed: {key}'
        digest = sha(roots[owner] / relative)
        dependencies[key] = {'sha256': digest, 'predecessor_sha256': prior['sha256']}
        if digest != prior['sha256']:
            changed.append(key)
    assert len(dependencies) == 98
    assert sorted(changed) == sorted(args.allow_change), (changed, args.allow_change)
    cc = str(CC)
    version = subprocess.check_output([cc, '--version'], text=True).splitlines()[0]
    assert version == receipt['compiler'], version
    compiler_hashes = {suffix: sha(cc.removesuffix('gcc') + suffix) for suffix in ('gcc', 'g++', 'objcopy', 'nm')}
    assert compiler_hashes == EXPECTED_COMPILER_HASHES, compiler_hashes
    output.mkdir(parents=True)
    (output / 'debug').mkdir()
    (output / 'default.map').write_text('{ global: app_main; local: *; };\n')
    boot_command = [cc.removesuffix('gcc') + 'g++', '-std=c++11', '-Os', '-fPIC', '-mtext-section-literals', '-mlongcalls', '-fvisibility=hidden', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics', '-ffreestanding', '-fno-builtin', '-Wall', '-Wextra', '-Werror', '-ffunction-sections', '-fdata-sections', '-I' + str(product / 'sdk/driver'), '-c', str(product / 'apps/clock/effects/boot.cpp'), '-o', str(output / 'boot-effect.o')]
    subprocess.run(boot_command, check=True)
    mapping = {
        '/workspace/shared/watch-clean-face-1114/product': str(product),
        '/workspace/shared/watch-fast-wake-20261012/system-clock': str(SYSTEM),
        '/workspace/shared/watch-fast-wake-20261012/utilities-clock': str(UTILITIES),
        '/workspace/shared/watch-sleep-failure-clock-build-0115': str(output),
    }
    def remap(value):
        for old, new in mapping.items():
            value = value.replace(old, new)
        return value
    command = [cc, *[remap(item) for item in receipt['fast_clock']['command'][1:]]]
    (output / 'commands.json').write_text(json.dumps({'boot': boot_command, 'link': command, 'mapping': mapping}, indent=2) + '\n')
    subprocess.run(command, check=True)
    target = output / 'default.elf'
    normalizer = module('home_normalize', UTILITIES / 'scripts/normalize_xtensa_relocations.py')
    compactor = module('home_compact', BASE / 'scripts/compact_current_elf.py')
    normalized = normalizer.normalize(target)
    compact = compactor.compact(target, cc, debug_path=output / 'debug/default.elf')
    symbols = subprocess.check_output([cc.removesuffix('gcc') + 'nm', '-D', str(target)], text=True)
    imports = {line.split()[-1] for line in symbols.splitlines() if ' U ' in ' ' + line}
    exports = {line.split()[-1] for line in symbols.splitlines() if len(line.split()) >= 3 and line.split()[-2] in ('T', 'D', 'B', 'R')}
    assert imports <= set(receipt['fast_clock']['imports']) and exports == {'app_main'}, (imports, exports)
    if not changed:
        assert sha(target) == EXPECTED_ELF and target.stat().st_size == 862880, (sha(target), target.stat().st_size)
        assert target.read_bytes() == (RETAINED / 'default.elf').read_bytes()
    manifest = json.loads((RETAINED / 'default.json').read_text())
    assert manifest['version'] == '0.11.5'
    manifest['version'] = args.version
    (output / 'default.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    proof = {
        'schema': 1, 'baseline_receipt_sha256': EXPECTED_RECEIPT,
        'baseline_elf_sha256': EXPECTED_ELF, 'baseline_reproduced_byte_for_byte': not bool(changed),
        'compiler': version, 'compiler_sha256': compiler_hashes,
        'toolchain_pins_sha256': EXPECTED_TOOLCHAIN_PINS,
        'product': str(product), 'product_source': product_source, 'product_tree': product_tree,
        'recipe_sha256': sha(P(__file__)), 'dependencies': dependencies,
        'changed_dependency_keys': sorted(changed), 'mapping': mapping,
        'boot_command': boot_command, 'command': command,
        'bytes': target.stat().st_size, 'sha256': sha(target),
        'imports': sorted(imports), 'exports': sorted(exports),
        'relocation_normalization': normalized, 'compaction': compact,
        'manifest': {'version': args.version, 'sha256': sha(output / 'default.json')},
        'hardware_verified': False, 'image_assembled': False,
        'feature_flags': [item for item in command if item.startswith('-D')],
        'fonts_unchanged': all(not ('font' in key.lower()) for key in changed),
    }
    assert not subprocess.check_output(['git', '-C', str(product), 'status', '--porcelain', '--untracked-files=no'], text=True).strip(), 'Source changed during target build'
    assert subprocess.check_output(['git', '-C', str(product), 'rev-parse', 'HEAD'], text=True).strip() == product_source
    (output / 'build.json').write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: proof[key] for key in ('baseline_reproduced_byte_for_byte', 'bytes', 'sha256', 'imports', 'exports', 'changed_dependency_keys')}))


if __name__ == '__main__':
    main()

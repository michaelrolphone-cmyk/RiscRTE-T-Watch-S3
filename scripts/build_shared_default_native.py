#!/usr/bin/env python3
"""Fresh native build plus default-specific same-process product qualification.

A detached build/JSON receipt is never accepted. This candidate command does
not publish, access devices, or claim hardware acceptance.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import native_idf61_build as controlled
import native_idf61_candidate as native
import package_shared_default as package
from package_alarm_sleep import make_archive
from package_shared_default import require, sha, record, encoded


def canonical(args, sources, p):
    spec = importlib.util.spec_from_file_location('canonical_default_verifier', sources['watch'] / 'scripts/verify_shared_default.py')
    verifier = importlib.util.module_from_spec(spec); spec.loader.exec_module(verifier)
    receipt = verifier.verify(args.first, args.second)
    elf, manifest, first = verifier.check_build(args.first)
    require(first['verified_dependencies']['system']['commit'] == p['system_revision'], 'Canonical System dependency differs')
    require(first['verified_dependencies']['utilities']['commit'] == p['utilities_revision'], 'Canonical Utilities dependency differs')
    require(first['compiler_sha256'] == controlled.compiler_family(args.compiler)['s3-gcc']['sha256'], 'Canonical compiler differs from pinned native S3 wrapper')
    return elf, manifest, receipt


def qualify(args, sources, proof):
    from shared_default_qualification import admit_product
    preservation_model = native.local_qualification().preservation_model
    from read_only_spiffs import read_image
    from prepare_preserving_update import layout, pair
    from current_bootfs import build
    p = package.pins()
    closure = controlled.validate_build_proof(proof, sources, args.native_build, args.compiler)
    lock = json.loads(args.lock.read_bytes())
    native.verify_sources(lock, sources)
    controlled.validate_build_proof(proof, sources, args.native_build, args.compiler, lock)
    contract = package.baseline_contract(p)
    baseline = args.baseline.read_bytes()
    require(record(baseline) == {'bytes': contract['factory_bytes'], 'sha256': contract['factory_sha256']}, 'Exact released alarm factory required')
    _, _, store = pair(baseline, 0, layout(baseline))
    require(sha(store) == contract['store_sha256'], 'Exact released store required')
    before = read_image(store, 0x550000); package.check_baseline(before, contract)
    # Reuse native validation without changing its historical contract. The
    # descriptor, board target, physical hooks and partition layout are retained.
    native_contract = json.loads(native.CONTRACT.read_bytes())
    blobs, native_proof = native.verify_native(lock, sources, args.native_build, args.compiler, native_contract, baseline)
    default, manifest, canonical_proof = canonical(args, sources, p)
    after = package.compose(before, default, manifest, p, lock['sources']['product']['revision'], blobs['firmware_bin'])
    imports = native.reject_private(after, sources['runtime'])
    packed, packing = build(after, size=0x550000)
    require(build(after, size=0x550000)[0] == packed and read_image(packed, 0x550000) == after, 'Deterministic store round-trip failed')
    preservation = package.verify_store(before, read_image(packed, 0x550000), default, manifest, p, lock['sources']['product']['revision'], blobs['firmware_bin'])
    factory, transition = native.make_images(baseline, blobs['firmware_bin'], blobs['bootloader'], packed)
    require(pair(factory, 0, layout(factory))[1:] == (blobs['firmware_bin'], packed), 'Final factory native/store binding differs')
    admission = admit_product(sources, blobs['firmware_elf'], before, after, native_proof, sanitized=False)
    admission_sanitized = admit_product(sources, blobs['firmware_elf'], before, after, native_proof, sanitized=True)
    require(admission['elf_count'] == admission_sanitized['elf_count'] == contract['elf_count'], 'Incomplete product ELF admission')
    fault_model = preservation_model(baseline, transition, contract['factory_sha256'])
    controlled.validate_build_proof(proof, sources, args.native_build, args.compiler, lock)
    native.verify_sources(lock, sources)
    assets = {'factory-candidate-erases-data-0x0.bin': factory, 'firmware.bin': blobs['firmware_bin'],
              'bootloader.bin': blobs['bootloader'], 'partitions.bin': blobs['partitions'], 'store.bin': packed}
    report = dict(schema=1, status='software-qualified-candidate-hardware-pending', publication_enabled=False,
                  product=p['product'], version=p['version'], source_revision=lock['sources']['product']['revision'],
                  hardware_tested=False, device_accessed=False, factory_erases_data=True, preserving_update_kit_emitted=False,
                  input_lock=lock, controlled_build=closure, native=native_proof, native_rebuilt=True,
                  default=canonical_proof, baseline_contract=contract, preservation=preservation, public_imports=imports,
                  admission=admission, admission_sanitized=admission_sanitized, preservation_software_model=fault_model,
                  packing=packing, artifacts={n: record(b) for n, b in assets.items()})
    assets.update({'qualification.json': encoded(report), 'source-lock.json': args.lock.read_bytes(),
                   'source-pins.json': (package.DOCS / 'source-pins.json').read_bytes(), 'default.elf': default, 'default.json': manifest})
    evidence = {'qualification.json': assets['qualification.json'], 'canonical-a.json': (args.first / 'build.json').read_bytes(),
                'canonical-b.json': (args.second / 'build.json').read_bytes(), 'default.elf': default, 'default.json': manifest}
    for key, row in lock['native_files'].items():
        evidence['build/' + row['path']] = native.safe_path(args.native_build, row['path']).read_bytes()
    for f in (args.native_build / 'native-build-evidence').rglob('*'):
        if f.is_file(): evidence['build-evidence/' + f.relative_to(args.native_build / 'native-build-evidence').as_posix()] = f.read_bytes()
    assets['candidate-evidence.zip'] = make_archive(evidence)
    assets['SHA256SUMS'] = ''.join(sha(b) + '  ' + n + '\n' for n, b in sorted(assets.items())).encode()
    args.output.mkdir(parents=True)
    for name, data in assets.items(): (args.output / name).write_bytes(data)
    print(p['product'] + ': native source closure, complete default store admission/extraction and preservation model PASS; hardware pending', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', default=[])
    for name in ('compiler', 'baseline', 'native-build', 'output', 'first', 'second'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    require(__debug__, 'Validation cannot be disabled')
    p = package.pins()
    require(p.get('runtime_revision'), 'Combined Runtime candidate pin is required')
    sources = native.parse_sources(args.source)
    required = {'product', 'runtime', 'system', 'utilities', 'drivers', 'sdk', 'watch', 'image_helper'}
    require(set(sources) == required, 'Exact source closure required')
    args.native_build, args.output, args.compiler = args.native_build.resolve(), args.output.resolve(), args.compiler.resolve()
    controlled.validate_layout(sources, args.native_build, args.output, package.ROOT)
    source_pins = {role: native.clean_source(root, native.git(root, 'rev-parse', 'HEAD').decode().strip()) for role, root in sources.items()}
    for role in required - {'product'}:
        require(source_pins[role]['revision'] == p[role + '_revision'], 'Candidate source pin differs: ' + role)
    canonical(args, sources, p)
    require('15.2.0' in controlled.run([args.compiler, '--version']), 'Pinned GCC15 required')
    env = controlled.clean_environment(sources['sdk'], args.compiler)
    cmake = Path(shutil.which('cmake', path=env['PATH'])).resolve()
    if cmake.read_bytes()[:2] == b'#!':
        cmake = (cmake.parent.parent / 'cmake/data/bin/cmake').resolve()
        require(cmake.is_file() and cmake.read_bytes()[:4] == b'\x7fELF', 'Native CMake required')
    env['PATH'] = str(cmake.parent) + ':' + env['PATH']
    tools = controlled.compiler_family(args.compiler)
    selected = [('gcc', str(args.compiler)), ('g++', str(args.compiler.with_name('xtensa-esp-elf-g++'))),
                ('python', sys.executable), ('cmake', str(cmake)), ('ninja', shutil.which('ninja', path=env['PATH']))]
    selected += [(n, str(args.compiler.with_name('xtensa-esp-elf-' + n))) for n in ('as', 'ld', 'ar', 'objcopy', 'objdump', 'readelf', 'nm', 'c++filt')]
    selected += [(n, controlled.compiler_child(args.compiler, n, env)) for n in ('cc1', 'cc1plus', 'collect2')]
    for name, executable in selected:
        require(executable is not None and Path(executable).is_file(), 'Build tool missing: ' + name)
        path = Path(executable).resolve(); tools[name] = {'path': str(path), **controlled.file_row(path)}
    commands = controlled.build_commands(sources, args.native_build, source_pins['runtime']['revision'], cmake)
    args.native_build.parent.mkdir(parents=True, exist_ok=True)
    for command in commands: subprocess.run(command, env=env, check=True)
    proof = controlled.collect_build_proof(native, sources, args.native_build, args.compiler, source_pins, commands, env, tools)
    args.lock = args.native_build / 'native-build-evidence/source-lock.json'
    native.freeze(sources, args.native_build, args.compiler, args.lock, p['version'])
    sys.path[:0] = [str(sources['runtime'] / 'scripts'), str(sources['image_helper'] / 'scripts')]
    qualify(args, sources, proof)


if __name__ == '__main__':
    main()

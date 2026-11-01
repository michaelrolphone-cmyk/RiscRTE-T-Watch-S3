#!/usr/bin/env python3
"""Build a source-locked Watch shared-Home candidate; no feed, release or device I/O.

The compiler and all native checks execute in this process. Historical fixed-pin
recipes remain unchanged; only this successor's committed inputs select versions.
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
import package_provisioning as legacy_package
import package_shared_app_native as package
from package_alarm_sleep import make_archive
from package_provisioning import require, sha, record, encoded

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/shared-app-native'
ROLES = {'product', 'runtime', 'system', 'utilities', 'drivers', 'sdk', 'watch', 'image_helper'}

def pins():
    p = json.loads((DOCS / 'source-pins.json').read_bytes())
    require(p['schema'] == 1 and p['product'] == 'twatch', 'Unsupported candidate identity')
    require(p['profile'] == 'profiles/native-provisioning.cmake', 'Retained provisioning profile required')
    return p


def canonical(args, sources, p):
    spec = importlib.util.spec_from_file_location('shared_home_verifier', sources['watch'] / 'scripts/verify_shared_default.py')
    verifier = importlib.util.module_from_spec(spec); spec.loader.exec_module(verifier)
    receipt = verifier.verify(args.first, args.second)
    elf, manifest, first = verifier.check_build(args.first)
    for role in ('system', 'utilities'):
        require(first['verified_dependencies'][role]['commit'] == p[role + '_revision'], 'Home dependency differs: ' + role)
    require(first['compiler_sha256'] == controlled.compiler_family(args.compiler)['s3-gcc']['sha256'], 'Home compiler differs')
    require(record(elf) == p['home']['elf'] and record(manifest) == p['home']['manifest'], 'Home bytes differ')
    require(json.loads(manifest)['version'] == p['home']['version'], 'Home version differs')
    for folder in (args.first, args.second):
        build = json.loads((folder / 'build.json').read_bytes())
        require(build.get('serial_transfer_mode') is not True and build.get('automatic_provision') is True, 'Automatic-only Home selection required')
        require(not any(flag.split('=', 1)[0] == '-DWATCH_SERIAL_TRANSFER_MODE' for flag in build['artifacts']['default']['defines']), 'Unexpected Home transfer mode')
    return elf, manifest, receipt


def preserved_native_images(baseline, firmware, packed, contract):
    """Keep the released bootloader/NVS prefix; only app/store/bank may change."""
    require(record(baseline) == {k: contract['factory'][k] for k in ('bytes', 'sha256')},
            'Exact released factory required for bootloader preservation')
    require(len(baseline) == 0x1000000, 'Retained factory layout differs')
    size = contract['bootloader']['bytes']
    require(type(size) is int and 0 < size <= 0x8000, 'Invalid released bootloader length')
    released_bootloader = baseline[:size]
    require(record(released_bootloader) == {k: contract['bootloader'][k] for k in ('bytes', 'sha256')},
            'Released bootloader digest differs')
    part_size = contract['partitions']['bytes']
    require(type(part_size) is int and 0 < part_size <= 0x1000, 'Invalid released partition length')
    require(record(baseline[0x8000:0x8000 + part_size]) ==
            {k: contract['partitions'][k] for k in ('bytes', 'sha256')}, 'Released partition digest differs')
    _, transition = native.make_images(baseline, firmware, released_bootloader, packed)
    # make_images' transition is the checked original-bootloader form. Do not
    # return its factory result, which rewrites bootloader padding to 0xff.
    require(len(transition) == len(baseline), 'Factory length changed')
    for start, end in ((0, 0x10000), (0x270000, 0x2f0000),
                       (0x840000, 0xff2000), (0xff3000, 0x1000000)):
        require(transition[start:end] == baseline[start:end], 'Protected released factory range changed')
    return transition, transition, released_bootloader


def linked_provisioning_layout(raw):
    import io
    from elftools.elf.elffile import ELFFile
    elf = ELFFile(io.BytesIO(raw))
    require(elf.has_dwarf_info(), 'Linked native type evidence missing')
    types = {}
    for cu in elf.get_dwarf_info().iter_CUs():
        name = cu.get_top_DIE().attributes.get('DW_AT_name')
        unit = name.value.decode() if name else ''
        if not unit.endswith(('/src/bootstrap/Runtime.cpp', '/src/ports/esp32s3/NativePackageVolume.cpp')):
            continue
        for die in cu.iter_DIEs():
            name = die.attributes.get('DW_AT_name')
            size = die.attributes.get('DW_AT_byte_size')
            if not name or not size or die.tag not in ('DW_TAG_class_type', 'DW_TAG_structure_type'):
                continue
            parent = die.get_parent()
            namespace = parent.attributes.get('DW_AT_name') if parent else None
            namespace = namespace.value if namespace else None
            if name.value == b'Runtime' and namespace == b'RiscBoot':
                members = [x for x in die.iter_children() if x.tag == 'DW_TAG_member'
                    and x.attributes.get('DW_AT_name') and x.attributes['DW_AT_name'].value == b'platforms_']
                require(len(members) == 1, 'Linked Runtime platform array missing')
                array = members[0].get_DIE_from_attribute('DW_AT_type')
                require(array.tag == 'DW_TAG_array_type', 'Unexpected linked platform member type')
                ranges = [x for x in array.iter_children() if x.tag == 'DW_TAG_subrange_type']
                require(len(ranges) == 1, 'Unexpected linked platform array rank')
                bounds = ranges[0].attributes
                count = bounds['DW_AT_count'].value if 'DW_AT_count' in bounds else bounds['DW_AT_upper_bound'].value + 1
                entry = array.get_DIE_from_attribute('DW_AT_type').attributes['DW_AT_byte_size'].value
                types.update(platform_slots=count, platform_entry_bytes=entry, runtime_bytes=size.value)
            elif name.value == b'Workspace' and unit.endswith('/NativePackageVolume.cpp'):
                types['package_workspace_bytes'] = size.value
    require(types.get('platform_slots') == 32 and types.get('package_workspace_bytes') == 15208,
            'Linked platform capacity or package workspace changed')
    symbols = elf.get_section_by_name('.symtab')
    placements = {}
    for label, suffix, expected_size in (
        ('boot_view', 'L15bootViewStorageE', 288), ('serial_workspace', 'L16workspaceStorageE', 2800)):
        rows = [x for x in symbols.iter_symbols() if x.name.endswith(suffix) and isinstance(x['st_shndx'], int)]
        require(len(rows) == 1 and rows[0]['st_size'] == expected_size, 'Linked workspace differs: ' + label)
        row = rows[0]; section = elf.get_section(row['st_shndx'])
        require(section.name == '.ext_ram.bss', 'Workspace escaped retained external memory: ' + label)
        placements[label] = dict(address=row['st_value'], bytes=row['st_size'], section=section.name)
    return dict(types=types, static_workspaces=placements,
                package_workspace_allocation='MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT',
                scope='Linked types and static placement; no physical heap or hardware acceptance')


def provisioning_compile_selection(commands, runtime):
    import shlex
    required = ('RISC_NATIVE_PACKAGE_VOLUME=1', 'RISC_NATIVE_PROVISION_REQUEST=1', 'RISC_PLATFORM_CAPACITY=32')
    source_root = (runtime / 'src').resolve()
    def source(row):
        path = Path(row['file'])
        return path.resolve() if path.is_absolute() else (Path(row['directory']) / path).resolve()
    selected = [r for r in commands if source(r).is_relative_to(source_root)]
    require(selected, 'Runtime compilation missing')
    for row in selected:
        arguments = row.get('arguments') or shlex.split(row['command'])
        transfer = [x for x in arguments if x.startswith('-DRISC_NATIVE_SERIAL_TRANSFER_MODE')]
        require(transfer in ([], ['-DRISC_NATIVE_SERIAL_TRANSFER_MODE=0']), 'Unexpected native transfer mode')
        for flag in required:
            definitions = [x for x in arguments if x.startswith('-D' + flag.split('=')[0] + '=')]
            require(definitions == ['-D' + flag], 'Provisioning product flags missing or ambiguous in actual compilation')
    return required, selected


def qualify_provisioning_native(blobs, proof, sources, build):
    commands = json.loads((build / 'compile_commands.json').read_bytes())
    required, selected = provisioning_compile_selection(commands, sources['runtime'])
    names = legacy_package.serial_files_product.linked_symbols(blobs['firmware_elf'])
    for symbol in ('RiscProvisionRequest', 'RiscPackageVolume', 'sleepPrepare', 'sleepResume', 'controlCheckpoint'):
        require(any(symbol in n for n in names), 'Provisioning adapter not linked: ' + symbol)
    linked = linked_provisioning_layout(blobs['firmware_elf'])
    from test_current_home_compatibility import qualify as qualify_home
    home_compatibility = qualify_home(sources['runtime'], sources['watch'])
    allocation = (sources['runtime'] / 'src/ports/esp32s3/NativePackageVolume.cpp').read_text()
    require('heap_caps_malloc(sizeof(Workspace),MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)' in allocation, 'Package workspace allocator selection changed')
    for name in ('NativeProvisionRequest.cpp', 'NativePackageVolume.cpp', 'NativePackageVolumeAdmission.cpp'):
        path = sources['runtime'] / 'src/ports/esp32s3' / name
        require(any(Path(r['file']).resolve() == path for r in selected), 'Provisioning unit not compiled: ' + name)
    return {'flags': list(required), 'compiled_runtime_rows': len(selected), 'linked_layout': linked, 'home_compatibility': home_compatibility, 'hardware_tested': False}



def qualify(args, sources, proof):
    from read_only_spiffs import read_image
    from prepare_preserving_update import layout, pair
    from current_bootfs import build
    from shared_app_native_admission import admit_product
    p = pins()
    lock = json.loads(args.lock.read_bytes())
    closure = controlled.validate_build_proof(proof, sources, args.native_build, args.compiler, lock)
    native.verify_sources(lock, sources)
    contract = package.baseline_contract()
    baseline = args.baseline.read_bytes()
    require(record(baseline) == {k: contract['factory'][k] for k in ('bytes', 'sha256')},
            'Exact released 1.1.46 factory required')
    _, _, store = pair(baseline, 0, layout(baseline))
    require(sha(store) == contract['store']['sha256'], 'Exact released store required')
    before = read_image(store, 0x550000)
    package.check_baseline(before, contract)
    # This unchanged verifier checks partitions, Xtensa ELF/BIN correspondence,
    # source markers, actual compiler rows, target bounds and physical hooks.
    native_contract = json.loads(native.CONTRACT.read_bytes())
    blobs, native_proof = native.verify_native(lock, sources, args.native_build, args.compiler, native_contract, baseline)
    serial = legacy_package.serial_files_product.check_native(blobs, native_proof, p['product'], sources['runtime'],
        (ROOT / 'profiles/native-idf61.cmake').read_text())
    provisioning = qualify_provisioning_native(blobs, native_proof, sources, args.native_build)
    home_abi = provisioning['home_compatibility']
    default, manifest, home_proof = canonical(args, sources, p)
    baseline_feed = args.feed.read_bytes()
    require(record(baseline_feed) == {k: contract['feed'][k] for k in ('bytes', 'sha256')}, 'Exact original feed required')
    expected = {'home': p['home'], 'firmware': {**record(blobs['firmware_bin']),
        'runtime_version': p['runtime_version'], 'runtime_revision': p['runtime_revision']}}
    after, preservation = package.compose(before, default, manifest, blobs['firmware_bin'],
        p['version'], lock['sources']['product']['revision'], expected)
    imports = native.reject_private(after, sources['runtime'])
    packed, packing = build(after, size=0x550000)
    require(build(after, size=0x550000)[0] == packed and read_image(packed, 0x550000) == after,
            'Deterministic store round-trip failed')
    factory, transition, released_bootloader = preserved_native_images(
        baseline, blobs['firmware_bin'], packed, contract)
    require(pair(factory, 0, layout(factory))[1:] == (blobs['firmware_bin'], packed), 'Factory binding differs')
    evidence = args.native_build / 'native-build-evidence'
    admission = admit_product(sources, blobs['firmware_elf'], before, after, native_proof, sanitized=False, receipt_dir=evidence)
    admission_san = admit_product(sources, blobs['firmware_elf'], before, after, native_proof, sanitized=True, receipt_dir=evidence)
    expected_count = sum(name.endswith('.elf') for name in after)
    require(expected_count > 0 and admission['elf_count'] == admission_san['elf_count'] == expected_count,
            'Incomplete product ELF admission')
    # Revalidate all immutable sources and native build artifacts after host checks.
    controlled.validate_build_proof(proof, sources, args.native_build, args.compiler, lock)
    native.verify_sources(lock, sources)
    assets = {'factory-candidate-erases-data-0x0.bin': factory, 'firmware.bin': blobs['firmware_bin'],
              'bootloader.bin': released_bootloader, 'partitions.bin': blobs['partitions'], 'store.bin': packed,
              'baseline-native-packages-v1.json': baseline_feed, 'default.elf': default, 'default.json': manifest}
    require(record(assets['baseline-native-packages-v1.json']) == {k: contract['feed'][k] for k in ('bytes', 'sha256')},
            'Baseline feed changed during qualification')
    report = dict(schema=1, status='software-qualified-candidate-hardware-pending', product=p['product'], version=p['version'],
        source_revision=lock['sources']['product']['revision'], hardware_tested=False, device_accessed=False,
        published=False, feed_emitted=False, factory_erases_data=True, preserving_update_kit_emitted=False,
        input_lock=lock, controlled_build=closure, native=native_proof, native_rebuilt=True,
        bootloader_preservation={'delivered': record(released_bootloader),
            'rebuilt_evidence_only': record(blobs['bootloader']),
            'released_prefix_bytes': 0x10000, 'released_prefix_sha256': sha(baseline[:0x10000]),
            'factory_prefix_sha256': sha(factory[:0x10000]),
            'partition_table_byte_identical': True},
        default=home_proof, serial_files=serial, provisioning=provisioning, home_abi=home_abi, baseline_contract=contract, preservation=preservation,
        public_imports=imports, admission=admission, admission_sanitized=admission_san,
        packing=packing,
        artifacts={name: record(raw) for name, raw in assets.items()})
    assets.update({'qualification.json': encoded(report), 'source-lock.json': args.lock.read_bytes(),
                   'source-pins.json': (DOCS / 'source-pins.json').read_bytes()})
    archive = {'qualification.json': assets['qualification.json'], 'canonical-a.json': (args.first / 'build.json').read_bytes(),
               'canonical-b.json': (args.second / 'build.json').read_bytes()}
    for row in lock['native_files'].values():
        archive['build/' + row['path']] = native.safe_path(args.native_build, row['path']).read_bytes()
    for path in evidence.rglob('*'):
        if path.is_file(): archive['build-evidence/' + path.relative_to(evidence).as_posix()] = path.read_bytes()
    assets['candidate-evidence.zip'] = make_archive(archive)
    assets['SHA256SUMS'] = ''.join(sha(raw) + '  ' + name + '\n' for name, raw in sorted(assets.items())).encode()
    args.output.mkdir(parents=True)
    for name, raw in assets.items(): (args.output / name).write_bytes(raw)
    print('Watch shared-Home candidate qualified; physical acceptance not established', flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', default=[])
    for name in ('compiler', 'baseline', 'native-build', 'output', 'first', 'second', 'feed'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    require(__debug__, 'Validation cannot be disabled')
    p = pins()
    require(p.get('runtime_revision'), 'Combined Runtime candidate pin is required')
    sources = native.parse_sources(args.source)
    required = ROLES
    require(set(sources) == required, 'Exact source closure required')
    args.native_build, args.output, args.compiler = args.native_build.resolve(), args.output.resolve(), args.compiler.resolve()
    controlled.validate_layout(sources, args.native_build, args.output, ROOT)
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
    commands = [[x.replace('profiles/native-idf61.cmake', 'profiles/native-provisioning.cmake') for x in row] for row in commands]
    args.native_build.parent.mkdir(parents=True, exist_ok=True)
    for command in commands: subprocess.run(command, env=env, check=True)
    proof = controlled.collect_build_proof(native, sources, args.native_build, args.compiler, source_pins, commands, env, tools)
    args.lock = args.native_build / 'native-build-evidence/source-lock.json'
    native.freeze(sources, args.native_build, args.compiler, args.lock, p['version'])
    sys.path[:0] = [str(sources['runtime'] / 'scripts'), str(sources['image_helper'] / 'scripts')]
    custody = args.native_build / 'native-build-evidence/locked-native'
    custody.mkdir()
    lock = json.loads(args.lock.read_bytes())
    for row in lock['native_files'].values():
        destination = custody / row['path']; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(native.safe_path(args.native_build, row['path']), destination)
    qualify(args, sources, proof)


if __name__ == '__main__':
    main()

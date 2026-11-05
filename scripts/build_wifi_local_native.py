#!/usr/bin/env python3
"""Build one isolated Watch native qualification variant with exact source closure.

This does not compose a store/factory, activate a released profile, migrate data,
or establish live heap, stack or shared AppData capacity.
"""
import argparse
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

import native_idf61_build as controlled
import native_idf61_candidate as native
import native_idf61_provenance as provenance
import wifi_local_native_contract as contract
from elftools.elf.elffile import ELFFile

require = contract.require
ROOT = contract.ROOT

def record(path):
    return controlled.file_row(path)

def select_tools(compiler, env):
    cmake = Path(shutil.which('cmake', path=env['PATH'])).resolve()
    if cmake.read_bytes()[:2] == b'#!':
        cmake = cmake.parent.parent / 'cmake/data/bin/cmake'
        require(cmake.is_file() and cmake.read_bytes()[:4] == b'\x7fELF', 'Native CMake required')
    env['PATH'] = str(cmake.parent) + os.pathsep + env['PATH']
    tools = controlled.compiler_family(compiler)
    selected = [('gcc', compiler), ('g++', compiler.with_name('xtensa-esp-elf-g++')),
                ('python', Path(sys.executable)), ('cmake', cmake),
                ('ninja', Path(shutil.which('ninja', path=env['PATH'])))]
    selected += [(n, compiler.with_name('xtensa-esp-elf-' + n))
                 for n in ('as', 'ld', 'ar', 'objcopy', 'objdump', 'readelf', 'nm', 'c++filt')]
    selected += [(n, Path(controlled.compiler_child(compiler, n, env)))
                 for n in ('cc1', 'cc1plus', 'collect2')]
    for name, path in selected:
        path = path.resolve()
        require(path.is_file(), 'Missing pinned tool: ' + name)
        tools[name] = {'path': str(path), **record(path)}
    return cmake, tools

def verify_selected(sources, build, compiler, lock, selection, variant):
    blobs = native.checked_artifacts(lock, build)
    effective = provenance.effective_sdkconfig(blobs)
    definitions = contract.definitions(selection['definitions'])
    required = {**definitions, 'RISC_NATIVE_ESP_IDF': '1',
                'RISC_TARGET': '"' + selection['target'] + '"'}
    family = controlled.compiler_family(compiler)
    require(family == lock['compiler_family'], 'Compiler family changed')
    rows = json.loads(blobs['compile_commands']) + json.loads(blobs['bootloader_compile_commands'])
    selected = []
    for row in rows:
        args = row.get('arguments') or shlex.split(row['command'])
        args = provenance.expand_response_files(args, build, row['directory'], blobs, lock['native_files'])
        provenance.compiler_command(args, compiler, family)
        if Path(row['file']).resolve().is_relative_to(sources['runtime'] / 'src'):
            provenance.compiler_definitions(args, required)
            if variant == 'local':
                require(args.count('-include') == 1 and
                        args[args.index('-include') + 1] == selection['settings'],
                        'Actual settings header differs')
                require('-fstack-usage' in args, 'Actual target frames not selected')
            else:
                require(not any('RISC_NATIVE_SETTINGS_' in x for x in args),
                        'Baseline unexpectedly selected settings lifecycle')
            selected.append(row)
    require(selected, 'No selected Runtime compilation')
    partition = Path(selection['partitions'])
    with tempfile.TemporaryDirectory(prefix='watch-wifi-partitions-') as tmp:
        expected = Path(tmp) / 'partitions.bin'
        subprocess.run([sys.executable, str(sources['sdk'] / 'components/partition_table/gen_esp32part.py'),
                        str(partition), str(expected)], check=True)
        require(expected.read_bytes() == blobs['partitions'], 'Linked partition bytes differ from retained layout')
    require(0 < len(blobs['firmware_bin']) <= 0x260000 and
            0 < len(blobs['bootloader']) <= 0x8000, 'Released firmware/bootloader slot exceeded')
    for binary, executable in (('firmware_bin', 'firmware_elf'), ('bootloader', 'bootloader_elf')):
        with tempfile.TemporaryDirectory(prefix='watch-wifi-image-') as tmp:
            output = Path(tmp) / 'image.bin'
            extra = ['--elf-sha256-offset', '0xb0', '--flash-mmu-page-size', '64KB'] if binary == 'firmware_bin' else []
            subprocess.run([sys.executable, '-m', 'esptool', '--chip', 'esp32s3', 'elf2image',
                '--flash-mode', 'dio', '--flash-freq', '80m', '--flash-size', '16MB',
                '--min-rev-full', '0', '--max-rev-full', '99', *extra, '-o', str(output),
                str(native.safe_path(build, lock['native_files'][executable]['path']))], check=True)
            require(output.read_bytes() == blobs[binary], 'ELF/BIN correspondence differs: ' + binary)
    p = contract.pins()
    for key in ('firmware_bin', 'firmware_elf'):
        require(set(re.findall(rb'RTE_SOURCE=([^\x00\s]+)', blobs[key])) == {p['runtime_revision'].encode()},
                'Runtime source identity differs')
        require(set(re.findall(rb'RISC_RUNTIME_VERSION:([^\x00]+)', blobs[key])) == {p['runtime_version'].encode()},
                'Runtime version differs')
    elf = ELFFile(io.BytesIO(blobs['firmware_elf']))
    require(elf.elfclass == 32 and elf.little_endian and elf['e_machine'] == 'EM_XTENSA',
            'Native Xtensa executable required')
    symbols = list(elf.get_section_by_name('.symtab').iter_symbols())
    labels = subprocess.check_output([str(compiler.with_name('xtensa-esp-elf-c++filt'))],
        input='\n'.join(s.name for s in symbols) + '\n', text=True).splitlines()
    require(not native.arduino_runtime_symbols(labels), 'Arduino runtime linked')
    named = {s.name: s for s in symbols}
    def symbol_bytes(name):
        require(name in named and isinstance(named[name]['st_shndx'], int), 'Missing linked ABI marker: ' + name)
        symbol = named[name]
        section = elf.get_section(symbol['st_shndx'])
        offset = symbol['st_value'] - section['sh_addr']
        return section.data()[offset:offset + symbol['st_size']]
    for name, value in {'risc_paired_store_abi': 3, 'risc_tcp_listener_abi': 1,
                        'risc_entropy_abi': 1, 'risc_file_source_abi': 1,
                        'risc_installed_app_capacity': 64}.items():
        require(symbol_bytes(name) == value.to_bytes(4, 'little'), 'Released linked ABI changed: ' + name)
    for name, prefix in (('risc_app_policy_rows', 'RISC_APP_POLICY_ROWS'),
                         ('risc_app_requirement_rows', 'RISC_APP_REQUIREMENT_ROWS')):
        require(symbol_bytes(name) == (prefix + ':32\0').encode(), 'Linked app policy bound changed')
    retained = json.loads(native.CONTRACT.read_bytes())['app_descriptor']
    descriptor = native.descriptor(blobs['firmware_bin'])
    require(descriptor['project_name'] == retained['project_name'] and
            descriptor['secure_version'] == retained['secure_version'],
            'Native project/security identity changed')
    for name in ('esp_ota_mark_app_valid_cancel_rollback', 'esp_ota_mark_app_invalid_rollback_and_reboot'):
        require(name in named and named[name]['st_shndx'] != 'SHN_UNDEF', 'Linked rollback operation missing')
    require(('risc_native_settings_admission' in named) == (variant == 'local'),
            'Actual settings backend linkage differs')
    require('risc_usb_controller_idf61_policy' not in named and
            'risc_usb_phy_resource_enabled' not in named, 'Unselected physical USB feature')
    require(not any(name == 'RiscCpu::selectedDisplayBackend()' and s['st_info']['bind'] == 'STB_GLOBAL'
                    for name, s in zip(labels, symbols)), 'Physical display selection changed')
    placements = {}
    if variant == 'local':
        for wanted in ('RiscCpu::NativeSettingsBackend::(anonymous namespace)::state',
                       'RiscCpu::NativeSettingsLifecycle::(anonymous namespace)::state',
                       'RiscCpu::NativeSettingsWorker::(anonymous namespace)::registry'):
            matches = [s for name, s in zip(labels, symbols) if name == wanted]
            require(len(matches) == 1, 'Missing linked settings control: ' + wanted)
            symbol = matches[0]
            section = elf.get_section(symbol['st_shndx'])
            require(section.name.startswith('.dram') and 0x3fc88000 <= symbol['st_value'] and
                    symbol['st_value'] + symbol['st_size'] <= 0x3fd00000,
                    'Settings control outside INTERNAL DRAM: ' + wanted)
            placements[wanted] = {'address': symbol['st_value'], 'bytes': symbol['st_size'],
                                  'section': section.name}
    sections = [{'name': s.name, 'address': s['sh_addr'], 'bytes': s['sh_size']}
                for s in elf.iter_sections() if s['sh_flags'] & 2 and
                s.name.startswith(('.dram', '.iram', '.ext_ram'))]
    sys.path.insert(0, str(sources['runtime'] / 'scripts'))
    from radio_iq_proof import prove
    iq = prove(blobs['firmware_elf'], selection['target'])
    subprocess.run([sys.executable, str(sources['runtime'] / 'test/native_firmware_idf6_test.py'),
                    '--build', str(build), '--cxxfilt', str(compiler.with_name('xtensa-esp-elf-c++filt'))],
                   check=True)
    return blobs, selected, {'effective_sdkconfig': effective, 'radio_iq': iq,
        'settings_static_controls': placements, 'linked_sections': sections,
        'compiled_runtime_rows': len(selected), 'partition_source_blob': p['partition_blob'],
        'elf_bin_identical': True, 'firmware_slot_bytes': 0x260000,
        'appdata_offset': 0x270000, 'appdata_bytes': 0x80000}

def target_layout(runtime, rows, build, output, compiler):
    chosen = [r for r in rows if Path(r['file']).resolve() == runtime / 'src/bootstrap/Runtime.cpp']
    require(len(chosen) == 1, 'Unique actual Runtime command required')
    row = chosen[0]
    arguments = row.get('arguments') or shlex.split(row['command'])
    base, skip = [], False
    for value in arguments:
        if skip:
            skip = False
            continue
        if value in ('-o', '-MF', '-MT', '-MQ'):
            skip = True
            continue
        if value in ('-c', '-MD', '-MMD', '-MP') or value == row['file']:
            continue
        base.append(value)
    obj = output / 'settings-layout.o'
    command = [*base, '-I' + str(runtime), '-fno-access-control', '-c',
               str(ROOT / 'tests/wifi_local_native/layout.cpp'), '-o', str(obj)]
    subprocess.run(command, cwd=row['directory'], check=True)
    nm = subprocess.check_output([str(compiler.with_name('xtensa-esp-elf-nm')), '-S', str(obj)], text=True)
    sizes = {line.split()[-1].removeprefix('measured_'): int(line.split()[1], 16)
             for line in nm.splitlines() if ' measured_' in line}
    require(len(sizes) == 11 and sizes['worker_stack_bytes'] == 8192 and sizes['worker_count'] == 2,
            'Incomplete actual ABI measurement or worker budget changed')
    frames = {}
    for path in sorted(build.rglob('*.su')):
        if 'esp-idf/runtime/' in path.as_posix():
            frames[path.relative_to(build).as_posix()] = path.read_text()
    require(frames and any('NativeSettingsBootstrap' in value for value in frames.values()),
            'Selected Runtime frame diagnostics missing')
    (output / 'target-frames.json').write_bytes(native.encoded(frames))
    result = {'sizes': sizes, 'compiler_command': command,
        'permanent_internal_allocation_bytes':
            sizes['assembly'] + sizes['assembly_alignment'] - 1 +
            2 * (sizes['worker_binding'] + sizes['worker_binding_alignment'] - 1),
        'worker_stack_bytes_total': 16384,
        'live_internal_heap_peak': None, 'live_psram_peak': None, 'runtime_stack_peak': None,
        'shared_appdata_capacity_admitted': False,
        'scope': 'Actual target object/layout and local compiler frames only; not live memory or stack-chain admission.'}
    (output / 'target-layout.json').write_bytes(native.encoded(result))
    (output / 'target-layout.nm').write_text(nm)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--variant', choices=('baseline', 'local'), required=True)
    args = parser.parse_args()
    require(__debug__, 'Validation cannot be disabled')
    contract.source_guard()
    p = contract.pins()
    sources = {'product': ROOT, 'runtime': args.runtime.resolve(), 'sdk': args.sdk.resolve()}
    build, output, compiler = args.build.resolve(), args.output.resolve(), args.compiler.resolve()
    controlled.validate_layout(sources, build, output, ROOT)
    pins = {role: native.clean_source(root, native.git(root, 'rev-parse', 'HEAD').decode().strip())
            for role, root in sources.items()}
    for role in ('runtime', 'sdk'):
        require(pins[role]['revision'] == p[role + '_revision'], 'Pinned source differs: ' + role)
    env = controlled.clean_environment(sources['sdk'], compiler)
    cmake, tools = select_tools(compiler, env)
    before, after = contract.profile_contract(sources['runtime'], cmake)
    selection = before if args.variant == 'baseline' else after
    profile = p['baseline_profile'] if args.variant == 'baseline' else p['qualification_profile']
    commands = controlled.build_commands(sources, build, p['runtime_revision'], cmake)
    commands = [[x.replace('profiles/native-idf61.cmake', profile) for x in row] for row in commands]
    build.parent.mkdir(parents=True, exist_ok=True)
    for command in commands:
        subprocess.run(command, env=env, check=True)
    proof = controlled.collect_build_proof(native, sources, build, compiler, pins, commands, env, tools)
    lock_path = build / 'native-build-evidence/source-lock.json'
    lock = native.freeze(sources, build, compiler, lock_path, p['runtime_version'])
    controlled.validate_build_proof(proof, sources, build, compiler, lock)
    blobs, rows, verified = verify_selected(sources, build, compiler, lock, selection, args.variant)
    output.mkdir(parents=True)
    layout = target_layout(sources['runtime'], rows, build, output, compiler) if args.variant == 'local' else None
    controlled.validate_build_proof(proof, sources, build, compiler, lock)
    native.verify_sources(lock, sources)
    contract.source_guard()
    report = {'schema': 1, 'variant': args.variant, 'sources': pins,
        'profile_before': before, 'profile_after': after, 'verification': verified,
        'target_layout': layout, 'product_activated': False, 'product_composed': False,
        'hardware_tested': False, 'shared_appdata_capacity_admitted': False,
        'source_closure_sha256': controlled.sha((build / 'native-build-evidence/build-closure.json').read_bytes()),
        'scope': __doc__, 'remaining': ['live per-pool heap and whole-call-chain stack admission',
            'real shared AppData allocation capacity with all writers and reboot',
            'full released app/provider/lifecycle and final byte-identical Wi-Fi composition',
            'device qualification before any released profile activation']}
    for name, key in (('firmware.bin', 'firmware_bin'), ('firmware.elf', 'firmware_elf'),
                      ('firmware.map', 'firmware_map'), ('partitions.bin', 'partitions')):
        (output / name).write_bytes(blobs[key])
    (output / 'source-lock.json').write_bytes(lock_path.read_bytes())
    for role in ('product', 'runtime'):
        (output / (role + '-source.tar')).write_bytes(native.git(sources[role], 'archive', '--format=tar', 'HEAD'))
    report['artifacts'] = {path.name: record(path) for path in output.iterdir() if path.is_file()}
    (output / 'qualification.json').write_bytes(native.encoded(report))
    (output / 'SHA256SUMS').write_text(''.join(controlled.sha(path.read_bytes()) + '  ' + path.name + '\n'
        for path in sorted(output.iterdir()) if path.is_file()))
    print(json.dumps(report, indent=2), flush=True)

if __name__ == '__main__':
    main()

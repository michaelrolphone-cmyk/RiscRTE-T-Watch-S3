#!/usr/bin/env python3
"""Full controlled SDK6.1 capacity-only successor; original recipe remains unchanged."""
import build_shared_app_native as base
from build_shared_app_native import *
import shared_home_capacity as capacity

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', default=[])
    for name in ('compiler', 'baseline', 'native-build', 'output'):
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
    commands = [[x.replace('profiles/native-idf61.cmake', 'profiles/shared-home-capacity.cmake') for x in row] for row in commands]
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
    capacity.qualify(args, sources, proof, base, cmake)


if __name__ == '__main__':
    main()

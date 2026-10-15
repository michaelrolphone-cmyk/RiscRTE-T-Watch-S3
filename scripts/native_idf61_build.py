#!/usr/bin/env python3
"""Fresh pinned IDF build and product qualification in one controlled invocation.

The JSON receipt is evidence, never an authorization token for a later process.
No existing build/cache is accepted. This command performs no device I/O.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

_TOKEN = object()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_row(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': sha(raw)}


def run(command, cwd=None, env=None):
    return subprocess.check_output([str(x) for x in command], cwd=cwd, env=env, text=True)


def clean_environment(sdk, compiler):
    env = dict(os.environ)
    for name in list(env):
        if name in {'CC', 'CXX', 'CPP', 'AR', 'AS', 'LD', 'NM', 'STRIP', 'OBJCOPY',
                    'CFLAGS', 'CPPFLAGS', 'CXXFLAGS', 'ASFLAGS', 'LDFLAGS', 'CPATH',
                    'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
                    'LIBRARY_PATH', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'GCC_EXEC_PREFIX',
                    'COMPILER_PATH', 'PYTHONPATH', 'PYTHONHOME', 'CMAKE_TOOLCHAIN_FILE',
                    'CMAKE_PREFIX_PATH', 'CMAKE_PROJECT_INCLUDE', 'CMAKE_PROJECT_INCLUDE_BEFORE',
                    'CMAKE_GENERATOR', 'IDF_CMAKE_ARGS', 'SDKCONFIG', 'SDKCONFIG_DEFAULTS'} or name.startswith(('CCACHE_', 'CMAKE_', 'RISC_', 'X4_', 'IDF_')) and name not in ('IDF_TOOLS_PATH', 'IDF_PYTHON_ENV_PATH', 'IDF_PYTHON_CHECK_CONSTRAINTS'):
            env.pop(name, None)
    env.update(IDF_PATH=str(sdk), CCACHE_DISABLE='1', IDF_CCACHE_ENABLE='0',
               PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', LC_ALL='C', TZ='UTC',
               CMAKE_BUILD_PARALLEL_LEVEL='1')
    env['PATH'] = str(compiler.parent) + os.pathsep + env.get('PATH', '')
    return env


def build_commands(sources, build, runtime_revision, cmake):
    configure = [sys.executable, sources['sdk'] / 'tools/idf.py', '-C', sources['runtime'] / 'idf', '-B', build,
                 '-D', 'RISC_PRODUCT_PROFILE=' + str(sources['product'] / 'profiles/native-idf61.cmake'),
                 '-D', 'RISC_SOURCE_SHA=' + runtime_revision, '-D', 'SDKCONFIG=' + str(build / 'sdkconfig'),
                 '-D', 'CCACHE_ENABLE=0', 'reconfigure']
    compile_one_job = [cmake, '--build', build, '--', '-j1']
    return [[str(value) for value in command] for command in (configure, compile_one_job)]


def validate_layout(sources, build, output, product_root):
    require(sources['product'] == product_root.resolve(), 'Controlled producer must be the pinned product checkout')
    require(not build.exists() and not output.exists(), 'Controlled build and candidate output must both be nonexistent')
    paths = [build.resolve(), output.resolve()]
    require(not paths[0].is_relative_to(paths[1]) and not paths[1].is_relative_to(paths[0]), 'Build and candidate output must be disjoint')
    for path in paths:
        for root in sources.values():
            root = root.resolve()
            require(not path.is_relative_to(root) and not root.is_relative_to(path), 'Build/output must not overlap a pinned source root')


def tracked_catalog(sources):
    """Index pinned Git blobs once, including exact initialized submodules."""
    result = {}
    for root in sorted(set(sources.values())):
        repositories = [root]
        lines = run(['git', '-C', root, 'submodule', 'status', '--recursive']).splitlines()
        require(all(line.startswith(' ') for line in lines), 'Changed/uninitialized submodule')
        repositories.extend(root / line.split()[1] for line in lines)
        for repository in repositories:
            raw = subprocess.check_output(['git', '-C', str(repository), 'ls-files', '--stage', '-z'])
            for record in raw.split(b'\0'):
                if not record:
                    continue
                metadata, name = record.split(b'\t', 1)
                mode, blob, stage = metadata.decode().split()
                require(stage == '0', 'Unmerged source index')
                if mode != '160000':
                    result[str((repository / name.decode()).absolute())] = blob
    return result


def dependency_rows(text, directory):
    """Read Ninja's compiler-produced dependency records, rejecting stale rows."""
    objects, paths, names = set(), set(), set()
    for line in text.splitlines():
        if not line:
            continue
        if not line.startswith(' '):
            match = re.fullmatch(r'(.+): #deps (\d+), deps mtime \d+ \((VALID|STALE)\)', line)
            require(match is not None and match[3] == 'VALID', 'Missing/stale Ninja dependency record: ' + line)
            objects.add((directory / match[1]).resolve())
        else:
            names.add(line.strip())
    for name in names:
        path = Path(name)
        paths.add((directory / path).resolve() if not path.is_absolute() else path.resolve())
    require(objects and paths, 'Empty Ninja dependency closure')
    return objects, paths


def ninja_input_paths(text, directory, query):
    """Resolve only Ninja-proven phony aliases; missing real inputs still fail.

    Ninja versions differ in whether `-t inputs` retains order-only phony
    targets. Query the actual graph instead of treating target-looking names
    or filename extensions as an exemption from source closure.
    """
    directory = directory.resolve()
    paths, aliases, visiting = set(), {}, set()

    def expand(name):
        require(name and not any(c in name for c in '\n\r\0'), 'Invalid Ninja input name')
        path = (directory / name).resolve()
        if path.exists():
            paths.add(path)
            return
        require(path.is_relative_to(directory), 'Missing external Ninja input: ' + str(path))
        canonical = path.relative_to(directory).as_posix()
        require(canonical not in visiting, 'Cyclic Ninja phony dependency: ' + canonical)
        if canonical in aliases:
            return
        require(len(aliases) + len(visiting) < 2048, 'Excessive Ninja phony closure')
        visiting.add(canonical)
        raw = query(canonical)
        lines = raw.splitlines()
        require(lines and lines[0] == canonical + ':' and len(lines) >= 3
                and lines[1] == '  input: phony', 'Missing non-phony Ninja input: ' + canonical)
        require(lines.count('  outputs:') == 1, 'Unrecognized Ninja query shape')
        stop = lines.index('  outputs:')
        require(stop >= 2, 'Unrecognized Ninja query order')
        children = []
        for line in lines[2:stop]:
            require(line.startswith('    '), 'Unrecognized Ninja dependency edge')
            child = line[4:]
            for prefix in ('|| ', '| '):
                if child.startswith(prefix):
                    child = child[len(prefix):]
                    break
            require(child, 'Empty Ninja dependency edge')
            children.append(child)
        for child in children:
            expand(child)
        visiting.remove(canonical)
        aliases[canonical] = {'rule': 'phony', 'inputs': children, 'query': raw}

    for name in text.splitlines():
        if name:
            expand(name)
    return paths, aliases


def map_inputs(raw, directory, executable, elf):
    from elftools.elf.elffile import ELFFile
    import io
    text = raw.decode()
    for marker in ('Memory Configuration', 'Linker script and memory map', 'Cross Reference Table'):
        require(marker in text, 'Incomplete native MAP: ' + marker)
    outputs = re.findall(r'^OUTPUT\((.+?) elf32-xtensa-le\)', text, re.M)
    require(len(outputs) == 1 and Path(outputs[0]).name == executable.name, 'MAP output differs from linked ELF')
    text = text.split('Linker script and memory map', 1)[1].split('Cross Reference Table', 1)[0]
    symbols = {symbol.name: symbol for symbol in ELFFile(io.BytesIO(elf)).get_section_by_name('.symtab').iter_symbols()}
    required = ['app_main', 'risc_installed_app_capacity', 'risc_elf_clock_gettime32', 'risc_app_policy_rows', 'risc_app_requirement_rows', 'risc_paired_store_abi', 'risc_runtime_update_version', 'vPortEvaluateYieldFromISR', '_Z5setupv', '_Z4loopv'] if 'app_main' in symbols else ['call_start_cpu0']
    required.extend(name for name, symbol in symbols.items() if (name.startswith('risc_x4') or 'reserved_region_risc_radio_iq' in name) and symbol['st_shndx'] != 'SHN_UNDEF')
    for name in required:
        require(name in symbols, 'Native MAP/ELF required symbol missing: ' + name)
        addresses = {int(match, 16) for match in re.findall(r'^\s+(0x[0-9a-fA-F]+)\s+' + re.escape(name) + r'\s*$', text, re.M)}
        sections = re.findall(r'^\s+\.(?!literal\.)[^\s]+\.' + re.escape(name) + r'\s+(0x[0-9a-fA-F]+)\s+', text, re.M)
        if 'reserved_region_risc_radio_iq' in name:
            sections.extend(re.findall(r'^\s+\.reserved_memory_address\s+(0x[0-9a-fA-F]+)\s+0x8\s+[^\n]*libruntime\.a\(NativeHardware\.cpp\.obj\)', text, re.M))
        addresses.update(int(address, 16) for address in sections)
        require(addresses == {symbols[name]['st_value']}, 'MAP/ELF symbol address differs or is ambiguous: ' + name)
    paths = set()
    for name in re.findall(r'^LOAD\s+(.+)$', text, re.M):
        path = Path(name.strip())
        paths.add((directory / path).resolve() if not path.is_absolute() else path.resolve())
    require(paths, 'MAP contains no linked inputs')
    return paths


class BuildProof:
    __slots__ = ('token', 'sources', 'build', 'compiler', 'pins', 'files', 'report', 'artifacts')


def collect_build_proof(recipe, sources, build, compiler, pins, command, env, tools):
    """Called only after this process's fixed fresh build has completed."""
    catalog = tracked_catalog(sources)
    rows = []
    objects, dependencies, traces = set(), set(), {}
    phony_aliases = {}
    evidence = build / 'native-build-evidence'; evidence.mkdir()
    for folder, label in ((build, 'app'), (build / 'bootloader', 'bootloader')):
        compilation = json.loads((folder / 'compile_commands.json').read_text())
        rows.extend(compilation)
        project = json.loads((folder / 'project_description.json').read_text()) if (folder / 'project_description.json').exists() else None
        executable = 'bootloader.elf' if label == 'bootloader' else Path(json.loads((build / 'flasher_args.json').read_text())['app']['file']).with_suffix('.elf').as_posix()
        for operation in ('deps', 'inputs', 'commands'):
            args = [tools['ninja']['path'], '-t', operation]
            if operation != 'deps':
                args.append(executable)
            content = run(args, cwd=folder, env=env)
            traces[label + '_' + operation] = content
            (evidence / (label + '_' + operation + '.txt')).write_text(content)
        found, headers = dependency_rows(traces[label + '_deps'], folder)
        objects.update(found); dependencies.update(headers)
        input_paths, aliases = ninja_input_paths(traces[label + '_inputs'], folder,
            lambda target: run([tools['ninja']['path'], '-t', 'query', target], cwd=folder, env=env))
        dependencies.update(input_paths)
        phony_aliases[label] = aliases
        traces[label + '_phony_queries'] = recipe.encoded(aliases).decode()
        (evidence / (label + '_phony_queries.txt')).write_text(traces[label + '_phony_queries'])
        executable_path = folder / executable
        map_path = executable_path.with_suffix('.map')
        dependencies.update(map_inputs(map_path.read_bytes(), folder, executable_path, executable_path.read_bytes()))
        dependencies.update((folder / 'build.ninja', folder / '.ninja_deps', folder / '.ninja_log', map_path, executable_path))
    for row in rows:
        arguments = shlex.split(row['command']) if 'command' in row else row['arguments']
        require('-o' in arguments, 'Compile command has no object output')
        directory = Path(row['directory']).resolve()
        obj = (directory / arguments[arguments.index('-o') + 1]).resolve()
        require(obj in objects, 'Compiled object lacks dependency record: ' + str(obj))
        dependencies.add(Path(row['file']).resolve())
    dependencies.update(objects)
    for suffix in ('*.a', '*.ld', '*.rsp'):
        dependencies.update(build.rglob(suffix))
    for folder in ('config', 'bootloader/config', 'toolchain', 'bootloader/toolchain'):
        dependencies.update(path for path in (build / folder).rglob('*') if path.is_file())
    dependencies.update(Path(item['path']) for item in tools.values())
    toolchain = compiler.parent.parent.resolve()
    rom = Path(env.get('ESP_ROM_ELF_DIR', '/nonexistent')).resolve()
    rom_file = rom / 'esp32s3_rev0_rom.elf'
    require(rom_file.is_file(), 'Pinned ROM ELF required')
    dependencies.add(rom_file)
    files, classes = {}, {}
    tool_paths = {Path(item['path']).resolve() for item in tools.values()}
    for path in sorted({path.resolve() for path in dependencies}):
        if path.is_dir():
            require(path == build / 'bootloader', 'Unreviewed directory dependency: ' + str(path))
            # Ninja represents the separately audited bootloader sub-build by
            # its directory; its complete object/header/link closure is above.
            classes['bootloader-build-directory'] = 1
            continue
        require(path.is_file(), 'Missing build dependency: ' + str(path))
        raw = path.read_bytes()
        if path.is_relative_to(build):
            kind = 'generated'
        elif str(path) in catalog:
            require(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == catalog[str(path)], 'Dependency differs from pinned Git blob: ' + str(path))
            kind = 'source'
        elif path.is_relative_to(toolchain) or path in tool_paths:
            kind = 'toolchain'
        elif path == rom_file:
            kind = 'rom-elf'
        else:
            raise ValueError('Dependency outside pinned source/build/toolchain roots: ' + str(path))
        files[str(path)] = {'bytes': len(raw), 'sha256': sha(raw), 'kind': kind}
        classes[kind] = classes.get(kind, 0) + 1
    for role, root in sources.items():
        require(recipe.clean_source(root, pins[role]['revision']) == pins[role], 'Source changed during fresh build: ' + role)
    artifacts = {key: file_row(recipe.safe_path(build, path)) for key, path in recipe.artifact_paths(build).items()}
    report = dict(schema=1, fresh_build=True, same_process_qualification=True,
                  detached_receipt_is_attestation=False, commands=command, compile_jobs=1, sources=pins,
                  tools=tools, dependency_counts=classes, files=files, artifacts=artifacts, phony_aliases=phony_aliases,
                  traces={key: {'sha256': sha(value.encode()), 'bytes': len(value.encode())} for key, value in traces.items()})
    for key, value in traces.items():
        (evidence / (key + '.txt')).write_text(value)
    (evidence / 'build-closure.json').write_bytes(recipe.encoded(report))
    proof = BuildProof(); proof.token = _TOKEN; proof.sources = dict(sources); proof.build = build
    proof.compiler = compiler; proof.pins = pins; proof.files = files; proof.report = report; proof.artifacts = artifacts
    return proof


def validate_build_proof(proof, sources, build, compiler, lock=None):
    require(type(proof) is BuildProof and proof.token is _TOKEN, 'Qualification requires a fresh controlled build in this process; JSON receipts are not attestation')
    require(proof.sources == sources and proof.build == build.resolve() and proof.compiler == compiler.resolve(), 'Controlled build inputs differ')
    for name, row in proof.files.items():
        path = Path(name)
        require(path.is_file() and file_row(path) == {key: row[key] for key in ('bytes', 'sha256')}, 'Controlled build input changed: ' + name)
    if lock is not None:
        require(lock['sources'] == proof.pins, 'Frozen sources differ from controlled build')
        for key, row in lock['native_files'].items():
            require(proof.artifacts.get(key) == {name: row[name] for name in ('bytes', 'sha256')}, 'Frozen artifact differs from controlled build: ' + key)
    return proof.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', default=[])
    for name in ('compiler', 'baseline', 'native-build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--candidate-version', required=True)
    parser.add_argument('--sd-archive', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('controlled_product_recipe', root / 'scripts/native_idf61_candidate.py')
    recipe = importlib.util.module_from_spec(spec); spec.loader.exec_module(recipe)
    sources = recipe.parse_sources(args.source)
    build, output, compiler = args.native_build.resolve(), args.output.resolve(), args.compiler.resolve()
    validate_layout(sources, build, output, root)
    pins = {role: recipe.clean_source(path, recipe.git(path, 'rev-parse', 'HEAD').decode().strip()) for role, path in sources.items()}
    require(pins['sdk']['revision'] == recipe.SDK_REVISION, 'Unreviewed SDK source')
    version = run([compiler, '--version']).splitlines()[0]
    require('15.2.0' in version and 'esp-15.2.0_20251204' in version, 'Exact native GCC15 required')
    env = clean_environment(sources['sdk'], compiler)
    cmake = shutil.which('cmake', path=env['PATH'])
    require(cmake is not None, 'Native CMake missing')
    cmake = Path(cmake).resolve()
    if cmake.read_bytes()[:2] == b'#!':
        native_cmake = cmake.parent.parent / 'cmake/data/bin/cmake'
        require(native_cmake.is_file() and native_cmake.read_bytes()[:4] == b'\x7fELF', 'Use native CMake or an isolated IDF environment; ambient PYTHONPATH is not allowed')
        cmake = native_cmake.resolve()
    env['PATH'] = str(cmake.parent) + os.pathsep + env['PATH']
    tools = {}
    selected_tools = [('gcc', str(compiler)), ('g++', str(compiler.with_name('xtensa-esp-elf-g++'))),
                             ('python', sys.executable), ('cmake', str(cmake)),
                             ('ninja', shutil.which('ninja', path=env['PATH']))]
    selected_tools.extend((name, str(compiler.with_name('xtensa-esp-elf-' + name))) for name in ('as', 'ld', 'ar', 'objcopy', 'objdump', 'readelf', 'nm', 'c++filt'))
    for name in ('cc1', 'cc1plus', 'collect2'):
        executable = run([compiler, '-print-prog-name=' + name]).strip()
        require(Path(executable).is_absolute(), 'Compiler child tool path is not absolute: ' + name)
        selected_tools.append((name, executable))
    for name, executable in selected_tools:
        require(executable is not None and Path(executable).is_file(), 'Required native build tool missing: ' + name)
        path = Path(executable).resolve(); tools[name] = {'path': str(path), **file_row(path)}
    commands = build_commands(sources, build, pins['runtime']['revision'], cmake)
    build.parent.mkdir(parents=True, exist_ok=True)
    for command in commands:
        subprocess.run(command, env=env, check=True)
    proof = collect_build_proof(recipe, sources, build, compiler, pins, commands, env, tools)
    args.native_build, args.compiler, args.output = build, compiler, output
    args.lock = build / 'native-build-evidence/source-lock.json'
    recipe.freeze(sources, build, compiler, args.lock, args.candidate_version)
    validate_build_proof(proof, sources, build, compiler, json.loads(args.lock.read_bytes()))
    recipe.qualify(args, sources, build_proof=proof)


if __name__ == '__main__':
    sys.modules['native_idf61_build'] = sys.modules[__name__]
    main()

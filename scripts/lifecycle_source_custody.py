"""Watch18 target compilation with independently pinned source admission."""
from pathlib import Path
import json
import subprocess

from build_contexts_cohort import Compiler, SECTION_FLAGS, LINK_FLAGS
from compact_current_elf import compact
from current_apps_overlay import metadata, require
from qualified_source_custody import dependencies, ordinary_file, source_head

PROVIDER_FLAGS = ['-std=c++17', '-fno-exceptions', '-fno-rtti',
                  '-DUPDATE_FIRMWARE=1', '-DUPDATE_SOURCE_ROUTES=1']


def catalog_inputs(out, rows):
    text = '#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={'
    text += ','.join('{' + ','.join('.' + k + '=' + json.dumps(v) for k, v in sorted(r.items())) + ',.compatible=true}' for r in rows)
    text += '};\nconst unsigned portable_catalog_count=' + str(len(rows)) + ';\n'
    return {Path(out) / 'catalog.c': text.encode(), Path(out) / 'empty_catalog.c':
            b'#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[1]={{.compatible=false}};\nconst unsigned portable_catalog_count=0;\n'}


def application_command(cc, out, name, sources, flags, includes):
    return [str(cc), '-std=c11', '-Os', '-fPIC', '-mtext-section-literals', '-mlongcalls',
            '-fvisibility=hidden', '-ffreestanding', '-fno-builtin', '-nostdlib', '-nostartfiles', '-shared',
            '-Wl,--no-relax', '-Wl,--hash-style=sysv', '-Wl,--version-script=' + str(Path(out) / (name + '.map')),
            '-Wall', '-Wextra', '-Werror', *SECTION_FLAGS, *LINK_FLAGS, *flags,
            *['-I' + str(p) for p in includes], *map(str, sources), '-lgcc', '-o', str(Path(out) / (name + '.elf'))]


def provider_command(cc, system, out, flags):
    # The independently pinned System script supplies these common options.
    # Admit its record's complete language/feature flags before reusing them.
    require(flags == PROVIDER_FLAGS, 'Firmware provider compiler flags differ')
    destination = Path(out) / 'update-provider-build/software-update-firmware'
    return [str(cc).removesuffix('gcc') + 'g++', '-Os', '-fPIC', '-mtext-section-literals',
            '-mlongcalls', '-fvisibility=hidden', '-ffreestanding', '-fno-builtin', '-nostdlib',
            '-nostartfiles', '-shared', '-Wl,--hash-style=sysv', '-Wall', '-Wextra', '-Werror',
            '-Wno-misleading-indentation', '-I' + str(Path(system) / 'lib/PortableApps/include'),
            '-I' + str(Path(system) / 'lib/NativeApps/include'), *flags,
            '-Wl,--version-script=' + str(destination / 'exports.map'),
            str(Path(system) / 'Services/update/service.cpp'), '-o', str(destination / 'driver.elf')]


class SourceCustody:
    def __init__(self, roots, pins, generated):
        require(set(roots) == set(pins), 'Compiler source inventory differs')
        self.roots = {name: Path(path).absolute() for name, path in roots.items()}
        self.pins = dict(pins)
        self.generated = {Path(path).absolute(): raw for path, raw in generated.items()}
        require(len(set(self.roots.values())) == len(self.roots), 'Compiler source roots overlap')
        for root in self.roots.values():
            require(root.resolve() == root and root.is_dir(), 'Real compiler source root required')
        self.preflight()

    def preflight(self):
        for name, root in self.roots.items():
            source_head(root, self.pins[name])
            # An ignored PCH may be consumed without the original header being
            # opened. Refuse it even when this particular scan does not use it.
            for path in root.rglob('*'):
                require(path.suffix not in ('.gch', '.pch'), 'Precompiled compiler input is not qualified: ' + str(path))
        for path, expected in self.generated.items():
            require(path.resolve() == path and path.is_file() and path.read_bytes() == expected,
                    'Generated compiler input changed: ' + str(path))

    def check(self, command):
        self.preflight()
        result = {}
        for path in dependencies(command, 180):
            if path in self.generated:
                result['generated:' + path.name] = metadata(self.generated[path])
                continue
            owners = [(name, root) for name, root in self.roots.items() if path.is_relative_to(root)]
            require(len(owners) == 1, 'Compiler input outside unique pinned source: ' + str(path))
            name, root = owners[0]
            relative = path.relative_to(root).as_posix()
            require(not {'test', 'tests', 'fixtures'} & set(Path(relative).parts), 'Target compiler used a host fixture: ' + str(path))
            try:
                expected = subprocess.check_output(['git', '-C', str(root), 'show', self.pins[name] + ':' + relative], stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as error:
                raise ValueError('Compiler input is not in pinned source: ' + str(path)) from error
            raw = ordinary_file(path, root)
            require(raw == expected, 'Compiler input differs from pinned source: ' + str(path))
            result[name + ':' + relative] = metadata(raw)
        for name, root in self.roots.items():
            source_head(root, self.pins[name])
        return result

    def compile(self, command):
        before = self.check(command)
        subprocess.run(command, check=True, timeout=180)
        require(self.check(command) == before, 'Compiler dependency closure changed during compilation')
        return before


def verify_dependencies(custody, command, recorded):
    require(custody.check(command) == recorded, 'Recorded compiler dependency custody differs')


class QualifiedCompiler(Compiler):
    def __init__(self, cc, root, out, repos, drivers, custody):
        self.custody = custody
        super().__init__(cc, root, out, repos, drivers)

    def build(self, name, sources, flags, includes, exports, allowed, *, compact_app=True):
        mapping = self.out / (name + '.map')
        mapping.write_text('{ global: ' + '; '.join(sorted(exports)) + '; local: *; };\n')
        elf = self.out / (name + '.elf')
        command = application_command(self.cc, self.out, name, sources, flags, includes)
        deps = self.custody.compile(command)
        subprocess.run([str(self.validator), str(elf)], check=True)
        proof = compact(elf, self.cc, debug_path=self.out / 'debug' / (name + '.elf')) if compact_app else None
        symbols = subprocess.check_output([self.cc.removesuffix('gcc') + 'nm', '-D', str(elf)], text=True)
        imports = {s.split()[-1] for s in symbols.splitlines() if ' U ' in ' ' + s}
        actual = {s.split()[-1] for s in symbols.splitlines() if len(s.split()) >= 3 and s.split()[-2] in ('T', 'D', 'B', 'R')}
        require(imports <= allowed and actual == exports, 'Unexpected target ABI: ' + name + ' ' + repr(sorted(imports - allowed)))
        subprocess.run([str(self.validator), str(elf)], check=True)
        raw = elf.read_bytes()
        require(raw[:7] == b'\x7fELF\x01\x01\x01' and raw[16:20] == b'\x03\x00\x5e\x00', 'Wrong Contexts target architecture')
        sizes = subprocess.check_output([self.cc.removesuffix('gcc') + 'size', str(elf)], text=True).splitlines()[1].split()
        return raw, {**metadata(raw), 'defines': flags, 'imports': sorted(imports), 'exports': sorted(actual),
            'section_gc': {'compile_flags': SECTION_FLAGS, 'link_flags': LINK_FLAGS, 'export_roots': sorted(exports)},
            'compaction': proof, 'sections_bytes': {k: int(v) for k, v in zip(('text', 'data', 'bss'), sizes[:3])},
            'target_dependencies': deps, 'host_fixture_excluded': True}

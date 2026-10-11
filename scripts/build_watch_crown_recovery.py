#!/usr/bin/env python3
"""Build the complete crown-cooperative Watch client overlay from named sources.

Inputs are the independently decoded, hash-verified delivered Watch 1.1.5 store
and clean source checkouts. This does not flash, assemble firmware, or qualify
physical hardware. The native reset fallback remains required for stalled apps.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = '089868395268b696c05651c33816345bfe0425df'
KEYBOARD = '377d471d284cf18e13927481362d011bc981dfee'
BASE_IMAGE = '376f5f57a2692e16d93180ad9cf6604ec32c6d53f794bb83c5d405731548da4c'
from watch_recovery_contract import PRESERVED_APPS, inspect_baseline, validate_overlay

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()

def clean(path):
    if git(path, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Dirty compiled source: ' + str(path))
    return git(path, 'rev-parse', 'HEAD')

def increment(version):
    parts = list(map(int, version.split('.')))
    assert len(parts) == 3
    parts[-1] += 1
    return '.'.join(map(str, parts))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

parser = argparse.ArgumentParser(description=__doc__)
for name in ('system', 'watch-canvas-system', 'utilities', 'watch-keyboard-utilities', 'productivity',
             'runtime', 'drivers', 'watch-profile', 'baseline', 'baseline-image',
             'baseline-receipt', 'output'):
    parser.add_argument('--' + name, type=Path, required=True)
a = parser.parse_args()
W = a.watch_profile.resolve()
S = a.system.resolve()
C = a.watch_canvas_system.resolve()
U = a.utilities.resolve()
O = a.output.resolve()
B = a.baseline.resolve()
repos = {'system-apps': C, 'shared-system-sdk': S, 'utilities': U, 'runtime': a.runtime.resolve(),
         'productivity': a.productivity.resolve(), 'drivers-sdk': a.drivers.resolve(),
         'watch-keyboard-utilities': a.watch_keyboard_utilities.resolve()}
source_pins = {name: clean(path) for name, path in repos.items()}
assert clean(W) == PROFILE
assert source_pins['watch-keyboard-utilities'] == KEYBOARD
assert source_pins['system-apps'] == '6ea07eb27488c2736b398fde1fb2915a392cfa68'
source_pins['watch-profile'] = PROFILE
source_pins['product'] = clean(ROOT)
assert sha(a.baseline_image) == BASE_IMAGE, 'Wrong delivered full image'
receipt = json.loads(a.baseline_receipt.read_text())
# The composition receipt records every decoded byte, not merely a list of apps.
expected = receipt['store']
if isinstance(expected, list):
    expected = {row['path']: row['sha256'] for row in expected}
actual = {str(p.relative_to(B)): sha(p) for p in B.rglob('*') if p.is_file()}
assert actual == expected, 'Decoded baseline does not match its complete receipt'
cohort = json.loads((B / 'cohort.json').read_text())
assert cohort['version'] == '1.1.5' and cohort['product'] == 'twatch-s3'
baseline_files = {str(p.relative_to(B)): p.read_bytes() for p in B.rglob('*') if p.is_file()}
boot, _ = inspect_baseline(baseline_files)
manifests = {Path(row['manifest']).stem: json.loads((B / row['manifest']).read_text())
             for row in boot['app_capabilities']}
assert len(manifests) == 25
assert not O.exists(), 'Choose a new output directory'
O.mkdir(parents=True)
store = O / 'store'
shutil.copytree(B, store)
build = O / 'build'
build.mkdir()
sys.path.insert(0, str(W / 'scripts'))
sys.path.insert(0, str(U / 'scripts'))
from build_contexts_cohort import definitions, Compiler, write_catalog
from build_current_apps import application_inputs
from contexts_profile import catalog
from compact_current_elf import compact
from normalize_xtensa_relocations import normalize
cc = os.environ.get('NATIVE_APP_CC') or shutil.which('xtensa-esp32s3-elf-gcc')
assert cc, 'Set NATIVE_APP_CC to the pinned compiler'
compiler = subprocess.check_output([cc, '--version'], text=True).splitlines()[0]
assert '8.4.0' in compiler and '2021r2-patch5' in compiler
rows = catalog(W) + [
    {'display_name': 'Lists', 'file_name': 'lists.elf', 'icon': 'solid:f274'},
    {'display_name': '3D Viewer', 'file_name': 'model_viewer.elf', 'icon': 'regular:f03e'},
]
assert len(rows) == 23
assert {row['file_name'] for row in rows} == {
    row['file_name'] for name, row in manifests.items() if name not in ('default', 'springboard')}
write_catalog(build, rows)
# Contexts workflows can launch from every eligible foreground app.
(build / 'empty_catalog.c').write_bytes((build / 'catalog.c').read_bytes())
alarm = build / 'watch-alarm-profile.h'
alarm.write_text('#include "' + str(U / 'lib/Alarm/include/AlarmServiceV1.h') + '"\n'
                 '#define ALARM_MODE_VISUAL 0u\n'
                 'static inline uint32_t alarm_service_output_modes(const alarm_service_v1*s)'
                 '{return s?ALARM_MODE_BOTH:ALARM_MODE_VISUAL;}\n')

class RecoveryCompiler(Compiler):
    def dependencies(self, sources, flags, includes):
        # The inherited builder calls its alarm-SDK root "drivers". This
        # composition intentionally takes that SDK from Utilities; record its
        # actual repository owner instead of creating a misleading source pin.
        original = super().dependencies(sources, flags, includes)
        mapped = {}
        for name, row in original.items():
            name = 'utilities:' + name.removeprefix('drivers:') if name.startswith('drivers:') else name
            if name in mapped and mapped[name] != row:
                raise ValueError('Conflicting dependency identity: ' + name)
            mapped[name] = row
        return mapped

    def build_client(self, name, sources, flags, includes, exports, allowed):
        deps = self.dependencies(sources, flags, includes)
        mapping = self.out / (name + '.map')
        mapping.write_text('{ global: ' + '; '.join(sorted(exports)) + '; local: *; };\n')
        elf = self.out / (name + '.elf')
        # The pinned Xtensa linker cannot GC the Spectrum/Waterfall dynamic
        # sections. Match their existing temporal build's documented workaround.
        sections = [] if name in ('audio_spectrum', 'waterfall') else [
            '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections']
        command = [self.cc, '-std=c11', '-Os', '-fPIC', '-mtext-section-literals', '-mlongcalls',
                   '-fvisibility=hidden', '-ffreestanding', '-fno-builtin', '-nostdlib',
                   '-nostartfiles', '-shared', '-Wl,--no-relax', '-Wl,--hash-style=sysv',
                   '-Wl,--version-script=' + str(mapping), '-Wall', '-Wextra', '-Werror',
                   *sections, *flags, *['-I' + str(p) for p in includes],
                   *map(str, sources), '-lgcc', '-o', str(elf)]
        subprocess.run(command, check=True)
        normalization = normalize(elf)
        subprocess.run([self.validator, elf], check=True)
        compaction = compact(elf, self.cc, debug_path=self.out / 'debug' / (name + '.elf'))
        subprocess.run([self.validator, elf], check=True)
        symbols = subprocess.check_output([self.cc.removesuffix('gcc') + 'nm', '-D', elf], text=True)
        imports = {s.split()[-1] for s in symbols.splitlines() if ' U ' in ' ' + s}
        actual_exports = {s.split()[-1] for s in symbols.splitlines()
                          if len(s.split()) >= 3 and s.split()[-2] in ('T', 'D', 'B', 'R')}
        assert imports <= allowed and actual_exports == exports, (name, imports - allowed)
        return {'bytes': elf.stat().st_size, 'sha256': sha(elf), 'command': command,
                'defines': flags, 'imports': sorted(imports), 'exports': sorted(actual_exports),
                'target_dependencies': deps, 'compaction': compaction,
                'relocation_normalization': normalization}

# The color Watch has no paper presentation provider. Preserve its existing
# color behavior while compiling the current portable Productivity sources.
shutil.copyfile(S / 'Apps/PaperPresentation.h', build / 'PaperPresentation.h')
paper = build / 'watch-paper-absent.c'
paper.write_text('#include \"PaperPresentation.h\"\n'
                 'const paper_presentation *paper_presentation_get(void){return 0;}\n')
comp = RecoveryCompiler(cc, W, build, repos, U)
proof = {}
for name, manifest in manifests.items():
    if name in PRESERVED_APPS | {'contexts', 'file_browser'}:
        continue
    owner = next((r for r in (C, U, a.productivity.resolve())
                  if (r / 'Apps' / (name + '.c')).exists()), None)
    assert owner, name
    source = owner / 'Apps' / ('timecard_portable.c' if name == 'timecard' else name + '.c')
    # New X4 Scanner sources require a shared-text provider absent from Watch.
    # Use the last published local-keyboard source, with this crown-aware adapter.
    # Never silently remove name editing or add a new capability to the store.
    if name == 'ble_scanner':
        source = repos['watch-keyboard-utilities'] / 'Apps/ble_scanner.c'
    version = increment(manifest['version'])
    flags = [f for f in definitions(name, version, W) if f != '-flto']
    if name == 'springboard':
        flags = [f for f in flags if not f.startswith('-DPORTABLE_CATALOG_LIMIT=')]
        flags += ['-DPORTABLE_CATALOG_LIMIT=23']
    flags += ['-include', str(alarm)]
    sources, includes, allowed = application_inputs(name, source, repos, W, build, 'runtime-features')
    includes += [U / 'lib/Contexts/include', repos['runtime'] / 'sdk/app',
                 S / 'lib/PortableApps/include', build]
    if name in ('points_in_time', 'timecard'):
        sources.append(paper)
    helper = C / 'lib/NativeApps/src/SingleFloatDivisionCompat.c'
    if name == 'audio_spectrum':
        sources.append(helper)
    if name not in ('audio_spectrum', 'waterfall'):
        flags += ['-flto']
        if helper in sources:
            flags += ['-Wl,--undefined=__divsf3']
    proof[name] = comp.build_client(name, sources, flags, includes,
        {'app_main', 'app_module_init', 'app_module_fini'}, allowed | {'memchr', 'strncmp', 'memmove'})
    manifest = dict(manifest, version=version)
    write(store / (name + '.json'), manifest)
    shutil.copyfile(build / (name + '.elf'), store / (name + '.elf'))
    write(O / 'clients.json', proof)
    print(name + ': full-profile crown client target passed', flush=True)

# Build the scene host against the baseline's four exact provider dependencies;
# optional native navigation does not add a new grant to this Watch product.
scene = load('watch_recovery_scene_builder', S / 'scripts/scene_build.py')
contexts = load('watch_recovery_contexts_builder', U / 'scripts/build_contexts_scene.py')
with tempfile.TemporaryDirectory(prefix='watch-crown-sdk-') as temporary:
    include = contexts.stage(repos['runtime'], S, Path(temporary))
    manifest = json.loads((B / 'ui-scene/manifest.json').read_text())
    manifest['version'] = increment(manifest['version'])
    proof['ui-scene'] = scene.build(cc, include, build / 'ui-scene', manifest,
                                    [S / 'Services/scene_host/host.c'])
    scene_elf = build / 'ui-scene/driver.elf'
    proof['ui-scene']['compaction'] = compact(scene_elf, cc, build / 'debug/ui-scene.elf')
    proof['ui-scene'].update(size_bytes=scene_elf.stat().st_size, sha256=sha(scene_elf))
    subprocess.run([comp.validator, scene_elf], check=True)
    for name in ('driver.elf', 'manifest.json'):
        shutil.copyfile(build / 'ui-scene' / name, store / 'ui-scene' / name)
    context_version = json.loads((U / 'Apps/contexts-scene.json').read_text())['version']
    assert tuple(map(int, context_version.split('.'))) >= (0, 4, 2), 'Qualified learning+crown Contexts required'
    manifest = dict(manifests['contexts'], version=context_version)
    proof['contexts'] = scene.build(cc, include, build / 'contexts', manifest,
        [U / 'Apps/contexts.c', build / 'catalog.c'],
        defines=['-include', str(W / 'apps/clock/faces/ContextsFaces.h')],
        exports={'app_main', 'risc_resident_app_descriptor_v1'})
    contexts_elf = build / 'contexts/contexts.elf'
    proof['contexts']['compaction'] = compact(contexts_elf, cc, build / 'debug/contexts.elf')
    proof['contexts'].update(size_bytes=contexts_elf.stat().st_size, sha256=sha(contexts_elf))
    subprocess.run([comp.validator, contexts_elf], check=True)
    for name in ('contexts.elf', 'contexts.json'):
        shutil.copyfile(build / 'contexts' / name, store / name)
write(O / 'clients.json', proof)

# Reuse the qualified ordinary Contexts service builder, including the completed
# bounded-learning correction. Its existing full Watch authority stays exact.
subprocess.run([sys.executable, str(U / 'scripts/build_contexts_service.py'),
                '--system-apps', str(S), '--drivers', str(repos['drivers-sdk']),
                '--runtime', str(repos['runtime']), '--profile', 'full'], check=True)
service_build = U / 'dist/contexts-service'
service_manifest = json.loads((service_build / 'manifest.json').read_text())
old_service = json.loads((B / 'contexts/manifest.json').read_text())
assert service_manifest['version'] == '0.3.2'
for field in ('type', 'id', 'driver_abi', 'architecture', 'file_name', 'requires', 'provides'):
    assert service_manifest[field] == old_service[field], 'Changed Contexts service authority: ' + field
shutil.copytree(service_build, build / 'contexts-service')
service_elf = build / 'contexts-service/driver.elf'
proof['contexts-service'] = json.loads((service_build / 'build-evidence.json').read_text())
proof['contexts-service']['compaction'] = compact(service_elf, cc, build / 'debug/contexts-service.elf')
proof['contexts-service'].update(size_bytes=service_elf.stat().st_size, elf_sha256=sha(service_elf))
subprocess.run([comp.validator, service_elf], check=True)
shutil.copyfile(service_elf, store / 'contexts/driver.elf')
# Keep the delivered descriptive metadata and authority; advance the code version.
write(store / 'contexts/manifest.json', dict(old_service, version=service_manifest['version']))
write(O / 'clients.json', proof)

# Preserve the specialized direct Files build and exact authority independently.
subprocess.run([sys.executable, str(S / 'scripts/build_watch_shared_files.py'),
                '--watch', str(W), '--utilities', str(U), '--runtime', str(repos['runtime']),
                '--baseline', str(B), '--output', str(build / 'files'), '--peer-files'], check=True)
files = json.loads((build / 'files/file_browser-build-record.json').read_text())
files_elf = build / 'files/file_browser.elf'
files['compaction'] = compact(files_elf, cc, build / 'debug/file_browser.elf')
files.update(bytes=files_elf.stat().st_size, sha256=sha(files_elf))
subprocess.run([comp.validator, files_elf], check=True)
old_policy = next(row for row in boot['app_capabilities'] if row['manifest'] == 'file_browser.json')
assert files['required_grants'] == old_policy['grants'], 'Unexpected Files authority change'
for name in ('file_browser.elf', 'file_browser.json'):
    shutil.copyfile(build / 'files' / name, store / name)
proof['file_browser'] = files
write(O / 'clients.json', proof)
contract = validate_overlay(baseline_files, {str(p.relative_to(store)): p.read_bytes()
                                               for p in store.rglob('*') if p.is_file()})
changed = {str(p.relative_to(store)): sha(p) for p in store.rglob('*')
           if p.is_file() and sha(p) != actual[str(p.relative_to(store))]}
assert len([p for p in store.glob('*.elf')]) == 25
assert (store / 'boot.json').read_bytes() == (B / 'boot.json').read_bytes()
for name in PRESERVED_APPS:
    assert (store / (name + '.elf')).read_bytes() == (B / (name + '.elf')).read_bytes()
write(O / 'recovery-overlay.json', {
    'schema': 1, 'product': 'twatch-s3', 'version': '1.1.6', 'baseline_version': '1.1.5',
    'baseline_image_sha256': BASE_IMAGE, 'baseline_store_sha256': actual,
    'source_pins': source_pins, 'builder_sha256': sha(Path(__file__)),
    'complete_store_contract': contract, 'compiler': compiler, 'changed_store_files': changed,
    'app_count': 25, 'provider_count': len(boot['drivers']),
    'unchanged_boot_authority': True, 'preserved_apps': sorted(PRESERVED_APPS),
    'canvas_profile': 'Delivered compact Watch lineage plus native crown hook; no shared X4 keyboard/UI port',
    'scanner_keyboard': 'Existing local Watch keyboard retained from exact published source',
    'settings_sd_persistence': 'Disabled; no shared_settings opt-in or persistence claim',
    'optional_paper_provider': 'Absent; explicit null provider preserves Watch color path',
    'target_validation': 'structural ELF and exact import/export checks',
    'physical_testing': 'not performed', 'native_assembly_and_admission_required': True,
})
print('Watch crown overlay complete; exact native and complete-store admission remain required.')

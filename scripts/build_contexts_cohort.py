#!/usr/bin/env python3
"""Build a new complete Contexts store without altering historical build lanes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from current_apps_overlay import ROOT, SYSTEM_APPS, UTILITY_APPS, CLOCK_APPS, encoded, metadata, require
from build_current_apps import definitions as prior_definitions, application_inputs
from build_wifi_common import zip_bytes
from compact_current_elf import compact
from current_cohort import encode as encode_cohort
from contexts_profile import (APPS, PRIOR_APPS, PROFILE, VERSION, SERVICE_MANIFEST,
    configuration, baseline_inputs, baseline_contract, catalog, upgrade_boot, app_manifest, check_policy)
SECTION_FLAGS = ['-ffunction-sections', '-fdata-sections']
LINK_FLAGS = ['-Wl,--gc-sections']
LTO_APPS = frozenset(('default','clock','audio_spectrum','waterfall','contexts'))
COMPILER_HELPERS = {'waterfall':('__divsf3',),
    'default':('__udivdi3','__umoddi3','__divdi3','__moddi3'),
    'clock':('__udivdi3','__umoddi3','__divdi3','__moddi3')}


def optimization_policy():
    return {'lto_apps':sorted(LTO_APPS),'compiler_helpers':{k:list(v) for k,v in sorted(COMPILER_HELPERS.items())},
            'boot_effect_lto':False,'service_compaction':True}

def verify_preserved_apps(files,root=ROOT):
    reference=json.loads((Path(root)/'apps/contexts-models-preserved.json').read_text())
    require(reference['schema']==1 and reference['source_version']=='1.0.15' and
            reference['source_revision']=='02f0225b1858ed4d3586891a9b22dd9af36ef210', 'Wrong frozen Contexts comparison')
    require(set(reference['changed_apps'])=={'audio_spectrum','waterfall'} and
            set(reference['preserved_apps'])==set(APPS)-{'audio_spectrum','waterfall'}, 'Capture cleanup rebuild scope differs')
    expected={name+suffix for name in reference['preserved_apps'] for suffix in ('.elf','.json')}
    require(set(reference['files'])==expected and len(expected)==42, 'Incomplete unchanged app inventory')
    for name,wanted in reference['files'].items():
        require(name in files and metadata(files[name])==wanted, 'Unrelated app changed from frozen1.0.15: '+name)
    require(set(reference['providers'])=={'contexts/driver.elf','contexts/manifest.json'},
            'Frozen model service inventory differs')
    for name,wanted in reference['providers'].items():
        require(name in files and metadata(files[name])==wanted, 'Model service changed from frozen1.0.15: '+name)
    return reference

def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()

def clean(path, expected=None):
    head = git(path, 'rev-parse', 'HEAD')
    require(expected is None or head == expected, 'Source pin differs: ' + str(path))
    require(not git(path, 'status', '--porcelain', '--untracked-files=no'), 'Tracked source is dirty: ' + str(path))
    return head

def definitions(name, version, root=ROOT):
    flags = prior_definitions(name, version, True, rf_spectrum=True, runtime_features=True)
    flags = [f for f in flags if not f.startswith('-DPORTABLE_CATALOG_LIMIT=')]
    if name in CLOCK_APPS:
        flags += ['-DWATCH_CONTEXTS_CLIENT']
    else:
        flags += ['-DPORTABLE_CONTEXTS_CLIENT', '-include', str(Path(root) / 'apps/clock/faces/ContextsFaces.h')]
    if name == 'springboard':
        flags += ['-DPORTABLE_CATALOG_LIMIT=21']
    if name == 'contexts':
        flags += ['-DPORTABLE_APP_OWNS_TOUCH_CHROME', '-DPORTABLE_CONTEXTS_EDITOR']
    if name in LTO_APPS:
        flags += ['-flto']
        flags += ['-Wl,--undefined=' + symbol for symbol in COMPILER_HELPERS.get(name,())]
    return flags

def source_manifest(repo, name):
    # These three have independent portable sidecars; never restamp or modify
    # the historical conditional Reader manifests.
    folder = 'native' if name in ('file_browser', 'ota_update', 'app_store', 'timecard') else ''
    return repo / 'Apps' / folder / (name + '.json')

class Compiler:
    def __init__(self, cc, root, out, repos, drivers):
        self.cc, self.root, self.out, self.repos, self.drivers = cc, root, out, repos, drivers
        self.validator = out / 'validate-elf'
        system = repos['system-apps']
        subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-I' + str(system / 'test/native_apps/stubs'), '-I' + str(system / 'lib/elf_loader/include'),
            str(system / 'lib/elf_loader/src/esp_elf_validate.c'), str(system / 'test/native_apps/validate_test.c'),
            '-o', str(self.validator)], check=True)
        (out / 'debug').mkdir()

    def dependencies(self, sources, flags, includes, *, cxx=False):
        deps = {}
        roots = {**self.repos, 'drivers': self.drivers, 'watch': self.root, 'generated': self.out}
        for source in sources:
            if str(source).endswith('.o'):
                continue
            executable = self.cc.removesuffix('gcc') + 'g++' if cxx else self.cc
            output = subprocess.check_output([executable, '-std=c++11' if cxx else '-std=c11', '-Os', '-fPIC', '-ffreestanding', '-fno-builtin',
                '-MM', *flags, *['-I' + str(p) for p in includes], str(source)], text=True)
            for item in shlex.split(output.replace('\\\n', ' ').split(':', 1)[1]):
                path = Path(item).resolve()
                require(path.is_file() and not {'test', 'tests', 'fixtures'} & set(path.parts), 'Unusable target dependency: ' + item)
                owners = [(owner, path.relative_to(base)) for owner, base in roots.items() if path.is_relative_to(base)]
                require(owners, 'Unowned target dependency: ' + item)
                owner, relative = owners[-1]
                deps[owner + ':' + relative.as_posix()] = metadata(path.read_bytes())
        return deps

    def build(self, name, sources, flags, includes, exports, allowed, *, compact_app=True):
        deps = self.dependencies(sources, flags, includes)
        mapping = self.out / (name + '.map')
        mapping.write_text('{ global: ' + '; '.join(sorted(exports)) + '; local: *; };\n')
        elf = self.out / (name + '.elf')
        subprocess.run([self.cc, '-std=c11', '-Os', '-fPIC', '-mtext-section-literals', '-mlongcalls',
            '-fvisibility=hidden', '-ffreestanding', '-fno-builtin', '-nostdlib', '-nostartfiles', '-shared',
            '-Wl,--no-relax', '-Wl,--hash-style=sysv', '-Wl,--version-script=' + str(mapping),
            '-Wall', '-Wextra', '-Werror', *SECTION_FLAGS, *LINK_FLAGS, *flags, *['-I' + str(p) for p in includes],
            *map(str, sources), '-lgcc', '-o', str(elf)], check=True)
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

def write_catalog(out, rows):
    text = '#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={'
    text += ','.join('{' + ','.join('.' + k + '=' + json.dumps(v) for k, v in sorted(r.items())) + ',.compatible=true}' for r in rows)
    text += '};\nconst unsigned portable_catalog_count=' + str(len(rows)) + ';\n'
    (out / 'catalog.c').write_text(text)
    (out / 'empty_catalog.c').write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[1]={{.compatible=false}};\nconst unsigned portable_catalog_count=0;\n')

def collect_licenses(root, repos, destination):
    for owner, repo in {**repos, 'watch': root}.items():
        for relative in git(repo, 'ls-files').splitlines():
            path = repo / relative
            if path.is_file() and not {'test', 'tests', 'fixtures'} & set(Path(relative).parts) and path.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
                target = destination / owner / relative
                target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(path.read_bytes())
    voice = repos['utilities'] / 'lib/VoiceActivity'
    for name in ('LICENSE', 'AUTHORS', 'PATENTS', 'SOURCES.json', 'PATCHES.md'):
        target = destination / 'voice-activity' / name
        target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes((voice / name).read_bytes())
    # Retained providers keep their existing bundled notices, including vendor
    # SDK dependency attributions. This is a copy, not a rebuild of providers.
    for path in (root / 'release/complete-1.0.7/licenses').rglob('*'):
        if path.is_file():
            target = destination / 'retained-providers' / path.relative_to(root / 'release/complete-1.0.7/licenses')
            target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(path.read_bytes())

def verify_build(directory, baseline, root=ROOT):
    directory, root = Path(directory), Path(root)
    record = json.loads((directory / 'contexts-build.json').read_text())
    require(record['schema'] == 1 and record['profile'] == PROFILE, 'Wrong Contexts build evidence')
    require(record['configuration'] == configuration(root), 'Context build source profile differs')
    require(record['optimization']==optimization_policy(), 'Context optimization policy differs')
    require(record['watch_source'] == git(root, 'rev-parse', 'HEAD'), 'Context build Watch source differs')
    previous = baseline_inputs(baseline, root)
    files = {p.relative_to(directory / 'files').as_posix(): p.read_bytes() for p in (directory / 'files').rglob('*') if p.is_file()}
    require(record['files'] == {n: metadata(raw) for n, raw in sorted(files.items())}, 'Context build file bytes differ')
    require(record['policy'] == check_policy(previous, files, record['configuration'], root), 'Context build policy proof differs')
    require(record['catalog'] == catalog(root) and set(record['apps']) == set(APPS), 'Context build catalog/apps differ')
    require(record['native_changed'] is False and record['native_rebuilt'] is False and record['physical_verification'] is False, 'Context build made an unsupported qualification claim')
    for name, proof in record['apps'].items():
        require(metadata(files[name + '.elf']) == {k: proof[k] for k in ('sha256', 'size_bytes')}, 'Context target proof differs: ' + name)
        require(proof['defines'] == definitions(name, record['configuration']['app_versions'][name], root), 'Context target flags differ: ' + name)
        require(proof['host_fixture_excluded'] and proof['target_dependencies'], 'Context target source closure absent: ' + name)
        require(proof['section_gc'] == {'compile_flags': SECTION_FLAGS, 'link_flags': LINK_FLAGS, 'export_roots': proof['exports']}, 'Context section-GC roots differ: ' + name)
        debug = directory / 'debug' / (name + '.elf')
        require(proof['compaction']['before_sha256'] == hashlib.sha256(debug.read_bytes()).hexdigest() and
                proof['compaction']['after_sha256'] == metadata(files[name + '.elf'])['sha256'], 'Context compaction custody differs: ' + name)
    require(record['preserved_from_1_0_15']==verify_preserved_apps(files,root), 'Unchanged app proof differs')
    provider=record['providers']['contexts-service'];compaction=provider['compaction']
    require(compaction['retained_loader_sections_symbols_relocations_unchanged'] is True and
            compaction['before_sha256']==metadata((directory/'debug/contexts-service.elf').read_bytes())['sha256'] and
            compaction['after_sha256']==metadata(files['contexts/driver.elf'])['sha256'], 'Provider compaction custody differs')
    from read_only_spiffs import read_image
    from current_bootfs import IMAGE_SIZE
    bootfs = (directory / 'contexts-bootfs.bin').read_bytes()
    require(len(bootfs) == IMAGE_SIZE and read_image(bootfs, IMAGE_SIZE) == files, 'Context bootfs independent bytes differ')
    require(record['packing']['sha256'] == hashlib.sha256(bootfs).hexdigest() and record['packing']['empty_blocks'] >= 2, 'Context bootfs capacity proof differs')
    require((directory / 'contexts-store.zip').read_bytes() == zip_bytes(files), 'Context store archive differs')
    return record

def build(system, utilities, productivity, runtime, drivers, baseline, out, *, root=ROOT, unpacked=None):
    root, out = Path(root).resolve(), Path(out).resolve()
    c = configuration(root)  # Final builds cannot admit null/pending pins.
    head = clean(root)
    repos = {key: Path(path).resolve() for key, path in [('system-apps', system), ('utilities', utilities), ('productivity', productivity), ('runtime', runtime)]}
    for name, repo in repos.items():
        clean(repo, c['sources'][name]['commit'])
    drivers = Path(drivers).resolve();clean(drivers, c['drivers']['commit'])
    require((repos['system-apps'] / 'lib/PortableApps/include/ContextsServiceV1.h').read_bytes() ==
            (repos['utilities'] / 'lib/Contexts/include/ContextsServiceV1.h').read_bytes(), 'Copied Contexts ABI differs')
    previous = baseline_inputs(baseline, root, unpacked)
    for directory in ('sdk/app', 'apps/runtime_features/sdk'):
        sdk = json.loads((root / directory / 'SOURCES.json').read_text())
        for name, proof in sdk.items():
            require(hashlib.sha256((root / directory / name).read_bytes()).hexdigest() == proof['sha256'], 'Canonical app SDK hash differs: ' + name)
    require(not out.exists(), 'Contexts output must be new; stale files are refused')
    out.mkdir(parents=True);files_dir = out / 'files';files_dir.mkdir()
    rows = catalog(root)
    require(json.loads((repos['system-apps'] / 'lib/PortableApps/additional-icons.json').read_text()).get('solid:f015') == 'house', 'Context house glyph is not audited')
    write_catalog(out, rows)
    cc = os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc')
    require(cc, 'Pinned TWATCH_CC required')
    compiler_version = subprocess.check_output([cc, '--version'], text=True).splitlines()[0]
    require('8.4.0' in compiler_version, 'GCC 8.4.0 required')
    compiler = Compiler(cc, root, out, repos, drivers)
    identity = json.loads(previous['cohort.json'])
    boot = upgrade_boot(json.loads(previous['boot.json']), identity)
    following = dict(previous)
    following['boot.json'] = (json.dumps(boot,sort_keys=True,separators=(',',':'))+'\n').encode()
    following['cohort.json'] = encode_cohort({**identity, 'version': VERSION, 'source_revision': head})
    record = {'schema': 1, 'profile': PROFILE, 'configuration': c, 'watch_source': head,
        'compiler': compiler_version, 'baseline': baseline_contract(root)['artifacts']['accepted-store.zip'],
        'native_changed': False, 'native_rebuilt': False, 'physical_verification': False,
        'catalog': rows, 'apps': {}, 'providers': {}, 'source_cohort': identity,
        'target_cohort': json.loads(following['cohort.json']),'optimization':optimization_policy()}
    for name in APPS:
        if name in CLOCK_APPS:
            continue
        owner = 'system-apps' if name in SYSTEM_APPS else 'utilities' if name in (*UTILITY_APPS, 'contexts') else 'productivity'
        repo = repos[owner]
        source = repo / 'Apps' / ('timecard_portable.c' if name == 'timecard' else name + '.c')
        source_sidecar = json.loads(source_manifest(repo, name).read_text())
        require(source_sidecar['version'] == c['source_app_versions'][name], 'Source manifest pin differs: ' + name)
        sources, includes, allowed = application_inputs(name, source, repos, root, out, 'runtime-features')
        includes += [repos['utilities'] / 'lib/Contexts/include']
        allowed |= {'memchr', 'strncmp'}
        flags = definitions(name, c['app_versions'][name], root)
        raw, proof = compiler.build(name, sources, flags, includes, {'app_main', 'app_module_init', 'app_module_fini'}, allowed)
        following[name + '.elf'] = raw
        old = json.loads(previous[name + '.json']) if name in PRIOR_APPS else None
        following[name + '.json'] = encoded(app_manifest(name, old, c, boot))
        record['apps'][name] = {**proof, 'repository': owner, 'repository_sha': c['sources'][owner]['commit'],
            'source_version': source_sidecar['version'], 'version': c['app_versions'][name]}
    effect = out / 'boot-effect.o'
    subprocess.run([cc.removesuffix('gcc') + 'g++', '-std=c++11', '-Os', '-fPIC', '-mtext-section-literals', '-mlongcalls',
        '-fvisibility=hidden', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics', '-ffreestanding', '-fno-builtin',
        '-Wall', '-Wextra', '-Werror', *SECTION_FLAGS, '-I' + str(root / 'sdk/driver'), '-c', str(root / 'apps/clock/effects/boot.cpp'), '-o', str(effect)], check=True)
    effect_deps = compiler.dependencies([root / 'apps/clock/effects/boot.cpp'], [], [root / 'sdk/driver'], cxx=True)
    clock_sidecar = root / 'apps/clock/contexts-manifest.json'
    clock_source_manifest = json.loads(clock_sidecar.read_text())
    require(clock_source_manifest['version'] == c['source_app_versions']['default'] == c['source_app_versions']['clock'] == c['app_versions']['default'] == c['app_versions']['clock'], 'Context Clock source/deployment version differs')
    for name in CLOCK_APPS:
        system = repos['system-apps']
        sources = [root / 'apps/clock/crown.c', root / 'apps/clock/nova/nova.c',
            *[system / 'lib/PortableApps/src' / n for n in ('quick_actions.c', 'quick_render.c', 'quick_session.c', 'quick_radios.c')],
            root / 'apps/clock/points_projection.c', root / 'apps/clock/effects/divdi3.c', effect]
        includes = [system / 'lib/PortableApps/include', repos['utilities'] / 'lib/Alarm/include',
            repos['utilities'] / 'lib/Contexts/include', root / 'sdk/app', root / 'sdk/driver', root / 'include']
        raw, proof = compiler.build(name, sources, definitions(name, c['app_versions'][name], root), includes,
            {'app_main'}, {'risc_runtime_get_api', 'memcpy', 'memset', 'memcmp', 'malloc', 'free', 'memchr', 'strncmp', 'strcmp', 'snprintf', 'strlen'})
        proof['target_dependencies'].update(effect_deps)
        following[name + '.elf'] = raw
        following[name + '.json'] = encoded(app_manifest(name, json.loads(previous[name + '.json']), c, boot))
        record['apps'][name] = {**proof, 'repository': 'watch', 'repository_sha': head, 'version': c['app_versions'][name],
            'source_version': clock_source_manifest['version'], 'source_manifest': metadata(clock_sidecar.read_bytes()),
            'boot_effect_source': metadata((root / 'apps/clock/effects/boot.cpp').read_bytes()), 'boot_effect_object': metadata(effect.read_bytes())}
    service = repos['utilities'] / 'Services/contexts'
    service_manifest = json.loads((service / 'manifest.json').read_text())
    require(service_manifest['id'] == c['contexts_service']['id'] and service_manifest['version'] == c['contexts_service']['version'], 'Wrong Contexts service source')
    raw, proof = compiler.build('contexts-service', [service / 'service.c'], [],
        [repos['utilities'] / 'Apps', repos['utilities'] / 'lib/Contexts/include', drivers / 'sdk/driver'],
        {'t5_driver_get'}, {'memcpy', 'memset', 'memcmp', 'memchr', 'strcmp', 'strlen'}, compact_app=True)
    following['contexts/driver.elf'] = raw;following[SERVICE_MANIFEST] = encoded(service_manifest)
    record['providers']['contexts-service'] = proof
    record['policy'] = check_policy(previous, following, c, root)
    record['preserved_from_1_0_15']=verify_preserved_apps(following,root)
    record['files'] = {name: metadata(raw) for name, raw in sorted(following.items())}
    record['preserved_providers'] = {name: metadata(raw) for name, raw in previous.items() if '/' in name}
    for name, raw in following.items():
        path = files_dir / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(raw)
    # SPIFFS round-trip/capacity is a separate mechanism with existing pinned
    # tooling. No native rebuild, erase image or device operation is performed.
    from current_bootfs import build as pack_store
    bootfs, packing = pack_store(following)
    require(packing['independent_round_trip_verified'] and packing['empty_blocks'] >= 2, 'Contexts bootfs capacity proof failed')
    (out / 'contexts-bootfs.bin').write_bytes(bootfs);record['packing'] = packing
    (out / 'contexts-store.zip').write_bytes(zip_bytes(following))
    collect_licenses(root, repos, out / 'licenses')
    for name, repo in repos.items():
        clean(repo, c['sources'][name]['commit'])
    clean(drivers, c['drivers']['commit']);clean(root, head)
    (out / 'contexts-build.json').write_bytes(encoded(record))
    (out / 'contexts-source-profile.json').write_bytes(encoded(c))
    members = {p.relative_to(out).as_posix(): p.read_bytes() for folder in (files_dir, out / 'debug', out / 'licenses') for p in folder.rglob('*') if p.is_file()}
    for name in ('contexts-build.json', 'contexts-source-profile.json'):
        members[name] = (out / name).read_bytes()
    (out / 'contexts-apps.zip').write_bytes(zip_bytes(members))
    verify_build(out, baseline, root)
    print('Contexts: 23 rebuilt apps, 22 preserved provider artifacts, 24 selections, native unchanged; target and bootfs checks PASS')
    return record

def main():
    p = argparse.ArgumentParser()
    for name in ('system-apps', 'utilities', 'productivity', 'runtime', 'drivers', 'baseline', 'output'):
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--unpacked-baseline', type=Path)
    a = p.parse_args()
    build(a.system_apps, a.utilities, a.productivity, a.runtime, a.drivers, a.baseline, a.output, unpacked=a.unpacked_baseline)

if __name__ == '__main__':
    main()

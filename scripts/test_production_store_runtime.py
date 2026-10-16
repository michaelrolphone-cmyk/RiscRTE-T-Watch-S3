#!/usr/bin/env python3
"""Launch the actual Clock through Runtime using unmodified production store JSON.

Native host recompilation substitutes executable architecture only. Policies,
board JSON and every app/provider manifest remain byte-for-byte untouched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from check_runtime_store_admission import archive_store, unpack_image, store_digest, validate_paths

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'tests/production_store_runtime'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, env=None):
    subprocess.run(list(map(str, command)), check=True, timeout=180, env=env)


def source_state(path):
    return {
        'commit': subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip(),
        'tracked_changes': subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=no'], text=True).strip(),
    }


def main():
    if not __debug__:
        raise RuntimeError('Run without Python optimization: custody assertions must remain enabled')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'system-apps', 'utilities'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--watch-source', type=Path, default=ROOT,
                        help='Exact Watch source for the supplied store (including historical Alarm stores)')
    parser.add_argument('--registry-support', type=Path,
                        help='Test adapter for compiling the actual target loader registry')
    parser.add_argument('--store', type=Path, action='append', default=[],
                        help='Exact production deployment store; repeat to check several stores')
    parser.add_argument('--archive', type=Path, nargs='+', action='extend', default=[])
    parser.add_argument('--image', type=Path, nargs='+', action='extend', default=[])
    parser.add_argument('--mkspiffs', type=Path)
    parser.add_argument('--read-only-spiffs', action='store_true')
    parser.add_argument('--output', type=Path, help='Keep host modules, copied stores and provenance here')
    parser.add_argument('--expect-prepare-error', help='Verify the old Runtime fails before any module is mapped')
    parser.add_argument('--expect-runtime-error', help='Verify a target-registry startup failure before Clock runs')
    args = parser.parse_args()
    if not (args.store or args.archive or args.image):
        parser.error('At least one exact --store, --archive or --image is required')
    if args.image and not (args.mkspiffs or args.read_only_spiffs):
        parser.error('--mkspiffs or --read-only-spiffs is required to extract images')
    runtime, system, utilities = (getattr(args, name).resolve() for name in ('runtime', 'system_apps', 'utilities'))
    watch = args.watch_source.resolve()
    registry = (args.registry_support or runtime/'test/support/native_registry').resolve()
    if args.expect_prepare_error and args.expect_runtime_error:
        parser.error('Select one expected failure stage')
    stores = [path.resolve() for path in args.store]
    temporary = None
    if args.output:
        build = args.output.resolve()
        build.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix='watch-production-runtime-')
        build = Path(temporary.name)
    sources = {'watch': watch, 'runtime': runtime, 'system-apps': system, 'utilities': utilities}
    provenance = {'sources': {name: source_state(path) for name, path in sources.items()},
                  'architecture': 'production target module registry with native host relocation; no Xtensa execution',
                  'stores': [], 'inputs': []}
    for index, path in enumerate([*args.archive, *args.image]):
        path = path.resolve()
        raw = path.read_bytes()
        content = archive_store(raw) if path in [p.resolve() for p in args.archive] else unpack_image(raw, args.mkspiffs)
        original = build/('original-' + str(index))
        # Retained evidence output may be reused after a compile failure, but
        # stale files must never enter the store or its custody digest.
        if original.exists():
            if any(p.is_file() for p in original.rglob('*')):
                assert {str(p.relative_to(original)): p.read_bytes() for p in original.rglob('*') if p.is_file()} == content, 'Output contains a different original store'
        for name, data in content.items():
            target = original/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        stores.append(original)
        provenance['inputs'].append({'path': str(path), 'sha256': sha(path), 'store_sha256': store_digest(content)})
    flags = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation']
    sanitized = os.environ.get('SANITIZE', '0') == '1' or os.environ.get('ADDRESS_SANITIZE') == '1'
    if sanitized:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
    execution_env = dict(os.environ)
    if sanitized:
        execution_env['UBSAN_OPTIONS'] = execution_env.get('UBSAN_OPTIONS', '') + ':halt_on_error=1'
    provenance['sanitizers'] = {'undefined': sanitized, 'address': sanitized,
        'asan_options': os.environ.get('ASAN_OPTIONS', '')}
    cc, cxx = os.environ.get('CC', 'cc'), os.environ.get('CXX', 'c++')
    includes = ['-I' + str(path) for path in (watch/'sdk/app', watch/'sdk/driver', watch/'include', watch)]
    clock_includes = ['-I' + str(path) for path in (system/'lib/PortableApps/include',
                       utilities/'lib/Alarm/include')] + includes
    modules = build/'modules'
    modules.mkdir(exist_ok=True)
    selections = {}
    compiled_sources = []
    source_manifests = {json.loads(path.read_text())['id']: path for path in (watch/'drivers').glob('*/manifest.json')}
    from build_legacy_sleep import legacy_manifests
    frozen_manifests = {json.loads(p.read_text())['id']: p for p in legacy_manifests(watch)}
    source_manifests.update(frozen_manifests)
    variants = {(source/'points_in_time.json').exists() for source in stores}
    assert len(variants) == 1, 'Run Alarm and Points/Wi-Fi stores separately with their exact source pins'
    points = variants.pop()
    for index, source in enumerate(stores):
        original_files = {str(path.relative_to(source)): path.read_bytes() for path in source.rglob('*') if path.is_file()}
        validate_paths(original_files)
        boot = json.loads((source/'boot.json').read_text())
        assert boot['default_app'] == 'default.elf', source
        # This regression must exercise the production multi-namespace policy,
        # not a stripped-down fixture that accidentally removes the failure.
        for name in ('default.json', 'clock.json', *(('points_in_time.json',) if points else ())):
            policy = next(item for item in boot['app_capabilities'] if item['manifest'] == name)
            assert sorted(grant['instance_id'] for grant in policy['grants']
                          if grant['capability'] == 'storage.key-value') == ([1, 5] if points else [1])
        assert len(boot['app_capabilities']) >= (10 if points else 9), source
        original_json = {str(path.relative_to(source)): sha(path) for path in source.rglob('*.json')}
        destination = build/('store-' + str(index))
        shutil.copytree(source, destination, dirs_exist_ok=True)
        record = {'source': str(source), 'host_store': str(destination), 'json_sha256': original_json,
                  'store_sha256': store_digest(original_files), 'original_files': len(original_files)}
        provenance['stores'].append(record)
        for selected in boot['drivers']:
            manifest_path = Path(selected['manifest'])
            manifest = json.loads((source/manifest_path).read_text())
            key = manifest['id']
            target = manifest_path.parent/manifest['file_name']
            if key != 'alarm-service':
                production = source_manifests[key]
                assert json.loads(production.read_text()) == manifest, (key, 'source/deployed manifest mismatch')
            selections.setdefault(key, {'manifest': manifest, 'targets': []})['targets'].append(destination/target)
    for name, selection in selections.items():
        output = modules/(name + '.elf')
        extra = []
        if name == 'alarm-service':
            source = utilities/'Services/alarm_service/service.c'
            manifest = 'points-manifest.json' if points else 'manifest.json'
            assert json.loads((utilities/'Services/alarm_service'/manifest).read_text()) == selection['manifest']
            extra = ['-DPOINTS_IN_TIME_SERVICE', '-DPORTABLE_RTC_UTC8_DENVER'] if points else []
            module_includes = ['-I' + str(path) for path in (utilities/'lib/Alarm/include',
                               runtime/'sdk/driver', system/'lib/PortableApps/include')]
        else:
            candidates = list(source_manifests[name].parent.glob('*.c'))
            assert len(candidates) == 1, name
            source = candidates[0]
            module_includes = includes
            if name in frozen_manifests:
                frozen_root = frozen_manifests[name].parents[2]
                module_includes=['-I'+str(frozen_root/p) for p in ('sdk/driver','include')]+includes
        run([cc, '-std=c11', *flags, '-fPIC', '-shared', '-fvisibility=hidden', *module_includes,
             *extra, source, '-o', output])
        compiled_sources.append(source)
        for target in selection['targets']:
            shutil.copy2(output, target)
    # Same translation units and feature flags as build_clock_app.py's current
    # Points/Wi-Fi default, compiled for host dlopen instead of Xtensa.
    clock_flags = ['-DWATCH_CLOCK_LAUNCHER', '-DWATCH_CLOCK_ALARMS', '-DPORTABLE_RTC_UTC8_DENVER']
    if points:
        clock_flags += ['-DWATCH_CLOCK_POINTS']
    objects = []
    for name in ('crown.c', 'nova/nova.c', *(('points_projection.c',) if points else ()), 'effects/divdi3.c'):
        output = modules/(Path(name).stem + '.o')
        run([cc, '-std=c11', *flags, '-fPIC', '-fvisibility=hidden', *clock_includes, *clock_flags,
             '-c', watch/'apps/clock'/name, '-o', output])
        compiled_sources.append(watch/'apps/clock'/name)
        objects.append(output)
    clock = modules/'default.elf'
    run([cxx, '-std=c++11', *flags, '-fPIC', '-shared', '-fvisibility=hidden', *includes,
         watch/'apps/clock/effects/boot.cpp', *objects, '-o', clock])
    for record in provenance['stores']:
        destination = Path(record['host_store'])
        shutil.copy2(clock, destination/'default.elf')
        assert record['json_sha256'] == {str(path.relative_to(destination)): sha(path) for path in destination.rglob('*.json')}
    registry_build = build/'native-registry'
    run(['bash', registry/'build.sh', registry_build, runtime],
        env={**os.environ, 'SANITIZE': '1' if sanitized else '0'})
    registry_objects = [registry_build/name for name in
                        ('target-dlfcn.o', 'target-dlmod.o', 'host-elf-backend.o')]
    host_includes = ['-I' + str(path) for path in (registry/'stubs', runtime/'lib/elf_loader/include',
                     registry, HERE, runtime/'src', runtime/'sdk/app',
                     runtime/'sdk/driver', runtime/'sdk/hardware', watch/'sdk/driver',
                     watch/'include', runtime/'lib/ArduinoJson/src')]
    runtime_sources = [runtime/path for path in ('src/bootstrap/Json.cpp', 'src/bootstrap/Board.cpp',
        'src/bootstrap/Runtime.cpp', 'src/ports/esp32s3/CpuPort.cpp',
        'src/runtime/drivers/ProviderGraphV2.cpp', 'src/runtime/drivers/ProviderModuleV2.cpp')]
    executable = build/'production-store-test'
    host_features = ['-DPRODUCTION_POINTS_READS=' + ('1' if points else '0')]
    ledger_objects = []
    defaults = points and '#define POINTS_DEFAULTS_AVAILABLE 1' in (utilities/'lib/Alarm/include/PointsRecords.h').read_text()
    provenance['virtual_points_defaults'] = defaults
    if defaults:
        host_features += ['-DPRODUCTION_POINTS_DEFAULTS']
        validator = build/'points-expiration-validator.c'
        validator.write_text('''#include "PointsRecords.h"
bool production_points_expiration_valid(const void* bytes,uint32_t size) {
    points_ledger ledger;
    return size==POINTS_RECORD_SIZE&&points_ledger_decode(&ledger,bytes,size)&&
        ledger.revision==points_default_config().revision&&ledger.generation==1&&
        !ledger.state&&!ledger.slot&&!ledger.edge&&!ledger.mode&&!ledger.deadline&&!ledger.recovery_until;
}
''')
        ledger = build/'points-expiration-validator.o'
        run([cc, '-std=c11', *flags, '-I'+str(utilities/'lib/Alarm/include'), '-c', validator, '-o', ledger])
        ledger_objects.append(ledger)
        compiled_sources.append(validator)
    if 'radioJoin' in (runtime/'src/ports/esp32s3/CpuPort.h').read_text():
        host_features += ['-DPRODUCTION_HAS_RADIO']
    if 'providerStorageSafe' in (runtime/'src/bootstrap/Runtime.h').read_text():
        host_features += ['-DPRODUCTION_STORAGE_SAFE']
    run([cxx, '-std=c++17', *flags, '-O0', '-Wno-missing-field-initializers', '-rdynamic', '-no-pie',
         *host_features, '-include', registry/'redirect.h',
         *host_includes, *runtime_sources, HERE/'host.cpp', *registry_objects, *ledger_objects, '-pthread', '-ldl', '-o', executable])
    registry_sources = [runtime/'lib/elf_loader/src/dlso'/name for name in ('dlfcn.c', 'dlmod.c')]
    provenance['compiled_source_sha256'] = {str(path): sha(path) for path in [*runtime_sources,
        *compiled_sources, *registry_sources, registry/'backend.c', registry/'redirect.h',
        HERE/'host.cpp', watch/'apps/clock/effects/boot.cpp']}
    provenance['target_registry'] = {'runtime_source': source_state(runtime)['commit'],
        'production_sources': {str(path.relative_to(runtime)): sha(path) for path in registry_sources},
        'adapter': str(registry), 'adapter_source': source_state(registry.parents[2]),
        'ordinary_dlopen_is_target_registry': True}
    for record in provenance['stores']:
        print('Unchanged production JSON:', record['source'], flush=True)
        command = [executable, record['host_store']]
        if args.expect_prepare_error:
            command += ['prepare', args.expect_prepare_error]
        if args.expect_runtime_error:
            command += ['runtime', args.expect_runtime_error]
        result = subprocess.run(list(map(str, command)), text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=60, env=execution_env)
        record['returncode'], record['output'] = result.returncode, result.stdout
        print(result.stdout, end='', flush=True)
        # Recheck the input and host copy after execution: the harness never
        # rewrites the boot, board or any application/provider policy.
        for location in (Path(record['source']), Path(record['host_store'])):
            assert record['json_sha256'] == {str(path.relative_to(location)): sha(path) for path in location.rglob('*.json')}
        original = Path(record['source'])
        assert record['store_sha256'] == store_digest({str(path.relative_to(original)): path.read_bytes()
               for path in original.rglob('*') if path.is_file()})
        for item in provenance['inputs']:
            assert item['sha256'] == sha(Path(item['path']))
        (build/'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
        if result.returncode:
            raise SystemExit(result.returncode)
    outcome = 'expected startup rejection' if args.expect_prepare_error or args.expect_runtime_error else 'Clock execution'
    print('All production-store ' + outcome + ' checks passed; JSON hashes unchanged.', flush=True)
    if temporary:
        temporary.cleanup()


if __name__ == '__main__':
    main()

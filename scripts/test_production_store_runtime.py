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


def run(command):
    subprocess.run(list(map(str, command)), check=True, timeout=180)


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
    parser.add_argument('--store', type=Path, action='append', default=[],
                        help='Exact production deployment store; repeat to check several stores')
    parser.add_argument('--archive', type=Path, nargs='+', action='extend', default=[])
    parser.add_argument('--image', type=Path, nargs='+', action='extend', default=[])
    parser.add_argument('--mkspiffs', type=Path)
    parser.add_argument('--output', type=Path, help='Keep host modules, copied stores and provenance here')
    parser.add_argument('--expect-prepare-error', help='Verify the old Runtime fails before any module is mapped')
    args = parser.parse_args()
    if not (args.store or args.archive or args.image):
        parser.error('At least one exact --store, --archive or --image is required')
    if args.image and not args.mkspiffs:
        parser.error('--mkspiffs is required to extract production images')
    runtime, system, utilities = (getattr(args, name).resolve() for name in ('runtime', 'system_apps', 'utilities'))
    stores = [path.resolve() for path in args.store]
    temporary = None
    if args.output:
        build = args.output.resolve()
        build.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix='watch-production-runtime-')
        build = Path(temporary.name)
    sources = {'watch': ROOT, 'runtime': runtime, 'system-apps': system, 'utilities': utilities}
    provenance = {'sources': {name: source_state(path) for name, path in sources.items()},
                  'architecture': 'native host shared modules; no Xtensa execution', 'stores': [], 'inputs': []}
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
    if os.environ.get('SANITIZE', '1') != '0':
        flags += ['-fsanitize=undefined', '-fno-sanitize-recover=all']
    if os.environ.get('ADDRESS_SANITIZE') == '1':
        flags += ['-fsanitize=address', '-fno-omit-frame-pointer']
    provenance['sanitizers'] = {'undefined': os.environ.get('SANITIZE', '1') != '0',
        'address': os.environ.get('ADDRESS_SANITIZE') == '1',
        'asan_options': os.environ.get('ASAN_OPTIONS', '')}
    cc, cxx = os.environ.get('CC', 'cc'), os.environ.get('CXX', 'c++')
    includes = ['-I' + str(path) for path in (ROOT/'sdk/app', ROOT/'sdk/driver', ROOT/'include', ROOT)]
    clock_includes = ['-I' + str(path) for path in (system/'lib/PortableApps/include',
                       utilities/'lib/Alarm/include')] + includes
    modules = build/'modules'
    modules.mkdir(exist_ok=True)
    selections = {}
    compiled_sources = []
    source_manifests = {json.loads(path.read_text())['id']: path for path in (ROOT/'drivers').glob('*/manifest.json')}
    for index, source in enumerate(stores):
        original_files = {str(path.relative_to(source)): path.read_bytes() for path in source.rglob('*') if path.is_file()}
        validate_paths(original_files)
        boot = json.loads((source/'boot.json').read_text())
        assert boot['default_app'] == 'default.elf', source
        # This regression must exercise the production multi-namespace policy,
        # not a stripped-down fixture that accidentally removes the failure.
        for name in ('default.json', 'clock.json', 'points_in_time.json'):
            policy = next(item for item in boot['app_capabilities'] if item['manifest'] == name)
            assert sorted(grant['instance_id'] for grant in policy['grants']
                          if grant['capability'] == 'storage.key-value') == [1, 5]
        assert len(boot['app_capabilities']) >= 10, source
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
            assert json.loads((utilities/'Services/alarm_service/points-manifest.json').read_text()) == selection['manifest']
            extra = ['-DPOINTS_IN_TIME_SERVICE', '-DPORTABLE_RTC_UTC8_DENVER']
            module_includes = ['-I' + str(path) for path in (utilities/'lib/Alarm/include',
                               runtime/'sdk/driver', system/'lib/PortableApps/include')]
        else:
            candidates = list(source_manifests[name].parent.glob('*.c'))
            assert len(candidates) == 1, name
            source = candidates[0]
            module_includes = includes
        run([cc, '-std=c11', *flags, '-fPIC', '-shared', '-fvisibility=hidden', *module_includes,
             *extra, source, '-o', output])
        compiled_sources.append(source)
        for target in selection['targets']:
            shutil.copy2(output, target)
    # Same translation units and feature flags as build_clock_app.py's current
    # Points/Wi-Fi default, compiled for host dlopen instead of Xtensa.
    clock_flags = ['-DWATCH_CLOCK_LAUNCHER', '-DWATCH_CLOCK_ALARMS', '-DWATCH_CLOCK_POINTS',
                   '-DPORTABLE_RTC_UTC8_DENVER']
    objects = []
    for name in ('crown.c', 'nova/nova.c', 'points_projection.c', 'effects/divdi3.c'):
        output = modules/(Path(name).stem + '.o')
        run([cc, '-std=c11', *flags, '-fPIC', '-fvisibility=hidden', *clock_includes, *clock_flags,
             '-c', ROOT/'apps/clock'/name, '-o', output])
        compiled_sources.append(ROOT/'apps/clock'/name)
        objects.append(output)
    clock = modules/'default.elf'
    run([cxx, '-std=c++11', *flags, '-fPIC', '-shared', '-fvisibility=hidden', *includes,
         ROOT/'apps/clock/effects/boot.cpp', *objects, '-o', clock])
    for record in provenance['stores']:
        destination = Path(record['host_store'])
        shutil.copy2(clock, destination/'default.elf')
        assert record['json_sha256'] == {str(path.relative_to(destination)): sha(path) for path in destination.rglob('*.json')}
    host_includes = ['-I' + str(path) for path in (HERE, runtime/'src', runtime/'sdk/app',
                     runtime/'sdk/driver', runtime/'sdk/hardware', ROOT/'sdk/driver',
                     ROOT/'include', runtime/'lib/ArduinoJson/src')]
    runtime_sources = [runtime/path for path in ('src/bootstrap/Json.cpp', 'src/bootstrap/Board.cpp',
        'src/bootstrap/Runtime.cpp', 'src/ports/esp32s3/CpuPort.cpp',
        'src/runtime/drivers/ProviderGraphV2.cpp', 'src/runtime/drivers/ProviderModuleV2.cpp')]
    executable = build/'production-store-test'
    run([cxx, '-std=c++17', *flags, '-O0', '-Wno-missing-field-initializers', '-rdynamic', '-no-pie',
         *host_includes, *runtime_sources, HERE/'host.cpp', '-ldl', '-o', executable])
    provenance['compiled_source_sha256'] = {str(path): sha(path) for path in [*runtime_sources,
        *compiled_sources, HERE/'host.cpp', HERE/'esp_dlfcn.h', ROOT/'apps/clock/effects/boot.cpp']}
    for record in provenance['stores']:
        print('Unchanged production JSON:', record['source'], flush=True)
        command = [executable, record['host_store']]
        if args.expect_prepare_error:
            command.append(args.expect_prepare_error)
        result = subprocess.run(list(map(str, command)), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
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
    print('All production-store Clock checks passed; JSON hashes unchanged.', flush=True)
    if temporary:
        temporary.cleanup()


if __name__ == '__main__':
    main()

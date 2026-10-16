#!/usr/bin/env python3
"""Update-only admission and real defaultClock startup against exact stores.

The delivered provider-registry correction remains in the baseline. This
lane uses the pinned paired Runtime and real target registry with host relocation.
"""
import argparse
import sys
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from check_runtime_store_admission import archive_store, unpack_image, store_digest, validate_paths, MKSPIFFS_SHA256, BOOTFS_SIZE

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'tests/update_production_store_runtime'
RUNTIME_COMMIT = json.loads((ROOT / 'apps/update-sources.json').read_text())['runtime']['commit']
RUNTIME_SOURCES = ('src/bootstrap/Json.cpp', 'src/bootstrap/Board.cpp',
    'src/bootstrap/Runtime.cpp', 'src/ports/esp32s3/CpuPort.cpp',
    'src/runtime/drivers/ProviderGraphV2.cpp', 'src/runtime/drivers/ProviderModuleV2.cpp')
SCENARIOS = ('healthy', 'early-health', 'frame-health-loss', 'confirm-refused', 'retained')
EXTERNAL_DRIVERS = {
    's3-radio-iq-v1': 's3_radio_iq_v1',
    'ble-hid': 'ble_hid',
    'ble-sensors': 'ble_sensors',
    'ble-telemetry': 'ble_telemetry',
    'telemetry-battery': 'telemetry_battery',
}


def external_driver_manifests(drivers):
    return {identity: Path(drivers) / 'Drivers' / folder / 'manifest.json'
            for identity, folder in EXTERNAL_DRIVERS.items()}


def external_source_hashes(drivers):
    roots = [Path(drivers) / 'Drivers' / folder for folder in EXTERNAL_DRIVERS.values()]
    roots.append(Path(drivers) / 'sdk/driver')
    return {str(p): sha(p) for root in roots for p in root.rglob('*') if p.is_file()}


def driver_source_manifests(current_profile=False, drivers=None, root=ROOT):
    from build_legacy_sleep import legacy_manifests
    sources = {json.loads(p.read_text())['id']: p for p in (root / 'drivers').glob('*/manifest.json')}
    frozen = {json.loads(p.read_text())['id']: p for p in legacy_manifests(root)}
    if current_profile:
        sources.update(external_driver_manifests(drivers))
        # The historical current-app overlay replaces GPIO/PMU but retains
        # the original panel. The separate power-repair profile replaces it.
        frozen = {'twatch-panel': frozen['twatch-panel']}
    sources.update(frozen)
    return sources, frozen



def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(args, timeout=180, env=None):
    completed = subprocess.run(list(map(str, args)), timeout=timeout,
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    if completed.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(map(str, args)) + '\n' + completed.stdout)
    return completed.stdout


def source_state(path):
    """Record exact source/tree and tracked modifications using read-only Git."""
    path = Path(path).resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()
    return {'path': str(path), 'commit': git('rev-parse', 'HEAD'),
            'tree': git('rev-parse', 'HEAD^{tree}'),
            'tracked_changes': git('status', '--porcelain', '--untracked-files=no')}


def _runtime(runtime, current_profile=False):
    runtime = Path(runtime).resolve()
    state = source_state(runtime)
    require(state['commit'] == (json.loads((ROOT/'apps/apex-runtime-requirements.json').read_text())['source_sha'] if current_profile else RUNTIME_COMMIT) and not state['tracked_changes'], 'Wrong or modified paired Runtime source')
    return runtime


def _flags():
    flags = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation']
    if os.environ.get('SANITIZE', '1') != '0':
        flags += ['-fsanitize=undefined', '-fno-sanitize-recover=all']
    if os.environ.get('ADDRESS_SANITIZE') == '1':
        flags += ['-fsanitize=address', '-fno-omit-frame-pointer']
    return flags


def _host(runtime, build, current_utilities=None, app_data=False, radio_iq=False):
    registry = runtime / 'test/support/native_registry'
    require((registry / 'build.sh').is_file(), 'Production target registry support is required')
    registry_build = build / 'native-registry'
    env = dict(os.environ)
    env['SANITIZE'] = '1' if os.environ.get('ADDRESS_SANITIZE') == '1' else '0'
    command(['bash', registry / 'build.sh', registry_build, runtime], env=env)
    objects = [registry_build / name for name in
               ('target-dlfcn.o', 'target-dlmod.o', 'host-elf-backend.o')]
    includes = [registry / 'stubs', runtime / 'lib/elf_loader/include', registry,
        ROOT / 'tests/production_store_runtime', runtime / 'src', runtime / 'sdk/app',
        runtime / 'sdk/driver', runtime / 'sdk/hardware', ROOT / 'sdk/driver',
        ROOT / 'include', runtime / 'lib/ArduinoJson/src']
    if current_utilities:
        validator = build / 'points-expiration-validator.c'
        validator.write_text('#include "PointsRecords.h"\nbool production_points_expiration_valid(const void* bytes,uint32_t size) {\n    points_ledger ledger;\n    return size==POINTS_RECORD_SIZE&&points_ledger_decode(&ledger,bytes,size)&&\n        ledger.revision==points_default_config().revision&&ledger.generation==1&&\n        !ledger.state&&!ledger.slot&&!ledger.edge&&!ledger.mode&&!ledger.deadline&&!ledger.recovery_until;\n}\n')
        ledger = build / 'points-expiration-validator.o'
        command([os.environ.get('CC', 'cc'), '-std=c11', *_flags(),
            '-I'+str(current_utilities/'lib/Alarm/include'), '-c', validator, '-o', ledger])
        objects.append(ledger)
    executable = build / 'update-store-test'
    sources = [runtime / name for name in RUNTIME_SOURCES]
    command([os.environ.get('CXX', 'c++'), '-std=c++17', *_flags(), '-O0',
        '-Wno-missing-field-initializers', '-rdynamic', '-no-pie',
        '-DPRODUCTION_POINTS_READS=1', '-DPRODUCTION_HAS_RADIO', '-DPRODUCTION_STORAGE_SAFE',
        *(['-DSTORE_ADMISSION_APP_DATA','-DRISC_PAIRED_APP_DATA=1'] if app_data else []),
        *(['-DCURRENT_RADIO_IQ'] if radio_iq else []),
        *(['-DCURRENT_IQ_LIFECYCLE'] if radio_iq and 'radioIqPrepare' in (runtime/'src/ports/esp32s3/CpuPort.h').read_text() else []),
        *(['-DPRODUCTION_POINTS_DEFAULTS','-DCURRENT_APPS_PROFILE','-I'+str(current_utilities/'lib/Alarm/include')] if current_utilities else []),
        '-include', registry / 'redirect.h',
        *['-I' + str(p) for p in includes], *sources, HERE / 'host.cpp', *objects,
        '-pthread', '-ldl', '-o', executable])
    return executable


@contextlib.contextmanager
def _build(output):
    if output:
        build = Path(output).resolve()
        build.mkdir(parents=True, exist_ok=True)
        yield build
    else:
        with tempfile.TemporaryDirectory(prefix='watch-update-store-') as temporary:
            yield Path(temporary)


def _files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def _write_store(destination, content):
    validate_paths(content)
    if destination.exists():
        require(_files(destination) == content, 'Output already contains a different store: ' + str(destination))
    for name, data in content.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _policies(content, current_profile=False):
    boot = json.loads(content['boot.json'])
    require(boot['default_app'] == 'default.elf', 'Not a defaultClock store')
    version=json.loads((ROOT/'apps/apex-apps-sources.json').read_text())['app_versions']['default'] if current_profile else '0.8.0'
    require(json.loads(content['default.json'])['version'] == version, 'Paired Clock manifest required')
    for name in ('default.json', 'clock.json', 'points_in_time.json'):
        policy = next(item for item in boot['app_capabilities'] if item['manifest'] == name)
        require(sorted(g['instance_id'] for g in policy['grants'] if g['capability'] == 'storage.key-value') == [1, 5], 'Clock/Points authority changed')
    require(len(boot['app_capabilities']) >= 11, 'Incomplete production application policy')
    for name, kind in [('ota_update', 'firmware'), ('app_store', 'apps')]:
        if name + '.json' not in content:
            continue
        policy = next(item for item in boot['app_capabilities'] if item['manifest'] == name + '.json')
        expected = {('display.output', 1, 5), ('input.touch.raw', 1, 6), ('rtc.clock', 2, 8),
                    ('board.battery', 1, 4), ('storage.key-value', 1, 6), ('net.wifi', 1, 15),
                    ('software.update.' + kind, 1, 0), ('alarm.service', 1, 0)}
        if current_profile:expected.update({('storage.key-value',1,1),('bluetooth.hci',1,16),('motion.accel',1,7)})
        actual = {(g['capability'], g['api'], g.get('instance_id', 0)) for g in policy['grants']}
        require(len(policy['grants']) == (11 if current_profile else 8) and actual == expected, 'Update app requires exactly its bounded grants')
    return boot


def _base_record(runtime):
    return {'schema': 1, 'runtime_source': source_state(runtime), 'runtime_version': json.loads((ROOT / 'apps/update-runtime-requirements.json').read_text())['firmware_version'],
            'architecture': 'production target registry with native host relocation, no Xtensa execution', 'policy_substitutions': 0,
            'physical_verification': 'pending', 'sanitizers': {'undefined': os.environ.get('SANITIZE', '1') != '0',
                'address': os.environ.get('ADDRESS_SANITIZE') == '1',
                'asan_options': os.environ.get('ASAN_OPTIONS', '')}, 'results': []}


def admit_many(runtime_source, stores, output=None):
    """Admit [(label, {relative_path: bytes})] without altering any store bytes."""
    runtime = _runtime(runtime_source)
    stores = list(stores)
    require(stores, 'At least one actual production store is required')
    require(len({label for label, _ in stores}) == len(stores), 'Duplicate store label')
    record = _base_record(runtime)
    before_sources = _source_hashes(runtime)
    with _build(output) as build:
        host = _host(runtime, build)
        for index, (label, content) in enumerate(stores):
            _policies(content)
            destination = build / ('admit-' + str(index))
            _write_store(destination, content)
            result = json.loads(command([host, destination, 'admit'], timeout=60))
            require(_files(destination) == content, 'Admission mutated the original store')
            record['results'].append(dict(label=label, store_files=len(content),
                store_sha256=store_digest(content), **result))
        record['source_sha256'] = _source_hashes(runtime)
        require(record['source_sha256'] == before_sources, 'Production source changed during admission')
        (build / 'admission-provenance.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def _source_hashes(runtime, system=None, utilities=None):
    files = [runtime / name for name in RUNTIME_SOURCES]
    for base in (runtime / 'sdk', runtime / 'src/bootstrap', runtime / 'src/runtime/drivers', ROOT / 'sdk', ROOT / 'include', ROOT / 'drivers', ROOT / 'apps/clock', HERE,
                 ROOT / 'tests/production_store_runtime', ROOT/'vendor',ROOT/'custody'):
        files += [p for p in base.rglob('*') if p.is_file() and p.suffix in ('.c', '.cpp', '.h', '.inc', '.json')]
    files += [Path(__file__), ROOT / 'apps/update-sources.json', runtime / 'src/bootstrap/Runtime.h', runtime / 'src/ports/esp32s3/CpuPort.h',
              runtime / 'test/run_update_runtime_test.sh', runtime / 'test/update_runtime_test.cpp',
              runtime / 'test/fixtures/update_health_app.c',
              runtime / 'lib/elf_loader/src/dlso/dlfcn.c', runtime / 'lib/elf_loader/src/dlso/dlmod.c']
    files += [p for p in (runtime / 'test/support/native_registry').rglob('*') if p.is_file()]
    if system:
        for base in (system / 'lib/PortableApps', system / 'Services/update', system / 'lib/NativeApps/include'):
            files += [p for p in base.rglob('*') if p.is_file() and p.suffix in ('.c', '.cpp', '.h', '.inc', '.json')]
    if system:
        files += [system / 'lib/NativeApps/src/UnsignedDivisionCompat.c']
    if utilities:
        files += [utilities / 'Services/alarm_service/service.c', utilities / 'Services/alarm_service/points-manifest.json']
        files += [p for p in (utilities / 'lib/Alarm/include').rglob('*') if p.is_file()]
    return {str(p): sha(p) for p in sorted(set(files))}


def verify_clock_abi(runtime_source, output=None, compiler=None, current_profile=False):
    """Guard-page tests using frozen/canonical SDKs, plus optional target compile."""
    runtime = _runtime(runtime_source,current_profile)
    compiler = compiler or os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc')
    require(compiler, 'Set TWATCH_CC to the pinned Xtensa compiler for the required target ABI checks')
    record = {'host': [], 'xtensa': [], 'target_executed': False}
    with _build(output) as build:
        for canonical in (False, True):
            name = 'canonical' if canonical else 'frozen'
            includes = ['-I' + str(runtime / 'sdk/app' if canonical else ROOT / 'sdk/app'),
                        '-I' + str(ROOT / 'apps/clock')]
            defines = ['-DUPDATE_CANONICAL_ABI'] if canonical else []
            binary = build / ('abi-' + name)
            output_text = command([os.environ.get('CC', 'cc'), '-std=c11', '-D_GNU_SOURCE', *_flags(),
                                  *includes, *defines, HERE / 'abi.c', '-no-pie', '-o', binary])
            output_text += command([binary])
            record['host'].append({'sdk': name, 'output': output_text.strip()})
            if compiler:
                target = build / ('abi-' + name + '.o')
                command([compiler, '-std=c11', '-Os', '-Wall', '-Wextra', '-Werror',
                         *includes, *defines, '-c', HERE / 'abi.c', '-o', target])
                record['xtensa'].append({'sdk': name, 'sha256': sha(target), 'size_bytes': target.stat().st_size})
        record['compiler'] = command([compiler, '--version']).splitlines()[0] if compiler else None
        (build / 'abi-provenance.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def execute_many(runtime_source, system_apps, utilities, productivity, stores, output=None, current_profile=False, app_data=False, drivers=None):
    """Run paired defaultClock against exact profile/common/extracted stores.

    productivity is recorded for the enclosing product's source custody; its
    applications are admitted but aren't substituted or executed by this lane.
    """
    runtime, system, utilities = _runtime(runtime_source,current_profile), Path(system_apps).resolve(), Path(utilities).resolve()
    stores = list(stores)
    require(stores, 'At least one actual production store is required')
    require(len({label for label, _ in stores}) == len(stores), 'Duplicate store label')
    record = _base_record(runtime)
    record['sources'] = {name: source_state(path) for name, path in
                         [('watch', ROOT), ('system-apps', system), ('utilities', utilities)]}
    if productivity:
        record['sources']['productivity'] = source_state(productivity)
    pins = (json.loads((ROOT/'apps/apex-apps-sources.json').read_text())['sources'] if current_profile else json.loads((ROOT / 'apps/update-sources.json').read_text()))
    record['current_apps_profile']=bool(current_profile)
    if current_profile:record['runtime_version']=json.loads((ROOT/'apps/apex-runtime-requirements.json').read_text())['firmware_version']
    for name, state in record['sources'].items():
        if name != 'watch':
            require(state['commit'] == pins[name]['commit'] and not state['tracked_changes'], 'Wrong or modified pinned production source: ' + name)
    before_sources = _source_hashes(runtime, system, utilities)
    record['clock_defines'] = ['WATCH_CLOCK_LAUNCHER', 'WATCH_CLOCK_ALARMS', 'WATCH_CLOCK_POINTS',
                              'PORTABLE_RTC_UTC8_DENVER', 'WATCH_PAIRED_BOOT_CONFIRM']
    if current_profile:record['clock_defines']+=['WATCH_QUICK_ACTIONS','WATCH_QUICK_RADIOS','WATCH_MOTION_WAKE','WATCH_ALARM_SLEEP_RESUME']
    with _build(output) as build:
        if current_profile:
            require(drivers is not None,'Exact SDR source required for current execution')
            drivers=Path(drivers).resolve();expected=json.loads((ROOT/'apps/apex-apps-sources.json').read_text())['sdr']
            record['sdr_source']=source_state(drivers)
            require(record['sdr_source']['commit']==expected['commit'] and not record['sdr_source']['tracked_changes'],'Wrong or modified SDR source')
            record['sdr_source_hashes']=external_source_hashes(drivers)
        host = _host(runtime, build, utilities if current_profile else None, app_data, radio_iq=current_profile)
        modules = build / 'modules'
        modules.mkdir(exist_ok=True)
        cc, cxx = os.environ.get('CC', 'cc'), os.environ.get('CXX', 'c++')
        includes = ['-I' + str(p) for p in (ROOT / 'sdk/app', ROOT / 'sdk/driver', ROOT / 'include', ROOT)]
        clock_includes = ['-I' + str(p) for p in (system / 'lib/PortableApps/include', utilities / 'lib/Alarm/include')] + includes
        source_manifests, frozen_manifests = driver_source_manifests(current_profile, drivers)
        selections = {}
        prepared = []
        for index, (label, content) in enumerate(stores):
            boot = _policies(content, current_profile)
            original, destination = build / ('original-' + str(index)), build / ('store-' + str(index))
            _write_store(original, content)
            # Never reuse a stale host store after different inputs.
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(original, destination)
            prepared.append((label, content, original, destination, boot))
            for selected in boot['drivers']:
                manifest_path = Path(selected['manifest'])
                manifest = json.loads(content[manifest_path.as_posix()])
                key = manifest['id']
                target = destination / manifest_path.parent / manifest['file_name']
                if key.startswith('software-update-'):
                    kind = key.removeprefix('software-update-')
                    production = system / 'Services/update' / kind / 'manifest.json'
                elif key == 'alarm-service':
                    production = utilities / 'Services/alarm_service/points-manifest.json'
                else:
                    production = source_manifests[key]
                require(json.loads(production.read_text()) == manifest, 'Source/deployed manifest mismatch: ' + key)
                selections.setdefault(key, []).append(target)
        for name, targets in selections.items():
            module = modules / (name + '.elf')
            extra, compiler, language = [], cc, '-std=c11'
            if name == 'alarm-service':
                source = utilities / 'Services/alarm_service/service.c'
                extra = ['-DPOINTS_IN_TIME_SERVICE', '-DPORTABLE_RTC_UTC8_DENVER']+(['-DALARM_VOLUME_CONTROL','-DALARM_DND_CONTROL'] if current_profile else [])
                module_includes = ['-I' + str(p) for p in (utilities / 'lib/Alarm/include', runtime / 'sdk/driver', system / 'lib/PortableApps/include')]
            elif name=='s3-radio-iq-v1':
                source=drivers/'Drivers/s3_radio_iq_v1/driver.c'
                extra=['-DRISC_IQ_HOST_TEST']
                module_includes=['-I'+str(drivers/'sdk/driver'),'-I'+str(drivers/'test')]
            elif name=='ble-hid':
                command([sys.executable,drivers/'scripts/build_ble_hid.py','--host',*(['--sanitize'] if os.environ.get('SANITIZE')=='1' else [])])
                built=drivers/('build/ble-hid-san' if os.environ.get('SANITIZE')=='1' else 'build/ble-hid-host')/'driver.so'
                shutil.copy2(built,module)
                for target in targets:shutil.copy2(module,target)
                continue
            elif name.startswith('software-update-'):
                source = system / 'Services/update/service.cpp'
                compiler, language = cxx, '-std=c++17'
                extra = ['-fno-exceptions', '-fno-rtti', '-DUPDATE_FIRMWARE=' + str(int(name.endswith('firmware')))]
                module_includes = ['-I' + str(system / part) for part in ('lib/PortableApps/include', 'lib/NativeApps/include')]
            else:
                candidates = list(source_manifests[name].parent.glob('*.c'))
                require(len(candidates) == 1, 'Driver does not have one production source: ' + name)
                source = candidates[0]
                module_includes = ['-I'+str(drivers/'sdk/driver')] if current_profile and name in EXTERNAL_DRIVERS else includes
                if name in frozen_manifests:
                    frozen_root = frozen_manifests[name].parents[2]
                    module_includes=['-I'+str(frozen_root/p) for p in ('sdk/driver','include')]+includes
            command([compiler, language, *_flags(), '-fPIC', '-shared', '-fvisibility=hidden',
                     *module_includes, *extra, source, *(__import__('imu_sources').extra_sources(name)), '-o', module])
            for target in targets:
                shutil.copy2(module, target)
        objects = []
        for name in ('crown.c', 'nova/nova.c', 'points_projection.c', 'effects/divdi3.c'):
            obj = modules / (Path(name).stem + '.o')
            command([cc, '-std=c11', *_flags(), '-fPIC', '-fvisibility=hidden', *clock_includes,
                     *['-D' + flag for flag in record['clock_defines']], '-c', ROOT / 'apps/clock' / name, '-o', obj])
            objects.append(obj)
        if current_profile:
            for name in ('quick_actions.c','quick_render.c','quick_session.c','quick_radios.c'):
                obj=modules/(Path(name).stem+'.o')
                command([cc,'-std=c11',*_flags(),'-fPIC','-fvisibility=hidden',*clock_includes,'-c',system/'lib/PortableApps/src'/name,'-o',obj]);objects.append(obj)
        clock = modules / 'default.elf'
        command([cxx, '-std=c++11', *_flags(), '-fPIC', '-shared', '-fvisibility=hidden', *includes,
                 ROOT / 'apps/clock/effects/boot.cpp', *objects, '-o', clock])
        for label, content, original, destination, boot in prepared:
            shutil.copy2(clock, destination / 'default.elf')
            expected_json = {name: data for name, data in content.items() if name.endswith('.json')}
            outcomes = []
            for scenario in SCENARIOS:
                text = command([host, destination, scenario], timeout=60)
                marker = next(line.removeprefix('UPDATE_CLOCK_RESULT ') for line in text.splitlines() if line.startswith('UPDATE_CLOCK_RESULT '))
                outcomes.append(dict(json.loads(marker), output=text))
            if any(json.loads(content[d['manifest']])['id'].startswith('software-update-') for d in boot['drivers']):
                outcomes.append(dict(scenario='missing-bank', **json.loads(command([host, destination, 'missing-bank'], timeout=60))))
            require(_files(original) == content, 'Original store changed after Clock execution')
            require(expected_json == {name: data for name, data in _files(destination).items() if name.endswith('.json')}, 'Host execution changed production JSON')
            record['results'].append({'label': label, 'store_sha256': store_digest(content),
                'store_files': len(content), 'json_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in expected_json.items()},
                'scenarios': outcomes})
        # Keep ownership/init/fini/child/queue/intentional-exit coverage in the
        # actual Runtime repository's established fixture, not a parallel stack.
        record['runtime_owner_regression'] = command(['bash', runtime / 'test/run_update_runtime_test.sh'])
        record['runtime_owner_regression_sanitized'] = os.environ.get('SANITIZE', '0') == '1'
        record['clock_abi'] = verify_clock_abi(runtime, build / 'abi',current_profile=current_profile)
        require(_runtime(runtime,current_profile) == runtime, 'Runtime identity changed during test')
        record['compiled_source_sha256'] = _source_hashes(runtime, system, utilities)
        require(record['compiled_source_sha256'] == before_sources, 'Production source changed during execution')
        if current_profile:
            require(record['sdr_source_hashes']==external_source_hashes(drivers),'External driver source changed during execution')
        (build / 'execution-provenance.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def paired_image_store(path, mkspiffs):
    """Extract a raw bootfs0 partition only after checking its paired metadata."""
    path = Path(path)
    metadata_path = path.with_suffix('.json')
    metadata = json.loads(metadata_path.read_text())
    raw = path.read_bytes()
    require(type(metadata.get('schema')) is int and type(metadata.get('store_abi')) is int and
            metadata.get('schema') == 1 and metadata.get('layout') == 'riscrte-paired-16m-v1' and
            metadata.get('store_abi') == 1 and metadata.get('partition_label') == 'bootfs0',
            'Raw image must have paired-store layout/ABI/partition metadata')
    require(metadata.get('image') == path.name and metadata.get('size_bytes') == BOOTFS_SIZE and
            len(raw) == BOOTFS_SIZE and metadata.get('sha256') == hashlib.sha256(raw).hexdigest(),
            'Raw paired image size/hash/name mismatch')
    require(metadata.get('page_size') == 256 and metadata.get('block_size') == 4096 and
            metadata.get('tool_sha256') == MKSPIFFS_SHA256, 'Unpinned SPIFFS extraction parameters')
    content = unpack_image(raw, mkspiffs)
    require(metadata.get('files') == len(content), 'Extracted paired-store file count mismatch')
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--system-apps', type=Path)
    parser.add_argument('--utilities', type=Path)
    parser.add_argument('--productivity', type=Path)
    parser.add_argument('--store', type=Path, action='append', default=[])
    parser.add_argument('--archive', type=Path, nargs='+', action='extend', default=[])
    parser.add_argument('--image', type=Path, nargs='+', action='extend', default=[])
    parser.add_argument('--mkspiffs', type=Path)
    parser.add_argument('--admission-only', action='store_true')
    parser.add_argument('--abi-only', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.abi_only:
        record = verify_clock_abi(args.runtime, args.output)
    else:
        if args.image and not args.mkspiffs:
            parser.error('--mkspiffs is required for raw paired SPIFFS image inputs')
        input_paths = [*args.archive, *args.image, *[path.with_suffix('.json') for path in args.image]]
        inputs = [{'path': str(path.resolve()), 'sha256': sha(path), 'size_bytes': path.stat().st_size} for path in input_paths]
        stores = [(str(path), _files(path)) for path in args.store]
        stores += [(str(path), archive_store(path.read_bytes())) for path in args.archive]
        stores += [(str(path), paired_image_store(path, args.mkspiffs)) for path in args.image]
        if not stores:
            parser.error('Supply actual --store, --archive, or raw paired --image inputs')
        if args.admission_only:
            record = admit_many(args.runtime, stores, args.output)
        else:
            if not args.system_apps or not args.utilities:
                parser.error('Execution requires --system-apps and --utilities')
            admission = admit_many(args.runtime, stores, args.output / 'admission' if args.output else None)
            record = execute_many(args.runtime, args.system_apps, args.utilities, args.productivity, stores, args.output)
            record['admission'] = admission
        require(all(sha(item['path']) == item['sha256'] for item in inputs), 'Archive/image/metadata input changed during verification')
        record['inputs'] = inputs
        if args.output:
            filename = 'admission-provenance.json' if args.admission_only else 'execution-provenance.json'
            (args.output / filename).write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()

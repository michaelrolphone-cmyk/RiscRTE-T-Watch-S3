#!/usr/bin/env python3
"""Host-only regression for Watch factory appdata images; never flash hardware.

Compile real Runtime NativeAppData, NativeAppDataMount, NativeFileSource and
hash-pinned ESP LittleFS/LittleFS against Runtime's host flash/RTOS fixture.
Require full-image SHA-256 pins through --selection or both --*-sha256 flags.
Generated CI images are explicitly labelled in their selection JSON.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import sys

FLASH_BYTES = 0x1000000
TABLE_OFFSET, TABLE_BYTES = 0x8000, 0x1000
APPDATA_OFFSET, APPDATA_BYTES = 0x270000, 0x80000


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def parse_appdata(table: bytes) -> dict:
    entries = []
    for offset in range(0, len(table), 32):
        entry = table[offset:offset + 32]
        if len(entry) < 32 or entry[:2] != b'\xaaP':
            break
        _, kind, subtype, address, size, raw_label, flags = struct.unpack('<HBBII16sI', entry)
        label = raw_label.split(b'\0', 1)[0].decode('ascii')
        if label == 'appdata':
            entries.append(dict(label=label, type=kind, subtype=subtype,
                                offset=address, size=size, flags=flags))
    expected = dict(label='appdata', type=1, subtype=0x41,
                    offset=APPDATA_OFFSET, size=APPDATA_BYTES, flags=0)
    if entries != [expected]:
        raise ValueError(f'Expected one unencrypted Watch appdata partition: {entries}')
    return expected


def inspect_image(path: Path, expected: str, role: str, expected_appdata: str | None) -> dict:
    if path.stat().st_size != FLASH_BYTES:
        raise ValueError(f'{role}: expected a full 16 MiB image')
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f'{role}: SHA-256 mismatch: expected {expected}, got {actual}')
    with path.open('rb') as stream:
        stream.seek(TABLE_OFFSET)
        table = stream.read(TABLE_BYTES)
        stream.seek(APPDATA_OFFSET)
        appdata = stream.read(APPDATA_BYTES)
    partition = parse_appdata(table)
    appdata_hash = hashlib.sha256(appdata).hexdigest()
    erased = appdata == b'\xff' * APPDATA_BYTES
    if role == 'old' and not erased:
        raise ValueError('The rejection baseline must have fully erased appdata')
    if role == 'recovered' and erased:
        raise ValueError('The recovered image still has fully erased appdata')
    if role == 'recovered' and expected_appdata and appdata_hash != expected_appdata:
        raise ValueError('Recovered appdata does not match the selected filesystem hash')
    return dict(path=str(path), size=FLASH_BYTES, sha256=actual,
                partition_table_sha256=hashlib.sha256(table).hexdigest(),
                appdata=partition, appdata_sha256=appdata_hash, appdata_all_erased=erased)


def verify_clean_runtime(root: Path) -> str:
    result = subprocess.run(['git', '-C', str(root), 'diff', 'HEAD', '--quiet'],
                            text=True, capture_output=True)
    if result.returncode == 1:
        raise ValueError('Runtime has tracked changes; use a clean source checkout')
    if result.returncode:
        raise ValueError('Could not verify clean Runtime source: ' + result.stderr.strip())
    return subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                          text=True, capture_output=True, check=True).stdout.strip()


def replace_exact(source: str, old: str, new: str, count: int = 1) -> str:
    found = source.count(old)
    if found != count:
        raise ValueError(f'Runtime fixture interface changed: expected {count} occurrences of {old!r}, found {found}')
    return source.replace(old, new)


def prepare_fixture(root: Path, build: Path) -> None:
    stubs = build / 'stubs'
    shutil.copytree(root / 'test/native_littlefs_profile_stubs', stubs, dirs_exist_ok=True)
    task = stubs / 'freertos/task.h'
    task.write_text(task.read_text() + '''
#ifdef __cplusplus
extern "C" {
#endif
void* xTaskGetCurrentTaskHandle(void);
int xPortInIsrContext(void);
#ifdef __cplusplus
}
#endif
#include <stddef.h>
typedef void* TaskHandle_t;
#define pdPASS 1
static inline void vTaskDelay(unsigned ticks){(void)ticks;}
static inline int xTaskCreate(void(*entry)(void*),const char*name,unsigned stack,void*arg,unsigned priority,TaskHandle_t*out){(void)entry;(void)name;(void)stack;(void)arg;(void)priority;(void)out;return 0;}
''')
    for name in ['esp_vfs.h', 'esp_partition.h']:
        path = stubs / name
        path.write_text('#ifdef __cplusplus\nextern "C" {\n#endif\n' + path.read_text() + '\n#ifdef __cplusplus\n}\n#endif\n')
    path = stubs / 'esp_partition.h'
    path.write_text(path.read_text() + '\ntypedef int esp_partition_subtype_t;\n')
    (stubs / 'esp_heap_caps.h').write_text('''#pragma once
#include <stdlib.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define MALLOC_CAP_INTERNAL 4
static inline void* heap_caps_malloc(size_t n,unsigned caps){(void)caps;return malloc(n);}
''')
    (stubs / 'esp_timer.h').write_text('''#pragma once
#include <stdint.h>
static inline int64_t esp_timer_get_time(){return 1000;}
''')
    source = (root / 'test/native_littlefs_profile_fixture.c').read_text()
    source = replace_exact(source, 'static esp_vfs_t registered_vfs;', '''static const char* mount_path="/native";
void native_lfs_fixture_select_appdata(void){mount_path="/appdata";}
esp_err_t __real_esp_littlefs_format_partition(const esp_partition_t*);
static esp_vfs_t registered_vfs;''')
    source = replace_exact(source, 'subtype != ESP_PARTITION_SUBTYPE_ANY', '(subtype != ESP_PARTITION_SUBTYPE_ANY && subtype != 0x41)')
    source = replace_exact(source, 'strcmp(path, "/native")', 'strcmp(path, mount_path)', 2)
    source = replace_exact(source, 'registered_context ? "/native"', 'registered_context ? mount_path')
    source = replace_exact(source, '.base_path = "/native"', '.base_path = mount_path')
    source = replace_exact(source, 'esp_littlefs_format_partition(&flash_partition)', '__real_esp_littlefs_format_partition(&flash_partition)')
    # No reset/format is called by the exact-image test. Load selected bytes into
    # a fresh process's modeled flash and reset counters before production mount.
    source += '\nint fixture_load_raw(const void*p,size_t n){if(!p||n!=FLASH_BYTES||registered_context)return -1;memcpy(flash_bytes,p,n);native_lfs_fixture_clear_counters();return 0;}\n'
    (build / 'fixture.c').write_text(source)


def run_mode(args, mode: str, profile) -> dict:
    root, build = args.runtime, args.output / mode
    build.mkdir(parents=True, exist_ok=True)
    vendor, stubs = build / 'vendor', build / 'stubs'
    profile.obtain_inputs(vendor, str(args.vendor) if args.vendor else None,
                          str(args.vendor / 'littlefs') if args.vendor else None)
    prepare_fixture(root, build)
    sanitize = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', '-g'] if mode == 'sanitized' else []
    env = os.environ.copy()
    if sanitize:
        env['ASAN_OPTIONS'] = 'halt_on_error=1:detect_leaks=' + ('1' if args.leak_check else '0')
        env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    common = ['-D_GNU_SOURCE', '-DLFS_NO_DEBUG', '-DLFS_NO_WARN', '-DLFS_NO_ERROR', '-pthread', *sanitize,
              '-include', str(stubs / 'sdkconfig.h')]
    includes = ['-I' + str(p) for p in [stubs, vendor, vendor / 'littlefs', root, root / 'src',
                 root / 'test', root / 'sdk/app', root / 'sdk/driver', root / 'sdk/hardware', root / 'src/ports/esp32s3']]
    cpp = ['-std=c++17', *common, *includes, '-DESP_PLATFORM', '-DRISC_PAIRED_APP_DATA=1',
           '-DRISC_PAIRED_BANKS=1', '-DRISC_NATIVE_APP_DATA_MOUNT=1', '-DRISC_NATIVE_FILE_SOURCE=1',
           '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation']
    cc, cxx = os.environ.get('CC', 'cc'), os.environ.get('CXX', 'c++')
    cases = []
    with (build / 'run.log').open('w') as log:
        def run(command, case=None):
            command = list(map(str, command))
            log.write('+ ' + shlex.join(command) + '\n')
            log.flush()
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, env=env)
            log.write(result.stdout)
            log.flush()
            if result.returncode:
                raise RuntimeError(f'{mode}: command failed ({result.returncode}); see {build / "run.log"}')
            if case:
                cases.append(dict(name=case, returncode=0, output=result.stdout.strip()))
                print(f'PASS host-only {mode}: {case}', flush=True)
        base = []
        for source in [vendor / 'littlefs/lfs.c', vendor / 'littlefs/lfs_util.c',
                       vendor / 'littlefs_esp_part.c', vendor / 'esp_littlefs.c', build / 'fixture.c']:
            obj = build / (source.name + '.o')
            run([cc, '-std=c11', *common, *includes, '-c', source, '-o', obj])
            base.append(obj)
        units = {'mount': 'src/ports/esp32s3/NativeAppDataMount.cpp',
                 'native-appdata': 'src/ports/esp32s3/NativeAppData.cpp',
                 'appdata': 'src/runtime/storage/AppDataFiles.cpp',
                 'posix': 'test/native_app_data_mount_posix.cpp',
                 'file-source': 'src/ports/esp32s3/NativeFileSource.cpp'}
        objects = {}
        for name, relative in units.items():
            obj = build / (name + '.o')
            run([cxx, *cpp, '-c', root / relative, '-o', obj])
            objects[name] = obj
        wrapped = ['stat', 'fstat', 'open', 'read', 'write', 'close', 'fsync', 'mkdir', 'unlink',
                   'rename', 'opendir', 'readdir', 'closedir', 'esp_vfs_register', 'esp_vfs_unregister',
                   'esp_partition_read', 'esp_partition_write', 'esp_partition_erase_range',
                   'esp_littlefs_format', 'esp_littlefs_format_partition']
        def link(name, source, additional, wraps):
            exe = build / name
            run([cxx, *cpp, '-no-pie', source, *base, *additional,
                 '-Wl,' + ','.join('--wrap=' + f for f in wraps), '-o', exe])
            return exe
        mount = link('mount-test', root / 'test/native_app_data_mount_test.cpp',
                     [objects[k] for k in ['mount', 'native-appdata', 'appdata', 'posix']], wrapped)
        for case in ['healthy', 'fault', 'close-failure', 'lost-custody', 'native-backend', 'recovery']:
            run([mount, case], 'mount/' + case)
        file_wraps = ['fstat', 'open', 'read', 'write', 'close', 'unlink', 'lseek', *wrapped[13:]]
        file_source = link('file-source-test', root / 'test/native_file_source_mount_test.cpp',
                           [objects['mount'], objects['file-source']], file_wraps)
        for case in ['healthy', 'open-fault', 'close-fault', 'read-fault']:
            run([file_source, case], 'file-source/' + case)
        factory = link('factory-appdata-test', Path(__file__).with_name('factory_appdata_mount_test.cpp'),
                       list(objects.values()), [*wrapped, 'lseek'])
        run([factory, args.old_image, 'reject', build / 'unused.bin'], 'image/old-zero-write-rejection')
        run([factory, args.recovered_image, 'fresh', build / 'fresh.bin'], 'image/recovered-fresh')
        run([factory, build / 'fresh.bin', 'reboot', build / 'rebooted.bin'], 'image/recovered-cold-remount')
    return dict(status='pass', cases=cases, address_sanitizer=bool(sanitize),
                undefined_behavior_sanitizer=bool(sanitize), leak_check=bool(sanitize) and args.leak_check,
                snapshots={name: sha256(build / name) for name in ['fresh.bin', 'rebooted.bin']})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True, help='Runtime checkout containing the real production code and host fixtures')
    parser.add_argument('--old-image', type=Path, required=True)
    parser.add_argument('--recovered-image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Host build, log and report directory')
    parser.add_argument('--vendor', type=Path, help='Offline pinned ESP LittleFS directory with littlefs/ child; otherwise fetch Runtime-pinned vendor files')
    parser.add_argument('--selection', type=Path, help='JSON with schema=1, kind, old.sha256, recovered.sha256 and optional recovered.appdata_sha256')
    parser.add_argument('--old-sha256')
    parser.add_argument('--recovered-sha256')
    parser.add_argument('--appdata-sha256', help='Optional additional pin for recovered 512 KiB appdata')
    parser.add_argument('--modes', nargs='+', choices=['normal', 'sanitized'], default=['normal', 'sanitized'])
    parser.add_argument('--leak-check', action='store_true', help='Also enable LeakSanitizer on hosts that support it; ASan/UBSan do not require this')
    args = parser.parse_args()
    for attr in ['runtime', 'old_image', 'recovered_image', 'output', 'vendor']:
        if getattr(args, attr) is not None:
            setattr(args, attr, getattr(args, attr).resolve())
    selection = json.loads(args.selection.read_text()) if args.selection else {}
    if selection and selection.get('schema') != 1:
        parser.error('Unsupported selection schema')
    expected = {role: getattr(args, role + '_sha256') or selection.get(role, {}).get('sha256')
                for role in ['old', 'recovered']}
    if any(not value or len(value) != 64 or any(c not in '0123456789abcdef' for c in value) for value in expected.values()):
        parser.error('Supply both full-image SHA-256 pins with --selection or --old-sha256 and --recovered-sha256')
    appdata_pin = args.appdata_sha256 or selection.get('recovered', {}).get('appdata_sha256')
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(schema=1, scope='host-only production storage regression; not Xtensa execution or hardware qualification',
                  kind=selection.get('kind', 'explicitly-pinned-images'), status='running', images={}, modes={},
                  started_at_utc=datetime.now(timezone.utc).isoformat(),
                  harness_sha256=sha256(Path(__file__).with_name('factory_appdata_mount_test.cpp')),
                  runner_sha256=sha256(Path(__file__)))
    report_path = args.output / 'report.json'
    try:
        for role in ['old', 'recovered']:
            report['images'][role] = inspect_image(getattr(args, role + '_image'), expected[role], role, appdata_pin)
        report['runtime_commit'] = verify_clean_runtime(args.runtime)
        report['runtime_tracked_files_clean_before'] = True
        inputs = ['src/ports/esp32s3/NativeAppData.cpp', 'src/ports/esp32s3/NativeAppDataMount.cpp',
                  'src/ports/esp32s3/NativeFileSource.cpp', 'src/runtime/storage/AppDataFiles.cpp',
                  'src/runtime/storage/FileSourceFiles.h', 'test/native_littlefs_profile_fixture.c',
                  'test/run_native_littlefs_profile_test.py', 'test/native_app_data_mount_test.cpp',
                  'test/native_app_data_mount_posix.cpp', 'test/native_file_source_mount_test.cpp']
        report['runtime_source_sha256'] = {name: sha256(args.runtime / name) for name in inputs}
        spec = importlib.util.spec_from_file_location('pinned_profile', args.runtime / 'test/run_native_littlefs_profile_test.py')
        profile = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(profile)
        report['vendor_pins'] = {item[2]: item[3] for item in profile.INPUTS}
        for mode in dict.fromkeys(args.modes):
            report['modes'][mode] = run_mode(args, mode, profile)
            report_path.write_text(json.dumps(report, indent=2) + '\n')
        for role in ['old', 'recovered']:
            if sha256(getattr(args, role + '_image')) != expected[role]:
                raise RuntimeError(f'{role}: input image changed during the audit')
        if verify_clean_runtime(args.runtime) != report['runtime_commit']:
            raise RuntimeError('Runtime revision changed during the audit')
        report['runtime_tracked_files_clean_after'] = True
        report['status'] = 'pass'
        report['input_images_unchanged'] = True
    except Exception as error:
        report['status'] = 'fail'
        report['error'] = str(error)
        print(f'FAIL: {error}', file=sys.stderr)
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(f'{report["status"].upper()}: host-only factory appdata regression; report {report_path}')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())

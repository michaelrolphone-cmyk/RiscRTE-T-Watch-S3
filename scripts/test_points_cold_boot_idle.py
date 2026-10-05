#!/usr/bin/env python3
"""Real crown/Points/PMU cold-boot idle integration, ASan/UBSan; no device I/O."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from test_contracts import config, initializer

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-apps', type=Path, required=True)
    parser.add_argument('--utilities', type=Path, required=True)
    parser.add_argument('--pmu-source', type=Path,
                        default=ROOT / 'drivers/twatch_pmu/driver.c',
                        help='Optional historical PMU source for a before-fix reproduction')
    args = parser.parse_args()
    system_apps = args.system_apps.resolve()
    utilities = args.utilities.resolve()
    board = json.loads((ROOT / 'hardware/sx1262-915-bma423.json').read_text())
    buses = {bus['instance_id']: bus for bus in board['buses']}
    entry = next(device for device in board['devices']
                 if device['compatible'] == 'x-powers,axp2101')
    kind, values = config(entry, buses, False)
    with tempfile.TemporaryDirectory(prefix='points-cold-boot-idle-') as directory:
        out = Path(directory)
        (out / 'fixture_config.h').write_text(
            f'static {kind} m_config={initializer(values)};\n'
            'static risc_hardware_device_v1 m_device={1,sizeof(m_device),'
            f'{entry["instance_id"]},"{entry["compatible"]}","unspecified",'
            f'"{entry["config_type"]}",1,sizeof(m_config),&m_config}};\n')
        includes = [system_apps / 'lib/PortableApps/include',
                    system_apps / 'lib/NativeApps/include',
                    utilities / 'lib/Alarm/include',
                    ROOT / 'sdk/app', ROOT / 'sdk/driver', ROOT / 'include', ROOT, out]
        flags = ['-O1', '-g', '-Wall', '-Wextra', '-Werror',
                 '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                 '-fno-omit-frame-pointer', '-fno-pie',
                 '-DPORTABLE_RTC_UTC8_DENVER']
        objects = []
        sources = [ROOT / 'apps/clock/crown.c', ROOT / 'apps/clock/nova/nova.c',
                   ROOT / 'apps/clock/points_projection.c', args.pmu_source.resolve(),
                   ROOT / 'tests/points_cold_boot_idle_test.c',
                   ROOT / 'tests/points_cold_boot_idle_test.c']
        for index, source in enumerate(sources):
            obj = out / f'source-{index}.o'
            defines = (['-DWATCH_CLOCK_LAUNCHER', '-DWATCH_CLOCK_ALARMS', '-DWATCH_CLOCK_POINTS',
                        '-Dnova_watch_face_render=test_points_face_render']
                       if index == 0 else [])
            if index == 5:
                defines = ['-DPOINTS_PMU_FIXTURE']
            selected_includes = ([ROOT / 'sdk/driver', ROOT / 'include', out]
                                 if index in (3, 5) else includes)
            include_flags = ['-I' + str(path) for path in selected_includes]
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', *flags, *defines, *include_flags,
                            '-c', str(source), '-o', str(obj)], check=True)
            objects.append(str(obj))
        executable = out / 'points-cold-boot-idle'
        subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++11', *flags, '-no-pie',
                        *['-I' + str(path) for path in includes],
                        str(ROOT / 'apps/clock/effects/boot.cpp'), *objects,
                        '-o', str(executable)], check=True)
        for frame_ms in (0, 7, 95):
            for wrap in (0, 1):
                print(f'Frame transport={frame_ms}ms, uptime wrap={wrap}', flush=True)
                subprocess.run([str(executable), str(frame_ms), str(wrap)],
                               check=True, timeout=90)
    print('Six cold-boot Points countdown lanes passed with real PMU/crown/rendering (ASan/UBSan).')


if __name__ == '__main__':
    main()

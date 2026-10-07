#!/usr/bin/env python3
"""Charge initialization, status and cleanup faults against the production PMU."""
import json
import os
import subprocess
from pathlib import Path
from test_contracts import config, initializer

ROOT = Path(__file__).resolve().parents[1]

def main():
    out = ROOT / 'dist/pmu-charge-status'
    out.mkdir(parents=True, exist_ok=True)
    board = json.loads((ROOT / 'hardware/sx1262-915-bma423.json').read_text())
    buses = {entry['instance_id']: entry for entry in board['buses']}
    entry = next(item for item in board['devices'] if item['config_type'] == 'power.axp2101')
    typ, cfg = config(entry, buses, False)
    (out / 'fixture_config.h').write_text(
        f'static {typ} m_config={initializer(cfg)};\n'
        'static risc_hardware_device_v1 m_device={1,sizeof(m_device),'
        f'{entry["instance_id"]},"{entry["compatible"]}","unspecified",'
        f'"{entry["config_type"]}",1,sizeof(m_config),&m_config}};\n')
    exe = out / 'pmu'
    subprocess.run([
        os.environ.get('CC', 'cc'), '-std=c11', '-g', '-fsanitize=undefined',
        '-fno-sanitize-recover=all',
        *['-I' + str(p) for p in [ROOT / 'sdk/driver', ROOT / 'include', out, ROOT]],
        '-DTEST_KIND=4', f'-DDRIVER_SOURCE="{ROOT}/drivers/twatch_pmu/driver.c"',
        str(ROOT / 'tests/pmu_charge_status_test.c'), '-o', str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True, timeout=30)

if __name__ == '__main__':
    main()

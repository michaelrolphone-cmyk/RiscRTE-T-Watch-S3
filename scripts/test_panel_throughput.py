#!/usr/bin/env python3
"""Execute the production panel under a bounded, deadline-aware transport model."""
import json
import os
from pathlib import Path
import subprocess
from test_contracts import config, initializer

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'dist/panel-throughput'
out.mkdir(parents=True, exist_ok=True)
board = json.loads((ROOT / 'hardware/sx1262-915-bma423.json').read_text())
entry = next(d for d in board['devices'] if d['instance_id'] == 5)
typ, value = config(entry, {b['instance_id']: b for b in board['buses']}, False)
value['rotation'] = 2
(out / 'fixture_config.h').write_text(
    f'static {typ} m_config={initializer(value)};\n'
    f'static risc_hardware_device_v1 m_device={{1,sizeof(m_device),5,"{entry["compatible"]}",'
    f'"unspecified","{entry["config_type"]}",1,sizeof(m_config),&m_config}};\n')
exe = out / 'panel-throughput'
subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-fsanitize=undefined',
                '-fno-sanitize-recover=all', '-DTEST_KIND=5',
                *['-I'+str(p) for p in (out, ROOT/'sdk/driver', ROOT/'include', ROOT)],
                str(ROOT/'tests/panel_throughput_test.c'), '-o', str(exe)], check=True)
subprocess.run([str(exe)], check=True, timeout=10)

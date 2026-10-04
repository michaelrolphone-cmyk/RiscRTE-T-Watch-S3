#!/usr/bin/env python3
"""Actual output ELFs' source through bounded host fault fixtures; no device I/O."""
import json, os, subprocess
from pathlib import Path
from test_contracts import ROOT, config, initializer

def main():
    build=ROOT/'dist/alarm-output-tests';build.mkdir(parents=True,exist_ok=True)
    board=json.loads((ROOT/'hardware/sx1262-915-bma423.json').read_text())
    buses={b['instance_id']:b for b in board['buses']}
    for kind,driver in ((9,'haptic'),(12,'speaker')):
        entry=next(d for d in board['devices'] if d['instance_id']==kind)
        typ,c=config(entry,buses,False)
        (build/'fixture_config.h').write_text(f'static {typ} m_config={initializer(c)};\nstatic risc_hardware_device_v1 m_device={{1,sizeof(m_device),{kind},"{entry["compatible"]}","unspecified","{entry["config_type"]}",1,sizeof(m_config),&m_config}};\n')
        exe=build/driver
        subprocess.run([os.environ.get('CC','clang'),'-std=c11','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all',
            '-I'+str(ROOT/'sdk/driver'),'-I'+str(ROOT/'include'),'-I'+str(ROOT),'-I'+str(build),
            f'-DTEST_KIND={kind}',f'-DDRIVER_SOURCE="{ROOT}/drivers/twatch_{driver}/driver.c"',str(ROOT/'tests/alarm_output_driver_test.c'),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Production Watch deep-only suffixes, with owned-pad/rollback fault injection."""
import json,os,subprocess
from pathlib import Path
from test_contracts import config,initializer
from generate_board import generate
ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'dist/deep-sleep-tests';out.mkdir(parents=True,exist_ok=True)
    generate();board=json.loads((ROOT/'hardware/sx1262-915-bma423.json').read_text());buses={b['instance_id']:b for b in board['buses']}
    for kind,name in [(1,'gpio'),(4,'pmu'),(5,'panel')]:
        entry=board['devices'][kind-1];typ,c=config(entry,buses,False)
        (out/'fixture_config.h').write_text(f'static {typ} m_config={initializer(c)};\nstatic risc_hardware_device_v1 m_device={{1,sizeof(m_device),{entry["instance_id"]},"{entry["compatible"]}","unspecified","{entry["config_type"]}",1,sizeof(m_config),&m_config}};\n')
        exe=out/name
        flags=['-std=c11','-g','-fsanitize=undefined','-fno-sanitize-recover=all']
        subprocess.run([os.environ.get('CC','cc'),*flags,*['-I'+str(p) for p in [ROOT/'sdk/driver',ROOT/'include',out,ROOT]],f'-DTEST_KIND={kind}',f'-DDRIVER_SOURCE="{ROOT}/drivers/twatch_{name}/driver.c"',str(ROOT/'tests/deep_sleep_driver_test.c'),'-o',str(exe)],check=True)
        for scenario in (['normal','hold-error','static-error','retained-hold','retained-unhold','resume-spi-error','resume-pwm-error'] if kind==5 else ['normal']):
            subprocess.run([str(exe),scenario],check=True)
    exe=out/'clock'
    subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',*['-I'+str(ROOT/p) for p in ('sdk/app','sdk/driver','include','.')],str(ROOT/'tests/deep_sleep_app_test.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Strictly replay, qualify and package the immutable cumulative .39 successor."""
import argparse, os, shutil, subprocess, sys
from pathlib import Path
from watch_launch_brightness import ROOT, PINS, clean, need, require_final, sha, write, compose, native_stage
from qualify_launch_brightness_replay import verify_replay, link_evidence


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','evidence','runtime','producer','utilities','springboard','bridges','compiler','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source-revision',required=True)
    p.add_argument('--qualified-replay',type=Path);p.add_argument('--qualified-host',type=Path);p.add_argument('--source-cache',type=Path)
    a=p.parse_args()
    for name,value in vars(a).items():
        if isinstance(value,Path):setattr(a,name,value.resolve())
    require_final();clean(ROOT,a.source_revision);clean(a.producer,PINS['producer_revision']);need(not a.output.exists(),'Output must be new')
    native_stage(a.runtime)
    from stage_launch_brightness import stage
    stage(a.baseline.read_bytes(),a.evidence.read_bytes(),a.runtime)
    from read_only_spiffs import read_image
    baseline=a.baseline.read_bytes();need(sha(baseline)==PINS['baseline_sha256'],'Wrong exact .38 baseline')
    work=a.output/'qualification';write(work/'baseline-store',read_image(baseline[0x2f0000:0x840000],0x550000))
    def run(script,*args,sanitize=False):
        subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,args)],check=True,
                       env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0','SANITIZE':'1' if sanitize else '0'})
    qualified=a.qualified_host or work/'host'
    if not a.qualified_host:
        run('qualify_launch_brightness.py','--system',a.producer,'--runtime',a.runtime,'--utilities',a.utilities,
            '--springboard',a.springboard,'--bridges',a.bridges,'--output',qualified)
    if a.qualified_replay:
        replay=verify_replay(a.qualified_replay,a.producer,a.compiler)
        names=['receipt.json']+[name+ext for name in PINS['expected_replaced_apps'] for ext in ('.elf','.log')]
        write(work/'replay',{name:(a.qualified_replay/name).read_bytes() for name in names})
        for name,data in link_evidence(a.qualified_replay,replay).items():
            path=work/'replay'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    else:
        command=[sys.executable,str(a.producer/'scripts/replay_shared_crash_apps.py'),'--product','twatch','--compiler',str(a.compiler),'--output',str(work/'replay')]
        if a.source_cache:command+=['--source-cache',str(a.source_cache)]
        subprocess.run(command,check=True)
    verify_replay(work/'replay',a.producer,a.compiler)
    run('test_launch_brightness_replay.py','--replay',work/'replay','--producer',a.producer,'--compiler',a.compiler)
    native=a.runtime/'.pio/build/watch-native-ui'
    compose(work/'baseline-store',work/'replay',(native/'firmware.bin').read_bytes(),a.source_revision,work/'composition')
    run('test_launch_brightness_contract.py','--baseline-store',work/'baseline-store','--store',work/'composition/store','--firmware',native/'firmware.bin','--source-revision',a.source_revision)
    for sanitize in (False,True):
        run('verify_launch_brightness.py','--runtime',a.runtime,'--compiler',a.compiler,'--store',work/'composition/store',
            '--baseline-store',work/'baseline-store','--output',work/('admission-sanitized' if sanitize else 'admission'),sanitize=sanitize)
    run('test_launch_brightness_preservation.py','--runtime',a.runtime,'--baseline',a.baseline,'--firmware',native/'firmware.bin','--store',work/'composition/store.bin','--output',work/'preservation')
    run('package_launch_brightness.py','--baseline',a.baseline,'--runtime',a.runtime,'--composition',work/'composition',
        '--admission',work/'admission','--admission-sanitized',work/'admission-sanitized','--preservation',work/'preservation',
        '--qualification',qualified,'--replay',work/'replay','--producer',a.producer,'--compiler',a.compiler,'--source-revision',a.source_revision,'--output',a.output/'assets')
    run('verify_launch_brightness_assets.py','--assets',a.output/'assets','--baseline',a.baseline,'--runtime',a.runtime,'--source-revision',a.source_revision)
    print('Complete exact-source 1.1.39 package; no hardware or publication I/O')


if __name__=='__main__':main()

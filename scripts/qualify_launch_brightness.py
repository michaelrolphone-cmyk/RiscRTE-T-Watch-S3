#!/usr/bin/env python3
"""Bind launch-brightness and custody host regressions to immutable sources."""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path
from watch_launch_brightness import PINS, clean, encoded, files, need, sha


def evidence(root):
    return {n:v for n,v in files(root).items() if n != 'qualification.json' and Path(n).suffix in ('.json', '.log')}


def verify(root):
    report = json.loads((root/'qualification.json').read_text())
    for name,key in (('system','producer_revision'),('runtime','runtime_revision'),('utilities','qualification_utilities_revision'),('springboard','preserved_springboard_system_revision'),('bridges','bridges_revision')):
        need(report['revisions'][name] == PINS[key], 'Qualification source differs: '+name)
    need(report['producer_sha256'] == sha(Path(__file__).read_bytes()), 'Qualification producer differs')
    need(report['evidence_sha256'] == {n:sha(v) for n,v in evidence(root).items()}, 'Qualification evidence differs')
    for name,count in (('brightness',126),('custody',192)):
        raw = json.loads((root/name/'receipt.json').read_text()); rows = raw['results']
        need(raw['source_commit'] == PINS['producer_revision'], 'Test source differs')
        need(len(rows) == count and all(row['exit'] == 0 for row in rows), 'Incomplete source regression: '+name)
        need({row['mode'] for row in rows} == {'normal','sanitized'}, 'Missing sanitizer coverage')
        for row in rows: need((root/name/Path(row['log']).name).is_file(), 'Missing source regression log')
    spring = json.loads((root/'springboard/source.json').read_text())
    need(spring['source_commit'] == PINS['preserved_springboard_system_revision'] and spring['production_source_changed'] is False, 'Springboard source differs')
    need(spring['real_controller_cases'] == 8 and spring['invocations_per_controller_case'] == 3 and spring['hardware_tested'] is False, 'Springboard coverage differs')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system','runtime','utilities','springboard','bridges','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    a = parser.parse_args()
    for name,value in vars(a).items(): setattr(a,name,value.resolve())
    revisions = {}
    for name,key in (('system','producer_revision'),('runtime','runtime_revision'),('utilities','qualification_utilities_revision'),('springboard','preserved_springboard_system_revision'),('bridges','bridges_revision')):
        clean(getattr(a,name),PINS[key]); revisions[name] = PINS[key]
    need(not a.output.exists(),'Qualification output must be new'); a.output.mkdir(parents=True)
    sdk = a.output/'sdk'; sdk.mkdir()
    for name in ('RiscRuntimeV1.h','RiscRealtimeV1.h','RiscAppDataV1.h'): shutil.copyfile(a.runtime/'sdk/app'/name,sdk/name)
    for name in ('AlarmServiceV1.h','AlarmServiceV2.h'): shutil.copyfile(a.utilities/'lib/Alarm/include'/name,sdk/name)
    common = ['--sdk-include',sdk,'--app-data-sdk',sdk,'--utilities-root',a.utilities]
    commands = [('brightness','test_shared_initial_brightness.py',common),('custody','test_shared_data_custody.py',common+['--callback-audit']),
                ('springboard','test_springboard_launch_brightness.py',['--springboard-root',a.springboard,'--bridges',a.bridges,'--sanitize'])]
    for label,name,args in commands:
        command = [sys.executable,str(a.system/'scripts'/name),*map(str,args),'--output',str(a.output/label)]
        result = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
        (a.output/(label+'.log')).write_text(result.stdout)
        if result.returncode: print(result.stdout,file=sys.stderr); raise SystemExit(result.returncode)
        print('PASS: '+label,flush=True)
    for name,key in (('system','producer_revision'),('runtime','runtime_revision'),('utilities','qualification_utilities_revision'),('springboard','preserved_springboard_system_revision'),('bridges','bridges_revision')): clean(getattr(a,name),PINS[key])
    report = dict(revisions=revisions,producer_sha256=sha(Path(__file__).read_bytes()),evidence_sha256={n:sha(v) for n,v in evidence(a.output).items()},
                  brightness_cases=126,custody_cases=192,springboard_controller_cases=8,springboard_invocations_per_case=3,hardware_tested=False,device_accessed=False)
    (a.output/'qualification.json').write_bytes(encoded(report)); verify(a.output)


if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Verify a deployment ZIP without extracting or accessing a device."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import zipfile
from check_twatch_drivers import check_board


def verify(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or any(n.startswith('/') or '..' in PurePosixPath(n).parts for n in names):
            raise ValueError('Unsafe or duplicate archive path')
        record=json.loads(z.read('deployment-record.json'))
        entries=record['entries']
        if len(entries)!=len({e['path'] for e in entries}) or set(names)!={e['path'] for e in entries}|{'deployment-record.json'}:
            raise ValueError('Deployment membership mismatch')
        for entry in entries:
            data=z.read(entry['path'])
            if len(data)!=entry['size_bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
                raise ValueError('Deployment checksum mismatch')
        launcher=record['schema']=='riscrte.watch-launcher-deployment'
        boot=json.loads(z.read('store/boot.json'))
        board=json.loads(z.read('store/board.json'))
        app=json.loads(z.read('store/default.json'))
        if tuple(map(int,app['version'].split('.'))) >= (0,3,1):
            policy=record.get('time_policy')
            if (not policy or json.loads(z.read('time-policy.json')) != policy or
                    policy.get('rtc_basis', {}).get('utc_offset_minutes') != 480 or
                    policy.get('display_zone') != 'America/Denver' or policy.get('writes_rtc') is not False):
                raise ValueError('Missing or mismatched configured clock time policy')
            if record.get('clock_policy') != {'idle_sleep_ms': 60000, 'boot_final_hold_ms': 250, 'screen_scrub': False}:
                raise ValueError('Mismatched clock interaction policy')
        if tuple(map(int,app['version'].split('.'))) >= (0,3,0):
            for notice in ('Orbitron-OFL.txt', 'Rajdhani-OFL.txt', 'SOURCES.txt'):
                if 'licenses/nova/' + notice not in names or not z.read('licenses/nova/' + notice):
                    raise ValueError('Missing NOVA font license/provenance')
        if tuple(map(int,app['version'].split('.'))) >= (0,2,2):
            runtime=record.get('runtime_requirements')
            if (not runtime or json.loads(z.read('runtime-requirements.json')) != runtime or
                    runtime != json.loads((Path(__file__).resolve().parents[1]/'apps/clock/runtime-requirements.json').read_text()) or
                    runtime.get('required_behavior', {}).get('spi_max_hz') != 40000000):
                raise ValueError('Missing or mismatched corrected runtime requirement')
        if boot['default_app']!='default.elf' or app['file_name']!='default.elf' or app['entry']!='app_main':
            raise ValueError('Default application path mismatch')
        if {d['instance_id'] for d in boot['drivers']}!=({1,2,3,4,5,6,8} if launcher else {1,2,4,5,8}) or len(boot['drivers'])!=(7 if launcher else 5):
            raise ValueError('Unexpected clock driver closure')
        expected=[{'manifest':'default.json','grants':[
            {'capability':'display.output','api':1,'instance_id':5},
            {'capability':'rtc.clock','api':2,'instance_id':8},
            {'capability':'board.battery','api':1,'instance_id':4}]}]
        if launcher:
            expected=[]
            for name in ('default','clock','springboard','battery','settings','calculator','stopwatch'):
                grants=[{'capability':'display.output','api':1,'instance_id':5},{'capability':'input.touch.raw','api':1,'instance_id':6}]
                if name in ('default','clock','springboard','settings','stopwatch'):grants.append({'capability':'rtc.clock','api':2,'instance_id':8})
                grants.append({'capability':'board.battery','api':1,'instance_id':4})
                if name in ('default','clock','settings'):grants.append({'capability':'storage.key-value','api':1,'instance_id':1})
                if name=='stopwatch':grants.append({'capability':'storage.key-value','api':1,'instance_id':2})
                expected.append({'manifest':name+'.json','grants':grants})
                child=json.loads(z.read('store/'+name+'.json'))
                if child.get('type')!='application' or child.get('architecture')!='xtensa-esp32s3' or child['file_name']!=name+'.elf' or child['entry']!='app_main' or child['requires']!=[{'capability':g['capability'],'api':g['api']} for g in grants]:
                    raise ValueError('Launcher app identity or declared capabilities mismatch')
                elf=z.read('store/'+name+'.elf')
                if elf[:7]!=b'\x7fELF\x01\x01\x01' or struct.unpack_from('<HH',elf,16)!=(3,94):raise ValueError('Launcher app is not target Xtensa ELF')
        if launcher:
            sources=json.loads(z.read('shared-app-build.json'))
            if sources.get('touch_rotation')!=0 or sources.get('rtc_policy')!='fixed-UTC+08-to-America/Denver':
                raise ValueError('Missing launcher transform/time policy')
            if sources.get('return_targets')!={'springboard':'clock.elf','battery':'springboard.elf','settings':'springboard.elf','calculator':'springboard.elf','stopwatch':'springboard.elf'} or sources.get('handoff_ms')!=60:
                raise ValueError('Missing explicit return targets or fast handoff policy')
            policy=json.loads(z.read('settings-time-policy.json'))
            if policy!={'rtc_basis_offset_minutes':480,'display_zone':'America/Denver','write_policy':'inverse-roundtrip','gap':'reject','fold':'explicit-MDT-or-MST','touch_rotation':0}:
                raise ValueError('Invalid Settings inverse time policy')
            catalog=json.loads(z.read('shared/catalog.json'))
            if [e['file_name'] for e in catalog]!=['clock.elf','battery.elf','settings.elf','calculator.elf','stopwatch.elf']:
                raise ValueError('Invalid launcher catalog')
            for notice in ('LICENSE-FontAwesome.txt','LICENSE-Orbitron.txt','LICENSE-Rajdhani.txt','font-sources.json','time-sources.json','RTC_PROVENANCE.json','settings_fonts/LICENSE-Orbitron.txt','settings_fonts/LICENSE-Rajdhani.txt','settings_fonts/SOURCES.json'):
                if not z.read('shared/'+notice):raise ValueError('Missing shared font/time provenance')
        if boot['app_capabilities']!=expected:
            raise ValueError('Unexpected application grant policy')
        manifests=[]
        for driver in boot['drivers']:
            manifest=json.loads(z.read('store/'+driver['manifest']))
            if manifest not in manifests:manifests.append(manifest)
            elf=z.read('store/'+str(PurePosixPath(driver['manifest']).parent/manifest['file_name']))
            if elf[:7]!=b'\x7fELF\x01\x01\x01' or struct.unpack_from('<HH',elf,16)!=(3,94):
                raise ValueError('Driver is not a target Xtensa shared ELF')
        elf=z.read('store/default.elf')
        if elf[:7]!=b'\x7fELF\x01\x01\x01' or struct.unpack_from('<HH',elf,16)!=(3,94):
            raise ValueError('Application is not a target Xtensa shared ELF')
        check_board(board,manifests)
        pmu=next(d for d in board['devices'] if d['instance_id']==4)
        if {r['id'] for r in pmu['config']['rails']}!={1,2}:
            raise ValueError('Clock must not enable unrelated rails')
        return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives',nargs='+',type=Path)
    args=parser.parse_args()
    for path in args.archives:
        record=verify(path)
        print(path.name,'verified',record['app_version'],record['profile'])

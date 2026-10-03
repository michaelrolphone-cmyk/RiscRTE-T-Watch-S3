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
        boot=json.loads(z.read('store/boot.json'))
        board=json.loads(z.read('store/board.json'))
        app=json.loads(z.read('store/default.json'))
        if tuple(map(int,app['version'].split('.'))) >= (0,3,0):
            for notice in ('Orbitron-OFL.txt', 'Rajdhani-OFL.txt', 'SOURCES.txt'):
                if 'licenses/nova/' + notice not in names or not z.read('licenses/nova/' + notice):
                    raise ValueError('Missing NOVA font license/provenance')
        if tuple(map(int,app['version'].split('.'))) >= (0,2,2):
            runtime=record.get('runtime_requirements')
            if (not runtime or json.loads(z.read('runtime-requirements.json')) != runtime or
                    runtime.get('source_sha') != 'a3d23da9cdc1b3a66c6429f29781856fa7fc8f75' or
                    runtime.get('required_behavior', {}).get('spi_max_hz') != 40000000):
                raise ValueError('Missing or mismatched corrected runtime requirement')
        if boot['default_app']!='default.elf' or app['file_name']!='default.elf' or app['entry']!='app_main':
            raise ValueError('Default application path mismatch')
        if {d['instance_id'] for d in boot['drivers']}!={1,2,4,5,8} or len(boot['drivers'])!=5:
            raise ValueError('Unexpected clock driver closure')
        expected=[{'manifest':'default.json','grants':[
            {'capability':'display.output','api':1,'instance_id':5},
            {'capability':'rtc.clock','api':2,'instance_id':8},
            {'capability':'board.battery','api':1,'instance_id':4}]}]
        if boot['app_capabilities']!=expected:
            raise ValueError('Unexpected application grant policy')
        manifests=[]
        for driver in boot['drivers']:
            manifest=json.loads(z.read('store/'+driver['manifest']))
            manifests.append(manifest)
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

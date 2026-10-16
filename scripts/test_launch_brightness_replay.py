#!/usr/bin/env python3
"""Reject altered strict-replay artifacts, receipts, compiler and link history."""
import argparse, copy, json, tempfile
from pathlib import Path
from watch_launch_brightness import PINS, encoded, need, write
from qualify_launch_brightness_replay import verify_replay, link_evidence


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('replay','producer','compiler'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();report=verify_replay(a.replay,a.producer,a.compiler)
    payload={n:(a.replay/n).read_bytes() for n in ['receipt.json']+[name+ext for name in PINS['expected_replaced_apps'] for ext in ('.elf','.log')]}
    payload.update(link_evidence(a.replay,report));cases=0
    with tempfile.TemporaryDirectory(prefix='brightness-negative-replay-') as temporary:
        root=Path(temporary)/'replay';write(root,payload);verify_replay(root,a.producer,a.compiler)
        def reject():
            nonlocal cases
            try:verify_replay(root,a.producer,a.compiler)
            except (ValueError,KeyError,FileNotFoundError):cases+=1
            else:raise ValueError('Corrupt replay was accepted')
        for name in PINS['expected_replaced_apps']:
            target=root/(name+'.elf');original=target.read_bytes();target.write_bytes(original+b'!');reject();target.write_bytes(original)
        mutations=[('product','wave'),('source_inputs_verified',False),('driver_sha256','0'*64),('compiler_sha256','0'*64),('spec_sha256',{}),('repositories',{})]
        for key,value in mutations:
            altered=copy.deepcopy(report);altered[key]=value;(root/'receipt.json').write_bytes(encoded(altered));reject()
        altered=copy.deepcopy(report);del altered['apps'][PINS['expected_replaced_apps'][0]];(root/'receipt.json').write_bytes(encoded(altered));reject()
        (root/'receipt.json').write_bytes(payload['receipt.json'])
        for name in PINS['expected_replaced_apps']:
            path=Path(report['apps'][name]['link_attempts'][0]['log']);target=root/path.parent.name/path.name
            original=target.read_bytes();target.write_bytes(original+b'!');reject();target.write_bytes(original)
    print('PASS:',cases,'strict replay mutation rejections')


if __name__=='__main__':main()

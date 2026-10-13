#!/usr/bin/env python3
"""Require the policy-disabled Watch target to equal unchanged Scanner source under the same current dependencies."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
from build_scanner_policy import build, require, sha, PINNED, PREDECESSOR, selected_predecessor, git

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    selected=json.loads((args.build/'ble_scanner-build-record.json').read_text())
    require(selected['modal_policy'],'Expected policy-on selected build')
    require(sha(args.build/'ble_scanner.elf')==selected['sha256'],'Policy target custody differs')
    roots={name:Path(value) for name,value in selected['source_roots'].items()}
    for name,row in selected['target_dependencies'].items():
        owner,relative=name.split(':',1)
        require(sha(roots[owner]/relative)==row['sha256'],'Selected input changed before flag-off check: '+name)
    with tempfile.TemporaryDirectory(prefix='scanner-policy-flagoff-') as temporary:
        out=Path(temporary)/'target'
        off=build(argparse.Namespace(system=roots['system-apps'],utilities=roots['utilities'],runtime=roots['runtime'],watch_profile=roots['watch'],
            utilities_commit=selected['sources']['utilities'],output=out,
            provisional=selected['source_publication']=='local-provisional',flag_off=True,pack_metadata=False))
        prior,_=selected_predecessor()
        original=Path(prior['source_roots']['utilities'])
        require(git(original,'rev-parse','HEAD')==prior['sources']['utilities'] and
                not git(original,'status','--porcelain','--untracked-files=no'), 'Original Scanner source is not exact and clean')
        for name,row in prior['target_dependencies'].items():
            if name.startswith('utilities:'):
                require(sha(original/name.split(':',1)[1])==row['sha256'],'Original Scanner dependency differs')
        reference=build(argparse.Namespace(system=roots['system-apps'],utilities=original,runtime=roots['runtime'],watch_profile=roots['watch'],
            utilities_commit=prior['sources']['utilities'],output=Path(temporary)/'unchanged-app',
            provisional=True,flag_off=True,pack_metadata=False))
        report=dict(schema='scanner.modal-policy.flagoff-target.v1',device='watch',
            passed=off['sha256']==reference['sha256'],raw_byte_equal=off['sha256']==PINNED['elf_sha256'],
            current_dependency_unchanged_app_sha256=reference['sha256'],
            current_dependency_unchanged_app_equal=off['sha256']==reference['sha256'],
            unchanged_app_source=prior['sources']['utilities'],
            inherited_system_attention_delta=None if off['sha256']==PINNED['elf_sha256'] else 'Selected predecessor differs; consult source-bound attribution evidence before assigning cause',
            selected_predecessor_sha256=PINNED['elf_sha256'],candidate_flagoff_sha256=off['sha256'],
            candidate_flagoff_bytes=off['bytes'],sources=selected['sources'],
            source_publication=selected['source_publication'],only_removed_flag='-DPORTABLE_TEXT_INPUT_POLICY',
            linker_attempts=off['linker_attempts'],target_instructions_executed=False,hardware_verified=False)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(out/'ble_scanner.elf',args.output.with_suffix('.elf'))
        report['flagoff_artifact']={'path':str(args.output.with_suffix('.elf')),'sha256':off['sha256'],'bytes':off['bytes']}
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
        require(report['passed'] and report['raw_byte_equal'],'Policy-disabled target differs from unchanged Scanner with current dependencies')
if __name__=='__main__': main()

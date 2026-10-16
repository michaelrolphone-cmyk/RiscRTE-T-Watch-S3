#!/usr/bin/env python3
"""Reproducible shared T046 target components; native firmware is untouched."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
p=argparse.ArgumentParser()
for n in ['system','runtime','watch-tools','output']:p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--target',choices=['watch','wave','x4'],required=True);a=p.parse_args()
a.system=a.system.resolve();a.runtime=a.runtime.resolve();a.output=a.output.resolve()
profile={'watch':'watch-compact','wave':'color-dynamic','x4':'full'}[a.target]
subprocess.run([sys.executable,str(a.system/'scripts/build_text_input_services.py'),'--runtime',str(a.runtime),'--output',str(a.output),'--host-profile',profile],check=True)
sys.path[:0]=[str(a.watch_tools.resolve()/'scripts'),str(a.system/'scripts')]
from compact_current_elf import compact
from scene_build import compiler_path
state=lambda root:subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
for name in ['presentation/scene-host','text-input-host']:
 d=a.output/name;receipt=json.loads((d/'build.json').read_text())
 if a.target!='x4':receipt['compaction']=compact(d/'driver.elf',compiler_path())
 receipt.update(sha256=hashlib.sha256((d/'driver.elf').read_bytes()).hexdigest(),size_bytes=(d/'driver.elf').stat().st_size,system_source=state(a.system),runtime_sdk=state(a.runtime),target=a.target)
 (d/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')

#!/usr/bin/env python3
"""Inspect actual selected scene target continuity entry frames and static custody."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
r=json.loads((a.build/'scene-build-record.json').read_text());elf=a.build/'driver.elf';debug=a.build/'debug/driver.elf';prefix=r['compiler_path'].removesuffix('gcc');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(elf)==r['sha256'];functions={};symbols={}
for line in subprocess.check_output([prefix+'nm','-S',str(debug)],text=True).splitlines():
 c=line.split()
 if len(c)!=4:continue
 address,size,kind,name=c
 if kind in 'tT':functions.setdefault(int(address,16),[]).append(name)
 if name in {'paused','pausing','lifecycle_enabled','lifecycle_features'} and kind in 'bBdD':symbols[name]={'bytes':int(size,16),'static_storage':True,'symbol_kind':kind}
frames={}
for line in subprocess.check_output([prefix+'objdump','-d',str(debug)],text=True).splitlines():
 m=re.match(r'^\s*([0-9a-f]+):.*\bentry\s+a1,\s*(0x[0-9a-f]+|[0-9]+)',line)
 if m and int(m[1],16) in functions:
  for name in functions[int(m[1],16)]:frames[name]=int(m[2],0)
checkpoint={n:v for n,v in frames.items() if n in {'scene_pause','scene_resume','scene_configure','scene_snapshot','detach_owned'}}
assert {'scene_pause','scene_resume','scene_configure','scene_snapshot'}<=set(checkpoint)
assert all(v<=512 for v in checkpoint.values()) and symbols and all(s['bytes']<=4 for s in symbols.values())
result=dict(schema='lists.scene-continuity-host.target-stack.v1',device=r['device'],system_source=r['sources']['system-apps'],target_elf_sha256=sha(elf),debug_elf_sha256=sha(debug),continuity_entry_frames_bytes=checkpoint,maximum_continuity_frame_bytes=max(checkpoint.values()),all_entry_frames_maximum_bytes=max(frames.values()),static_continuity_storage=symbols,per_frame_regression_checks_passed=True,target_instructions_executed=False,peak_call_chain_stack_usage_proven=False)
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

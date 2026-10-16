#!/usr/bin/env python3
"""Inspect actual target entry frames and static editor state; no target execution."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
r=json.loads((a.build/'contexts-build-record.json').read_text());elf=a.build/'contexts.elf';debug=a.build/'debug/contexts.elf';prefix=r['compiler_path'].removesuffix('gcc');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(elf)==r['sha256']
nm=subprocess.check_output([prefix+'nm','-S',str(debug)],text=True).splitlines();functions={};symbols={}
for line in nm:
 cols=line.split()
 if len(cols)!=4:continue
 address,size,kind,name=cols
 if kind in 'tT':functions.setdefault(int(address,16),[]).append(name)
 if name in ('cs_text','cs_text_navigation','cs_text_accepted','cs_text_outcome','cu_name'):
  symbols[name]={'bytes':int(size,16),'symbol_kind':kind,'static_storage':kind in 'bBdD','address':int(address,16)}
frames={}
for line in subprocess.check_output([prefix+'objdump','-d',str(debug)],text=True).splitlines():
 m=re.match(r'^\s*([0-9a-f]+):.*\bentry\s+a1,\s*(0x[0-9a-f]+|[0-9]+)',line)
 if m and int(m[1],16) in functions:
  for name in functions[int(m[1],16)]:frames[name]=int(m[2],0)
modal={n:v for n,v in frames.items() if n.startswith(('cs_text','portable_text_')) or n=='app_main'}
assert {n:r['bytes'] for n,r in symbols.items()}=={'cs_text':48,'cs_text_navigation':80,'cs_text_accepted':33,'cs_text_outcome':4,'cu_name':33}
assert all(r['static_storage'] for r in symbols.values()) and 'app_main' in frames
assert all(v<=512 for v in modal.values())
result=dict(schema='contexts.target-stack.v1',device=r['device'],application_source=r['sources']['utilities'],system_source=r['sources']['system-apps'],target_elf_sha256=sha(elf),debug_elf_sha256=sha(debug),method='Actual target entry a1 disassembly operands; no target instructions executed',entry_frames_bytes=modal,maximum_modal_frame_bytes=max(modal.values()),all_entry_frames_maximum_bytes=max(frames.values()),static_modal_storage=symbols,per_frame_regression_checks_passed=True,peak_call_chain_stack_usage_proven=False,limits=['Compiler inlining folds absent helpers into callers.','Per-frame ceilings do not establish dynamic call-chain peak, Runtime allocation or hardware behavior.'])
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

#!/usr/bin/env python3
"""Read actual Xtensa entry frames and static modal storage without execution."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
r=json.loads((a.build/'waterfall-build-record.json').read_text());elf=a.build/'waterfall.elf';debug=a.build/'debug/waterfall.elf';cc=r['command'][0];prefix=cc.removesuffix('gcc');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(elf)==r['sha256']
nm=subprocess.check_output([prefix+'nm','-S',str(debug)],text=True).splitlines()
functions={}
for line in nm:
    cols=line.split()
    if len(cols)==4 and cols[2] in 'tT':functions.setdefault(int(cols[0],16),[]).append(cols[3])
lines=subprocess.check_output([prefix+'objdump','-d',str(debug)],text=True).splitlines();frames={}
for line in lines:
    m=re.match(r'^\s*([0-9a-f]+):.*\bentry\s+a1,\s*(0x[0-9a-f]+|[0-9]+)',line)
    if m and int(m[1],16) in functions:
        for name in functions[int(m[1],16)]:
            key=name if name not in frames else name+'@0x'+m[1]
            assert key not in frames
            frames[key]=int(m[2],0)
normalize=lambda n:re.sub(r'\$(?:lto_priv|constprop|isra|part)\$\d+','',n)
modal={n:frame for n,frame in frames.items() if normalize(n).startswith(('text_','portable_text_client_','portable_text_checkpoint_','portable_text_adapter_policy_','portable_app_before_')) or n in ('app_main','app_module_init','app_module_fini')}
symbols={}
for line in nm:
 cols=line.split()
 if len(cols)!=4:continue
 address,size,kind,name=cols;n=normalize(name)
 if n in ('text_client','text_state','text_checkpoint','editing'):
  assert n not in symbols
  symbols[n]={'bytes':int(size,16),'symbol_kind':kind,'static_storage':kind in 'bBdD','address':int(address,16)}
assert symbols['editing']['bytes']==32 and symbols['text_state']['bytes']==88 and symbols['text_client']['bytes']==48 and symbols['text_checkpoint']['bytes']==8
assert len(symbols)==4 and all(row['static_storage'] for row in symbols.values()) and 'app_main' in frames
# These are per-frame regression ceilings, not a claim about peak stack use.
assert modal['app_main']<=256 and all(n<=512 for n in modal.values())
result={'schema':'rf.target-stack.v1','device':r['device'],'application_source':r['sources']['utilities'],'system_source':r['sources']['system-apps'],'target_elf_sha256':sha(elf),'debug_elf_sha256':sha(debug),'method':'Actual target disassembly entry a1 frame operands; no target instructions executed','entry_frames_bytes':modal,'maximum_modal_frame_bytes':max(modal.values()),'all_entry_frames_maximum_bytes':max(frames.values()),'static_modal_storage':symbols,'bounded_label_buffer_bytes':17, 'static_editing_record_bytes':32,'per_frame_regression_checks_passed':True,'peak_call_chain_stack_usage_proven':False,'limits':['Inlining folds helper frames into their callers; absent standalone symbols are not separate frame measurements.','Disassembly frame sizes do not prove dynamic call-chain peak stack use, Runtime stack allocation, or physical execution.']}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

#!/usr/bin/env python3
"""Rebuild the two synchronous NVS UI apps from recorded exact compile recipes."""
from pathlib import Path
import argparse,json,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('--shared',type=Path,required=True);p.add_argument('--recipes',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(a.shared.resolve()/'scripts'));from normalize_xtensa_relocations import normalize
from compact_current_elf import compact
for name in ('settings','springboard'):
 command=json.loads((a.recipes/(name+'-command.json')).read_text());assert not any('ATOMIC' in arg for arg in command)
 target=a.output/(name+'.elf');command[command.index('-o')+1]=str(target);mapping=a.output/(name+'.map');mapping.write_text('{ global: app_main; app_module_init; app_module_fini; local: *; };\n');command=[arg if not arg.startswith('-Wl,--version-script=') else '-Wl,--version-script='+str(mapping) for arg in command]
 subprocess.run(command,check=True);normalize(target);receipt=compact(target,command[0],debug_path=a.output/'debug'/(name+'.elf'));(a.output/(name+'-proof.json')).write_text(json.dumps(receipt,indent=2)+'\n')

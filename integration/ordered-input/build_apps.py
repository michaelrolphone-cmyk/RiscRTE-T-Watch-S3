from pathlib import Path
import json,subprocess,sys,hashlib
import argparse
p=argparse.ArgumentParser()
p.add_argument('--system',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();O=a.output.resolve();O.mkdir(parents=True,exist_ok=True);src=a.system.resolve();recipes=Path(__file__).resolve().parent
sys.path.insert(0,'/tmp/waveshare-generic-bridges/scripts')
from normalize_xtensa_relocations import normalize
from compact_current_elf import compact
proof={}
for name in ['springboard','battery','calculator','stopwatch','frequency_generator','alarms','countdown','ble_touchpad','ble_buttons']:
 recipe=recipes/(name+'-command.json')
 cmd=json.loads(recipe.read_text());old='/Users/micahelbyrns/Documents/Codex/2026-10-13/task/System-input-decoupling';cmd=[x.replace(old,str(src)) for x in cmd]
 target=O/(name+'.elf');cmd[cmd.index('-o')+1]=str(target)
 (O/(name+'-command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
 with (O/(name+'.log')).open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 normalize(target);p=compact(target,cmd[0],debug_path=O/'debug'/(name+'.elf'))
 result=subprocess.run(['/Users/micahelbyrns/Documents/Codex/2026-10-13/task-2/target-providers/validate-elf',str(target)],text=True,capture_output=True,check=True)
 p['validation']=result.stdout;p['system_revision']=subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip();proof[name]=p
 (O/'build-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(name,p['after_bytes'],p['after_sha256'],flush=True)

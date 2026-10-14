from pathlib import Path
import json,subprocess,sys,hashlib
R=Path(__file__).resolve().parents[1];S=R.parent/'task-2';O=R/'ordered-input-build';src=R/'System-input-decoupling'
sys.path.insert(0,'/tmp/waveshare-generic-bridges/scripts')
from normalize_xtensa_relocations import normalize
from compact_current_elf import compact
proof={}
for name in ['springboard','battery','calculator','stopwatch','frequency_generator','alarms','countdown','ble_touchpad','ble_buttons']:
 recipe=S/'springboard-performance-build/command.json' if name=='springboard' else S/('watch-builds/build-recipes/'+name+'-command.json')
 cmd=json.loads(recipe.read_text());cmd=[x.replace(str(S/'springboard-performance'),str(src)).replace('/tmp/waveshare-watch-system',str(src)) for x in cmd]
 target=O/(name+'.elf');cmd[cmd.index('-o')+1]=str(target)
 (O/(name+'-command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
 with (O/(name+'.log')).open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 normalize(target);p=compact(target,cmd[0],debug_path=O/'debug'/(name+'.elf'))
 result=subprocess.run([str(S/'target-providers/validate-elf'),str(target)],text=True,capture_output=True,check=True)
 p['validation']=result.stdout;p['system_revision']=subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip();proof[name]=p
 (O/'build-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(name,p['after_bytes'],p['after_sha256'],flush=True)

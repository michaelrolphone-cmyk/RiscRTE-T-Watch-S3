#!/usr/bin/env python3
"""Restore the qualified Points shared caller with its inherited color app features."""
from pathlib import Path
import argparse,subprocess,json,hashlib,os,sys,shlex
p=argparse.ArgumentParser()
for n in ['system','utilities','productivity','runtime','watch','output']:p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--wave',action='store_true');a=p.parse_args();wave=a.wave;del a.wave;roots={k:v.resolve() for k,v in vars(a).items()};roots['system-apps']=roots.pop('system');roots['generated']=roots['productivity']/'test/native_apps/points_policy_profile';out=roots['output'];out.mkdir(parents=True,exist_ok=True)
profile=json.loads((roots['generated']/'profile.json').read_text());mapped=lambda x:x.format(**{k:str(v) for k,v in roots.items()})
flags=list(map(mapped,profile['defines']))+['-DPOINTS_TEST_ALARM_HEADER="'+str(roots['utilities']/'lib/Alarm/include/AlarmServiceV1.h')+'"','-mno-target-align','-flto']
if wave:flags=[x for x in flags if x!='-DPORTABLE_WATCH_COLOR_ONLY']+['-DPORTABLE_WATCH_NATIVE_HEIGHT']
includes=list(map(mapped,profile['includes']));sources=list(map(mapped,profile['sources']))+[str(roots['watch']/'apps/clock'/n) for n in ['portable_navigation.c','portable_sleep.c']]
cc=os.environ.get('NATIVE_APP_CC',str(Path.home()/'.platformio/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc'));mapping=out/'exports.map';mapping.write_text('{global:app_main;app_module_init;app_module_fini;local:*;};\n')
cmd=[cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',*flags,*includes,*sources,'-lgcc','-o',str(out/'points_in_time.elf')]
subprocess.run(cmd,check=True);sys.path.insert(0,str(roots['watch']/'scripts'));from compact_current_elf import compact
compaction=compact(out/'points_in_time.elf',cc)
raw=(out/'points_in_time.elf').read_bytes();assert b'ui.text-input\0' in raw
pins={k:subprocess.check_output(['git','-C',str(v),'rev-parse','HEAD'],text=True).strip() for k,v in roots.items() if k not in ['generated','output']}
deps={}
for src in sources:
 dep=subprocess.check_output([cc,'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM',*flags,*includes,src],text=True)
 for n in shlex.split(dep.replace('\\\n',' ').split(':',1)[1]):
  f=Path(n).resolve();deps[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
receipt={'version':'0.6.19','source_sha256':deps,'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),'sources':pins,'command':cmd,'defines':flags,'source_roots':{k:str(v) for k,v in roots.items()},'compaction':compaction,'hardware_tested':False}
(out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt['sha256'],len(raw))

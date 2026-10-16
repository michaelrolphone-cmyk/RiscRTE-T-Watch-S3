#!/usr/bin/env python3
"""Replay exact inherited Buttons target profiles, replacing only app source."""
from pathlib import Path
import argparse,json,subprocess,shutil,hashlib,sys,shlex
p=argparse.ArgumentParser()
for n in ['utilities','system','profile','output','watch-tools']:p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--bridges',type=Path);p.add_argument('--runtime-sdk',type=Path);p.add_argument('--compiler',type=Path);p.add_argument('--color',action='store_true');a=p.parse_args();a.utilities=a.utilities.resolve();a.system=a.system.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
source=json.loads(a.profile.read_text());cmd=source if a.color else source['compile_command'];cc=str(Path.home()/'.platformio/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc');cc=str(a.compiler.resolve()) if a.compiler else cc;cmd[0]=cc
if a.color:
 maps={'/Users/micahelbyrns/Documents/Codex/2026-10-13/task-2/utilities-current':str(a.utilities),'/Users/micahelbyrns/Documents/Codex/2026-10-13/task/System-input-decoupling':str(a.system)}
 assert a.bridges and a.runtime_sdk
 profile=a.profile.resolve().parent
 maps.update({'/tmp/waveshare-generic-bridges':str(a.bridges.resolve()),'/Users/micahelbyrns/Documents/Codex/2026-10-13/task-2/runtime':str(a.runtime_sdk.resolve()),'/Users/micahelbyrns/Documents/Codex/2026-10-13/task-2/corrected-apps':str(profile),'/Users/micahelbyrns/Documents/Codex/2026-10-12/task/storage-candidate-019g/components':str(profile)})
 oldout=next(x for x in cmd if x.startswith('-Wl,--version-script=')).split('=',1)[1];Path(out/'exports.map').write_text('{global:app_main;app_module_init;app_module_fini;local:*;};\n');cmd=[x.replace(oldout,str(out/'exports.map')) for x in cmd];cmd[-1]=str(out/'ble_buttons.elf')
else:
 original=a.profile.parent.parent;shutil.copytree(original/'sdk',out.parent/'sdk',dirs_exist_ok=True)
 for h in (a.system/'lib/PortableApps/include').glob('*.h'):shutil.copyfile(h,out.parent/'sdk/include'/h.name)
 for n in ['catalog.c','exports.map']:shutil.copyfile(a.profile.parent/n,out/n)
 maps={'/workspace/shared/ble-buttons-report-recovery-20261010/target-x4':str(out.parent),'/workspace/shared/ble-buttons-report-recovery-20261010/utilities':str(a.utilities),'/workspace/shared/ui-qualified-raster-source-20261010/system':str(a.system)}
for old,new in maps.items():cmd=[x.replace(old,new) for x in cmd]
subprocess.run(cmd,check=True);sys.path.insert(0,str(a.watch_tools.resolve()/'scripts'));from compact_current_elf import compact
proof=compact(out/'ble_buttons.elf',cc,debug_path=out/'debug/ble_buttons.elf');deps={}
# Hash the compiler-reported closure with the exact profile definitions/includes.
flags=[];i=0
while i<len(cmd):
 x=cmd[i]
 if x=='-include':flags+=cmd[i:i+2];i+=2;continue
 if x.startswith(('-I','-D')):flags.append(x)
 i+=1
for src in [x for x in cmd if x.endswith('.c')]:
 d=subprocess.check_output([cc,'-std=c11','-Os','-fPIC','-MM',*flags,src],text=True)
 for n in shlex.split(d.replace('\\\n',' ').split(':',1)[1]):
  f=Path(n).resolve();deps[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
r={'version':'0.1.26','sha256':hashlib.sha256((out/'ble_buttons.elf').read_bytes()).hexdigest(),'bytes':(out/'ble_buttons.elf').stat().st_size,'command':cmd,'source_sha256':deps,'compaction':proof,'utilities':subprocess.check_output(['git','-C',str(a.utilities),'rev-parse','HEAD'],text=True).strip(),'system':subprocess.check_output(['git','-C',str(a.system),'rev-parse','HEAD'],text=True).strip(),'hardware_tested':False}
(out/'build.json').write_text(json.dumps(r,indent=2)+'\n');print(r['sha256'],r['bytes'])

#!/usr/bin/env python3
"""Rebuild real Watch Home/Springboard with the complete canvas app catalogue."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from build_current_apps import application_inputs
from build_contexts_cohort import definitions,write_catalog
from contexts_profile import catalog
W=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
for name in ('system','utilities','runtime','baseline','output'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();S=a.system.resolve();U=a.utilities.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(U/'scripts'),str(S/'scripts')]
from normalize_xtensa_relocations import normalize
from compact_current_elf import compact
cc=os.environ.get('NATIVE_APP_CC') or shutil.which('xtensa-esp32s3-elf-gcc') or str(Path.home()/'.platformio/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc')
rows=catalog(W)+[{'display_name':'Lists','file_name':'lists.elf','icon':'solid:f274'},{'display_name':'3D Viewer','file_name':'model_viewer.elf','icon':'regular:f03e'}]
assert len(rows)==23 and len({r['file_name'] for r in rows})==23
write_catalog(out,rows);(out/'catalog.json').write_text(json.dumps({'apps':rows},indent=2)+'\n')
(out/'empty_catalog.c').write_bytes((out/'catalog.c').read_bytes())
repos={'system-apps':S,'utilities':U,'runtime':a.runtime.resolve()}
records={}
def build(name,sources,flags,includes,exports,version):
 target=out/(name+'.elf');mapping=out/(name+'.map');mapping.write_text('{ global: '+'; '.join(sorted(exports))+'; local: *; };\n')
 command=[cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror',*flags,*['-I'+str(x) for x in includes],*map(str,sources),'-lgcc','-o',str(target)]
 subprocess.run(command,check=True);normalize(target)
 proof=compact(target,cc,debug_path=out/'debug'/(name+'.elf'))
 symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',target],text=True)
 imports={x.split()[-1] for x in symbols.splitlines() if ' U ' in ' '+x}
 found={x.split()[-1] for x in symbols.splitlines() if len(x.split())>=3 and x.split()[-2] in ('T','D','B','R')}
 assert imports<={'risc_runtime_get_api','memcpy','memset','memcmp','memmove','strcmp','strncmp','strlen','snprintf','malloc','calloc','free','strcpy','memchr','strrchr'} and found==exports,(name,imports,found)
 deps={}
 for source in sources:
  if source.suffix=='.o':continue
  dep=subprocess.check_output([cc,'-std=c11','-MM',*flags,*['-I'+str(x) for x in includes],str(source)],text=True).replace('\\\n',' ')
  for token in dep.split()[1:]:
   f=Path(token).resolve()
   if f.is_file():deps[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
 m=json.loads((a.baseline/(name+'.json')).read_text());m['version']=version
 (out/(name+'.json')).write_text(json.dumps(m,indent=2)+'\n')
 records[name]={'command':command,'dependencies':deps,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size,'version':version,'imports':sorted(imports),'exports':sorted(found),'compaction':proof,'hardware_verified':False}
 (out/'build.json').write_text(json.dumps(records,indent=2)+'\n')
 print(name+': target ABI PASS',flush=True)
old=json.loads((a.baseline/'springboard.json').read_text())['version'];v=list(map(int,old.split('.')));v[-1]+=1;version='.'.join(map(str,v))
sources,includes,_=application_inputs('springboard',S/'Apps/springboard.c',repos,W,out,'runtime-features')
includes+=[U/'lib/Contexts/include']
flags=[f for f in definitions('springboard',version,W) if not f.startswith('-DPORTABLE_CATALOG_LIMIT=')]+['-DPORTABLE_CATALOG_LIMIT=23']
build('springboard',sources,flags,includes,{'app_main','app_module_init','app_module_fini'},version)
effect=out/'boot-effect.o'
subprocess.run([cc.removesuffix('gcc')+'g++','-std=c++11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-I'+str(W/'sdk/driver'),'-c',str(W/'apps/clock/effects/boot.cpp'),'-o',effect],check=True)
sources=[W/'apps/clock/crown.c',W/'apps/clock/nova/nova.c',*[S/'lib/PortableApps/src'/n for n in ('quick_actions.c','quick_render.c','quick_session.c','quick_radios.c')],W/'apps/clock/points_projection.c',W/'apps/clock/effects/divdi3.c',effect]
includes=[S/'lib/PortableApps/include',U/'lib/Alarm/include',U/'lib/Contexts/include',W/'sdk/app',W/'sdk/driver',W/'include']
build('default',sources,definitions('default','0.11.2',W),includes,{'app_main'},'0.11.2')
records['default']['boot_effect_sources']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (W/'apps/clock/effects').glob('*') if p.is_file()}
(out/'build.json').write_text(json.dumps(records,indent=2)+'\n')

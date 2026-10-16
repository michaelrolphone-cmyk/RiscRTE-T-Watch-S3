#!/usr/bin/env python3
"""Build only opt-in touch .2.2; never alter accepted dist/catalog or recipes."""
import argparse,hashlib,json,shlex,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',required=True);p.add_argument('--reader',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);source=ROOT/'drivers/candidates/twatch_touch_022/driver.c';elf=out/'driver.elf'
flags=['-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(ROOT/'exports.map'),'-Wall','-Wextra','-Werror','-I'+str(ROOT/'sdk/driver'),'-I'+str(ROOT/'include')]
command=[a.cc,*flags,str(source),'-lgcc','-o',str(elf)];subprocess.run(command,check=True)
for name in ['normalize_xtensa_relocations.py','validate_xtensa_relative_targets.py']:subprocess.run([sys.executable,str(a.reader/'scripts'/name),str(elf)],check=True)
symbols=subprocess.check_output([a.cc.removesuffix('gcc')+'readelf','--dyn-syms','--wide',str(elf)],text=True);(out/'symbols.txt').write_text(symbols)
rows=[l.split() for l in symbols.splitlines()];imports=sorted({r[7] for r in rows if len(r)>=8 and r[4]=='GLOBAL' and r[6]=='UND'});exports=sorted({r[7] for r in rows if len(r)>=8 and r[4]=='GLOBAL' and r[6]!='UND' and r[3]=='FUNC'})
assert set(imports)<={'memcpy','memset','strcmp','strlen'} and exports==['t5_driver_get']
closure=subprocess.check_output([a.cc,*flags,'-MM',str(source)],text=True);paths=[Path(x) for x in shlex.split(closure.replace('\\\n',' ').split(':',1)[1])]
hash=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=source.with_name('manifest.json');data=json.loads(manifest.read_text());assert data['id']=='twatch-touch' and data['version']=='0.2.2';(out/'manifest.json').write_bytes(manifest.read_bytes())
b=elf.read_bytes();assert b[:7]==b'\x7fELF\x01\x01\x01' and int.from_bytes(b[18:20],'little')==94
r={'source_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'source_dirty':bool(subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True).strip()),'driver_sha256':hash(source),'source_closure_sha256':{str(x.relative_to(ROOT)):hash(x) for x in paths},'command':command,'compiler':subprocess.check_output([a.cc,'--version'],text=True).splitlines()[0],'bytes':len(b),'sha256':hash(elf),'imports':imports,'exports':exports,'manifest':data,'hardware_tested':False,'default_selection_changed':False}
(out/'qualification.json').write_text(json.dumps(r,indent=2)+'\n');print(r['sha256'],r['bytes'])

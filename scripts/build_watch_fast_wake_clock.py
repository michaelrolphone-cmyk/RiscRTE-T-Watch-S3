#!/usr/bin/env python3
"""Build only the opt-in fast Watch default from its delivered dependency receipt.

This produces an ELF and manifest, not a successor image or hardware claim.
The unchanged-feature build must first reproduce the delivered default exactly.
"""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RECEIPT=ROOT/'docs/watch-110-touch-buttons/delivery/clock-reproduction.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
p=argparse.ArgumentParser(description=__doc__)
for arg in ('system','utilities','baseline','output'):p.add_argument('--'+arg,type=Path,required=True)
a=p.parse_args();S=a.system.resolve();U=a.utilities.resolve();B=a.baseline.resolve();O=a.output.resolve()
assert not O.exists(),'Choose a new output directory'
record=json.loads(RECEIPT.read_text())['default']
original='/Users/micahelbyrns/Documents/Codex/2026-10-11/task-6'
mapping={original+'/system':str(S),original+'/utilities':str(U),original+'/watch':str(ROOT),original+'/evidence/clock-reproduction':str(O)}
def remap(value):
 for old,new in mapping.items():value=value.replace(old,new)
 return value
checks={};changed=[]
for name,wanted in record['dependencies'].items():
 path=Path(remap(name));actual=sha(path);key=next(owner+':'+str(path.relative_to(folder)) for owner,folder in (('system',S),('utilities',U),('watch',ROOT)) if path.is_relative_to(folder))
 checks[key]={'sha256':actual,'delivered_sha256':wanted}
 if actual!=wanted:changed.append(key)
assert changed==['watch:apps/clock/crown.c'],changed
assert sha(B/'default.elf')==record['sha256'],'Delivered Clock differs'
assert json.loads((B/'default.json').read_text())['version']=='0.11.2'
cc=os.environ.get('NATIVE_APP_CC') or shutil.which('xtensa-esp32s3-elf-gcc')
assert cc,'Set NATIVE_APP_CC to the pinned compiler'
version=subprocess.check_output([cc,'--version'],text=True).splitlines()[0]
assert '8.4.0' in version and '2021r2-patch5' in version
O.mkdir(parents=True);(O/'debug').mkdir()
normalizer=load('wake_normalize',U/'scripts/normalize_xtensa_relocations.py')
compactor=load('wake_compact',ROOT/'scripts/compact_current_elf.py')
(O/'default.map').write_text('{ global: app_main; local: *; };\n')
effect=O/'boot-effect.o'
subprocess.run([cc.removesuffix('gcc')+'g++','-std=c++11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-I'+str(ROOT/'sdk/driver'),'-c',str(ROOT/'apps/clock/effects/boot.cpp'),'-o',str(effect)],check=True)
command=[cc,*[remap(x) for x in record['command'][1:]]]
proof={'schema':1,'compiler':version,'receipt_sha256':sha(RECEIPT),'dependencies':checks,'changed_dependency_keys':changed,'hardware_verified':False,'image_assembled':False,'clock_return_wrapper_changed':False}
for fast in (False,True):
 cmd=command[:] if not fast else [*command[:-2],'-DWATCH_FAST_WAKE',*command[-2:]]
 subprocess.run(cmd,check=True)
 target=O/'default.elf';normalization=normalizer.normalize(target)
 compaction=compactor.compact(target,cc,debug_path=O/'debug'/('fast.elf' if fast else 'reproduction.elf'))
 symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(target)],text=True)
 imports={x.split()[-1] for x in symbols.splitlines() if ' U ' in ' '+x}
 exports={x.split()[-1] for x in symbols.splitlines() if len(x.split())>=3 and x.split()[-2] in ('T','D','B','R')}
 assert imports<=set(record['imports']) and exports=={'app_main'},(imports,exports)
 stage={'bytes':target.stat().st_size,'sha256':sha(target),'imports':sorted(imports),'exports':sorted(exports),'compaction':compaction,'relocation_normalization':normalization,'command':cmd}
 if not fast:
  assert sha(target)==record['sha256'],'No-fast build did not reproduce delivered Clock'
  proof['delivered_reproduction']=stage;shutil.copyfile(target,O/'reproduction.elf')
 else:proof['fast_clock']=stage
manifest=json.loads((B/'default.json').read_text());manifest['version']='0.11.3'
(O/'default.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
proof['manifest']={'sha256':sha(O/'default.json'),'version':manifest['version'],'only_version_changed':True}
(O/'build.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
print('Exact delivered Clock reproduced; opt-in fast Clock target ABI/import checks passed. No image assembled.')

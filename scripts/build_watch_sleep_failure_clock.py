#!/usr/bin/env python3
"""Reproduce delivered Clock 0.11.4, then build the focused sleep-failure diagnostic successor.

Uses the pinned 98-file target receipt. No device access or publication.
"""
import argparse,hashlib,importlib.util,json,os,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE='8ed572f02941d79c3ffbf4e05e0c4218b99b4d7e'
BASE_ELF='82e06ed773f21c0dfa1936bd7d2a0f1f7e27de14a16a65bcfa1e10641ed791ac'
BASE_RECEIPT='b3f3edc848c6f497433d5e7e82d3b2e2a702c57ae1529e7d2acdae7751452639'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(p,*args):return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=argparse.ArgumentParser(description=__doc__)
for n in ('baseline-product','baseline-clock','system','utilities','output'):p.add_argument('--'+n,type=pathlib.Path,required=True)
a=p.parse_args();B=a.baseline_product.resolve();C=a.baseline_clock.resolve();S=a.system.resolve();U=a.utilities.resolve();O=a.output.resolve()
assert git(B,'rev-parse','HEAD')==BASE and not git(B,'status','--porcelain','--untracked-files=no')
assert sha(C/'build.json')==BASE_RECEIPT and sha(C/'default.elf')==BASE_ELF
assert git(S,'rev-parse','HEAD')=='63532e4611749acad2060d0437a883b7c4ac8fd5'
assert git(U,'rev-parse','HEAD')=='814502e51125d799a7ca625b78707753ca12d4e5'
r=json.loads((C/'build.json').read_text());checks={};changed=[]
for k,v in r['dependencies'].items():
 owner,relative=k.split(':',1);base={'watch':B,'system':S,'utilities':U}[owner];actual={'watch':ROOT,'system':S,'utilities':U}[owner]
 assert sha(base/relative)==v['sha256'],k
 digest=sha(actual/relative);checks[k]={'sha256':digest,'predecessor_sha256':v['sha256']}
 if digest!=v['sha256']:changed.append(k)
assert sorted(changed)==['watch:apps/clock/crown.c','watch:apps/clock/watch_motion_client.h'],changed
assert len(checks)==98 and not O.exists()
cc=os.environ.get('NATIVE_APP_CC') or shutil.which('xtensa-esp32s3-elf-gcc');assert cc
version=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];assert '8.4.0' in version and '2021r2-patch5' in version
normalizer=module('sleep_failure_normalize',U/'scripts/normalize_xtensa_relocations.py');compactor=module('sleep_failure_compact',ROOT/'scripts/compact_current_elf.py')
O.mkdir(parents=True);(O/'debug').mkdir();(O/'default.map').write_text('{ global: app_main; local: *; };\n')
proof={'schema':1,'compiler':version,'baseline_product':BASE,'receipt_sha256':BASE_RECEIPT,'dependencies':checks,'changed_dependency_keys':sorted(changed),'hardware_verified':False,'image_assembled':False,'clock_return_wrapper_changed':False}
old_watch='/workspace/shared/watch-deep-wake-stages-product';old_system='/workspace/shared/watch-fast-wake-20261012/system-clock';old_utilities='/workspace/shared/watch-fast-wake-20261012/utilities-clock';old_output='/workspace/shared/watch-deep-wake-clock-build-0114-final'
for label,watch in [('delivered_reproduction',B),('fast_clock',ROOT)]:
 subprocess.run([cc.removesuffix('gcc')+'g++','-std=c++11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-I'+str(watch/'sdk/driver'),'-c',str(watch/'apps/clock/effects/boot.cpp'),'-o',str(O/'boot-effect.o')],check=True)
 mapping={old_watch:str(watch),old_system:str(S),old_utilities:str(U),old_output:str(O)}
 def remap(value):
  for old,new in mapping.items():value=value.replace(old,new)
  return value
 command=[cc,*[remap(x) for x in r['fast_clock']['command'][1:]]]
 subprocess.run(command,check=True);target=O/'default.elf';relocations=normalizer.normalize(target)
 debug=O/'debug'/('reproduction.elf' if label=='delivered_reproduction' else 'fast.elf');compact=compactor.compact(target,cc,debug_path=debug)
 symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(target)],text=True);imports={x.split()[-1] for x in symbols.splitlines() if ' U ' in ' '+x};exports={x.split()[-1] for x in symbols.splitlines() if len(x.split())>=3 and x.split()[-2] in ('T','D','B','R')}
 assert imports<=set(r['fast_clock']['imports']) and exports=={'app_main'},(imports,exports)
 proof[label]={'bytes':target.stat().st_size,'sha256':sha(target),'imports':sorted(imports),'exports':sorted(exports),'command':command,'compaction':compact,'relocation_normalization':relocations}
 if label=='delivered_reproduction':assert sha(target)==BASE_ELF;shutil.copyfile(target,O/'reproduction.elf')
manifest=json.loads((C/'default.json').read_text());assert manifest['version']=='0.11.4';manifest['version']='0.11.5';(O/'default.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n');proof['manifest']={'sha256':sha(O/'default.json'),'version':'0.11.5','only_version_changed':True}
(O/'build.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n');print('Delivered Clock 0.11.4 reproduced byte-for-byte; Clock 0.11.5 target imports/exports/grants preserved')

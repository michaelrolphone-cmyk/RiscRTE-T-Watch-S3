#!/usr/bin/env python3
"""Build only the selected scene Contexts client with its complete inherited profile."""
import argparse,hashlib,importlib.util,json,os,shlex,shutil,subprocess,sys
from pathlib import Path
DEVICE='x4' if Path(__file__).resolve().parent.parent.name=='minimal' else 'watch'
ROOT=Path(__file__).resolve().parents[2 if DEVICE=='x4' else 1]
DOCS=ROOT/('minimal/docs/contexts-shared-input' if DEVICE=='x4' else 'docs/contexts-shared-input')
VERSION='0.4.3'
SYSTEM='7fb13b09b4dac275a8111b224784f8a472f39264'
UTILITIES='2a06ff127e6f7c7d687b1361bed05da97aa05b2d'
UTILITIES_BASE='4beb9778d300ec9f6b18448e1ec86317e063c98c'
PROFILE='089868395268b696c05651c33816345bfe0425df'
RUNTIMES={'watch':'64c8e52e46fd91e8fdafd636db04eed88f0c51a9','x4':'1c1ed8661ea30d47e7e9707c41d492ce3a2b4d70'}
PRIOR={'watch':'4896654c86b0c1c203af5e07a20425157a512c48b68dd5bca1c86756ca7dfe9a','x4':'f2fd480a5d3135cf01decbaec4b7288285cee5677e29251d12badcb10928babb'}
ADDITIONS=['-DPORTABLE_CONTEXTS_SHARED_TEXT_INPUT']
EXPORTS={'app_main','risc_resident_app_descriptor_v1'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(p,*args):return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()
def require(ok,message):
 if not ok:raise ValueError(message)
def clean(p,pin):require(git(p,'rev-parse','HEAD')==pin and not git(p,'status','--porcelain','--untracked-files=no'),'Wrong or dirty source: '+str(p))
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def build(a):
 S,U,R,W,O,B=[getattr(a,n).resolve() for n in ('system','utilities','runtime','watch_profile','output','baseline')]
 revision=git(ROOT,'rev-parse','HEAD');require(a.utilities_commit==UTILITIES,'Unqualified Contexts application source')
 for path,pin in [(ROOT,revision),(S,SYSTEM),(U,a.utilities_commit),(R,RUNTIMES[DEVICE]),(W,PROFILE)]:clean(path,pin)
 subprocess.run(['git','-C',str(U),'merge-base','--is-ancestor',UTILITIES_BASE,a.utilities_commit],check=True)
 require(not O.exists(),'Use a fresh output directory')
 previous=json.loads((DOCS/'baseline.json').read_text());require(previous['elf_sha256']==PRIOR[DEVICE],'Wrong selected predecessor')
 sys.path.insert(0,str(a.watch_tools.resolve()/'scripts'))
 from compact_current_elf import compact
 if DEVICE=='watch':
  from current_bootfs import read_image
  store=read_image((B/'components/bootfs.bin').read_bytes(),0x510000);old=store['contexts.elf'];manifest=json.loads(store['contexts.json'])
  inherited=['-include',str(W/'apps/clock/faces/ContextsFaces.h')]
 else:
  boot=json.loads((B/'store/boot.json').read_text());row=next(r for r in boot['app_capabilities'] if r['manifest']=='contexts.json')
  # The immutable SD selection is authoritative; the flat fallback is not.
  path=row.get('image_source',{}).get('path')
  if path is None:
   rows=json.loads((B/'receipts/evening-composition.json').read_text())['selected_sd_images'];path=next(r['path'] for r in rows if r['manifest']=='contexts.json')
  old=(B/'SD'/path).read_bytes();manifest=json.loads((B/'store/contexts.json').read_text());inherited=previous['defines']
 require(hashlib.sha256(old).hexdigest()==PRIOR[DEVICE] and manifest['version']=='0.4.2','Wrong Contexts predecessor')
 require({'capability':'ui.text-input','api':1} not in manifest['requires'],'Already opted in')
 manifest['version']=VERSION;manifest['requires'].append({'capability':'ui.text-input','api':1})
 O.mkdir(parents=True);(O/'debug').mkdir()
 builder=load('contexts_scene_builder',S/'scripts/scene_build.py');stager=load('contexts_sdk_stager',U/'scripts/build_contexts_scene.py')
 include=stager.stage(R,S,O/'sdk')
 require((include/'RiscTextEntryV1.h').is_file() and (include/'PortableTextInputClient.h').is_file(),'Shared text SDK not staged')
 catalog=O/'catalog.c';shutil.copyfile(DOCS/'catalog.c',catalog);require(sha(catalog)==previous['catalog_sha256'],'Frozen full app catalog differs')
 flags=inherited+ADDITIONS;sources=[U/'Apps/contexts.c',catalog]
 cc=builder.compiler_path();compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];require('8.4.0' in compiler and '2021r2-patch5' in compiler,'Wrong compiler')
 owners={'system-apps':S,'utilities':U,'runtime':R,'watch':W,'generated':O};deps={}
 for source in sources:
  output=subprocess.check_output([cc,'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM','-I'+str(include),*flags,str(source)],text=True)
  for token in shlex.split(output.replace('\\\n',' ').split(':',1)[1]):
   path=Path(token).resolve();require(path.is_file() and not {'test','tests','fixtures'}&set(path.parts),'Invalid target input: '+token)
   matches=[(key,path.relative_to(root)) for key,root in owners.items() if path.is_relative_to(root)];require(matches,'Unowned target input: '+token);owner,relative=matches[-1]
   deps[owner+':'+relative.as_posix()]={'sha256':sha(path),'bytes':path.stat().st_size}
 require(any(n.endswith('contexts_text_input.inc') for n in deps) and any(n.endswith('PortableTextInputClient.h') for n in deps),'Shared Contexts path was not compiled')
 require(not any('/fonts/' in n or '/paper_fonts/' in n or '/settings_fonts/' in n for n in deps),'Unexpected application font compilation')
 command=[cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(O/'exports.map'),'-Wall','-Wextra','-Werror','-I'+str(include),*flags,*map(str,sources),'-o',str(O/'contexts.elf')]
 target=builder.build(cc,include,O,manifest,sources,defines=flags,exports=EXPORTS)
 elf=O/'contexts.elf';shutil.copyfile(elf,O/'debug/contexts.elf')
 compaction=compact(elf,cc,debug_path=O/'debug/contexts.elf') if DEVICE=='watch' else None
 validator=O/'validate-elf';subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(S/'test/native_apps/stubs'),'-I'+str(S/'lib/elf_loader/include'),str(S/'lib/elf_loader/src/esp_elf_validate.c'),str(S/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True);subprocess.run([str(validator),str(elf)],check=True)
 require(b'ui.text-input\0' in elf.read_bytes(),'Shared text service missing in target');require(elf.stat().st_size<=100000,'Contexts component budget exceeded')
 for name,row in deps.items():
  owner,relative=name.split(':',1);require(sha(owners[owner]/relative)==row['sha256'],'Source changed during build')
 for path,pin in [(ROOT,revision),(S,SYSTEM),(U,a.utilities_commit),(R,RUNTIMES[DEVICE]),(W,PROFILE)]:clean(path,pin)
 record=dict(schema='contexts.shared-input.component.v1',device=DEVICE,version=VERSION,sha256=sha(elf),bytes=elf.stat().st_size,manifest_sha256=sha(O/'contexts.json'),compiler=compiler,compiler_path=cc,command=command,scene_builder_sha256=sha(S/'scripts/scene_build.py'),defines=flags,inherited_defines=inherited,feature_additions=ADDITIONS,sources={k:git(v,'rev-parse','HEAD') for k,v in owners.items() if k!='generated'},source_roots={k:str(v) for k,v in owners.items()},product_recipe=revision,build_recipe_sha256=sha(__file__),target_dependencies=deps,staged_sdk_sha256=target['sdk_sha256'],catalog_sha256=sha(catalog),original_fonts_retained=True,fonts_owned_by_unchanged_scene_host=True,baseline_features_preserved=True,predecessor_elf_sha256=PRIOR[DEVICE],imports=target['imports'],exports=target['exports'],compaction=compaction,shared_text_input=True,native_changed=False,hardware_verified=False,command_profile='System scripts/scene_build.py build; flags and source dependencies recorded')
 (O/'contexts-build-record.json').write_text(json.dumps(record,indent=2)+'\n');print(DEVICE,'Contexts',VERSION,record['bytes'],record['sha256'])
 return record

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['system','utilities','runtime','watch-profile','watch-tools','baseline','output']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--utilities-commit',required=True);build(p.parse_args())
if __name__=='__main__':main()

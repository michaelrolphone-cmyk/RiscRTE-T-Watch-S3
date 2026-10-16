#!/usr/bin/env python3
"""Build the selected Lists client over its exact scene-only inherited profile."""
import argparse,hashlib,importlib.util,json,shlex,shutil,subprocess,sys,tempfile
from pathlib import Path
DEVICE='x4' if Path(__file__).resolve().parent.parent.name=='minimal' else 'watch'
ROOT=Path(__file__).resolve().parents[2 if DEVICE=='x4' else 1]
DOCS=ROOT/('minimal/docs/lists-shared-input' if DEVICE=='x4' else 'docs/lists-shared-input')
VERSION='0.1.2'
SYSTEM_BASE='7fb13b09b4dac275a8111b224784f8a472f39264'
PRODUCTIVITY_BASE='395c48de8fa10b672816c89c02dd9a5d4987a094'
RUNTIMES={'watch':'64c8e52e46fd91e8fdafd636db04eed88f0c51a9','x4':'1c1ed8661ea30d47e7e9707c41d492ce3a2b4d70'}
PRIOR={'watch':'79dcedcce8ea351e9ae16d4745aee5311f72832e0d8d71841a14b7468185d9da','x4':'716458214fe30123c186d1972a6950332820f5922397a7a506b3802edffbb582'}
ADDITIONS=['-DPORTABLE_LISTS_SHARED_TEXT_INPUT']
SOURCES=('Apps/lists_scene.c','Apps/ListsScene.c','lib/Lists/ListsModel.c','lib/Lists/ListsStore.c')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(p,*args):return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()
def require(ok,message):
 if not ok:raise ValueError(message)
def clean(p,pin):require(git(p,'rev-parse','HEAD')==pin and not git(p,'status','--porcelain','--untracked-files=no'),'Wrong or dirty source: '+str(p))
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def build(a):
 S,P,R,O,B=[getattr(a,n).resolve() for n in ('system','productivity','runtime','output','baseline')]
 revision=git(ROOT,'rev-parse','HEAD')
 for path,pin in [(ROOT,revision),(S,a.system_commit),(P,a.productivity_commit),(R,RUNTIMES[DEVICE])]:clean(path,pin)
 subprocess.run(['git','-C',str(S),'merge-base','--is-ancestor',SYSTEM_BASE,a.system_commit],check=True)
 subprocess.run(['git','-C',str(P),'merge-base','--is-ancestor',PRODUCTIVITY_BASE,a.productivity_commit],check=True)
 require(not O.exists(),'Use fresh target output')
 previous=json.loads((DOCS/'baseline.json').read_text());require(previous['elf_sha256']==PRIOR[DEVICE],'Wrong selected predecessor')
 sys.path.insert(0,str(a.watch_tools.resolve()/'scripts'));from compact_current_elf import compact
 if DEVICE=='watch':
  from current_bootfs import read_image
  store=read_image((B/'components/bootfs.bin').read_bytes(),0x510000);old=store['lists.elf'];manifest=json.loads(store['lists.json'])
 else:
  row=next(r for r in json.loads((B/'store/boot.json').read_bytes())['app_capabilities'] if r['manifest']=='lists.json')
  require(row['image_source']=={'path':'Apps/lists/lists.elf','volume_instance':9},'Wrong selected Lists source')
  old=(B/'SD'/row['image_source']['path']).read_bytes();manifest=json.loads((B/'store/lists.json').read_bytes())
 require(hashlib.sha256(old).hexdigest()==PRIOR[DEVICE] and manifest==previous['manifest'],'Wrong Lists predecessor')
 manifest['version']=VERSION;manifest['requires'].append({'capability':'ui.text-input','api':1})
 subprocess.run([sys.executable,str(P/'scripts/build_lists_scene.py'),'--runtime',str(R),'--system-apps',str(S),'--output',str(O),'--shared-text-input'],check=True)
 builder=load('lists_scene_builder',S/'scripts/scene_build.py');stager=load('lists_sdk_stager',P/'scripts/build_lists_scene.py')
 cc=builder.compiler_path();compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];require('8.4.0' in compiler and '2021r2-patch5' in compiler,'Wrong compiler')
 target=json.loads((O/'lists/build.json').read_bytes());require(target['defines']==ADDITIONS and target['version']==VERSION,'Wrong Lists target profile')
 for n in ('lists.elf','lists.json'):shutil.copyfile(O/'lists'/n,O/n)
 # Project only the selected device manifest: catalog metadata is not runtime authority.
 (O/'lists.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 (O/'debug').mkdir();shutil.copyfile(O/'lists.elf',O/'debug/lists.elf')
 owners={'system-apps':S,'productivity':P,'runtime':R,'generated':O};deps={}
 include=stager.stage(R,S,O/'sdk',shared_input=True)
 require({p.name:sha(p) for p in include.glob('*.h')}==target['sdk_sha256'],'SDK staging differs from compiled target')
 selected_profile=json.loads((P/'sdk/lists-selected-profile/source.json').read_text());require(selected_profile['commit']=='eec748ca081fe59346be03180600c65013cc7298' and selected_profile['sha256']==sha(P/'sdk/lists-selected-profile/RiscSceneResidentV1.h')==sha(include/'RiscSceneResidentV1.h')=='a657fcd906217fdbb03894c15b10009b352d6a5b7466868afa603a03236b8851','Selected resident helper differs')
 require((include/'RiscTextEntryV1.h').is_file() and (include/'PortableTextInputClient.h').is_file(),'Shared SDK not staged')
 for source in [P/p for p in SOURCES]:
  output=subprocess.check_output([cc,'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM','-I'+str(include),*ADDITIONS,str(source)],text=True)
  for token in shlex.split(output.replace('\\\n',' ').split(':',1)[1]):
   path=Path(token).resolve();require(path.is_file() and not {'test','tests','fixtures'}&set(path.parts),'Invalid target input: '+token)
   matches=[(key,path.relative_to(root)) for key,root in owners.items() if path.is_relative_to(root)];require(matches,'Unowned target input: '+token);owner,relative=matches[-1]
   deps[owner+':'+relative.as_posix()]={'sha256':sha(path),'bytes':path.stat().st_size}
 require(any(n.endswith('PortableTextInputCheckpointClient.h') for n in deps),'Checkpoint client suffix was not compiled')
 require(any(n.endswith('PortableTextInputResidentCheckpoint.h') for n in deps),'Resident continuity reply helper was not compiled')
 require(any(n.endswith('lists_text_input.inc') for n in deps) and any(n.endswith('PortableTextInputClient.h') for n in deps),'Shared path was not compiled')
 require(not any('/fonts/' in n or '/paper_fonts/' in n or '/settings_fonts/' in n for n in deps),'Unexpected embedded font')
 elf=O/'lists.elf';compaction=compact(elf,cc,debug_path=O/'debug/lists.elf') if DEVICE=='watch' else None
 validator=O/'validate-elf';subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(S/'test/native_apps/stubs'),'-I'+str(S/'lib/elf_loader/include'),str(S/'lib/elf_loader/src/esp_elf_validate.c'),str(S/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True);subprocess.run([str(validator),str(elf)],check=True)
 require(b'ui.text-input\0' in elf.read_bytes() and elf.stat().st_size<=45000,'Missing text service or component budget exceeded')
 for name,row in deps.items():
  owner,relative=name.split(':',1);require(sha(owners[owner]/relative)==row['sha256'],'Source changed during build')
 for path,pin in [(ROOT,revision),(S,a.system_commit),(P,a.productivity_commit),(R,RUNTIMES[DEVICE])]:clean(path,pin)
 command=[sys.executable,str(P/'scripts/build_lists_scene.py'),'--runtime',str(R),'--system-apps',str(S),'--output',str(O),'--shared-text-input']
 compiler_command=[cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(O/'lists/exports.map'),'-Wall','-Wextra','-Werror','-I<invocation-staged-sdk>',*ADDITIONS,*[str(P/p) for p in SOURCES],'-o',str(O/'lists/lists.elf')]
 record=dict(schema='lists.shared-input.component.v1',device=DEVICE,version=VERSION,sha256=sha(elf),bytes=elf.stat().st_size,manifest_sha256=sha(O/'lists.json'),compiler=compiler,compiler_path=cc,command=command,compiler_command=compiler_command,scene_builder_sha256=sha(S/'scripts/scene_build.py'),application_builder_sha256=sha(P/'scripts/build_lists_scene.py'),defines=ADDITIONS,inherited_defines=[],feature_additions=ADDITIONS,sources={k:git(v,'rev-parse','HEAD') for k,v in owners.items() if k!='generated'},source_roots={k:str(v) for k,v in owners.items()},product_recipe=revision,build_recipe_sha256=sha(__file__),target_dependencies=deps,staged_sdk_sha256=target['sdk_sha256'],selected_resident_profile=selected_profile,original_fonts_retained=True,fonts_owned_by_scene_host=True,baseline_features_preserved=True,predecessor_elf_sha256=PRIOR[DEVICE],imports=target['imports'],exports=target['exports'],compaction=compaction,shared_text_input=True,native_changed=False,hardware_verified=False,raw_elf_sha256=sha(O/'debug/lists.elf'),raw_elf_bytes=(O/'debug/lists.elf').stat().st_size)
 (O/'lists-build-record.json').write_text(json.dumps(record,indent=2)+'\n');print(DEVICE,'Lists',VERSION,record['bytes'],record['sha256'])
 return record

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['system','productivity','runtime','watch-tools','baseline','output']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--productivity-commit',required=True);p.add_argument('--system-commit',required=True);build(p.parse_args())
if __name__=='__main__':main()

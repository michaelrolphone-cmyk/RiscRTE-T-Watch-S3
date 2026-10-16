#!/usr/bin/env python3
"""Build only the shared text host, retaining existing device selection and authority."""
import argparse,hashlib,json,shlex,shutil,subprocess,sys
from pathlib import Path
from build_lists_shared_input import DEVICE,ROOT,RUNTIMES,SYSTEM_BASE,sha,git,require,clean,load
TEXT_VERSION='0.1.7'
HOST_PATH={'watch':'text-input','x4':'ui-text'}
HOST_PRIOR={'watch':('0.1.6','3b71583ae513ab3b523fcd84e80f5871835455abe1fbee368914fc6bf2e4c2cb'),'x4':('0.1.5','5517367ec213230ca5cc7e33c3f92231a89dae90cb9aba29d5bb8a36791890a1')}

def build(a):
 S,R,O,B=[getattr(a,n).resolve() for n in ('system','runtime','output','baseline')];revision=git(ROOT,'rev-parse','HEAD')
 for path,pin in [(ROOT,revision),(S,a.system_commit),(R,RUNTIMES[DEVICE])]:clean(path,pin)
 subprocess.run(['git','-C',str(S),'merge-base','--is-ancestor',SYSTEM_BASE,a.system_commit],check=True)
 require(not O.exists(),'Use fresh text output');O.mkdir(parents=True)
 sys.path.insert(0,str(a.watch_tools.resolve()/'scripts'));from compact_current_elf import compact
 if DEVICE=='watch':
  from current_bootfs import read_image
  old=read_image((B/'components/bootfs.bin').read_bytes(),0x510000)
 else:old={p.relative_to(B/'store').as_posix():p.read_bytes() for p in (B/'store').rglob('*') if p.is_file()}
 folder=HOST_PATH[DEVICE];previous=json.loads(old[folder+'/manifest.json']);prior_version,prior_sha=HOST_PRIOR[DEVICE]
 require(previous['version']==prior_version and hashlib.sha256(old[folder+'/driver.elf']).hexdigest()==prior_sha,'Wrong selected text host')
 manifest=json.loads((S/'Services/text_input/manifest.json').read_bytes());require(manifest==dict(previous,version=TEXT_VERSION),'Text host authority/profile changed')
 stage=load('text_sdk',S/'scripts/scene_sdk.py');builder=load('text_builder',S/'scripts/scene_build.py');include=stage.stage_sdk(R,S,O/'sdk')
 shutil.copyfile(S/'sdk/app/RiscTextEntryV1.h',include/'RiscTextEntryV1.h')
 for name in ['RiscUsbHidV1.h','RiscUsbControllerV1.h','RiscUsbProviderV1.h']:
  source=S/'Services/text_input'/name;dest=include/name
  require(not dest.exists() or dest.read_bytes()==source.read_bytes(),'USB contract differs');shutil.copyfile(source,dest)
 cc=builder.compiler_path();compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];require('8.4.0' in compiler and '2021r2-patch5' in compiler,'Wrong compiler')
 sources=[S/'Services/text_input/host.c'];deps={};owners={'system-apps':S,'runtime':R,'generated':O}
 for source in sources:
  output=subprocess.check_output([cc,'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM','-I'+str(include),str(source)],text=True)
  for token in shlex.split(output.replace('\\\n',' ').split(':',1)[1]):
   path=Path(token).resolve();require(path.is_file() and not {'test','tests','fixtures'}&set(path.parts),'Invalid target dependency')
   matches=[(owner,path.relative_to(root)) for owner,root in owners.items() if path.is_relative_to(root)];require(matches,'Unowned dependency');owner,relative=matches[-1]
   deps[owner+':'+relative.as_posix()]={'sha256':sha(path),'bytes':path.stat().st_size}
 require(any(n.endswith('/checkpoint.inc') for n in deps),'Checkpoint host suffix not compiled')
 require(not any('/fonts/' in n or '/paper_fonts/' in n or '/settings_fonts/' in n for n in deps),'Text host unexpectedly embeds fonts')
 target=builder.build(cc,include,O,manifest,sources)
 # Same raw host and deterministic compiler profile; retain debug metadata separately.
 builder.build(cc,include,O/'repeat',manifest,sources);require(sha(O/'driver.elf')==sha(O/'repeat/driver.elf'),'Text host target is not reproducible')
 (O/'debug').mkdir();shutil.copyfile(O/'driver.elf',O/'debug/driver.elf');compaction=compact(O/'driver.elf',cc,debug_path=O/'debug/driver.elf') if DEVICE=='watch' else None
 validator=O/'validate-elf';subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(S/'test/native_apps/stubs'),'-I'+str(S/'lib/elf_loader/include'),str(S/'lib/elf_loader/src/esp_elf_validate.c'),str(S/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True);subprocess.run([str(validator),str(O/'driver.elf')],check=True)
 for name,row in deps.items():
  owner,relative=name.split(':',1);require(sha(owners[owner]/relative)==row['sha256'],'Dependency changed while building')
 for path,pin in [(ROOT,revision),(S,a.system_commit),(R,RUNTIMES[DEVICE])]:clean(path,pin)
 record=dict(schema='lists.shared-text-host.component.v1',device=DEVICE,version=TEXT_VERSION,sha256=sha(O/'driver.elf'),bytes=(O/'driver.elf').stat().st_size,manifest_sha256=sha(O/'manifest.json'),compiler=compiler,compiler_path=cc,defines=[],sources={k:git(v,'rev-parse','HEAD') for k,v in owners.items() if k!='generated'},source_roots={k:str(v) for k,v in owners.items()},product_recipe=revision,build_recipe_sha256=sha(__file__),target_dependencies=deps,staged_sdk_sha256=target['sdk_sha256'],imports=target['imports'],exports=target['exports'],compaction=compaction,raw_elf_sha256=sha(O/'debug/driver.elf'),raw_elf_bytes=(O/'debug/driver.elf').stat().st_size,prior_version=prior_version,prior_elf_sha256=prior_sha,authority_unchanged=True,embeds_fonts=False,scene_renderer_not_built_by_text_recipe=True,native_changed=False,hardware_verified=False)
 (O/'text-build-record.json').write_text(json.dumps(record,indent=2)+'\n');print(DEVICE,'shared text host',TEXT_VERSION,record['bytes'],record['sha256']);return record
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['system','runtime','watch-tools','baseline','output']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--system-commit',required=True);build(p.parse_args())

#!/usr/bin/env python3
"""Build only the selected scene host with its exact profile and frozen font assets."""
import argparse,hashlib,json,shlex,shutil,subprocess,sys
from pathlib import Path
from build_lists_shared_input import DEVICE,ROOT,RUNTIMES,SYSTEM_BASE,sha,git,require,clean,load
SCENE_VERSION='0.4.6'
SCENE_PRIOR={'watch':('0.4.5','9b89bca7a6fa1a8f8ae58c5205785bb1aed0ca8328ca47afa4c8594ea1653cfe'),'x4':('0.4.4','f9a3b503531154a6479c5c36780daee51d6e0050a1a54b7327624b242930b188')}
SCENE_FLAGS={'watch':['-DSCENE_HOST_TELEMETRY=0','-DSCENE_HOST_WATCH_240=1'],'x4':[]}
TELEMETRY_SHA='2d7501e42d6223ebbc191817715431182c435fea944a1a02166a0748a577eaf1'
def stage_telemetry_font(system,include):
 import PIL
 require(PIL.__version__=='12.3.0','Exact telemetry rasterizer Pillow12.3.0 required')
 require(sha(system/'scripts/generate_telemetry_fonts.py')==hashlib.sha256(subprocess.check_output(['git','-C',str(system),'show',SYSTEM_BASE+':scripts/generate_telemetry_fonts.py'])).hexdigest(),'Telemetry font generator changed')
 generated=include.parent/'telemetry-font-source';fontdir=generated/'Services/scene_host/fonts';fontdir.mkdir(parents=True);(generated/'scripts').mkdir()
 shutil.copyfile(system/'scripts/generate_telemetry_fonts.py',generated/'scripts/generate_telemetry_fonts.py')
 for name in ['Orbitron-700.ttf','Orbitron-900.ttf','Rajdhani-700.ttf']:shutil.copyfile(system/'Services/scene_host/fonts'/name,fontdir/name)
 subprocess.run([sys.executable,str(generated/'scripts/generate_telemetry_fonts.py')],check=True)
 require(sha(fontdir/'telemetry.inc')==TELEMETRY_SHA,'Generated telemetry font differs from selected X4 bytes')
 (include/'fonts').mkdir();shutil.copyfile(fontdir/'telemetry.inc',include/'fonts/telemetry.inc')
 return {'sha256':TELEMETRY_SHA,'bytes':(fontdir/'telemetry.inc').stat().st_size,'pillow_version':PIL.__version__,'generator_sha256':sha(system/'scripts/generate_telemetry_fonts.py'),'font_inputs':{n:sha(fontdir/n) for n in ['Orbitron-700.ttf','Orbitron-900.ttf','Rajdhani-700.ttf']}}

def build(a):
 S,R,O,B=[getattr(a,n).resolve() for n in ('system','runtime','output','baseline')];revision=git(ROOT,'rev-parse','HEAD')
 for path,pin in [(ROOT,revision),(S,a.system_commit),(R,RUNTIMES[DEVICE])]:clean(path,pin)
 subprocess.run(['git','-C',str(S),'merge-base','--is-ancestor',SYSTEM_BASE,a.system_commit],check=True)
 require(not O.exists(),'Use fresh scene output');O.mkdir(parents=True)
 sys.path.insert(0,str(a.watch_tools.resolve()/'scripts'));from compact_current_elf import compact
 if DEVICE=='watch':
  from current_bootfs import read_image
  old=read_image((B/'components/bootfs.bin').read_bytes(),0x510000)
 else:old={p.relative_to(B/'store').as_posix():p.read_bytes() for p in (B/'store').rglob('*') if p.is_file()}
 previous=json.loads(old['ui-scene/manifest.json']);prior_version,prior_sha=SCENE_PRIOR[DEVICE]
 require(previous['version']==prior_version and hashlib.sha256(old['ui-scene/driver.elf']).hexdigest()==prior_sha,'Wrong selected scene host')
 manifest_name='manifest-watch-compact.json' if DEVICE=='watch' else 'manifest.json';manifest=json.loads((S/'Services/scene_host'/manifest_name).read_bytes());require(manifest==dict(previous,version=SCENE_VERSION),'Scene host authority/profile changed')
 fonts_tree=git(S,'rev-parse',a.system_commit+':Services/scene_host/fonts');require(fonts_tree==git(S,'rev-parse',SYSTEM_BASE+':Services/scene_host/fonts'),'Font source tree changed')
 stage=load('scene_sdk_selected',S/'scripts/scene_sdk.py');builder=load('scene_builder_selected',S/'scripts/scene_build.py');include=stage.stage_sdk(R,S,O/'sdk')
 telemetry_font=stage_telemetry_font(S,include) if DEVICE=='x4' else None
 cc=builder.compiler_path();compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];require('8.4.0' in compiler and '2021r2-patch5' in compiler,'Wrong compiler')
 sources=[S/'Services/scene_host/host.c'];flags=SCENE_FLAGS[DEVICE];deps={};owners={'system-apps':S,'runtime':R,'generated':O}
 for source in sources:
  output=subprocess.check_output([cc,'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM','-I'+str(include),*flags,str(source)],text=True)
  for token in shlex.split(output.replace('\\\n',' ').split(':',1)[1]):
   path=Path(token).resolve();require(path.is_file() and not {'test','tests','fixtures'}&set(path.parts),'Invalid target dependency')
   matches=[(owner,path.relative_to(root)) for owner,root in owners.items() if path.is_relative_to(root)];require(matches,'Unowned dependency');owner,relative=matches[-1]
   deps[owner+':'+relative.as_posix()]={'sha256':sha(path),'bytes':path.stat().st_size}
 fonts={name:row for name,row in deps.items() if '/fonts/' in name};require(fonts,'No compiled font dependency found')
 for name,row in fonts.items():
  owner,relative=name.split(':',1)
  if relative.endswith('/fonts/telemetry.inc'):require((owner,relative) in [('generated','sdk/include/fonts/telemetry.inc'),('system-apps','Services/scene_host/fonts/telemetry.inc')] and row['sha256']==TELEMETRY_SHA,'Unexpected generated font')
  else:require(owner=='system-apps' and hashlib.sha256(subprocess.check_output(['git','-C',str(S),'show',SYSTEM_BASE+':'+relative])).hexdigest()==row['sha256'],'Font asset drift: '+relative)
 target=builder.build(cc,include,O,manifest,sources,defines=flags);builder.build(cc,include,O/'repeat',manifest,sources,defines=flags);require(sha(O/'driver.elf')==sha(O/'repeat/driver.elf'),'Scene target is not reproducible')
 (O/'debug').mkdir();shutil.copyfile(O/'driver.elf',O/'debug/driver.elf');compaction=compact(O/'driver.elf',cc,debug_path=O/'debug/driver.elf') if DEVICE=='watch' else None
 validator=O/'validate-elf';subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(S/'test/native_apps/stubs'),'-I'+str(S/'lib/elf_loader/include'),str(S/'lib/elf_loader/src/esp_elf_validate.c'),str(S/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True);subprocess.run([str(validator),str(O/'driver.elf')],check=True)
 for name,row in deps.items():
  owner,relative=name.split(':',1);require(sha(owners[owner]/relative)==row['sha256'],'Dependency changed while building')
 for path,pin in [(ROOT,revision),(S,a.system_commit),(R,RUNTIMES[DEVICE])]:clean(path,pin)
 record=dict(schema='lists.scene-continuity-host.component.v1',device=DEVICE,version=SCENE_VERSION,sha256=sha(O/'driver.elf'),bytes=(O/'driver.elf').stat().st_size,manifest_sha256=sha(O/'manifest.json'),compiler=compiler,compiler_path=cc,defines=flags,sources={k:git(v,'rev-parse','HEAD') for k,v in owners.items() if k!='generated'},source_roots={k:str(v) for k,v in owners.items()},product_recipe=revision,build_recipe_sha256=sha(__file__),target_dependencies=deps,staged_sdk_sha256=target['sdk_sha256'],font_dependencies=fonts,telemetry_font=telemetry_font,fonts_tree=fonts_tree,fonts_baseline_system=SYSTEM_BASE,all_compiled_font_bytes_preserved=True,presentation_profiles_unchanged=True,imports=target['imports'],exports=target['exports'],compaction=compaction,raw_elf_sha256=sha(O/'debug/driver.elf'),raw_elf_bytes=(O/'debug/driver.elf').stat().st_size,prior_version=prior_version,prior_elf_sha256=prior_sha,authority_unchanged=True,native_changed=False,hardware_verified=False)
 (O/'scene-build-record.json').write_text(json.dumps(record,indent=2)+'\n');print(DEVICE,'scene host',SCENE_VERSION,record['bytes'],record['sha256']);return record
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['system','runtime','watch-tools','baseline','output']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--system-commit',required=True);build(p.parse_args())

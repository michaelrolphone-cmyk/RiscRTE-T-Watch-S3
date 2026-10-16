#!/usr/bin/env python3
"""Reproduce exact selected scene-host bytes and prove the inherited font trees."""
import argparse,hashlib,io,json,shutil,subprocess,sys,tarfile,tempfile
from pathlib import Path
from build_lists_scene_host import SCENE_PRIOR,SCENE_FLAGS,stage_telemetry_font
from build_lists_shared_input import sha,git,require,load,RUNTIMES,clean
p=argparse.ArgumentParser(description=__doc__)
for n in ['baseline-system','watch-runtime','x4-runtime','watch-tools','output']:p.add_argument('--'+n,type=lambda v:Path(v).resolve(),required=True)
a=p.parse_args();S=a.baseline_system;require(git(S,'rev-parse','HEAD')=='7fb13b09b4dac275a8111b224784f8a472f39264' and not git(S,'status','--porcelain','--untracked-files=no'),'Wrong baseline System');clean(a.watch_runtime,RUNTIMES['watch']);clean(a.x4_runtime,RUNTIMES['x4'])
sys.path.insert(0,str(a.watch_tools/'scripts'));from compact_current_elf import compact
builder=load('scene_prior_builder',S/'scripts/scene_build.py');sdk=load('scene_prior_sdk',S/'scripts/scene_sdk.py');cc=builder.compiler_path();results={}
oldpin='e3fd26c2257cef91c8f6a7b98065b52f1db7a54d';font_tree=git(S,'rev-parse',oldpin+':Services/scene_host/fonts');require(font_tree==git(S,'rev-parse','HEAD:Services/scene_host/fonts'),'Historical font trees differ')
with tempfile.TemporaryDirectory(prefix='lists-scene-predecessor-') as tmp:
 tmp=Path(tmp);old=tmp/'system-e3fd';old.mkdir();blob=subprocess.check_output(['git','-C',str(S),'archive',oldpin,'Services/scene_host'])
 with tarfile.open(fileobj=io.BytesIO(blob)) as archive:archive.extractall(old,filter='data')
 for device,source,runtime,pin in [('watch',S,a.watch_runtime,git(S,'rev-parse','HEAD')),('x4',old,a.x4_runtime,oldpin)]:
  out=tmp/device;include=sdk.stage_sdk(runtime,S,out/'sdk');telemetry=stage_telemetry_font(S,include) if device=='x4' else None;manifest_name='manifest-watch-compact.json' if device=='watch' else 'manifest.json';manifest=json.loads((source/'Services/scene_host'/manifest_name).read_bytes());receipt=builder.build(cc,include,out/'host',manifest,[source/'Services/scene_host/host.c'],defines=SCENE_FLAGS[device]);elf=out/'host/driver.elf'
  row={'source_commit':pin,'runtime_commit':git(runtime,'rev-parse','HEAD'),'version':manifest['version'],'defines':receipt['defines'],'raw_elf_sha256':sha(elf),'raw_elf_bytes':elf.stat().st_size,'fonts_tree':font_tree};compact(elf,cc);row.update(compacted_elf_sha256=sha(elf),compacted_elf_bytes=elf.stat().st_size);results[device]=row
 require(results['watch']['compacted_elf_sha256']==SCENE_PRIOR['watch'][1],'Selected Watch scene host not reproduced')
 require(results['x4']['raw_elf_sha256']==SCENE_PRIOR['x4'][1],'Selected X4 scene host not reproduced')
report={'schema':'lists.scene-host-predecessor-identity.v1','passed':True,'targets':results,'watch_selected_exact_identity':True,'x4_selected_exact_identity':True,'historical_font_trees_identical':True,'source_difference':'System7fb scene host0.4.5 only raises the opt-in long-keyboard limit; X4 still selected scene host0.4.4 from Systeme3fd. All font files are identical. The continuity host must preserve both selected compile profiles and old unopted runtime behavior.','target_instructions_executed':False,'temporary_builds_removed':True}
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

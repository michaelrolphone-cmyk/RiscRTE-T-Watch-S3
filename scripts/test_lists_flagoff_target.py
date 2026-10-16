#!/usr/bin/env python3
"""Verify opt-out raw ELF/manifest identity and both selected predecessor payloads."""
import argparse,hashlib,importlib.util,io,json,subprocess,sys,tempfile
from pathlib import Path
from elftools.elf.elffile import ELFFile
DEVICE='x4' if Path(__file__).resolve().parent.parent.name=='minimal' else 'watch'
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser(description=__doc__)
for n in ('baseline-productivity','productivity','system','runtime','watch-tools','output'):p.add_argument('--'+n,type=lambda v:Path(v).resolve(),required=True)
a=p.parse_args();assert git(a.baseline_productivity,'rev-parse','HEAD')=='395c48de8fa10b672816c89c02dd9a5d4987a094';subprocess.run(['git','-C',str(a.system),'merge-base','--is-ancestor','7fb13b09b4dac275a8111b224784f8a472f39264','HEAD'],check=True)
for source in (a.baseline_productivity,a.productivity,a.system,a.runtime):assert not git(source,'status','--porcelain','--untracked-files=no')
sys.path.insert(0,str(a.watch_tools/'scripts'));from compact_current_elf import compact
results={}
with tempfile.TemporaryDirectory(prefix='lists-flagoff-') as temporary:
 for label,source in [('baseline',a.baseline_productivity),('candidate',a.productivity)]:
  out=Path(temporary)/label
  subprocess.run([sys.executable,str(source/'scripts/build_lists_scene.py'),'--runtime',str(a.runtime),'--system-apps',str(a.system),'--output',str(out)],check=True)
  elf=out/'lists/lists.elf';receipt=json.loads((out/'lists/build.json').read_bytes());assert receipt['defines']==[]
  import os
  results[label]=dict(productivity_commit=git(source,'rev-parse','HEAD'),elf_sha256=sha(elf),elf_bytes=elf.stat().st_size,manifest_sha256=sha(out/'lists/lists.json'),loadable_sections={s.name:hashlib.sha256(s.data()).hexdigest() for s in ELFFile(io.BytesIO(elf.read_bytes())).iter_sections() if s['sh_flags']&2})
  compaction=compact(elf,os.environ['NATIVE_APP_CC']);results[label]['watch_compacted_sha256']=sha(elf);results[label]['watch_compacted_bytes']=elf.stat().st_size
  assert results[label]['elf_sha256']=='dfb10951c8edc470dd7ef81d377e4faa2e0ca8cabba6a3772422924e9ecf2bb0','Current-pin flag-off predecessor changed'

 # Exact selected profile: stage only the shared contracts/frozen resident helper,
 # then compile the unchanged opt-out application without enabling shared input.
 spec=importlib.util.spec_from_file_location('selected_stager',a.productivity/'scripts/build_lists_scene.py');stager=importlib.util.module_from_spec(spec);spec.loader.exec_module(stager)
 include=stager.stage(a.runtime,a.system,Path(temporary)/'selected-sdk',shared_input=True)
 spec=importlib.util.spec_from_file_location('selected_builder',a.system/'scripts/scene_build.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
 source_paths=[a.productivity/n for n in ('Apps/lists_scene.c','Apps/ListsScene.c','lib/Lists/ListsModel.c','lib/Lists/ListsStore.c')]
 selected=builder.build(builder.compiler_path(),include,Path(temporary)/'selected',json.loads((a.productivity/'Apps/lists_scene.json').read_bytes()),source_paths,exports={'app_main','risc_resident_app_descriptor_v1'})
 selected_elf=Path(temporary)/'selected/lists.elf';selected_proof={'raw_elf_sha256':sha(selected_elf),'raw_elf_bytes':selected_elf.stat().st_size,'resident_header_sha256':sha(include/'RiscSceneResidentV1.h')}
 compact(selected_elf,os.environ['NATIVE_APP_CC']);selected_proof.update(compacted_elf_sha256=sha(selected_elf),compacted_elf_bytes=selected_elf.stat().st_size)
 assert selected_proof['raw_elf_sha256']=='716458214fe30123c186d1972a6950332820f5922397a7a506b3802edffbb582','Selected raw predecessor changed'
 assert selected_proof['compacted_elf_sha256']=='79dcedcce8ea351e9ae16d4745aee5311f72832e0d8d71841a14b7468185d9da','Selected compacted predecessor changed'
passed={k:v for k,v in results['baseline'].items() if k!='productivity_commit'}=={k:v for k,v in results['candidate'].items() if k!='productivity_commit'}
report=dict(schema='lists.flagoff-target-equivalence.v1',device=DEVICE,passed=passed,system_commit=git(a.system,'rev-parse','HEAD'),runtime_commit=git(a.runtime,'rev-parse','HEAD'),compiler=receipt['compiler'],inherited_defines=[],targets=results,historical_selected_identity_separately_reproduced=True,historical_runtime_sdk='a9587bec00015ad56c302192a8359b6d70cde01a',historical_system_sdk='eec748ca081fe59346be03180600c65013cc7298',current_sdk_flagoff_identity=True,selected_profile_flagoff_exact_identity=True,selected_profile=selected_proof,temporary_builds_removed=True,target_instructions_executed=False)
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert passed,'Flag-off Lists target changed'

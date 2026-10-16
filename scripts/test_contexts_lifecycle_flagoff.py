#!/usr/bin/env python3
"""Prove opt-out Contexts ELF identity at the exact frozen device build profile."""
import argparse,hashlib,importlib.util,io,json,shutil,subprocess,tempfile
from elftools.elf.elffile import ELFFile
from pathlib import Path
from build_contexts_input_lifecycle import SYSTEM,UTILITIES,SELECTION,RUNTIMES,PROFILE
DEVICE='x4' if Path(__file__).resolve().parent.parent.name=='minimal' else 'watch'
ROOT=Path(__file__).resolve().parents[2 if DEVICE=='x4' else 1]
DOCS=ROOT/('minimal/docs/contexts-input-lifecycle' if DEVICE=='x4' else 'docs/contexts-input-lifecycle')
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
p=argparse.ArgumentParser(description=__doc__)
for n in ('baseline-utilities','utilities','system','runtime','watch-profile','output'):p.add_argument('--'+n,type=lambda v:Path(v).resolve(),required=True)
a=p.parse_args();assert SELECTION['finalized'];assert git(a.utilities,'rev-parse','HEAD')==UTILITIES;assert git(a.runtime,'rev-parse','HEAD')==RUNTIMES[DEVICE];assert git(a.watch_profile,'rev-parse','HEAD')==PROFILE;assert git(a.baseline_utilities,'rev-parse','HEAD')=='4beb9778d300ec9f6b18448e1ec86317e063c98c';assert git(a.system,'rev-parse','HEAD')==SYSTEM
for source in (a.baseline_utilities,a.utilities,a.system,a.runtime,a.watch_profile):assert not git(source,'status','--porcelain','--untracked-files=no')
prior=json.loads((DOCS/'baseline.json').read_text());flags=prior['defines'] if DEVICE=='x4' else ['-include',str(a.watch_profile/'apps/clock/faces/ContextsFaces.h')]
builder=load('flagoff_scene_build',a.system/'scripts/scene_build.py');results={}
with tempfile.TemporaryDirectory(prefix='contexts-flagoff-') as temporary:
 for label,source in [('baseline',a.baseline_utilities),('candidate',a.utilities)]:
  out=Path(temporary)/label;out.mkdir();stage=load('flagoff_'+label,source/'scripts/build_contexts_scene.py');include=stage.stage(a.runtime,a.system,out/'sdk')
  catalog=out/'catalog.c';shutil.copyfile(DOCS/'catalog.c',catalog);manifest=json.loads((source/'Apps/contexts-scene.json').read_text());assert manifest['version']=='0.4.2'
  if DEVICE=='x4':
   next(r for r in manifest['requires'] if r['capability']=='alarm.service')['api']=2
   next(r for r in manifest['requires'] if r['capability']=='rtc.clock').update(capability='runtime.realtime',api=1)
  receipt=builder.build(builder.compiler_path(),include,out,manifest,[source/'Apps/contexts.c',catalog],defines=flags,exports={'app_main','risc_resident_app_descriptor_v1'})
  elf=(out/'contexts.elf').read_bytes();results[label]=dict(utilities_commit=git(source,'rev-parse','HEAD'),elf_sha256=hashlib.sha256(elf).hexdigest(),elf_bytes=len(elf),manifest_sha256=hashlib.sha256((out/'contexts.json').read_bytes()).hexdigest(),loadable_sections={section.name:hashlib.sha256(section.data()).hexdigest() for section in ELFFile(io.BytesIO(elf)).iter_sections() if section['sh_flags']&2})
 passed={k:v for k,v in results['baseline'].items() if k!='utilities_commit'}=={k:v for k,v in results['candidate'].items() if k!='utilities_commit'}
report=dict(schema='contexts.flagoff-target-equivalence.v1',device=DEVICE,passed=passed,system_commit=git(a.system,'rev-parse','HEAD'),runtime_commit=git(a.runtime,'rev-parse','HEAD'),watch_profile_commit=git(a.watch_profile,'rev-parse','HEAD'),compiler=receipt['compiler'],inherited_defines=flags,catalog_sha256=hashlib.sha256((DOCS/'catalog.c').read_bytes()).hexdigest(),targets=results,temporary_builds_removed=True,target_instructions_executed=False)
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert passed,'Flag-off Contexts target changed'

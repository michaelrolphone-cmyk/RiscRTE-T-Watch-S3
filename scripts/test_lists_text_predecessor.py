#!/usr/bin/env python3
"""Reproduce both selected historical text hosts without rebuilding any presenter."""
import argparse,hashlib,importlib.util,io,json,os,shlex,shutil,subprocess,sys,tarfile,tempfile
from pathlib import Path
from build_lists_text_host import HOST_PRIOR
from build_lists_shared_input import sha,git,require,load,RUNTIMES,clean
p=argparse.ArgumentParser(description=__doc__)
for n in ['baseline-system','watch-runtime','x4-runtime','watch-tools','output']:p.add_argument('--'+n,type=lambda v:Path(v).resolve(),required=True)
a=p.parse_args();S=a.baseline_system;require(git(S,'rev-parse','HEAD')=='7fb13b09b4dac275a8111b224784f8a472f39264' and not git(S,'status','--porcelain','--untracked-files=no'),'Wrong baseline System')
clean(a.watch_runtime,RUNTIMES['watch']);clean(a.x4_runtime,RUNTIMES['x4'])
sys.path.insert(0,str(a.watch_tools/'scripts'));from compact_current_elf import compact
builder=load('text_prior_builder',S/'scripts/scene_build.py');sdk=load('text_prior_sdk',S/'scripts/scene_sdk.py');cc=builder.compiler_path();results={}
with tempfile.TemporaryDirectory(prefix='lists-text-predecessor-') as tmp:
 tmp=Path(tmp);old=tmp/'system-e3fd';old.mkdir();oldpin='e3fd26c2257cef91c8f6a7b98065b52f1db7a54d'
 blob=subprocess.check_output(['git','-C',str(S),'archive',oldpin,'Services/text_input','sdk/app/RiscTextEntryV1.h'])
 with tarfile.open(fileobj=io.BytesIO(blob)) as archive:archive.extractall(old,filter='data')
 for label,source,runtime,source_pin in [('system-7fb-watch',S,a.watch_runtime,git(S,'rev-parse','HEAD')),('system-7fb-x4',S,a.x4_runtime,git(S,'rev-parse','HEAD')),('system-e3fd-x4',old,a.x4_runtime,oldpin)]:
  out=tmp/label;include=sdk.stage_sdk(runtime,S,out/'sdk');shutil.copyfile(source/'sdk/app/RiscTextEntryV1.h',include/'RiscTextEntryV1.h')
  for name in ['RiscUsbHidV1.h','RiscUsbControllerV1.h','RiscUsbProviderV1.h']:shutil.copyfile(source/'Services/text_input'/name,include/name)
  source_file=source/'Services/text_input/host.c';manifest=json.loads((source/'Services/text_input/manifest.json').read_bytes());receipt=builder.build(cc,include,out/'host',manifest,[source_file]);elf=out/'host/driver.elf'
  deps=subprocess.check_output([cc,'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM','-I'+str(include),str(source_file)],text=True);dependencies={}
  for token in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):
   path=Path(token);owner='historical-system' if path.is_relative_to(source) else 'staged-sdk';relative=path.relative_to(source) if owner=='historical-system' else path.relative_to(include)
   dependencies[owner+':'+relative.as_posix()]={'sha256':sha(path),'bytes':path.stat().st_size}
  r={'source_commit':source_pin,'runtime_commit':git(runtime,'rev-parse','HEAD'),'version':manifest['version'],'defines':receipt['defines'],'raw_elf_sha256':sha(elf),'raw_elf_bytes':elf.stat().st_size,'actual_dependencies':dependencies};compact(elf,cc);r.update(compacted_elf_sha256=sha(elf),compacted_elf_bytes=elf.stat().st_size);results[label]=r
 require(results['system-7fb-watch']['compacted_elf_sha256']==HOST_PRIOR['watch'][1],'Selected Watch host not reproduced')
 require(results['system-e3fd-x4']['raw_elf_sha256']==HOST_PRIOR['x4'][1],'Selected X4 host not reproduced')
 require(results['system-7fb-x4']['raw_elf_sha256']!=HOST_PRIOR['x4'][1],'Expected historical long-suffix source difference was not observed')
report={'schema':'lists.text-host-predecessor-identity.v1','passed':True,'targets':results,'watch_selected_exact_identity':True,'x4_selected_exact_identity':True,'watch_selected_source':'7fb13b09b4dac275a8111b224784f8a472f39264','x4_selected_source':oldpin,'source_difference':'System7fb text host0.1.6 adds an opt-in long-text request/result suffix and wider internal draft state; X4 still selected the preceding 0.1.5 host from Systeme3fd. This is source/API growth, not merely a manifest/version change. Base and extended prefix ABI methods remain supported by the new checkpoint host.','new_host_legacy_behavior_tests_required':True,'scene_host_fonts_native_rebuilt':False,'target_instructions_executed':False,'temporary_builds_removed':True}
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='targets'},indent=2))

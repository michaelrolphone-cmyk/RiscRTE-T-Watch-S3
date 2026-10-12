#!/usr/bin/env python3
"""Compare policy-disabled exact RF target profiles and selected RF 0.3.4 bytes."""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for n in ['build','baseline-system','baseline-utilities','tools','output']:p.add_argument('--'+n,type=lambda v:Path(v).resolve(),required=True)
a=p.parse_args();record=json.loads((a.build/'waterfall-build-record.json').read_text());roots=record['source_roots'];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
assert git(a.baseline_system,'rev-parse','HEAD')=='f4b30f8ebcc6d8cb905c8e90c91b1691acbe8165'
assert git(a.baseline_utilities,'rev-parse','HEAD')=='d068784cb5d581f1e81b5021f5d96d2917e03ec3'
for root in [a.baseline_system,a.baseline_utilities,Path(roots['system-apps']),Path(roots['utilities'])]:assert not git(root,'status','--porcelain','--untracked-files=no')
sys.path.insert(0,str(a.tools/'scripts'));from compact_current_elf import compact
spec=importlib.util.spec_from_file_location('rf_flagoff_normalizer',Path(roots['utilities'])/'scripts/normalize_xtensa_relocations.py');normalizer=importlib.util.module_from_spec(spec);spec.loader.exec_module(normalizer)
results={}
with tempfile.TemporaryDirectory(prefix='rf-policy-flagoff-') as tmp:
 for label in ['predecessor','candidate']:
  generated=Path(tmp)/label;generated.mkdir();system=a.baseline_system if label=='predecessor' else Path(roots['system-apps']);utilities=a.baseline_utilities if label=='predecessor' else Path(roots['utilities'])
  mappings=[(roots['system-apps'],str(system)),(roots['utilities'],str(utilities)),(roots['generated'],str(generated))]
  def mapped(v):
   for old,new in mappings:v=v.replace(old,new)
   return v
  for name in ['exports.map','catalog.c','empty_catalog.c','watch-alarm-profile.h','watch-rf-presentation.h']:
   source=a.build/name
   if source.exists():(generated/name).write_text(mapped(source.read_text()))
  if (a.build/'sdk').exists():
   shutil.copytree(a.build/'sdk',generated/'sdk')
   for source in (system/'lib/PortableApps/include').glob('*.h'):shutil.copyfile(source,generated/'sdk/include'/source.name)
   shutil.copytree(system/'lib/PortableApps/time',generated/'sdk/time',dirs_exist_ok=True)
  command=[mapped(v) for v in record['command'] if v!='-DPORTABLE_TEXT_INPUT_POLICY'];elf=generated/'waterfall.elf'
  subprocess.run(command,check=True);normalizer.normalize(elf);compact(elf,command[0],debug_path=generated/'waterfall-debug.elf')
  results[label]=dict(sha256=sha(elf),bytes=elf.stat().st_size)
 report=dict(schema='rf.modal-policy.flagoff-target.v1',device=record['device'],passed=results['predecessor']==results['candidate'],targets=results,selected_rf_034_sha256=record['predecessor_elf_sha256'],selected_rf_034_byte_equal=results['candidate']['sha256']==record['predecessor_elf_sha256'],source=record['sources'],baseline_system=git(a.baseline_system,'rev-parse','HEAD'),baseline_utilities=git(a.baseline_utilities,'rev-parse','HEAD'),only_removed_flag='-DPORTABLE_TEXT_INPUT_POLICY',hardware_verified=False,target_instructions_executed=False)
 a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['passed'] and report['selected_rf_034_byte_equal'],'Policy-disabled target differs from predecessor or selected RF 0.3.4'

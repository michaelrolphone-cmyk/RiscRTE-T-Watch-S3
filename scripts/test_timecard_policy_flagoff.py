#!/usr/bin/env python3
"""Compare exact selected-profile target ELF bytes with the modal policy flag off."""
import argparse,hashlib,importlib.util,json,subprocess,sys,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for n in ['build','baseline-system','baseline-productivity','tools','output']:p.add_argument('--'+n,type=lambda v:Path(v).resolve(),required=True)
a=p.parse_args();record=json.loads((a.build/'timecard-build-record.json').read_text());roots=record['source_roots'];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
assert git(a.baseline_system,'rev-parse','HEAD')=='f4b30f8ebcc6d8cb905c8e90c91b1691acbe8165'
assert git(a.baseline_productivity,'rev-parse','HEAD')=='f83d79a0753c2a451730000d2f553aa21fda7830'
for root in [a.baseline_system,a.baseline_productivity,Path(roots['system-apps']),Path(roots['productivity'])]:assert not git(root,'status','--porcelain','--untracked-files=no')
sys.path.insert(0,str(a.tools/'scripts'));from compact_current_elf import compact
spec=importlib.util.spec_from_file_location('flagoff_normalizer',Path(roots['utilities'])/'scripts/normalize_xtensa_relocations.py');normalizer=importlib.util.module_from_spec(spec);spec.loader.exec_module(normalizer)
results={}
with tempfile.TemporaryDirectory(prefix='timecard-policy-flagoff-') as tmp:
 for label in ['predecessor','candidate']:
  command=[v for v in record['command'] if v!='-DPORTABLE_TEXT_INPUT_POLICY'];elf=Path(tmp)/(label+'.elf');command[command.index('-o')+1]=str(elf)
  if label=='predecessor':command=[v.replace(roots['system-apps'],str(a.baseline_system)).replace(roots['productivity'],str(a.baseline_productivity)) for v in command]
  subprocess.run(command,check=True);normalizer.normalize(elf);compact(elf,command[0],debug_path=Path(tmp)/(label+'-debug.elf'))
  results[label]=dict(sha256=sha(elf),bytes=elf.stat().st_size)
 report=dict(schema='timecard.modal-policy.flagoff-target.v1',device=record['device'],passed=results['predecessor']==results['candidate'],targets=results,source=record['sources'],baseline_system=git(a.baseline_system,'rev-parse','HEAD'),baseline_productivity=git(a.baseline_productivity,'rev-parse','HEAD'),only_removed_flag='-DPORTABLE_TEXT_INPUT_POLICY',hardware_verified=False,target_instructions_executed=False)
 a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['passed'],'Policy-disabled target differs'

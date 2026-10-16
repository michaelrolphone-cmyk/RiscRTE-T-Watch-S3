#!/usr/bin/env python3
"""Replay the exact selected target with policy disabled and require byte equality."""
import argparse
import json
import io
import re
import shutil
from elftools.elf.elffile import ELFFile
from compact_current_elf import compact
from pathlib import Path
import tempfile
from build_files_policy import build, require, sha, PINNED, PREDECESSORS

def parity(selected, candidate, compiler, temporary):
 raw_equal = selected.read_bytes() == candidate.read_bytes()
 a,b = [ELFFile(io.BytesIO(path.read_bytes())) for path in (selected,candidate)]
 sections_a = {section.name:section for section in a.iter_sections()}
 sections_b = {section.name:section for section in b.iter_sections()}
 require(set(sections_a)==set(sections_b), 'Flag-off section inventory changed')
 changed = [name for name in sections_a if sections_a[name].data()!=sections_b[name].data()]
 require(set(changed)<={'.strtab'}, 'Flag-off runtime or other section bytes changed')
 renames=[]
 if changed:
  old=sections_a['.strtab'].data().split(b'\0')
  new=sections_b['.strtab'].data().split(b'\0')
  require(len(old)==len(new), 'Flag-off static name table count changed')
  allowed={'digits','buffer','phase','direct','hex','hit_q8','hit_origin'}
  for left,right in zip(old,new):
   if left==right:continue
   lm=re.fullmatch(rb'([a-z0-9_]+)\$[0-9]+',left)
   rm=re.fullmatch(rb'([a-z0-9_]+)\$[0-9]+',right)
   require(lm and rm and lm[1]==rm[1] and lm[1].decode() in allowed,'Unexpected static name change')
   rows=[symbol for symbol in sections_a['.symtab'].iter_symbols() if symbol.name==left.decode()]
   require(rows and all(symbol['st_info']['bind']=='STB_LOCAL' for symbol in rows),'Renamed non-local symbol')
   renames.append({'before':left.decode(),'after':right.decode()})
 compacted={}
 for label,source in [('selected',selected),('flagoff',candidate)]:
  path=temporary/(label+'-compacted.elf');shutil.copyfile(source,path)
  proof=compact(path,compiler,debug_path=temporary/(label+'-uncompacted.elf'))
  compacted[label]={'sha256':sha(path),'bytes':path.stat().st_size,'preservation':proof}
 require(compacted['selected']['sha256']==compacted['flagoff']['sha256'],'Flag-off loader metadata parity failed')
 return {'raw_byte_equal':raw_equal,'changed_sections':changed,'local_compiler_symbol_renames':renames,
         'all_other_section_bytes_identical':True,'loader_metadata_compacted_equal':True,'compaction':compacted}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--build',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 selected=json.loads((a.build/'file_browser-build-record.json').read_text())
 require(selected['modal_policy'],'Expected policy-on selected build')
 require(sha(a.build/'file_browser.elf')==selected['sha256'],'Policy target custody differs')
 system=Path(selected['source_roots']['system-apps'])
 for path,row in selected['target_dependencies'].items():
  require(sha(path)==row['sha256'],'Selected input changed before flag-off check: '+path)
 with tempfile.TemporaryDirectory(prefix='files-policy-flagoff-') as temporary:
  off=build(argparse.Namespace(device=selected['device'],system=system,
       system_commit=selected['sources']['system-apps'],output=Path(temporary)/'target',
       provisional=selected['source_publication']=='local-provisional',flag_off=True))
  comparison=parity(PREDECESSORS/(selected['device']+'-files')/'file_browser.elf', Path(temporary)/'target/file_browser.elf', off['command'][0], Path(temporary))
  require(selected['device'] != 'watch' or comparison['raw_byte_equal'], 'Watch flag-off target must equal selected raw bytes')
  report=dict(schema='files.modal-policy.flagoff-target.v1',device=selected['device'],
       passed=comparison['loader_metadata_compacted_equal'],comparison=comparison,selected_predecessor_sha256=PINNED[selected['device']]['elf'],
       candidate_flagoff_sha256=off['sha256'],candidate_flagoff_bytes=off['bytes'],
       source=selected['sources']['system-apps'],source_publication=selected['source_publication'],
       only_removed_flag='-DPORTABLE_TEXT_INPUT_POLICY',linker_attempts=off['linker_attempts'],
       target_instructions_executed=False,hardware_verified=False)
  a.output.parent.mkdir(parents=True,exist_ok=True)
  shutil.copyfile(Path(temporary)/'target/file_browser.elf',a.output.with_suffix('.elf'))
  report['flagoff_artifact']={'path':str(a.output.with_suffix('.elf')),'sha256':off['sha256'],'bytes':off['bytes']}
  a.output.write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report,indent=2))
  require(report['passed'],'Policy-disabled target differs from selected Files 1.5.34')
if __name__=='__main__': main()

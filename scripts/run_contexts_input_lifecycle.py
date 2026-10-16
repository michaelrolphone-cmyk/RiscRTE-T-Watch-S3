#!/usr/bin/env python3
"""Reproduce Contexts lifecycle component, exact overlay and full qualification."""
import argparse,os,subprocess,sys
from pathlib import Path
from build_contexts_input_lifecycle import DEVICE,SELECTION,UTILITIES,require

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('baseline','baseline-handoff','baseline-utilities','utilities','system','runtime','watch-profile','watch-tools','output'):p.add_argument('--'+n,type=lambda v:Path(v).resolve(),required=True)
 p.add_argument('--native-candidate',type=lambda v:Path(v).resolve())
 a=p.parse_args();require(SELECTION['finalized'],'Final published qualified baseline is not selected');require(not a.output.exists(),'Use fresh output directory')
 require(DEVICE!='watch' or a.native_candidate is not None,'Watch needs its frozen native candidate')
 scripts=Path(__file__).resolve().parent
 def call(name,options,extra=(),sanitize=None):
  command=[sys.executable,str(scripts/name)]
  for key,value in options.items():command+=['--'+key,str(value)]
  environment=dict(os.environ)
  if sanitize is not None:environment['SANITIZE']=str(sanitize)
  subprocess.run(command+list(extra),env=environment,check=True)
 a.output.mkdir(parents=True)
 call('build_contexts_input_lifecycle.py',{'baseline':a.baseline,'utilities':a.utilities,'utilities-commit':UTILITIES,'system':a.system,'runtime':a.runtime,'watch-profile':a.watch_profile,'watch-tools':a.watch_tools,'output':a.output/'contexts'})
 common={'baseline':a.baseline,'baseline-handoff':a.baseline_handoff,'contexts-build':a.output/'contexts','runtime':a.runtime,'output':a.output/'candidate'}
 if DEVICE=='watch':
  common.update({'native-candidate':a.native_candidate,'system':a.system})
  call('assemble_watch_contexts_input_lifecycle.py',common,sanitize=0)
  call('assemble_watch_contexts_input_lifecycle.py',common,extra=['--verify-only'],sanitize=1)
  require((a.output/'candidate/receipts/final-normal.json').read_bytes()==(a.output/'candidate/receipts/final-sanitized.json').read_bytes(),'Admission modes differ')
 else:
  common['tools']=a.watch_tools;call('compose_contexts_input_lifecycle.py',common)
  call('qualify_contexts_input_lifecycle.py',{'runtime':a.runtime,'tools':a.watch_tools,'delivery':a.output/'candidate','output':a.output/'qualification'})
 call('inspect_contexts_lifecycle_stack.py',{'build':a.output/'contexts','output':a.output/'target-stack.json'})
 call('test_contexts_lifecycle_flagoff.py',{'baseline-utilities':a.baseline_utilities,'utilities':a.utilities,'system':a.system,'runtime':a.runtime,'watch-profile':a.watch_profile,'output':a.output/'flagoff-target.json'})
if __name__=='__main__':main()

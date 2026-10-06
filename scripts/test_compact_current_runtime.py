#!/usr/bin/env python3
"""Execute the actual Runtime lifecycle suite with original and compacted ELFs."""
import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
from compact_current_elf import compact,sha

def run(args):
 r=subprocess.run(list(map(str,args)),check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 return r.stdout

def verify(runtime,output):
 runtime=Path(runtime).resolve();cc=shutil.which('gcc');cxx=shutil.which('g++')
 if not cc or not cxx:raise ValueError('GCC/G++ host compilers required')
 with tempfile.TemporaryDirectory(prefix='current-runtime-compaction-') as temporary:
  build=Path(temporary);original=build/'original';after=build/'compacted';debug=build/'debug'
  for p in (original,after,debug):p.mkdir()
  include=['-I'+str(runtime/p) for p in ('src','sdk/app','sdk/driver','sdk/hardware','lib/ArduinoJson/src','test/drivers/stubs')]
  flags=['-std=c11','-g','-Wall','-Wextra','-Werror','-fPIC','-fvisibility=hidden','-shared',*include]
  fixtures=[('default','test/fixtures/default.c',[]),('child','test/fixtures/child.c',[]),
    ('probe','test/fixtures/provider.c',[]),('heartbeat','apps/heartbeat/main.c',[]),
    ('cap-app','test/fixtures/capability_app.c',[]),('cap-child','test/fixtures/capability_app.c',['-DCHILD_WITHOUT_POLICY']),
    ('yield','test/fixtures/yield_app.c',[]),('yield-probe','test/fixtures/provider.c',['-DYIELD_PROVIDER'])]
  proofs={}
  for name,source,defines in fixtures:
   before=original/(name+'.elf');target=after/before.name
   run([cc,*flags,*defines,runtime/source,'-o',before]);shutil.copyfile(before,target)
   proofs[name]=compact(target,cc,debug_path=debug/before.name)
   if (debug/before.name).read_bytes()!=before.read_bytes():raise ValueError('Original fixture sidecar changed')
  sources=['src/bootstrap/Json.cpp','src/bootstrap/Board.cpp','src/bootstrap/Runtime.cpp',
    'src/runtime/drivers/ProviderGraphV2.cpp','src/runtime/drivers/ProviderModuleV2.cpp','test/runtime_test.cpp']
  executable=build/'runtime-test'
  run([cxx,'-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-rdynamic',*include,
       *[runtime/p for p in sources],'-ldl','-o',executable])
  first=run([executable,original]);second=run([executable,after])
  if first!=second:raise ValueError('Runtime lifecycle output differs after ELF compaction')
  source=run(['git','-C',runtime,'rev-parse','HEAD']).strip()
  record={'schema':1,'runtime_source':source,'architecture':'native host ELF execution through actual Runtime and ProviderGraph',
    'original_and_compacted_outputs_identical':True,'runtime_output':first,'runtime_output_sha256':sha(first.encode()),'fixtures':proofs}
  if output:Path(output).write_text(json.dumps(record,indent=2)+'\n')
  print('Original/compacted ELF Runtime execution identical: 8 modules, lifecycle, grants, retention, imports/exports and scheduler checks passed')
  return record

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--runtime',required=True,type=Path);p.add_argument('--output',type=Path)
 a=p.parse_args();verify(a.runtime,a.output)

#!/usr/bin/env python3
"""Exercise the actual current catalog against the pinned production adapter."""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path
from current_apps_overlay import ROOT,config,verify,require
p=argparse.ArgumentParser();p.add_argument('--system-apps',type=Path,required=True);p.add_argument('--current-apps-artifact-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();_,record=verify(a.current_apps_artifact_dir,head);cfg=config();system=a.system_apps.resolve()
require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=system,text=True).strip()==cfg['sources']['system-apps']['commit'],'Wrong System adapter source')
require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=system,text=True).strip(),'Dirty adapter source')
require('-DPORTABLE_CATALOG_LIMIT=18' in record['apps']['springboard']['defines'],'Final launcher lacks explicit18-entry profile')
catalog=a.current_apps_artifact_dir/'catalog.c'
expected='#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={'+','.join('{'+','.join('.'+k+'='+json.dumps(v) for k,v in sorted(x.items()))+',.compatible=true}' for x in record['catalog'])+'};\nconst unsigned portable_catalog_count='+str(len(record['catalog']))+';\n'
require(catalog.read_text()==expected,'Generated catalog differs from verified build record')
results=[]
with tempfile.TemporaryDirectory(prefix='watch-catalog-') as d:
 for sanitize in [False,True]:
  exe=Path(d)/('catalog-san' if sanitize else 'catalog');flags=['-fsanitize=address,undefined','-fno-sanitize-recover=all'] if sanitize else []
  subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-O1','-no-pie',*flags,'-DPORTABLE_CATALOG_LIMIT=18',*['-I'+str(system/p) for p in ('test/native_apps','lib/PortableApps/include','lib/NativeApps/include')],str(ROOT/'tests/sdr_upgrade/launcher_catalog.c'),str(catalog),str(system/'lib/PortableApps/src/adapter.c'),'-o',str(exe)],check=True)
  result=subprocess.run([str(exe)],check=True,capture_output=True,text=True);results.append({'sanitized':sanitize,'output':result.stdout.strip()})
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps({'schema':1,'watch_source':head,'system_source':cfg['sources']['system-apps']['commit'],'catalog_sha256':hashlib.sha256(catalog.read_bytes()).hexdigest(),'entries':len(record['catalog']),'tests':results},indent=2)+'\n');print(results[-1]['output'])

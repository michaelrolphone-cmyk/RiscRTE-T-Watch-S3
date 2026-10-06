#!/usr/bin/env python3
"""Read the actual final store, then run current paired Clock through Runtime.

Only architecture is substituted in a separate host copy. The input image and
all JSON policies/manifests remain unchanged; target instructions are not run.
"""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
from current_apps_overlay import ROOT,verify,config,metadata,require
from read_only_spiffs import read_image
from check_runtime_store_admission import admit_many,admit_cohort
from update_test_production_store_runtime import execute_many

def main():
 p=argparse.ArgumentParser()
 for n in ('runtime','system-apps','utilities','productivity','current-apps-artifact-dir','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--native-elf',type=Path)
 g=p.add_mutually_exclusive_group(required=True);g.add_argument('--bin',type=Path);g.add_argument('--image',type=Path)
 a=p.parse_args();head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip();files,record=verify(a.current_apps_artifact_dir,head)
 deployment=json.loads((ROOT/'apps/current-runtime-requirements.json').read_text())['deployment']
 from current_flash_layout import validate
 app_data=deployment['store_abi']==2;validate(deployment,app_data)
 offset=deployment['partitions']['bootfs0']['offset'];size=deployment['partitions']['bootfs0']['size']
 path=a.bin or a.image;raw=path.read_bytes();require(len(raw)==(16777216 if a.bin else size),'Wrong actual image size')
 content=read_image(raw[offset:offset+size] if a.bin else raw,size)
 for name,b in files.items():require(content.get(name)==b,'Actual store differs from current payload: '+name)
 require(json.loads(content['boot.json'])==record['boot'],'Actual store current policies differ')
 cfg=config()
 for name,repo in [('runtime',a.runtime),('system-apps',a.system_apps),('utilities',a.utilities),('productivity',a.productivity)]:
  require(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==cfg['sources'][name]['commit'],'Wrong execution source: '+name)
 a.output.mkdir(parents=True,exist_ok=True)
 admitted=admit_many(a.runtime,[(path.name,content)],app_data=app_data)
 cohort=None
 if 'cohort.json' in content:
  require(a.native_elf is not None,'Cohort validation requires the exact native ELF')
  cohort=admit_cohort(a.runtime,a.native_elf.read_bytes(),content,content)
 executed=execute_many(a.runtime,a.system_apps,a.utilities,a.productivity,[(path.name,content)],output=a.output/'execution',current_profile=True,app_data=app_data)
 evidence={'schema':1,'watch_source':head,'configuration':cfg,'input':{'file':path.name,**metadata(raw)},'current_artifact_sha256':hashlib.sha256((a.current_apps_artifact_dir/'current-apps.zip').read_bytes()).hexdigest(),'store_files':len(content),'admission':admitted,'cohort_admission':cohort,'execution':executed,'policy_substitutions':0,'physical_verification':'pending'}
 (a.output/'current-runtime-provenance.json').write_text(json.dumps(evidence,indent=2)+'\n')
 print('Exact current final store: Runtime admission and six paired Clock startup/lifecycle scenarios passed')
if __name__=='__main__':main()

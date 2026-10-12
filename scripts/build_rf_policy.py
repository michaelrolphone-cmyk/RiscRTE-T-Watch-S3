#!/usr/bin/env python3
"""Rebuild only RF 0.3.5 from the exact selected 0.3.4 target profile.

Every inherited command option, model/storage contract and original font is
retained. PORTABLE_TEXT_INPUT_POLICY is the sole feature addition. No native or
unrelated app rebuild, full-image materialization or hardware operation occurs.
"""
import argparse,hashlib,importlib.util,json,os,shlex,shutil,subprocess,sys
from pathlib import Path
VERSION='0.3.5'
DEVICE='x4' if Path(__file__).resolve().parent.parent.name=='minimal' else 'watch'
ROOT=Path(__file__).resolve().parents[2 if DEVICE=='x4' else 1]
SELECTION=json.loads((ROOT/('minimal/docs/rf-input-policy/selection.json' if DEVICE=='x4' else 'docs/rf-input-policy/selection.json')).read_text())
SYSTEM='fd4b1e52fe2a49c3c4c22f9ccd4c98a91f88afa0'
PROFILE='089868395268b696c05651c33816345bfe0425df'
RUNTIMES={'watch':'64c8e52e46fd91e8fdafd636db04eed88f0c51a9','x4':'1c1ed8661ea30d47e7e9707c41d492ce3a2b4d70'}
PRIOR={'watch':'c0612e63664bfcb25f2bb3ea79286e97b36c6f62eb95a4ddb1c719868890bd05','x4':'305be3c20fc1f657bc060fc45193a2415ca3a1e38c4de6c4b6da95f3ec9faf08'}
COMMON=['-DPORTABLE_TEXT_INPUT_POLICY']
MODELS=['rf_background.h','rf_dsp.h','rf_identity.h','rf_math.h','rf_neural.h','rf_neural_store.h','rf_presentation.h','rf_signature_store.h','rf_signatures.h','rf_store.h','rf_temporal.h','rf_temporal_files.h','rf_temporal_store.h']
EXPORTS={'app_main','app_module_init','app_module_fini'}
ALLOWED={'risc_runtime_get_api','memcpy','memset','memcmp','memmove','strcmp','strncmp','strlen','snprintf','malloc','calloc','free','strcpy','memchr','strrchr'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(p,*args):return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()
def require(ok,reason):
 if not ok:raise ValueError(reason)
def clean(p,pin):require(git(p,'rev-parse','HEAD')==pin and not git(p,'status','--porcelain','--untracked-files=no'),'Wrong or dirty source: '+str(p))
def add_unique(old,extra):return old+[v for v in extra if v not in old]

def build(a):
 S,U,R,W,O,P,B=[getattr(a,n).resolve() for n in ('system','utilities','runtime','watch_profile','output','predecessor_record','selected_baseline')]
 require(SELECTION['finalized'] and a.utilities_commit==SELECTION['sources']['utilities'],'RF source selection is not finalized')
 owners={'system-apps':S,'utilities':U,'runtime':R,'watch':W,'generated':O}
 pins={'system-apps':SYSTEM,'utilities':a.utilities_commit,'runtime':RUNTIMES[a.device],'watch':PROFILE}
 for owner,pin in pins.items():clean(owners[owner],pin)
 recipe=git(ROOT,'rev-parse','HEAD');clean(ROOT,recipe)
 require(not O.exists(),'Use fresh output directory')
 require(sha(P)==SELECTION['baseline']['rf_predecessor_record_sha256'],'Wrong RF predecessor receipt')
 prior=json.loads(P.read_text());require(prior['version']=='0.3.4' and prior['device']==a.device and prior['sha256']==PRIOR[a.device],'Wrong RF predecessor')
 require(sha(P.parent/'waterfall.elf')==prior['sha256'] and sha(P.parent/'waterfall.json')==prior['manifest_sha256'],'Changed RF predecessor artifacts')
 manifest=json.loads((P.parent/'waterfall.json').read_text());require(manifest['version']=='0.3.4' and manifest['requires'].count({'capability':'ui.text-input','api':1})==1,'Wrong RF inherited authority')
 sys.path.insert(0,str(a.watch_tools.resolve()/'scripts'))
 from compact_current_elf import compact
 if a.device=='watch':
  from current_bootfs import read_image
  selected=read_image((B/'components/bootfs.bin').read_bytes(),0x510000);current=selected['waterfall.elf'];current_manifest=selected['waterfall.json']
 else:
  boot=json.loads((B/'store/boot.json').read_text());row=next(r for r in boot['app_capabilities'] if r['manifest']=='waterfall.json');current=(B/'SD'/row['image_source']['path']).read_bytes();current_manifest=(B/'store/waterfall.json').read_bytes()
 require(hashlib.sha256(current).hexdigest()==PRIOR[a.device] and json.loads(current_manifest)==manifest,'Wrong RF in complete selected union')
 manifest['version']=VERSION
 require(sha(U/'Apps/rf_app_data_scope.h')==prior['startup_storage_fix_sha256']=='5b21f23b2505f12ef38ed1fc0e90b3c665066f639f2ccd8ca90e3b8073f69010','RF operation-scoped storage contract changed')
 models={n:sha(U/'Apps'/n) for n in MODELS};require(models==prior['rf_models'],'RF model/storage format changed')
 O.mkdir(parents=True);(O/'debug').mkdir()
 oldroots=prior['source_roots']
 def mapped(value):
  for owner,path in oldroots.items():value=value.replace(path,str(owners[owner]))
  return value
 generated_provenance={}
 for name,row in prior['target_dependencies'].items():
  owner,relative=name.split(':',1)
  if owner=='generated':
   src=P.parent/relative;require(sha(src)==row['sha256'],'Changed predecessor generated input: '+relative)
   dest=O/relative;dest.parent.mkdir(parents=True,exist_ok=True);raw=src.read_bytes();data=mapped(raw.decode()).encode();dest.write_bytes(data)
   generated_provenance[relative]={'baseline_sha256':row['sha256'],'selected_sha256':sha(dest),'operation':'source-root relocation'}
  if owner=='watch' or (owner=='system-apps' and any(t in relative for t in ['/fonts/','/paper_fonts/','/settings_fonts/'])):
   require(sha(owners[owner]/relative)==row['sha256'],'Original Watch source or font changed: '+name)
 if a.device=='x4':
  # PortableApps headers in the generated compatibility SDK must resolve to
  # exact current System inputs, including the opt-in policy bridge.
  for source in sorted((S/'lib/PortableApps/include').glob('*.h')):
   dest=O/'sdk/include'/source.name;shutil.copyfile(source,dest)
   generated_provenance['sdk/include/'+source.name]={'selected_sha256':sha(dest),'source':'system-apps:lib/PortableApps/include/'+source.name,'operation':'exact current System header'}
  shutil.copytree(S/'lib/PortableApps/time',O/'sdk/time')
 flags=add_unique([mapped(v) for v in prior['defines']],COMMON)
 require([v for v in flags if v not in [mapped(x) for x in prior['defines']]]==COMMON,'Unexpected feature addition')
 command=[mapped(v) for v in prior['command']];cc=os.environ.get('NATIVE_APP_CC') or command[0];command[0]=cc
 require(all(flag in command for flag in flags[:-1]),'Inherited target options lost')
 command[command.index('-o'):command.index('-o')]=COMMON
 compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];require('8.4.0' in compiler and '2021r2-patch5' in compiler,'Wrong compiler')
 exports=EXPORTS|({'risc_resident_app_descriptor_v1'} if a.device=='x4' else set())
 (O/'exports.map').write_text('{global:'+';'.join(sorted(exports))+';local:*;};\n')
 sources=[Path(v) for v in command if v.endswith('.c')];includes=[v for v in command if v.startswith('-I')]
 deps={}
 for source in sources:
  text=subprocess.check_output([cc,'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM',*flags,*includes,str(source)],text=True)
  for token in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
   path=Path(token).resolve();require(path.is_file() and not {'test','tests','fixtures'}&set(path.parts),'Invalid target source: '+token)
   matches=[(k,path.relative_to(v)) for k,v in owners.items() if path.is_relative_to(v)];require(matches,'Unowned source: '+str(path));owner,relative=matches[-1]
   deps[owner+':'+relative.as_posix()]={'sha256':sha(path),'bytes':path.stat().st_size}
 require(any(n.endswith('PortableTextInputClient.h') for n in deps) and any(n.endswith('PortableTextInputPolicy.h') for n in deps),'Modal policy bridge missing')
 require(not any('text-faces-' in n for n in deps),'Font subset selected')
 subprocess.run(command,check=True);elf=O/'waterfall.elf'
 normalizer=U/'scripts/normalize_xtensa_relocations.py';require(sha(normalizer)=='f71d9ca3b267166bc69d0e4853463774a8dde5384924132e1aca0e0c2f3a965f','Relocation normalizer changed')
 spec=importlib.util.spec_from_file_location('rf_policy_normalizer',normalizer);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 shutil.copyfile(elf,O/'debug/waterfall-linker.elf');normalization=mod.normalize(elf)
 validator=O/'validate-elf';subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(S/'test/native_apps/stubs'),'-I'+str(S/'lib/elf_loader/include'),str(S/'lib/elf_loader/src/esp_elf_validate.c'),str(S/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True)
 subprocess.run([str(validator),str(elf)],check=True);compaction=compact(elf,cc,debug_path=O/'debug/waterfall.elf');subprocess.run([str(validator),str(elf)],check=True)
 symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True);imports={l.split()[-1] for l in symbols.splitlines() if ' U ' in ' '+l};actual={l.split()[-1] for l in symbols.splitlines() if len(l.split())>=3 and l.split()[-2] in ('T','D','B','R')}
 require(imports<=ALLOWED and actual==exports,'Unexpected RF ABI');require(b'ui.text-input\0' in elf.read_bytes(),'Shared service missing')
 budget=249392 if a.device=='watch' else 290000;require(elf.stat().st_size<=budget,'RF component budget exceeded')
 for name,row in deps.items():
  owner,relative=name.split(':',1);require(sha(owners[owner]/relative)==row['sha256'],'Source changed during build')
 for owner,pin in pins.items():clean(owners[owner],pin)
 clean(ROOT,recipe);(O/'waterfall.json').write_text(json.dumps(manifest,indent=2)+'\n')
 record=dict(schema='rf.modal-policy.component.v1',device=a.device,version=VERSION,sha256=sha(elf),bytes=elf.stat().st_size,manifest_sha256=sha(O/'waterfall.json'),compiler=compiler,command=command,defines=flags,inherited_defines=[mapped(v) for v in prior['defines']],feature_additions=COMMON,sources=pins,source_roots={k:str(v) for k,v in owners.items()},product_recipe=recipe,build_recipe_sha256=sha(__file__),target_dependencies=deps,generated_provenance=generated_provenance,original_fonts_retained=True,baseline_features_preserved=True,rf_models=models,startup_storage_fix_sha256=sha(U/'Apps/rf_app_data_scope.h'),predecessor_receipt_sha256=sha(P),predecessor_elf_sha256=PRIOR[a.device],imports=sorted(imports),exports=sorted(exports),compaction=compaction,relocation_normalization=normalization,component_budget_bytes=budget,shared_text_input=True,modal_policy=True,native_changed=False,hardware_verified=False,canonical_paper_contract_selected=(a.device=='watch'))
 (O/'waterfall-build-record.json').write_text(json.dumps(record,indent=2)+'\n');print(a.device,'RF',VERSION,record['bytes'],record['sha256']);return record

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',choices=[DEVICE],required=True)
 for n in ('system','utilities','runtime','watch-profile','watch-tools','selected-baseline','predecessor-record','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--utilities-commit',required=True);build(p.parse_args())
if __name__=='__main__':main()

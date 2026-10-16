#!/usr/bin/env python3
"""Build a narrowly checked source-Open overlay for the complete Watch store.
The final integrator must bind the new native firmware into cohort.json and
run full Runtime admission. This command deliberately emits no flash image.
"""
import argparse,copy,hashlib,json,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='e0b43ef70f312cc512861926109ebe99f41c964d'
REQUIREMENT={'capability':'file.open.source','api':1}
GRANT=dict(REQUIREMENT,instance_id=0)
CHANGED={'boot.json','file_browser.json','file_browser.elf','model_viewer.json','model_viewer.elf'}
FLAGS=['-DRISC_NATIVE_FILE_SOURCE=1','-DRISC_NATIVE_APP_DATA_MOUNT=1']+['-Wl,--wrap='+n for n in ['esp_vfs_register', 'esp_vfs_unregister', 'esp_partition_read', 'esp_partition_write', 'esp_partition_erase_range', 'esp_littlefs_format', 'esp_littlefs_format_partition']]+['-Wl,-u,risc_file_source_abi','-Wl,-u,__wrap_esp_littlefs_format','-Wl,-u,__wrap_esp_littlefs_format_partition']
def require(ok,message):
 if not ok:raise ValueError(message)
def encoded(x):return (json.dumps(x,indent=2,sort_keys=True)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def changed_store(old,files_elf,files_manifest,viewer_elf,viewer_manifest):
 boot=json.loads(old['boot.json']);before=copy.deepcopy(boot)
 for app,version,manifest in [('file_browser','1.5.33',files_manifest),('model_viewer','1.3.1',viewer_manifest)]:
  expected=json.loads(old[app+'.json']);require(REQUIREMENT not in expected['requires'],'Source capability already present')
  expected['version']=version;expected['requires'].append(REQUIREMENT)
  require(json.loads(manifest)==expected,'App changed beyond version/source capability: '+app)
  rows=[r for r in boot['app_capabilities'] if r['manifest']==app+'.json'];require(len(rows)==1,'Missing or duplicate app policy: '+app)
  require(GRANT not in rows[0]['grants'],'Source grant already present');rows[0]['grants'].append(GRANT)
 require(boot['drivers']==before['drivers'],'Provider graph changed')
 new=dict(old);new.update({'boot.json':encoded(boot),'file_browser.elf':files_elf,'file_browser.json':files_manifest,'model_viewer.elf':viewer_elf,'model_viewer.json':viewer_manifest})
 require(set(new)==set(old) and {n for n in old if old[n]!=new[n]}==CHANGED,'Unexpected store changes')
 return new

def build(args):
 old={p.relative_to(args.baseline_store).as_posix():p.read_bytes() for p in args.baseline_store.rglob('*') if p.is_file()}
 cohort=json.loads(old['cohort.json']);require(cohort['version']=='1.1.17' and cohort['source_revision']==BASE,'Wrong complete Watch predecessor')
 require(json.loads(old['file_browser.json'])['version']=='1.5.31','Wrong Files predecessor')
 require(json.loads(old['model_viewer.json'])['version']=='1.3.0','Wrong Model Viewer predecessor')
 f=args.files_build;v=args.canvas_build/'model_viewer';fr=json.loads((f/'file_browser-build-record.json').read_text());vr=json.loads((v/'build.json').read_text())
 fe=(f/'file_browser.elf').read_bytes();ve=(v/'model_viewer.elf').read_bytes()
 require(fr['sha256']==sha(fe) and fr['bytes']==len(fe),'Files binary receipt mismatch')
 require(vr['sha256']==sha(ve) and vr['size_bytes']==len(ve),'Viewer binary receipt mismatch')
 require('-DPORTABLE_FILE_BROWSER_SOURCE_HANDOFF' in fr['defines'] and '-DCANVAS_FILE_SOURCE' in vr['defines'],'Source handoff not compiled')
 require(vr['target']=='watch','Wrong viewer target')
 for record in [fr,vr]:
  for name,digest in record['source_sha256'].items():
   p=Path(name);require(p.is_file() and sha(p.read_bytes())==digest,'Compiled source changed: '+name)
 require(fr['baseline_files']=={n:sha(old[n]) for n in ('boot.json','file_browser.json')},'Files built against another authority baseline')
 from compact_current_elf import compact
 compiler=os.environ.get('NATIVE_APP_CC');require(bool(compiler),'Set pinned NATIVE_APP_CC')
 compactions={}
 with tempfile.TemporaryDirectory(prefix='watch-file-source-') as temp:
  for app,raw in [('file_browser',fe),('model_viewer',ve)]:
   path=Path(temp)/(app+'.elf');path.write_bytes(raw);compactions[app]=compact(path,compiler)
   if app=='file_browser':fe=path.read_bytes()
   else:ve=path.read_bytes()
 new=changed_store(old,fe,(f/'file_browser.json').read_bytes(),ve,(v/'model_viewer.json').read_bytes())
 row=next(r for r in json.loads(new['boot.json'])['app_capabilities'] if r['manifest']=='file_browser.json')
 require(row['grants']==fr['required_grants'],'Files grants differ from compiled profile')
 require(not args.output.exists(),'Use a fresh output directory');args.output.mkdir(parents=True)
 for name in CHANGED:(args.output/name).write_bytes(new[name])
 profile=(ROOT/'docs/file-source/watch-file-source-profile.ini').read_bytes();(args.output/'watch-file-source-profile.ini').write_bytes(profile)
 receipt={'schema':1,'baseline_product':BASE,'baseline_version':'1.1.17','changed_store_files':sorted(CHANGED),'preserved_store_files':len(old)-len(CHANGED),'all_existing_grants_preserved':True,'provider_graph_byte_preserved':True,'original_type_handler_declarations_preserved':True,'added_app_grants':{n:[GRANT] for n in ['file_browser.json','model_viewer.json']},'required_native_flags':FLAGS,'private_scratch_root':'/appdata/.risc-file-source','scratch_reserved_headroom_bytes':65536,'whole_file_ram_buffer':False,'remote_range_streaming':False,'hardware_verified':False,'full_native_and_cohort_admission_required':True,'overlay_sha256':{n:sha(new[n]) for n in sorted(CHANGED)},'compactions':compactions,'source_builds':{'files':fr,'model_viewer':vr}}
 (args.output/'binding-receipt.json').write_bytes(encoded(receipt));print(json.dumps({k:v for k,v in receipt.items() if k!='source_builds'},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['baseline-store','files-build','canvas-build','output']:p.add_argument('--'+name,type=Path,required=True)
 build(p.parse_args())

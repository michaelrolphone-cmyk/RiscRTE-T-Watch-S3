#!/usr/bin/env python3
"""Feature-faithful selected Home source fixture, consuming retained Settings records."""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
import qualify
PINS={'watch':'416fa9f144fa5bd5471e6f4c9cefff21455c8361','system':'bb0cadf3cec3445a64e11513b47b2676f3fdd92d','utilities':'4fdcad2495c33fe63f5f6faca9b11ced3c739a5b'}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in (*PINS,'assets','records','output'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 repos={k:getattr(a,k).resolve() for k in PINS}
 for k,path in repos.items():qualify.source(path,PINS[k])
 raw=qualify.assets(a.assets)
 with zipfile.ZipFile(__import__('io').BytesIO(raw['TWatch-1.1.46-Provisioning-Evidence.zip'])) as z:
  canonical=z.read('canonical-a.json');row=json.loads(canonical)['artifacts']['default']
 assert (row['bytes'],row['sha256'])==qualify.HOME
 flags=[f for f in row['defines'] if f.startswith('-D')]
 assert '-DWATCH_CRASH_REPORT_NAMESPACE=61' in flags and '-DPORTABLE_LOW_BATTERY' in flags
 inputs=json.loads(a.records.read_text())
 runs=[]
 with tempfile.TemporaryDirectory(prefix='retained-home-profile-') as tmp:
  work=Path(tmp);w,s,u=[repos[k] for k in ('watch','system','utilities')]
  sys.path.insert(0,str(w/'scripts'));from merged_sdk import headers
  sdk=headers(work,s,u,w)
  original=(w/'tests/fast_wake_clock_test.c').read_text()
  assert original.count('static const risc_runtime_api_v1 fast_runtime=')==1
  original=original.replace('static const risc_runtime_api_v1 fast_runtime=','static risc_runtime_api_v1 fast_runtime=')
  assert original.count('int main(void){')==1
  original=original.replace('int main(void){','static int __attribute__((unused)) inherited_fast_main(void){')
  for f in flags:
   name=f[2:].split('=')[0]
   original=re.sub(r'^#define '+re.escape(name)+r'\s*$',lambda m:'#ifndef '+name+'\n'+m.group(0)+'\n#endif',original,flags=re.M)
  (work/'home_fixture.inc').write_text(original)
  commands=[]
  def run(name,cmd):
   r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=180,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0','UBSAN_OPTIONS':'halt_on_error=1'})
   (out/(name+'.log')).write_text(r.stdout+r.stderr);commands.append({'name':name,'command':list(map(str,cmd)),'returncode':r.returncode});r.check_returncode();return r.stdout
  sources=[Path(__file__).with_suffix('.c').resolve(),*[w/'apps/clock'/n for n in ('nova/nova.c','points_projection.c','viewport.c','capability_clients.c','quick_radios.c')],*[s/'lib/PortableApps/src'/n for n in ('quick_actions.c','quick_render.c','quick_session.c','PortableAutomaticProvision.c','PortableNetworkSession.c')]]
  for sanitized in (False,True):
   common=['-O1','-g','-Wall','-Wextra','-Werror',*flags,*['-I'+str(x) for x in (work,sdk,w/'include',w,w/'tests',s/'lib/PortableApps/src')]]
   if sanitized:common+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie']
   objects=[]
   for i,src in enumerate(sources):
    obj=work/f'{sanitized}-{i}.o';run(f'compile-{sanitized}-{i}',['cc','-std=c11',*common,'-c',src,'-o',obj]);objects.append(obj)
   exe=work/f'home-{sanitized}';run(f'link-{sanitized}',['c++','-std=c++11',*common,w/'apps/clock/effects/boot.cpp',*objects,'-o',exe])
   # Record file contract is emitted by settings_profile.py from actual UI Save.
   for index,row in enumerate(inputs['profiles']):
    rec=row['records'];mode=row['mode'];idle=row['idle_ms'];deep=row['deep_ms']
    for fault in range(6):
     expected=(mode,idle,deep) if not fault else (2,60000,300000)
     text=run(f'case-{sanitized}-{index}-{fault}',[exe,rec['sleep_mode'],rec['sleep_idle'],rec['sleep_deep'],*expected,fault])
     runs.append({'sanitized':sanitized,'case':row.get('name',index),'fault':fault,'stdout':text.strip()})
  # Removing the selected timer feature must fail the fixture's preprocessor gate.
  bad=subprocess.run(['cc','-std=c11',*[f for f in common if f!='-DPORTABLE_LOW_BATTERY'],'-fsyntax-only',sources[0]],capture_output=True,text=True)
  assert bad.returncode and 'Exact selected Home timer' in bad.stderr
 receipt={'status':'passed','source_pins':PINS,'canonical_receipt_sha256':hashlib.sha256(canonical).hexdigest(),'record_file_sha256':hashlib.sha256(a.records.read_bytes()).hexdigest(),'production_defines':flags,'commands':commands,'runs':runs,'wrong_flag_rejected':True,'scope':'Actual selected Home and quick_session host execution with production -D features, namespace1 storage and Runtime preference mocks. Not target compiler/ELF execution or physical timing. Deep requests return modeled refusal for cleanup.'}
 (out/'home-profile.json').write_text(json.dumps(receipt,indent=2)+'\n');print('Home profile PASS',len(runs),'cases')
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Feature-faithful selected Home source fixture, consuming retained Settings records."""
import argparse, copy, hashlib, json, os, re, subprocess, sys, tempfile, zipfile
from pathlib import Path
import qualify
import source_checks
import settings_profile
PINS={'watch':'416fa9f144fa5bd5471e6f4c9cefff21455c8361','system':'bb0cadf3cec3445a64e11513b47b2676f3fdd92d','utilities':'4fdcad2495c33fe63f5f6faca9b11ced3c739a5b'}

def validate_records(data):
 assert data['producer_system']==settings_profile.PINS['producer_system']
 assert data['bridge']==settings_profile.PINS['bridge']
 assert data['recipe_sha256']==settings_profile.RECIPE_SHA256
 assert len(data['profiles'])==3 and {r['mode'] for r in data['profiles']}=={0,1,2}
 for row in data['profiles']:
  assert row['namespace']==1
  assert set(row['records'])=={'sleep_mode','sleep_idle','sleep_deep'}
  for key,value in row['records'].items():
   assert re.fullmatch('[0-9a-f]+',value) and len(value)==(8 if key=='sleep_mode' else 10)
  assert row['idle_ms']==65000 and row['deep_ms']==360000


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in (*PINS,'assets','records','historical-records','output'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 repos={k:getattr(a,k).resolve() for k in PINS}
 for k,path in repos.items():qualify.source(path,PINS[k])
 raw=qualify.assets(a.assets)
 with zipfile.ZipFile(__import__('io').BytesIO(raw['TWatch-1.1.46-Provisioning-Evidence.zip'])) as z:
  canonical=z.read('canonical-a.json');row=json.loads(canonical)['artifacts']['default']
 assert (row['bytes'],row['sha256'])==qualify.HOME
 flags=[f for f in row['defines'] if f.startswith('-D')]
 assert '-DWATCH_CRASH_REPORT_NAMESPACE=61' in flags and '-DPORTABLE_LOW_BATTERY' in flags
 inputs=json.loads(a.records.read_text());validate_records(inputs)
 negative=[]
 for changed in ('producer_system','namespace'):
  bad=copy.deepcopy(inputs)
  if changed=='namespace':bad['profiles'][0]['namespace']=2
  else:bad[changed]=PINS['system']
  try:validate_records(bad)
  except AssertionError:negative.append('wrong '+changed+' rejected')
  else:raise AssertionError('invalid producer record provenance accepted')
 try:qualify.source(repos['system'],PINS['watch'])
 except ValueError:negative.append('wrong selected source rejected')
 else:raise AssertionError('wrong selected source accepted')
 history=json.loads(a.historical_records.read_text())
 assert history['status']=='passed' and history['git_pins']==source_checks.PINS
 assert history['script_sha256']==hashlib.sha256(Path(source_checks.__file__).read_bytes()).hexdigest()
 differences=history['matrices'][0]['persisted_record_differences'];assert len(differences)==6
 cases=[]
 for index,row in enumerate(inputs['profiles']):
  for fault in range(6):
   expected=(row['mode'],row['idle_ms'],row['deep_ms']) if not fault else (2,60000,300000)
   cases.append((f'ui-{index}-fault-{fault}',row['records'],expected,fault))
 # These six records were produced by the historical policy helper, NOT by UI
 # choices. Pass their opaque bytes to the actual Home path, never re-encode.
 template=next(r for r in inputs['profiles'] if r['mode']==2)
 for index,difference in enumerate(differences):
  rec=dict(template['records']);key='sleep_deep' if difference['deep'] else 'sleep_idle'
  rec[key]=difference['record_hex'];assert difference['selected_home_read'][0]==2
  expected=[2,template['idle_ms'],template['deep_ms']]
  expected[2 if difference['deep'] else 1]=difference['selected_home_read'][1]
  cases.append((f'inherited-{index}',rec,expected,0))
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
   for name,rec,expected,fault in cases:
    text=run(f'case-{sanitized}-{name}',[exe,rec['sleep_mode'],rec['sleep_idle'],rec['sleep_deep'],*expected,fault])
    runs.append({'sanitized':sanitized,'case':name,'fault':fault,'expected_mode_idle_deep':expected,'stdout':text.strip()})
  # Removing the selected timer feature must fail the fixture's preprocessor gate.
  bad=subprocess.run(['cc','-std=c11',*[f for f in common if f!='-DPORTABLE_LOW_BATTERY'],'-fsyntax-only',sources[0]],capture_output=True,text=True)
  assert bad.returncode and 'Exact selected Home timer' in bad.stderr
 receipt={'status':'passed','source_pins':PINS,'canonical_receipt_sha256':hashlib.sha256(canonical).hexdigest(),'record_file_sha256':hashlib.sha256(a.records.read_bytes()).hexdigest(),'production_defines':flags,'commands':commands,'runs':runs,'wrong_flag_rejected':True,'negative_controls':negative,'historical_record_file_sha256':hashlib.sha256(a.historical_records.read_bytes()).hexdigest(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256(Path(__file__).with_suffix('.c').read_bytes()).hexdigest(),'host_compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],'scope':'Actual selected Home and quick_session host execution with production -D features, namespace1 storage and Runtime preference mocks. Not target compiler/ELF execution or physical timing. Deep requests return modeled refusal for cleanup. Persistent KV acquisition denial instead refuses at motion preflight after paired Runtime begin/end. The enabled Runtime preference facade is acquired and read; no atomic transaction or native atomic-group durability is claimed.'}
 (out/'home-profile.json').write_text(json.dumps(receipt,indent=2)+'\n');print('Home profile PASS',len(runs),'cases')
if __name__=='__main__':main()

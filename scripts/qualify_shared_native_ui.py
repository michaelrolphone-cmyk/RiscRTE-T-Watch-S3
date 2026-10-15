#!/usr/bin/env python3
"""Qualify exact shared System app source at both Watch dimensions and e-ink fallback.
Runs host-only C fixtures; no PlatformIO, native firmware build or device access.
"""
import argparse,json,os,subprocess,sys,tempfile
from pathlib import Path
from shared_native_ui import PINS,archive,clean,encoded,need,require_final,sha

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('system','bridges','output'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args()
 for name in vars(a):setattr(a,name,getattr(a,name).resolve())
 require_final();clean(a.system,PINS['system_revision']);clean(a.bridges,PINS['bridge_revision'])
 need(not a.output.exists(),'Output must be new');a.output.mkdir(parents=True)
 reports={};logs={}
 def run(script,*args):
  result=subprocess.run([sys.executable,str(script),*map(str,args)],text=True,capture_output=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
  label=script.stem+'-'+str(len(logs));(a.output/(label+'.log')).write_text(result.stdout+result.stderr);logs[label]=sha((result.stdout+result.stderr).encode())
  if result.returncode:print(result.stdout,result.stderr);result.check_returncode()
  print(script.name+': PASS',flush=True)
 with tempfile.TemporaryDirectory(prefix='shared-ui-qualification-') as td:
  system=Path(td)/'system';archive(a.system,PINS['system_revision'],system)
  for script,path,expected in (
   ('test_watch_native_springboard.py','build/watch-native-springboard/results.json',108),
   ('test_watch_native_springboard_features.py','build/watch-native-springboard/feature-results.json',72),
   ('test_watch_native_fallback.py','build/watch-native-fallback/results.json',24)):
   run(system/'scripts'/script)
   d=json.loads((system/path).read_text());rows=d['checks'] if isinstance(d,dict) else d;need(len(rows)==expected,'Incomplete matrix '+script)
   reports[script]={'cases':expected,'results':d};(a.output/(script+'.json')).write_bytes(encoded(d))
  for script in ('test_watch_native_input.py','test_watch_async_canvas.py','test_watch_canvas_crown_exit.py','test_navigation_retention_adapter.py'):
   run(system/'scripts'/script)
  for sanitize in (False,True):
   out=a.output/('brightness-sanitized' if sanitize else 'brightness')
   run(system/'scripts/test_initial_frame_brightness.py','--bridges',a.bridges,'--output',out,'--stage-profile',*(['--sanitize'] if sanitize else []))
   rows=json.loads((out/'results.json').read_text());need(len(rows)==32,'Incomplete brightness matrix');reports[out.name]={'cases':32,'results':rows}
   out=a.output/('geometry-sanitized' if sanitize else 'geometry')
   run(system/'scripts/profile_springboard_full.py','--bridges',a.bridges,'--output',out,'--verify','--stage-profile',*(['--sanitize'] if sanitize else []))
   rows=json.loads((out/'results.json').read_text());need([(r['width'],r['height']) for r in rows]==[(160,160),(239,293),(240,240),(320,320),(320,390),(410,502),(800,1000)],'Geometry matrix changed')
   reports[out.name]={'cases':len(rows),'results':rows}
 need(reports['geometry']['results']==reports['geometry-sanitized']['results'],'Sanitized native geometry differs')
 report={'system_revision':PINS['system_revision'],'bridge_revision':PINS['bridge_revision'],'stage_profile':True,'reports':reports,'logs_sha256':logs,'device_accessed':False,'native_firmware_built':False,'target_instructions_executed':False,'hardware_tested':False,'leak_sanitizer':'disabled under ptrace; ASan/UBSan remain enabled'}
 (a.output/'qualification.json').write_bytes(encoded(report));print('Shared native app source qualified; hardware and native firmware remain separate gates')
if __name__=='__main__':main()

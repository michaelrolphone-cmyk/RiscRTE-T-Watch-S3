#!/usr/bin/env python3
"""Run and bind the pinned native SDR canvas and raster host regressions."""
import argparse,json,re,subprocess,sys,tempfile
from pathlib import Path
from watch_app_repair import ROOT,PINS,clean,encoded,files,need,sha

SPECS={
 'native-canvas': {'dimensions':[(160,160),(200,200),(240,240),(410,502),(320,240),(640,240),(240,320)],'key':'checks','per_run':41},
 'native-raster': {'dimensions':[(160,160),(240,240),(410,502),(640,240)],'key':'comparisons','per_run':79},
}

def evidence(root):
 return {p.relative_to(root).as_posix():p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file() and p.name!='renderer.json' and p.suffix in ('.json','.log','.txt')}

def check_cases(root):
 reports={}
 for name,spec in SPECS.items():
  raw=(root/name/'evidence.json').read_bytes();report=json.loads(raw)
  rows=report['runs'];expected={(w,h,san) for w,h in spec['dimensions'] for san in (False,True)}
  need(len(rows)==len(expected) and {(r['dimensions'][0],r['dimensions'][1],r['sanitized']) for r in rows}==expected,'Incomplete native SDR matrix: '+name)
  for row in rows:
   need(type(row['sanitized']) is bool and isinstance(row['command'],list) and row['command'], 'Invalid native source receipt')
   if name=='native-raster':need(row['result'].endswith(' PASS'), 'Native raster did not pass')
   counts=re.findall(r'(?<![\w-])'+spec['key']+r'=(\d+)(?!\d)',row['result'])
   need(counts==[str(spec['per_run'])],'Native SDR assertion count differs: '+name)
   dimensions='x'.join(map(str,row['dimensions']))+('-san' if row['sanitized'] else '')
   log=root/name/(dimensions+'/run.log' if name=='native-canvas' else dimensions+'.log')
   need(row['result'] in log.read_text(),'Native SDR report/log mismatch: '+str(log))
  need(report['hardware_verified'] is False,'Host matrix cannot qualify hardware')
  reports[name]={'runs':len(rows),'assertions_per_run':spec['per_run'],'assertions':len(rows)*spec['per_run'],'evidence_sha256':sha(raw)}
 return reports

def verify(root):
 report=json.loads((root/'renderer.json').read_text())
 need(report['system_revision']==PINS['sdr_system_revision'] and report['utilities_revision']==PINS['sdr_utilities_revision'],'Renderer source binding differs')
 declared=(root/'source-reported-qualification.json').read_bytes()
 need(sha(declared)==PINS['source_renderer_qualification_sha256']==report['source_report_sha256'],'Source-reported renderer qualification differs')
 need(report['source_report_inputs_verified'] is True,'Source qualification inputs not checked')
 declaration=json.loads(declared)
 need(report['source_test_sha256']=={'system':declaration['system_test_source_sha256']['scripts/test_rf_native_raster.py'],'utilities':declaration['test_source_sha256']['scripts/test_rf_native_canvas.py']},'Source tests differ from declaration')
 need(report['source_checkouts_isolated'] is True,'Renderer sources were not isolated')
 need(report['producer_sha256']==sha(Path(__file__).read_bytes()),'Renderer proof producer differs')
 need(report['reports']==check_cases(root),'Renderer matrix receipt differs')
 need(report['evidence_sha256']=={n:sha(v) for n,v in evidence(root).items()},'Renderer evidence changed')
 return report

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for name in ('system','utilities','output'):parser.add_argument('--'+name,type=Path,required=True)
 a=parser.parse_args();a.system=a.system.resolve();a.utilities=a.utilities.resolve();a.output=a.output.resolve()
 clean(a.system,PINS['sdr_system_revision']);clean(a.utilities,PINS['sdr_utilities_revision']);need(not a.output.exists(),'Renderer output must be new');a.output.mkdir(parents=True)
 workspace=tempfile.TemporaryDirectory(prefix='twatch-sdr-source-')
 roots={}
 for label,path in [('system',a.system),('utilities',a.utilities)]:
  target=Path(workspace.name)/label
  subprocess.run(['git','clone','--quiet','--no-hardlinks',str(path),str(target)],check=True)
  subprocess.run(['git','-C',str(target),'checkout','--quiet','--detach',PINS['sdr_'+label+'_revision']],check=True)
  roots[label]=target
 declared=(roots['utilities']/'docs/rf-native-qualification.json').read_bytes()
 need(sha(declared)==PINS['source_renderer_qualification_sha256'] and declared==(ROOT/'docs/shared-app-repair/source-renderer-qualification.json').read_bytes(),'Pinned source-reported qualification differs')
 declaration=json.loads(declared)
 for label,key in [('utilities','test_source_sha256'),('system','system_test_source_sha256'),('utilities','application_sha256')]:
  for name,digest in declaration[key].items():
   need(not Path(name).is_absolute() and '..' not in Path(name).parts,'Unsafe source evidence path')
   need(sha((roots[label]/name).read_bytes())==digest,'Source qualification file differs: '+label+'/'+name)
 (a.output/'source-reported-qualification.json').write_bytes(declared)
 source_hashes={label:sha((roots[label]/script).read_bytes()) for label,script in [('system','scripts/test_rf_native_raster.py'),('utilities','scripts/test_rf_native_canvas.py')]}
 commands=[(roots['utilities']/'scripts/test_rf_native_canvas.py',['--system-apps',str(roots['system'])],'native-canvas'),(roots['system']/'scripts/test_rf_native_raster.py',[],'native-raster')]
 for script,args,name in commands:
  subprocess.run([sys.executable,str(script),*args,'--output',str(a.output/name)],check=True)
 report={'system_revision':PINS['sdr_system_revision'],'utilities_revision':PINS['sdr_utilities_revision'],'producer_sha256':sha(Path(__file__).read_bytes()),'source_checkouts_isolated':True,'source_report_inputs_verified':True,'source_report_sha256':sha(declared),'source_test_sha256':source_hashes,'reports':check_cases(a.output),'evidence_sha256':{n:sha(v) for n,v in evidence(a.output).items()},'hardware_tested':False,'device_accessed':False}
 (a.output/'renderer.json').write_bytes(encoded(report));verify(a.output);workspace.cleanup();print(json.dumps(report['reports'],indent=2))
if __name__=='__main__':main()

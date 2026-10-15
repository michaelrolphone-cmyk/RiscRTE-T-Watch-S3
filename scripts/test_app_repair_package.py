#!/usr/bin/env python3
"""No-network contract checks for successor packaging and pinned source replay."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import package_app_repair as p

class PackageTests(unittest.TestCase):
 def test_release_notes_only_actual_changes(self):
  self.assertEqual(p.release_notes(),'- Renders RF Spectrum and Waterfall plots at the display’s native resolution.\n- Keeps status text clear of the RF plots.\n')
 def test_nonbaseline_factory_refused(self):
  with self.assertRaisesRegex(ValueError,'Exact released .36'):p.make_factory(b'wrong',b'',b'',Path('/unused'),Path('/unused'))
 def test_same_size_wrong_factory_refused(self):
  with self.assertRaisesRegex(ValueError,'Exact released .36'):p.make_factory(b'\xff'*0x1000000,b'',b'',Path('/unused'),Path('/unused'))
 def test_update_instructions_bind_only_official_baseline(self):
  text=p.instructions();self.assertIn(p.PINS['baseline_sha256'],text);self.assertIn('baseline-1.1.36.bin',text);self.assertIn('candidate-1.1.37.bin',text);self.assertIn('sector LAST',text);self.assertNotIn('baseline-1.1.33.bin',text)
 def test_exact_published_native_source_binding(self):
  from stage_app_repair_native import NATIVE
  self.assertEqual(NATIVE['source_revision'],p.PINS['baseline_source'])
  self.assertEqual(NATIVE['runtime_revision'],p.PINS['runtime_revision'])
  self.assertEqual(NATIVE['baseline_factory_sha256'],p.PINS['baseline_sha256'])
  self.assertEqual(set(NATIVE['files']),{'firmware.bin','firmware.elf','native-radio-iq-proof.json','release.json','source-pins.json'})
  for name,digest in NATIVE['profile_sha256'].items():
   self.assertEqual(p.sha((p.ROOT/'native/shared-ui-profile'/name).read_bytes()),digest)
 def test_native_wrong_baseline_refused(self):
  import stage_app_repair_native as native
  with patch.object(native,'clean'):
   with self.assertRaisesRegex(ValueError,'baseline factory differs'):native.stage(b'wrong',b'',Path('/unused'))
 def test_native_wrong_evidence_refused(self):
  import stage_app_repair_native as native
  with patch.object(native,'clean'),patch.dict(native.NATIVE,{'baseline_factory_sha256':p.sha(b'factory')}),patch.dict(p.PINS,{'baseline_sha256':p.sha(b'factory')}):
   with self.assertRaisesRegex(ValueError,'native evidence differs'):native.stage(b'factory',b'wrong',Path('/unused'))
 def renderer_fixture(self,root):
  import qualify_app_repair_renderer as renderer
  for name,spec in renderer.SPECS.items():
   rows=[];directory=root/name;directory.mkdir()
   for width,height in spec['dimensions']:
    for sanitized in (False,True):
     dimensions=f'{width}x{height}'+('-san' if sanitized else '')
     text=spec['key']+'='+str(spec['per_run'])+' PASS'
     log=directory/(dimensions+'/run.log' if name=='native-canvas' else dimensions+'.log');log.parent.mkdir(exist_ok=True);log.write_text(text+'\n')
     rows.append({'dimensions':[width,height],'sanitized':sanitized,'command':['cc'],'result':text})
   (directory/'evidence.json').write_text(json.dumps({'runs':rows,'hardware_verified':False}))
  return renderer
 def test_renderer_matrix_counts(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);renderer=self.renderer_fixture(root);report=renderer.check_cases(root)
   self.assertEqual(report['native-canvas']['assertions'],574);self.assertEqual(report['native-raster']['assertions'],632)
 def test_incomplete_renderer_matrix_refused(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);renderer=self.renderer_fixture(root);path=root/'native-canvas/evidence.json';report=json.loads(path.read_text());report['runs'].pop();path.write_text(json.dumps(report))
   with self.assertRaisesRegex(ValueError,'Incomplete'):renderer.check_cases(root)
 def test_renderer_count_and_log_tampering_refused(self):
  for mode in ('count','log'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
    root=Path(td);renderer=self.renderer_fixture(root)
    if mode=='count':
     path=root/'native-raster/evidence.json';report=json.loads(path.read_text());report['runs'][0]['result']='comparisons=78';path.write_text(json.dumps(report))
    else:(root/'native-raster/160x160.log').write_text('tampered')
    with self.assertRaises(ValueError):renderer.check_cases(root)
 def replay_fixture(self,root):
  source=root/'source';spec=source/'docs/shared-app-crashes/replay';spec.mkdir(parents=True);(source/'scripts').mkdir();(source/'scripts/replay_shared_crash_apps.py').write_bytes(b'driver');(spec/'inputs.json').write_bytes(b'{}');compiler=root/'cc';compiler.write_bytes(b'compiler');out=root/'out';out.mkdir()
  apps={}
  for name in p.PINS['expected_replayed_apps']:
   value=name.encode();(out/(name+'.elf')).write_bytes(value);apps[name]={'sha256':p.sha(value),'bytes':len(value)}
   folder=out/(name+'-link-attempts');folder.mkdir();log=folder/'attempt-01.log';log.write_bytes(b'');history=[{'attempt':1,'returncode':0,'log':str(log),'log_sha256':p.sha(b''),'recognized_linker_abort':False}];apps[name]['link_attempts']=history;(folder/'receipt.json').write_text(json.dumps({'command':['cc','-o',name+'.elf'],'max_attempts':6,'attempts':history}))
  report={'product':'twatch','source_inputs_verified':True,'driver_sha256':p.sha(b'driver'),'compiler_sha256':p.sha(b'compiler'),'spec_sha256':{'inputs.json':p.sha(b'{}')},'apps':apps}
  (out/'receipt.json').write_text(json.dumps(report));return out,source,{'apps':apps},compiler,report
 def test_exact_replay_bindings(self):
  with tempfile.TemporaryDirectory() as td,patch.object(p,'clean'),patch.dict(p.PINS,{'replay_source_revision':'a'*40}):
   out,source,manifest,compiler,report=self.replay_fixture(Path(td));self.assertEqual(p.verify_replay(out,source,manifest,compiler),report)
 def test_replay_tampering_refused(self):
  for key,value in [('product','wave'),('source_inputs_verified',False),('driver_sha256','0'*64),('compiler_sha256','0'*64),('spec_sha256',{})]:
   with self.subTest(key=key),tempfile.TemporaryDirectory() as td,patch.object(p,'clean'),patch.dict(p.PINS,{'replay_source_revision':'a'*40}):
    out,source,manifest,compiler,report=self.replay_fixture(Path(td));report[key]=value;(out/'receipt.json').write_text(json.dumps(report))
    with self.assertRaises(ValueError):p.verify_replay(out,source,manifest,compiler)
 def test_incomplete_replay_refused(self):
  with tempfile.TemporaryDirectory() as td,patch.object(p,'clean'),patch.dict(p.PINS,{'replay_source_revision':'a'*40}):
   out,source,manifest,compiler,report=self.replay_fixture(Path(td));del report['apps']['calculator'];(out/'receipt.json').write_text(json.dumps(report))
   with self.assertRaisesRegex(ValueError,'Incomplete'):p.verify_replay(out,source,manifest,compiler)
 def test_replayed_payload_tampering_refused(self):
  with tempfile.TemporaryDirectory() as td,patch.object(p,'clean'),patch.dict(p.PINS,{'replay_source_revision':'a'*40}):
   out,source,manifest,compiler,report=self.replay_fixture(Path(td));(out/'calculator.elf').write_bytes(b'tampered')
   with self.assertRaisesRegex(ValueError,'app differs'):p.verify_replay(out,source,manifest,compiler)

 def test_compiler_attempt_logs_retained(self):
  with tempfile.TemporaryDirectory() as td:
   out,source,manifest,compiler,report=self.replay_fixture(Path(td));evidence=p.link_evidence(out,report);self.assertEqual(len(evidence),36)
 def test_compiler_log_tampering_refused(self):
  with tempfile.TemporaryDirectory() as td:
   out,source,manifest,compiler,report=self.replay_fixture(Path(td));(out/'calculator-link-attempts/attempt-01.log').write_bytes(b'tampered')
   with self.assertRaisesRegex(ValueError,'log hash'):p.link_evidence(out,report)
 def test_compiler_history_escape_and_failure_refused(self):
  for key,value in [('log','/escape/attempt-01.log'),('attempt',2),('returncode',1),('recognized_linker_abort',True)]:
   with self.subTest(key=key),tempfile.TemporaryDirectory() as td:
    out,source,manifest,compiler,report=self.replay_fixture(Path(td));report['apps']['calculator']['link_attempts'][0][key]=value
    with self.assertRaises(ValueError):p.link_evidence(out,report)

if __name__=='__main__':unittest.main()

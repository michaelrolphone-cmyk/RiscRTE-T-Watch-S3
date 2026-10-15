#!/usr/bin/env python3
"""No-network contract checks for successor packaging and pinned source replay."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import package_app_repair as p

class PackageTests(unittest.TestCase):
 def test_release_notes_only_actual_changes(self):
  self.assertEqual(p.release_notes(),'- Fixes shared-app crashes, including Points in Time.\n- Prevents SDR scheduling starvation that could trigger watchdog resets.\n')
 def test_nonbaseline_factory_refused(self):
  with self.assertRaisesRegex(ValueError,'Exact released .35'):p.make_factory(b'wrong',b'',b'',Path('/unused'),Path('/unused'))
 def test_same_size_wrong_factory_refused(self):
  with self.assertRaisesRegex(ValueError,'Exact released .35'):p.make_factory(b'\xff'*0x1000000,b'',b'',Path('/unused'),Path('/unused'))
 def test_update_instructions_bind_only_official_baseline(self):
  text=p.instructions();self.assertIn(p.PINS['baseline_sha256'],text);self.assertIn('baseline-1.1.35.bin',text);self.assertIn('candidate-1.1.36.bin',text);self.assertIn('sector LAST',text);self.assertNotIn('baseline-1.1.33.bin',text)
 def replay_fixture(self,root):
  source=root/'source';spec=source/'docs/shared-app-crashes/replay';spec.mkdir(parents=True);(source/'scripts').mkdir();(source/'scripts/replay_shared_crash_apps.py').write_bytes(b'driver');(spec/'inputs.json').write_bytes(b'{}');compiler=root/'cc';compiler.write_bytes(b'compiler');out=root/'out';out.mkdir()
  apps={}
  for name in p.PINS['expected_repaired_apps']:
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

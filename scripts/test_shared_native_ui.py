#!/usr/bin/env python3
"""Fail-closed product custody and no-extra-authority tests."""
import copy,json,tempfile,unittest
from pathlib import Path
import shared_native_ui as m
class SharedNativeUi(unittest.TestCase):
 def policy(self):
  r={'capability':'runtime.retained-wake','api':1}
  return {'default.json':m.encoded({'id':'twatch-clock','requires':[r]}),'boot.json':m.encoded({'app_capabilities':[{'manifest':'default.json','grants':[{**r,'instance_id':0}]}]})}
 def test_policy_no_mutation(self):
  s=self.policy();before=copy.deepcopy(s);self.assertTrue(m.verify_wake(s)['unchanged']);self.assertEqual(s,before)
 def test_policy_missing_requirement(self):
  s=self.policy();d=json.loads(s['default.json']);d['requires']=[];s['default.json']=m.encoded(d)
  with self.assertRaises(ValueError):m.verify_wake(s)
 def test_policy_wrong_instance(self):
  s=self.policy();d=json.loads(s['boot.json']);d['app_capabilities'][0]['grants'][0]['instance_id']=1;s['boot.json']=m.encoded(d)
  with self.assertRaises(ValueError):m.verify_wake(s)
 def test_policy_duplicate_requirement(self):
  s=self.policy();d=json.loads(s['default.json']);d['requires']*=2;s['default.json']=m.encoded(d)
  with self.assertRaises(ValueError):m.verify_wake(s)
 def test_baseline_inventory(self):
  self.assertEqual(len(m.PINS['baseline_files']),121);self.assertEqual(sum(k.endswith('.elf') for k in m.PINS['baseline_files']),59)
 def test_reserved_version(self):
  self.assertEqual(m.PINS['version'],'1.1.35');self.assertEqual(m.PINS['provisioning_version_reserved'],'1.1.34')
 def test_flags_preserved(self):
  with tempfile.TemporaryDirectory() as td:
   out=Path(td);a=m.command(Path('/system'),Path('/bridges'),Path('/cc'),out,False);b=m.command(Path('/system'),Path('/bridges'),Path('/cc'),out,True)
   self.assertEqual(b,a+['-DPORTABLE_STAGE_PROFILE'])
   for flag in ('-DPORTABLE_QUICK_ACTIONS','-DPORTABLE_QUICK_RADIOS','-DPORTABLE_MOTION_WAKE','-DPORTABLE_NAVIGATION_RETENTION','-DWATCH_ALARM_SLEEP_RESUME','-DPORTABLE_CONTEXTS_CLIENT','-DPORTABLE_ASYNC_RGB565','-DPORTABLE_WATCH_NATIVE_HEIGHT'):
    self.assertIn(flag,b)
 def test_no_provisioning_or_vendor_profile(self):
  p=(m.ROOT/'native/shared-ui-profile/watch-native-ui.ini').read_text()
  self.assertIn('custom_radio_iq_target_identity = esp32s3-16mb-appdata-expanded-iq',p)
  self.assertIn('-DRISC_PERFORMANCE_TRACE_CAPACITY=64',p)
  for forbidden in ('RISC_OWNER_INSTALLER','RISC_NATIVE_PACKAGE_VOLUME','VendorDisplay','waveshare','t023-migration'):
   self.assertNotIn(forbidden,p)
if __name__=='__main__':unittest.main()

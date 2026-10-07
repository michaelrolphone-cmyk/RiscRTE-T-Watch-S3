"""The new automatic profile cannot silently use frozen versions or omit policy."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from current_apps_overlay import APPS,CLOCK_APPS,config
from build_current_apps import definitions
from build_clock_app import clock_manifest
from test_current_clock_manifest import CompilerCaptured
import build_clock_app
from unittest.mock import patch
import os,shutil
class LowBatteryProfile(unittest.TestCase):
 def test_automatic_every_app_and_distinct_versions(self):
  future=config(profile='low-battery');current=config()
  self.assertEqual(future['features'],{'low_battery':True})
  self.assertEqual(future['product_version'],'1.0.7')
  for name in APPS:
   self.assertIn('-DPORTABLE_LOW_BATTERY',definitions(name,future['app_versions'][name],True))
   self.assertNotIn('-DPORTABLE_LOW_BATTERY',definitions(name,current['app_versions'][name]))
   self.assertGreater(tuple(map(int,future['app_versions'][name].split('.'))),tuple(map(int,current['app_versions'][name].split('.'))))
  self.assertEqual(current['app_versions']['clock'],'0.10.2')
  self.assertEqual(future['app_versions']['clock'],'0.10.3')
  self.assertEqual(clock_manifest(paired=True,current=True)['version'],'0.10.2')
  self.assertEqual(clock_manifest(paired=True,current=True,low_battery=True)['version'],'0.10.3')
 def test_reject_missing_enablement_or_reused_versions(self):
  for mutation in ('features','version','profile','sources'):
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'apps').mkdir();c=copy.deepcopy(config(profile='low-battery'))
    (root/'apps/apex-apps-sources.json').write_text(json.dumps(config()))
    if mutation=='features':c['features']={'low_battery':False}
    elif mutation=='version':c['app_versions']['clock']='0.10.2'
    elif mutation=='profile':c['profile']='watch-current-apps-v1'
    else:del c['source_app_versions']['settings']
    (root/'apps/low-battery-sources.json').write_text(json.dumps(c))
    with self.assertRaises(ValueError):config(root,profile='low-battery')
 def test_clock_compiler_uses_policy_and_existing_alarm_resume(self):
  for returning in (False,True):
   commands=[]
   def capture(command,**kwargs):
    commands.append(command)
    if '-shared' in command:raise CompilerCaptured()
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);shutil.copytree(ROOT/'sdk/app',root/'sdk/app')
    header=root/'utilities/lib/Alarm/include/PointsRecords.h';header.parent.mkdir(parents=True);header.write_text('#define POINTS_DEFAULTS_AVAILABLE 1\n')
    with patch.object(build_clock_app,'ROOT',root),patch.object(build_clock_app.subprocess,'run',side_effect=capture),patch.dict(os.environ,{'TWATCH_CC':'mock-gcc'}):
     with self.assertRaises(CompilerCaptured):
      build_clock_app.build(launcher=True,returning=returning,alarm_system=root/'system',points_utilities=root/'utilities',paired=True,current=True,low_battery=True)
   actual=[x for x in commands[-1] if x.startswith('-D')]
   self.assertCountEqual(actual,definitions('clock' if returning else 'default','0.10.3',True))
 def test_legacy_header_parity_uses_frozen_clock_input(self):
  from build_legacy_sleep import legacy_clock
  from build_launcher_apps import verify_sleep_policy
  import hashlib
  source=legacy_clock(ROOT)
  old=(source/'PortableSleepPolicy.h').read_bytes()
  self.assertEqual(hashlib.sha256(old).hexdigest(),'a543173afd4ceec4707fcda3b63c75108546b95813abed550edf05383dbc0532')
  self.assertNotEqual(old,(ROOT/'apps/clock/PortableSleepPolicy.h').read_bytes())
  with tempfile.TemporaryDirectory() as tmp:
   system=Path(tmp);header=system/'lib/PortableApps/include/PortableSleepPolicy.h';header.parent.mkdir(parents=True);header.write_bytes(old)
   verify_sleep_policy(system,source)
   header.write_bytes(old+b'changed')
   with self.assertRaises(ValueError):verify_sleep_policy(system,source)
 def test_no_low_battery_in_legacy_builds(self):
  with self.assertRaises(ValueError):clock_manifest(low_battery=True)
  with self.assertRaises(ValueError):build_clock_app.build(low_battery=True)
if __name__=='__main__':unittest.main()

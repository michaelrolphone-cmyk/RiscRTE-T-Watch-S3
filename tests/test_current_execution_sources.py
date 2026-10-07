"""Live execution follows apex pins; accepted midpoint fixtures stay isolated."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import update_test_production_store_runtime as execution
from current_apps_overlay import config
from frozen_watch_cohort_fixture import fixture as frozen_fixture
from test_next_watch_cohort import fixture as live_fixture
import build_next_watch_cohort as frozen
import build_current_watch_cohort as live
import check_runtime_store_admission as admission
import test_next_watch_upgrade as upgrade

class CurrentExecutionSources(unittest.TestCase):
 def test_runtime_routes_to_apex_and_legacy_remains_exact(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'apps').mkdir()
   (root/'apps/apex-runtime-requirements.json').write_text(json.dumps({'source_sha':'a'*40}))
   (root/'apps/current-runtime-requirements.json').write_text(json.dumps({'source_sha':'b'*40}))
   with patch.object(execution,'ROOT',root),patch.object(execution,'source_state',return_value={'commit':'a'*40,'tracked_changes':''}):
    self.assertEqual(execution._runtime(root,current_profile=True),root.resolve())
   for head,dirty in [('b'*40,''),('a'*40,'modified')]:
    with patch.object(execution,'ROOT',root),patch.object(execution,'source_state',return_value={'commit':head,'tracked_changes':dirty}):
     with self.assertRaisesRegex(ValueError,'Wrong or modified'):execution._runtime(root,current_profile=True)
   with patch.object(execution,'ROOT',root),patch.object(execution,'source_state',return_value={'commit':execution.RUNTIME_COMMIT,'tracked_changes':''}):
    self.assertEqual(execution._runtime(root),root.resolve())
 def test_clock_policy_uses_the_live_version(self):
  boot={'default_app':'default.elf','app_capabilities':[{'manifest':name+'.json','grants':[{'capability':'storage.key-value','instance_id':n} for n in (1,5)]} for name in ('default','clock','points_in_time')]}
  boot['app_capabilities'] += [{'manifest':str(n)+'.json','grants':[]} for n in range(8)]
  store={'boot.json':json.dumps(boot).encode(),'default.json':json.dumps({'version':'1.2.3'}).encode()}
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'apps').mkdir()
   (root/'apps/apex-apps-sources.json').write_text(json.dumps({'app_versions':{'default':'1.2.3'}}))
   (root/'apps/current-apps-sources.json').write_text(json.dumps({'app_versions':{'default':'9.9.9'}}))
   with patch.object(execution,'ROOT',root):
    self.assertEqual(execution._policies(store,True),boot)
    store['default.json']=json.dumps({'version':'9.9.9'}).encode()
    with self.assertRaisesRegex(ValueError,'Paired Clock'):execution._policies(store,True)
 def test_all_integrated_external_provider_sources_are_registered(self):
  c=config();identities={c[key]['id'] for key in ('sdr','hid','ble_sensors','ble_telemetry','telemetry_battery')}
  paths=execution.external_driver_manifests(Path('/drivers'))
  self.assertEqual(set(paths),identities)
  self.assertEqual(paths['telemetry-battery'],Path('/drivers/Drivers/telemetry_battery/manifest.json'))
  self.assertEqual(paths['ble-sensors'],Path('/drivers/Drivers/ble_sensors/manifest.json'))
 def test_external_source_hashes_cover_nested_driver_inputs(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);nested=root/'Drivers/ble_sensors/nested/header.h';nested.parent.mkdir(parents=True);nested.write_text('first')
   before=execution.external_source_hashes(root);self.assertIn(str(nested),before)
   nested.write_text('changed');self.assertNotEqual(before,execution.external_source_hashes(root))
 def test_frozen_and_live_fixtures_each_exercise_their_own_policy(self):
  old_before,old_after=frozen_fixture();new_before,new_after=live_fixture()
  frozen.check_policy(old_before,old_after);live.check_policy(new_before,new_after)
  self.assertFalse(any(name.startswith(('ble-sensors/','ble-telemetry/','battery-telem/')) for name in old_after))
  with self.assertRaisesRegex(ValueError,'inventory'):frozen.check_policy(new_before,new_after)

 def test_admission_iq_lifecycle_tracks_selected_runtime(self):
  for declaration,enabled in [('radioIqReady',False),('radioIqReady radioIqPrepare radioIqCleanup',True)]:
   with self.subTest(declaration=declaration),tempfile.TemporaryDirectory() as temp:
    root=Path(temp);header=root/'src/ports/esp32s3/CpuPort.h';header.parent.mkdir(parents=True);header.write_text(declaration)
    with patch.object(admission.subprocess,'run') as run:
     admission.compile_harness(root,root/'admit')
    self.assertEqual('-DSTORE_ADMISSION_IQ_LIFECYCLE' in run.call_args.args[0],enabled)
 def test_execution_iq_lifecycle_tracks_selected_runtime(self):
  for declaration,enabled in [('radioIqReady',False),('radioIqReady radioIqPrepare radioIqCleanup',True)]:
   with self.subTest(declaration=declaration),tempfile.TemporaryDirectory() as temp:
    root=Path(temp);header=root/'src/ports/esp32s3/CpuPort.h';header.parent.mkdir(parents=True);header.write_text(declaration)
    registry=root/'test/support/native_registry/build.sh';registry.parent.mkdir(parents=True);registry.touch()
    with patch.object(execution,'command') as run:
     execution._host(root,root/'build',radio_iq=True)
    self.assertEqual('-DCURRENT_IQ_LIFECYCLE' in run.call_args.args[0],enabled)
 def test_transaction_links_provisioning_only_when_present(self):
  for enabled in (False,True):
   with self.subTest(enabled=enabled),tempfile.TemporaryDirectory() as temp:
    root=Path(temp);header=root/'src/runtime/provisioning/StoreFiles.h'
    if enabled:header.parent.mkdir(parents=True);header.touch()
    with patch.object(upgrade,'run') as run:
     upgrade.compile_transaction(root,root/'build','0.1.37')
    self.assertEqual(header.with_suffix('.cpp') in run.call_args.args,enabled)
 def test_negative_private_namespace_targets_hid_not_last_provider(self):
  previous,following=live_fixture()
  original=json.loads(following['boot.json'])
  self.assertNotEqual(original['drivers'][-1]['manifest'],'ble-hid/manifest.json')
  for label,candidate in upgrade.negative_stores(previous,following):
   if label=='new-provider-steals-private-kv':break
  changed=json.loads(candidate['boot.json'])
  for before,after in zip(original['drivers'],changed['drivers']):
   if before['manifest']=='ble-hid/manifest.json':
    self.assertTrue(after['key_value']);self.assertTrue(all(row['namespace']==4 for row in after['key_value']))
   else:self.assertEqual(before,after)

if __name__=='__main__':unittest.main()

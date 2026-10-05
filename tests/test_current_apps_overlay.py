import copy,json,tempfile,unittest,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import current_apps_overlay as current
from build_current_apps import definitions
from build_wifi_common import zip_bytes
class CurrentAppsOverlay(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'apps').mkdir();self.art=self.root/'artifact';(self.art/'files').mkdir(parents=True);(self.art/'licenses').mkdir()
  self.cfg={'schema':1,'profile':current.PROFILE,'sources':{n:{'repository':n,'commit':'1'*40} for n in ['system-apps','utilities','productivity','runtime']},'app_versions':{n:'1.0.1' for n in current.APPS},'service_version':'0.4.1'}
  (self.root/'apps/current-apps-sources.json').write_bytes(current.encoded(self.cfg));self.head='2'*40
  bindings={'alarm_cfg':(3,'read'),'timer_cfg':(3,'read'),'alarm_occ':(4,'read-write'),'timer_occ':(4,'read-write'),'alert_mode':(1,'read'),'points_cfg':(5,'read'),'points_occ':(4,'read-write')}
  grants=[{'capability':'storage.key-value','api':1,'instance_id':3},{'capability':'alarm.service','api':1,'instance_id':0}]
  self.boot={'drivers':[{'manifest':'alarm-service/manifest.json','key_value':[{'key':k,'namespace':n,'access':a} for k,(n,a) in bindings.items()]}],'app_capabilities':[{'manifest':n+'.json','grants':copy.deepcopy(grants)} for n in current.APPS]}
  self.store={n:b'baseline' for n in current.PAYLOADS-current.ADDED_PAYLOADS};self.store.update({'board.json':current.encoded({'devices':[]}),'pmu/driver.elf':b'original-PMU','default.elf':b'paired-clock-default','clock.elf':b'paired-clock-return','boot.json':current.encoded(self.boot)})
  (self.root/'hardware').mkdir();(self.root/'hardware/sx1262-915-bma423.json').write_bytes((ROOT/'hardware/sx1262-915-bma423.json').read_bytes());(self.root/'hardware/sx1262-915-bma456h.json').write_bytes((ROOT/'hardware/sx1262-915-bma456h.json').read_bytes())
  r={'schema':1,'profile':current.PROFILE,'watch_source':self.head,'configuration':self.cfg,'compiler':'GCC8.4.0','target_validation':True,'baseline_boot':self.boot,'boot':current.configure_boot(self.boot),'catalog':[],'apps':{},'service':{'defines':['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER','-DALARM_VOLUME_CONTROL','-DALARM_DND_CONTROL']},'files':{}}
  r['baseline_board']={'devices':[]};r['board']=current.configure_board(r['baseline_board'],self.root,motion_model='bma423');r['motion_model']='bma423'
  for n in current.PAYLOADS:
   p=self.art/'files'/n;p.parent.mkdir(exist_ok=True)
   if n=='board.json':b=current.encoded(r['board'])
   elif '/' not in n and n.endswith('.json'):
    name=n[:-5];v={'version':'1.0.1','file_name':name+'.elf','entry':'app_main','architecture':'xtensa-esp32s3','requires':[{'capability':'storage.key-value','api':1},{'capability':'alarm.service','api':1},{'capability':'rtc.clock','api':2},{'capability':'net.wifi','api':1},{'capability':'bluetooth.hci','api':1},{'capability':'motion.accel','api':1}]};b=current.encoded(v)
   elif n=='alarm-service/manifest.json':b=current.encoded({'version':'0.4.1'})
   else:b=('current-'+n).encode()
   p.write_bytes(b);r['files'][n]=current.metadata(b)
  for n in current.APPS:r['apps'][n]={**r['files'][n+'.elf'],'version':'1.0.1','defines':definitions(n,'1.0.1'),'compaction':{'retained_sections_symbols_relocations_unchanged':True,'removed_sections':['.xt.lit','.xt.prop'],'before_bytes':r['files'][n+'.elf']['size_bytes'],'after_bytes':r['files'][n+'.elf']['size_bytes']}}
  r['service']['points_headers']={'PointsRecords.h':'schema','PointsSchedule.h':'schema2'}
  r['clock']={'watch_source':self.head,'sources':self.cfg['sources'],'paired_boot_confirmation':True,'headers':r['service']['points_headers'],'files':{n+e:r['files'][n+e] for n in current.CLOCK_APPS for e in ('.elf','.json')}}
  (self.root/'clock-test.c').write_bytes(b'clock');r['clock']['source_sha256']={'clock-test.c':current.sha(b'clock')}
  (self.art/'source-profile.json').write_bytes(current.encoded(self.cfg));(self.art/'licenses/LICENSE.txt').write_text('test license')
  self.record=r;self.write_record()
 def tearDown(self):self.tmp.cleanup()
 def write_record(self):
  (self.art/'current-apps-build.json').write_bytes(current.encoded(self.record))
  names=['current-apps-build.json','source-profile.json']+['files/'+n for n in current.PAYLOADS]+['licenses/LICENSE.txt']
  (self.art/'current-apps.zip').write_bytes(zip_bytes({n:(self.art/n).read_bytes() for n in names}))
 def test_exact_allowlist_and_grants(self):
  original=copy.deepcopy(self.store);out,proof=current.apply(self.store,self.art,self.head,self.root)
  self.assertEqual(self.store,original);self.assertEqual(set(out),set(original)|current.ADDED_PAYLOADS)
  self.assertEqual(set(proof['files'])|set(proof['preserved_files']),set(out))
  self.assertFalse(set(proof['files'])&set(proof['preserved_files']))
  self.assertEqual(out['pmu/driver.elf'],b'current-pmu/driver.elf')
  self.assertEqual(out['gpio/driver.elf'],b'current-gpio/driver.elf')
  self.assertEqual(out['imu/driver.elf'],b'current-imu/driver.elf')
  self.assertEqual(json.loads(out['board.json']),current.configure_board(json.loads(original['board.json']),self.root,motion_model='bma423'))
  b=json.loads(out['boot.json']);a=next(x for x in b['app_capabilities'] if x['manifest']=='alarms.json');self.assertEqual([x['instance_id'] for x in a['grants'] if x['capability']=='storage.key-value'],[3,1])
  self.assertEqual(b['drivers'][0]['key_value'][-1],current.ALARM_DND)
 def test_bluetooth_projection_cannot_replace_existing_device(self):
  b={'devices':[{'instance_id':16}]}
  with self.assertRaises(ValueError):current.configure_board(b,self.root,motion_model='bma423')
 def test_wrong_head_and_configuration(self):
  with self.assertRaises(ValueError):current.verify(self.art,'3'*40,self.root)
  self.record['configuration']['service_version']='0.5.0';self.write_record()
  with self.assertRaises(ValueError):current.verify(self.art,self.head,self.root)
 def test_stale_file_and_zip_rejected(self):
  (self.art/'files/audio_spectrum.elf').write_bytes(b'wrong')
  with self.assertRaises(ValueError):current.verify(self.art,self.head,self.root)
 def test_archive_copy_must_match(self):
  (self.art/'licenses/LICENSE.txt').write_text('changed outer member')
  with self.assertRaises(ValueError):current.verify(self.art,self.head,self.root)
 def test_unexpected_preexisting_policy_rejected(self):
  b=copy.deepcopy(self.boot);b['app_capabilities'][0]['grants'].append({'capability':'storage.key-value','api':1,'instance_id':99});self.store['boot.json']=current.encoded(b)
  with self.assertRaises(ValueError):current.apply(self.store,self.art,self.head,self.root)
 def test_missing_or_additional_payload_rejected(self):
  self.record['files'].pop('settings.elf');self.write_record()
  with self.assertRaises(ValueError):current.verify(self.art,self.head,self.root)
 def test_every_current_client_uses_cue(self):
  for n in current.NON_CLOCK_APPS:self.assertIn('-DPORTABLE_ALARM_CLIENT',definitions(n,'1.0.1'))
  for n in current.CLOCK_APPS:self.assertIn('-DWATCH_PAIRED_BOOT_CONFIRM',definitions(n,'1.0.1'))
  for n in set(current.NON_CLOCK_APPS)-{'frequency_generator'}:self.assertIn('-DPORTABLE_NOVA_UI',definitions(n,'1.0.1'))
  self.assertIn('-DALARM_RETURN_APP="springboard.elf"',definitions('alarms','0.2.0'))
  self.assertIn('-DCALCULATOR_RETURN_APP="springboard.elf"',definitions('calculator','0.1.4'))
  self.assertIn('-DPORTABLE_APP_OWNS_TOUCH_CHROME',definitions('audio_spectrum','0.2.2'))
 def test_clock_source_bytes_and_paths(self):
  (self.root/'clock-test.c').write_bytes(b'changed')
  with self.assertRaises(ValueError):current.verify(self.art,self.head,self.root)
  self.record['clock']['source_sha256']={'../unsafe':'0'*64};self.write_record()
  with self.assertRaises(ValueError):current.verify(self.art,self.head,self.root)
 def test_volume_policy_not_broadened(self):
  b=copy.deepcopy(self.boot);b['drivers'][0]['key_value'][0]['namespace']=9
  with self.assertRaises(ValueError):current.configure_boot(b)
 def test_ci_upload_has_exact_canonical_envelope(self):
  workflow=(ROOT/'.github/workflows/drivers.yml').read_text()
  block=workflow.split('name: twatch-current-apps-',1)[1].split('if-no-files-found:',1)[0]
  paths={line.strip() for line in block.split('path: |',1)[1].splitlines() if line.strip()}
  self.assertEqual(paths,{'dist/current-apps/current-apps.zip','dist/current-apps/current-apps-build.json','dist/current-apps/source-profile.json','dist/current-apps/files/','dist/current-apps/licenses/'})
if __name__=='__main__':unittest.main()

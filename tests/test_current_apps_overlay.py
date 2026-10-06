import copy,json,tempfile,unittest,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import current_apps_overlay as current
from build_current_apps import definitions
from build_wifi_common import zip_bytes
class CurrentAppsOverlay(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'apps').mkdir();self.art=self.root/'artifact';(self.art/'files').mkdir(parents=True);(self.art/'licenses').mkdir()
  (self.art/'debug').mkdir()
  self.cfg={'schema':1,'profile':current.PROFILE,'sources':{n:{'repository':n,'commit':'1'*40} for n in ['system-apps','utilities','productivity','runtime']},'app_versions':{n:'1.0.1' for n in current.APPS},'service_version':'0.4.1','sdr':{'id':'s3-radio-iq-v1','commit':'4'*40,'version':'0.1.1'}}
  (self.root/'apps/current-apps-sources.json').write_bytes(current.encoded(self.cfg));self.head='2'*40
  bindings={'alarm_cfg':(3,'read'),'timer_cfg':(3,'read'),'alarm_occ':(4,'read-write'),'timer_occ':(4,'read-write'),'alert_mode':(1,'read'),'points_cfg':(5,'read'),'points_occ':(4,'read-write')}
  grants=[{'capability':'storage.key-value','api':1,'instance_id':3},{'capability':'alarm.service','api':1,'instance_id':0}]
  self.boot={'drivers':[{'manifest':'alarm-service/manifest.json','key_value':[{'key':k,'namespace':n,'access':a} for k,(n,a) in bindings.items()]}],'app_capabilities':[{'manifest':n+'.json','grants':copy.deepcopy(grants)} for n in current.APPS if n not in current.NEW_APPS]}
  next(x for x in self.boot['app_capabilities'] if x['manifest']=='audio_spectrum.json')['grants'][0]['instance_id']=7
  self.store={n:b'baseline' for n in current.PAYLOADS-current.ADDED_PAYLOADS};self.store.update({'board.json':current.encoded({'devices':[],'buses':[]}),'pmu/driver.elf':b'original-PMU','default.elf':b'paired-clock-default','clock.elf':b'paired-clock-return','boot.json':current.encoded(self.boot)})
  (self.root/'hardware').mkdir();
  (self.root/'hardware/current').mkdir()
  for profile in (ROOT/'hardware/current').glob('*.json'):(self.root/'hardware/current'/profile.name).write_bytes(profile.read_bytes())
  for hardware in (ROOT/'hardware').glob('*.json'):(self.root/'hardware'/hardware.name).write_bytes(hardware.read_bytes())
  (self.root/'hardware/sx1262-915-bma423.json').write_bytes((ROOT/'hardware/sx1262-915-bma423.json').read_bytes());(self.root/'hardware/sx1262-915-bma456h.json').write_bytes((ROOT/'hardware/sx1262-915-bma456h.json').read_bytes())
  r={'schema':1,'profile':current.PROFILE,'watch_source':self.head,'configuration':self.cfg,'compiler':'GCC8.4.0','target_validation':True,'baseline_boot':self.boot,'boot':current.configure_boot(self.boot),'catalog':[],'apps':{},'service':{'defines':['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER','-DALARM_VOLUME_CONTROL','-DALARM_DND_CONTROL']},'files':{}}
  r['baseline_board']={'devices':[],'buses':[]};r['board']=current.configure_board(r['baseline_board'],self.root,motion_model='bma423',radio_model='sx1262-915');r['motion_model']='bma423';r['radio_model']='sx1262-915'
  for n in current.PAYLOADS:
   p=self.art/'files'/n;p.parent.mkdir(exist_ok=True)
   if n=='board.json':b=current.encoded(r['board'])
   elif '/' not in n and n.endswith('.json'):
    name=n[:-5];v={'version':'1.0.1','file_name':name+'.elf','entry':'app_main','architecture':'xtensa-esp32s3','requires':[{'capability':'storage.key-value','api':1},{'capability':'alarm.service','api':1},{'capability':'rtc.clock','api':2},{'capability':'net.wifi','api':1},{'capability':'bluetooth.hci','api':1},{'capability':'motion.accel','api':1}]}
    if name=='audio_spectrum':v['requires'] += [{'capability':'storage.key-value','api':2},{'capability':'storage.app-data','api':1}]
    if name=='timecard':v['requires'] += [{'capability':c,'api':1} for c in ('display.output','input.touch.raw','board.battery','storage.app-data')]
    if name=='waterfall':v['requires'] += [{'capability':c,'api':1} for c in ('display.output','input.touch.raw','board.battery','radio.iq')]
    if name=='ble_scanner':v['requires'] += [{'capability':c,'api':1} for c in ('display.output','input.touch.raw','board.battery')]
    if name=='lora_messages':v['requires'] += [{'capability':c,'api':1} for c in ('display.output','input.touch.raw','board.battery')]+[{'capability':'radio.lora','api':2}]
    if name=='file_browser':v['requires']+=[{'capability':c,'api':1} for c in ('display.output','input.touch.raw','board.battery','storage.installed-files')]
    b=current.encoded(v)
   elif n=='s3-radio-iq/manifest.json':b=current.encoded({'id':'s3-radio-iq-v1','version':'0.1.1','requires':[{'capability':'platform.radio.iq.resource','api':1}],'provides':[{'capability':'radio.iq','api':1}]})
   elif n=='alarm-service/manifest.json':b=current.encoded({'version':'0.4.1'})
   else:b=('current-'+n).encode()
   p.write_bytes(b);r['files'][n]=current.metadata(b)
  r['sdr']={**self.cfg['sdr'],'build':{'source_revision':self.cfg['sdr']['commit'],**r['files']['s3-radio-iq/driver.elf']},'resource_header_sha256':'5'*64}
  r['debug']={}
  for n in current.APPS:
   debug=(self.art/'files'/(n+'.elf')).read_bytes();(self.art/'debug'/(n+'.elf')).write_bytes(debug);r['debug'][n+'.elf']=current.metadata(debug)
   r['apps'][n]={**r['files'][n+'.elf'],'version':'1.0.1','defines':definitions(n,'1.0.1'),'compaction':{'profile':current.COMPACTION_PROFILE,'retained_loader_sections_symbols_relocations_unchanged':True,'original_elf_retained':True,'tool':'GNU objcopy test','options':list(current.COMPACTION_OPTIONS),'removed_sections':[],'before_bytes':len(debug),'after_bytes':len(debug),'before_sha256':current.sha(debug),'after_sha256':current.sha(debug)}}
   if n=='audio_spectrum':r['apps'][n].update(host_fixture_excluded=True,target_dependencies={'utilities:Apps/audio_spectrum.c':current.metadata(debug)})
  r['service']['points_headers']={'PointsRecords.h':'schema','PointsSchedule.h':'schema2'}
  r['clock']={'watch_source':self.head,'sources':self.cfg['sources'],'paired_boot_confirmation':True,'headers':r['service']['points_headers'],'files':{n+e:r['files'][n+e] for n in current.CLOCK_APPS for e in ('.elf','.json')}}
  (self.root/'clock-test.c').write_bytes(b'clock');r['clock']['source_sha256']={'clock-test.c':current.sha(b'clock')}
  (self.art/'source-profile.json').write_bytes(current.encoded(self.cfg));(self.art/'licenses/LICENSE.txt').write_text('test license')
  self.record=r;self.write_record()
 def tearDown(self):self.tmp.cleanup()
 def write_record(self):
  (self.art/'current-apps-build.json').write_bytes(current.encoded(self.record))
  names=['current-apps-build.json','source-profile.json']+['files/'+n for n in current.PAYLOADS]+['debug/'+n+'.elf' for n in current.APPS]+['licenses/LICENSE.txt']
  (self.art/'current-apps.zip').write_bytes(zip_bytes({n:(self.art/n).read_bytes() for n in names}))
 def test_exact_allowlist_and_grants(self):
  original=copy.deepcopy(self.store);out,proof=current.apply(self.store,self.art,self.head,self.root)
  self.assertEqual(self.store,original);self.assertEqual(set(out),set(original)|current.ADDED_PAYLOADS)
  self.assertEqual(set(proof['files'])|set(proof['preserved_files']),set(out))
  self.assertFalse(set(proof['files'])&set(proof['preserved_files']))
  self.assertEqual(out['pmu/driver.elf'],b'current-pmu/driver.elf')
  self.assertEqual(out['gpio/driver.elf'],b'current-gpio/driver.elf')
  self.assertEqual(out['imu/driver.elf'],b'current-imu/driver.elf')
  self.assertEqual(json.loads(out['board.json']),current.configure_board(json.loads(original['board.json']),self.root,motion_model='bma423',radio_model='sx1262-915'))
  b=json.loads(out['boot.json']);a=next(x for x in b['app_capabilities'] if x['manifest']=='alarms.json');self.assertEqual([x['instance_id'] for x in a['grants'] if x['capability']=='storage.key-value'],[3,1])
  self.assertEqual(b['drivers'][0]['key_value'][-1],current.ALARM_DND)
  browser=next(x for x in b['app_capabilities'] if x['manifest']=='file_browser.json')
  self.assertEqual([g for g in browser['grants'] if g['capability'].startswith('storage.')],[{'capability':'storage.installed-files','api':1,'instance_id':0},current.ALARM_PREFERENCES])
  self.assertFalse(any(g['capability']=='storage.installed-files' for row in b['app_capabilities'] if row['manifest']!='file_browser.json' for g in row['grants']))
 def test_waterfall_has_only_granted_iq_and_explicit_shared_migration(self):
  boot=current.configure_boot(self.boot)
  grants=next(row['grants'] for row in boot['app_capabilities'] if row['manifest']=='waterfall.json')
  self.assertEqual([g for g in grants if g['capability']=='radio.iq'],[{'capability':'radio.iq','api':1,'instance_id':0}])
  self.assertFalse(any(g['capability']=='radio.iq' for row in boot['app_capabilities'] if row['manifest']!='waterfall.json' for g in row['grants']))
  self.assertFalse(any(g['capability'].startswith('platform.') or g['capability']=='storage.app-data' for g in grants))
  self.assertEqual(boot['cohort_migration']['shared_key_value'],[{'application_id':'waterfall','api':1,'namespace':1}])
  self.assertEqual(boot['cohort_migration']['from']['version'],'1.0.2')
  self.assertEqual(boot['cohort_migration']['to']['version'],'1.0.4')
  self.assertIn({'manifest':'s3-radio-iq/manifest.json'},boot['drivers'])
  flags=definitions('waterfall','0.1.2')
  for flag in ('-DPORTABLE_RADIO_SESSION','-DPORTABLE_APP_OWNS_TOUCH_CHROME','-DPORTABLE_APP_SLEEP_LOCAL'):self.assertIn(flag,flags)
 def test_sdr_source_and_resource_authority_are_not_substitutable(self):
  self.record['sdr']['build']['source_revision']='a'*40;self.write_record()
  with self.assertRaisesRegex(ValueError,'SDR target custody'):current.verify(self.art,self.head,self.root)
  self.record['sdr']['build']['source_revision']=self.cfg['sdr']['commit']
  path=self.art/'files/s3-radio-iq/manifest.json';m=json.loads(path.read_bytes());m['requires']=[];path.write_bytes(current.encoded(m));self.record['files']['s3-radio-iq/manifest.json']=current.metadata(path.read_bytes());self.write_record()
  with self.assertRaisesRegex(ValueError,'SDR capability authority'):current.verify(self.art,self.head,self.root)
 def test_new_browser_cannot_replace_prior_files_or_policy(self):
  self.store['file_browser.elf']=b'preexisting'
  with self.assertRaises(ValueError):current.apply(self.store,self.art,self.head,self.root)
  b=copy.deepcopy(self.boot);b['app_capabilities'].append({'manifest':'file_browser.json','grants':[]})
  with self.assertRaises(ValueError):current.configure_boot(b)
 def test_browser_cannot_request_unrestricted_volume(self):
  path=self.art/'files/file_browser.json';m=json.loads(path.read_bytes())
  next(x for x in m['requires'] if x['capability']=='storage.installed-files')['capability']='storage.volume'
  path.write_bytes(current.encoded(m));self.record['files']['file_browser.json']=current.metadata(path.read_bytes());self.write_record()
  with self.assertRaises(ValueError):current.apply(self.store,self.art,self.head,self.root)
 def test_bluetooth_projection_cannot_replace_existing_device(self):
  b={'devices':[{'instance_id':16}]}
  with self.assertRaises(ValueError):current.configure_board(b,self.root,motion_model='bma423',radio_model='sx1262-915')
 def test_explicit_radio_profile_and_no_replacement(self):
  for radio in current.RADIO_MODELS:
   for sensor in ('bma423','bma456h'):
    source=json.loads((ROOT/('hardware/current' if radio=='selectable' else 'hardware')/(radio+'-'+sensor+'.json')).read_text())
    board=current.configure_board({'devices':[],'buses':[]},self.root,motion_model=sensor,radio_model=radio)
    selected=next(x for x in board['devices'] if x['instance_id']==11)
    self.assertEqual(selected,next(x for x in source['devices'] if x['instance_id']==11))
    self.assertEqual(board['buses'],[next(x for x in source['buses'] if x['instance_id']==selected['config']['bus_instance_id'])])
    self.assertEqual(len(board['devices']),3)
  for radio in (None,'915','auto','sx1262-unknown'):
   with self.assertRaises(ValueError):current.configure_board({'devices':[],'buses':[]},self.root,motion_model='bma423',radio_model=radio)
  for board in ({'devices':[{'instance_id':11}],'buses':[]},{'devices':[],'buses':[{'instance_id':104}]}):
   with self.assertRaises(ValueError):current.configure_board(board,self.root,motion_model='bma423',radio_model='sx1262-915')
 def test_lora_authority_and_nested_back(self):
  boot=current.configure_boot(self.boot)
  app=next(x for x in boot['app_capabilities'] if x['manifest']=='lora_messages.json')
  self.assertEqual(len(app['grants']),11)
  self.assertEqual([g['instance_id'] for g in app['grants'] if g['capability']=='storage.key-value'],[9,1])
  self.assertEqual([g for g in app['grants'] if g['capability']=='radio.lora'],[{'capability':'radio.lora','api':2,'instance_id':11}])
  self.assertFalse(any(g['capability']=='radio.lora' for row in boot['app_capabilities'] if row!=app for g in row['grants']))
  flags=definitions('lora_messages','0.1.0')
  for flag in ('-DPORTABLE_RADIO_SESSION','-DPORTABLE_APP_OWNS_TOUCH_CHROME','-DLORA_RETURN_APP="springboard.elf"'):self.assertIn(flag,flags)
  self.assertFalse(any(x.startswith('-DPORTABLE_RETURN_APP=') for x in flags))
 def test_ble_exact_authority_and_owned_chrome(self):
  boot=current.configure_boot(self.boot);self.assertEqual(len(boot['app_capabilities']),20)
  scanner=next(x for x in boot['app_capabilities'] if x['manifest']=='ble_scanner.json')
  self.assertEqual(len(scanner['grants']),9)
  self.assertEqual([g for g in scanner['grants'] if g['capability']=='bluetooth.hci'],[{'capability':'bluetooth.hci','api':1,'instance_id':16}])
  self.assertEqual([g for g in scanner['grants'] if g['capability'].startswith('storage.')],[current.ALARM_PREFERENCES])
  self.assertFalse(any(g['capability']=='radio.lora' for g in scanner['grants']))
  flags=definitions('ble_scanner','0.1.0')
  for flag in ('-DPORTABLE_RADIO_SESSION','-DPORTABLE_APP_OWNS_TOUCH_CHROME','-DPORTABLE_RETURN_APP="springboard.elf"'):self.assertIn(flag,flags)
 def test_spectrum_profile_storage_v2_is_scoped(self):
  boot=current.configure_boot(self.boot)
  spectrum=next(x for x in boot['app_capabilities'] if x['manifest']=='audio_spectrum.json')
  self.assertEqual([g for g in spectrum['grants'] if g['capability']=='storage.key-value'],[{'capability':'storage.key-value','api':2,'instance_id':7},current.ALARM_PREFERENCES])
  self.assertFalse(any(g['capability']=='storage.key-value' and g['api']==2 for row in boot['app_capabilities'] if row!=spectrum for g in row['grants']))
  bad=copy.deepcopy(self.boot);next(x for x in bad['app_capabilities'] if x['manifest']=='audio_spectrum.json')['grants'][0]['instance_id']=9
  with self.assertRaises(ValueError):current.configure_boot(bad)
 def test_app_data_authority_is_distinct_and_bounded(self):
  boot=current.configure_boot(self.boot)
  owners={row['manifest']:[g['instance_id'] for g in row['grants'] if g['capability']=='storage.app-data'] for row in boot['app_capabilities']}
  self.assertEqual({name:ids for name,ids in owners.items() if ids},{'timecard.json':[1],'audio_spectrum.json':[2]})
  timecard=next(row for row in boot['app_capabilities'] if row['manifest']=='timecard.json')
  self.assertIn({'capability':'board.battery','api':1,'instance_id':4},timecard['grants'])
  self.assertFalse(any(g['capability']=='input.navigation' for g in timecard['grants']))
  flags=definitions('timecard','0.1.0')
  for flag in ('-DTIMECARD_APP_DATA','-DPORTABLE_INPUT_NAVIGATION_LOCAL','-DPORTABLE_APP_OWNS_TOUCH_CHROME'):self.assertIn(flag,flags)
  self.assertFalse(any(x.startswith('-DPORTABLE_RETURN_APP=') for x in flags))
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
 def test_original_debug_elf_cannot_be_replaced(self):
  (self.art/'debug/file_browser.elf').write_bytes(b'altered');self.write_record()
  with self.assertRaisesRegex(ValueError,'Original app ELF differs'):current.verify(self.art,self.head,self.root)
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
 def test_continuous_capture_is_only_for_spectrum(self):
  flag='-DPORTABLE_AUDIO_CONTINUOUS_CAPTURE'
  for name in current.APPS:self.assertEqual(flag in definitions(name,'0.4.2'),name=='audio_spectrum')
  self.record['apps']['audio_spectrum']['defines'].remove(flag);self.write_record()
  with self.assertRaisesRegex(ValueError,'continuous capture profile'):
   current.verify(self.art,self.head,self.root)
 def test_other_apps_cannot_inherit_capture_idle_override(self):
  self.record['apps']['settings']['defines'].append('-DPORTABLE_AUDIO_CONTINUOUS_CAPTURE');self.write_record()
  with self.assertRaisesRegex(ValueError,'continuous capture profile'):
   current.verify(self.art,self.head,self.root)
 def test_spectrum_cannot_include_host_fixture_dependencies(self):
  self.record['apps']['audio_spectrum']['target_dependencies']['utilities:tests/fixtures/speech.pcm']={};self.write_record()
  with self.assertRaisesRegex(ValueError,'Host fixture'):
   current.verify(self.art,self.head,self.root)
  browser=definitions('file_browser','1.4.0')
  self.assertIn('-DPORTABLE_FILE_BROWSER_APP',browser)
  self.assertIn('-DPORTABLE_APP_OWNS_TOUCH_CHROME',browser)
  self.assertIn('-DFILE_BROWSER_RETURN_APP="springboard.elf"',browser)
  self.assertFalse(any(x.startswith('-DPORTABLE_RETURN_APP=') for x in browser))
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
  self.assertEqual(paths,{'dist/current-apps/current-apps.zip','dist/current-apps/current-apps-build.json','dist/current-apps/source-profile.json','dist/current-apps/files/','dist/current-apps/debug/','dist/current-apps/licenses/'})
if __name__=='__main__':unittest.main()

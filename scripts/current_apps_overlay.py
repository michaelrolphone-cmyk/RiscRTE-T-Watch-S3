#!/usr/bin/env python3
"""Verified current-app overlay; historical custody stores are never rewritten."""
import copy,hashlib,json,re,zipfile
from pathlib import Path
from compact_current_elf import PROFILE as COMPACTION_PROFILE, OPTIONS as COMPACTION_OPTIONS
ROOT=Path(__file__).resolve().parents[1]
PROFILE='watch-current-apps-v1'
LOW_BATTERY_PROFILE='watch-low-battery-apps-v1'
SYSTEM_APPS=('springboard','settings','wifi_settings','ota_update','app_store','file_browser')
UTILITY_APPS=('battery','calculator','stopwatch','alarms','countdown','frequency_generator','audio_spectrum','lora_messages','ble_scanner','waterfall','ble_touchpad','ble_buttons')
PRODUCTIVITY_APPS=('points_in_time','timecard')
CLOCK_APPS=('default','clock')
NON_CLOCK_APPS=SYSTEM_APPS+UTILITY_APPS+PRODUCTIVITY_APPS
APPS=NON_CLOCK_APPS+CLOCK_APPS
PROVIDERS=('alarm-service','update-fw','update-apps')
NEW_APPS={'waterfall': {'display_name': 'Waterfall', 'icon': 'solid:f0ec'}, 'file_browser': {'display_name': 'Files', 'icon': 'solid:f07c'}, 'lora_messages': {'display_name': 'LoRa Messages', 'icon': 'solid:f27a'}, 'ble_scanner': {'display_name': 'BLE Scanner', 'icon': 'solid:f7c0'}, 'timecard': {'display_name': 'Timecard', 'icon': 'solid:f274'}, 'ble_touchpad': {'display_name': 'BLE Touchpad', 'icon': 'solid:f245'}, 'ble_buttons': {'display_name': 'BLE Buttons', 'icon': 'solid:f11c'}}
RADIO_MODELS=('sx1262-433','sx1262-868','sx1262-915','sx1280-2400','selectable')
ADDED_PAYLOADS={folder+'/'+name for folder in ('ble','imu','lora','s3-radio-iq','ble-hid','ble-sensors','ble-telemetry','battery-telem') for name in ('driver.elf','manifest.json')}|{n+suffix for n in NEW_APPS for suffix in ('.elf','.json')}
PAYLOADS=ADDED_PAYLOADS|{'board.json'}|{folder+'/'+name for folder in ('gpio','pmu') for name in ('driver.elf','manifest.json')}|{n+suffix for n in APPS for suffix in ('.elf','.json')}|{n+'/'+suffix for n in PROVIDERS for suffix in ('driver.elf','manifest.json')}
ALLOWED=PAYLOADS|{'boot.json'}
ALARM_VOLUME={'key':'alarm_volume','namespace':1,'access':'read'}
ALARM_DND={'key':'alert_dnd','namespace':1,'access':'read'}
ALARM_PREFERENCES={'capability':'storage.key-value','api':1,'instance_id':1}
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return (json.dumps(v,indent=2,sort_keys=True)+'\n').encode()
def require(ok,message):
 if not ok:raise ValueError(message)
def metadata(b):return {'size_bytes':len(b),'sha256':sha(b)}
def config(root=ROOT,profile='current'):
 require(profile in ('current','low-battery'),'Unknown application profile')
 path='apps/low-battery-sources.json' if profile=='low-battery' else 'apps/apex-apps-sources.json'
 c=json.loads((Path(root)/path).read_text())
 require(c.get('schema')==1 and c.get('profile')==(LOW_BATTERY_PROFILE if profile=='low-battery' else PROFILE),'Wrong current-app profile')
 if profile=='low-battery':
  require(c.get('features')=={'low_battery':True} and c.get('product_version')=='1.0.7','Low battery must be automatic in the future profile')
  require(set(c.get('source_app_versions',{}))==set(APPS),'Low-battery source versions incomplete')
  baseline=json.loads((Path(root)/'apps/apex-apps-sources.json').read_text())
  for name,version in c['app_versions'].items():
   require(tuple(map(int,version.split('.')))>tuple(map(int,baseline['app_versions'][name].split('.'))),'Rebuilt app requires a new deployment version: '+name)
 require(set(c['sources'])=={'system-apps','utilities','productivity','runtime'},'Current source inventory differs')
 for p in c['sources'].values():require(re.fullmatch('[0-9a-f]{40}',p.get('commit','')) is not None,'Unpinned current source')
 require(c.get('sdr',{}).get('id')=='s3-radio-iq-v1' and re.fullmatch('[0-9a-f]{40}',c['sdr'].get('commit','')) is not None and c['sdr'].get('version')=='0.1.2','Unpinned guarded SDR source')
 require(c.get('hid',{}).get('id')=='ble-hid' and c['hid'].get('commit')==c['sdr']['commit'] and c['hid'].get('version')=='0.1.1','Unpinned consolidated HID source')
 for key,identity in (('ble_sensors','ble-sensors'),('ble_telemetry','ble-telemetry'),('telemetry_battery','telemetry-battery')):
  require(c.get(key,{}).get('id')==identity and c[key].get('commit')==c['sdr']['commit'] and c[key].get('version')=='0.1.0','Unpinned '+identity+' source')
 require(set(c['app_versions'])==set(APPS),'Current app versions incomplete')
 for v in list(c['app_versions'].values())+[c['service_version']]:require(re.fullmatch(r'\d+\.\d+\.\d+',v) is not None,'Bad current version')
 require(c['service_version']=='0.4.2','Expected reviewed CUE/volume/sleep-resume service0.4.2')
 return c

def configure_board(original,root=ROOT,*,motion_model,radio_model):
 b=copy.deepcopy(original)
 require(motion_model in ('bma423','bma456h'),'Explicit supported motion model required')
 require(radio_model in RADIO_MODELS,'Explicit supported radio model/band required')
 folder='hardware/current/' if radio_model=='selectable' else 'hardware/'
 source=json.loads((Path(root)/(folder+radio_model+'-'+motion_model+'.json')).read_text())
 candidates=[d for d in source['devices'] if d['instance_id']==16 and d['compatible']=='espressif,esp32s3-ble']
 require(len(candidates)==1,'Missing canonical Bluetooth hardware')
 require(not any(d['instance_id']==16 for d in b['devices']),'Unexpected prior Bluetooth hardware')
 b['devices'].append(copy.deepcopy(candidates[0]))
 motion=[d for d in source['devices'] if d['instance_id']==7 and d['compatible']=='bosch,bma4xx']
 require(len(motion)==1 and not any(d['instance_id']==7 for d in b['devices']),'Unexpected prior motion hardware')
 require(motion[0]['config']['irq_active_high'] is True and motion[0]['config']['irq_pull_up'] is False,'Motion polarity must match fitted pulldown')
 b['devices'].append(copy.deepcopy(motion[0]))
 radio=[d for d in source['devices'] if d['instance_id']==11 and d['config_type']=='radio.lora']
 require(len(radio)==1 and not any(d['instance_id']==11 for d in b['devices']),'Unexpected prior radio hardware')
 bus=[x for x in source['buses'] if x['instance_id']==radio[0]['config']['bus_instance_id']]
 require(len(bus)==1 and not any(x['instance_id']==bus[0]['instance_id'] for x in b['buses']),'Unexpected prior radio bus')
 b['devices'].append(copy.deepcopy(radio[0]));b['buses'].append(copy.deepcopy(bus[0]))
 return b

def configure_boot(original):
 """Add shared settings/RTC grants explicitly; preserve each existing grant."""
 b=copy.deepcopy(original)
 require(not any(x['manifest'] in {n+'.json' for n in NEW_APPS} for x in b['app_capabilities']),'New application policy unexpectedly preexists')
 b['app_capabilities'].append({'manifest':'file_browser.json','grants':[
  {'capability':'display.output','api':1,'instance_id':5},
  {'capability':'input.touch.raw','api':1,'instance_id':6},
  {'capability':'board.battery','api':1,'instance_id':4},
  {'capability':'storage.installed-files','api':1,'instance_id':0},
  {'capability':'alarm.service','api':1,'instance_id':0}]})
 b['app_capabilities'].append({'manifest':'lora_messages.json','grants':[
  {'capability':'display.output','api':1,'instance_id':5},
  {'capability':'input.touch.raw','api':1,'instance_id':6},
  {'capability':'board.battery','api':1,'instance_id':4},
  {'capability':'radio.lora','api':2,'instance_id':11},
  {'capability':'storage.key-value','api':1,'instance_id':9},
  {'capability':'alarm.service','api':1,'instance_id':0}]})
 b['app_capabilities'].append({'manifest':'ble_scanner.json','grants':[
  {'capability':'display.output','api':1,'instance_id':5},
  {'capability':'input.touch.raw','api':1,'instance_id':6},
  {'capability':'board.battery','api':1,'instance_id':4},
  {'capability':'bluetooth.sensors','api':1,'instance_id':0},
  {'capability':'alarm.service','api':1,'instance_id':0}]})
 b['app_capabilities'].append({'manifest':'timecard.json','grants':[
  {'capability':'display.output','api':1,'instance_id':5},
  {'capability':'input.touch.raw','api':1,'instance_id':6},
  {'capability':'board.battery','api':1,'instance_id':4},
  {'capability':'storage.app-data','api':1,'instance_id':1},
  {'capability':'alarm.service','api':1,'instance_id':0}]})
 b['app_capabilities'].append({'manifest':'waterfall.json','grants':[
  {'capability':'display.output','api':1,'instance_id':5},
  {'capability':'input.touch.raw','api':1,'instance_id':6},
  {'capability':'board.battery','api':1,'instance_id':4},
  {'capability':'radio.iq','api':1,'instance_id':0},
  {'capability':'alarm.service','api':1,'instance_id':0}]})
 for name in ('ble_touchpad','ble_buttons'):
  grants=[{'capability':cap,'api':api,'instance_id':instance} for cap,api,instance in [('display.output',1,5),('input.touch.raw',1,6),('board.battery',1,4),('bluetooth.hid',1,0),('alarm.service',1,0)]]
  if name=='ble_buttons':grants.append({'capability':'storage.key-value','api':1,'instance_id':11})
  b['app_capabilities'].append({'manifest':name+'.json','grants':grants})
 spectrum=next(x for x in b['app_capabilities'] if x['manifest']=='audio_spectrum.json')
 storage=[g for g in spectrum['grants'] if g['capability']=='storage.key-value']
 require(storage==[{'capability':'storage.key-value','api':1,'instance_id':7}],'Unexpected prior Spectrum namespace')
 storage[0]['api']=2
 spectrum['grants'].append({'capability':'storage.app-data','api':1,'instance_id':2})
 rows=[x for x in b['app_capabilities'] if x['manifest']=='alarms.json'];require(len(rows)==1,'Missing/duplicate Alarms policy')
 grants=rows[0]['grants'];kv=[x for x in grants if x['capability']=='storage.key-value']
 require(kv==[{'capability':'storage.key-value','api':1,'instance_id':3}],'Unexpected prior Alarms storage policy')
 grants.insert(next(i for i,x in enumerate(grants) if x['capability']=='alarm.service'),copy.deepcopy(ALARM_PREFERENCES))
 rows=[x for x in b['drivers'] if x['manifest']=='alarm-service/manifest.json'];require(len(rows)==1,'Missing/duplicate alarm provider')
 keys=rows[0]['key_value'];require(len(keys)==7 and not any(x['key']=='alarm_volume' for x in keys),'Unexpected prior bound service policy')
 expected={'alarm_cfg':(3,'read'),'timer_cfg':(3,'read'),'alarm_occ':(4,'read-write'),'timer_occ':(4,'read-write'),'alert_mode':(1,'read'),'points_cfg':(5,'read'),'points_occ':(4,'read-write')}
 require({x['key']:(x['namespace'],x['access']) for x in keys}==expected,'Legacy service bindings differ')
 keys.append(copy.deepcopy(ALARM_VOLUME));keys.append(copy.deepcopy(ALARM_DND))
 require(not any(x.get('instance_id')==16 for x in b['drivers']),'Unexpected prior Bluetooth provider')
 b['drivers'].append({'manifest':'ble/manifest.json','instance_id':16})
 require(not any(x.get('instance_id')==7 for x in b['drivers']),'Unexpected prior motion provider')
 b['drivers'].append({'manifest':'imu/manifest.json','instance_id':7})
 require(not any(x.get('instance_id')==11 for x in b['drivers']),'Unexpected prior radio provider')
 b['drivers'].append({'manifest':'lora/manifest.json','instance_id':11})
 require(not any(x['manifest']=='s3-radio-iq/manifest.json' for x in b['drivers']),'Unexpected prior SDR provider')
 b['drivers'].append({'manifest':'s3-radio-iq/manifest.json'})
 require(not any(x['manifest']=='ble-hid/manifest.json' for x in b['drivers']),'Unexpected prior HID provider')
 b['drivers'].append({'manifest':'ble-hid/manifest.json','key_value':[{'key':key,'namespace':10,'access':'read-write'} for key in ('hid_ours','hid_peer','hid_ccc','hid_identity')]})
 for manifest in ('ble-sensors/manifest.json','battery-telem/manifest.json','ble-telemetry/manifest.json'):
  require(not any(x['manifest']==manifest for x in b['drivers']),'Unexpected prior BLE sensor/telemetry provider')
  b['drivers'].append({'manifest':manifest})
 for row in b['app_capabilities']:
  if row['manifest'] in {n+'.json' for n in APPS}:
   for grant in (ALARM_PREFERENCES,{'capability':'rtc.clock','api':2,'instance_id':8},{'capability':'net.wifi','api':1,'instance_id':15},{'capability':'bluetooth.hci','api':1,'instance_id':16},{'capability':'motion.accel','api':1,'instance_id':7}):
    if grant not in row['grants']:row['grants'].append(copy.deepcopy(grant))
  require(len(row['grants'])<=12,'Current application exceeds Runtime grant bound')
 b['cohort_migration']={'schema':1,'from':{'product':'twatch-s3','version':'1.0.4','source_revision':'674729dbade10c15368731745844e6dc2f6ebd0b'},'to':{'product':'twatch-s3','version':'1.0.5'},'shared_key_value':[{'application_id':name,'api':1,'namespace':1} for name in ('ble_touchpad','ble_buttons')]}
 return b

def verify(artifact,head,root=ROOT,profile='current'):
 artifact=Path(artifact);c=config(root,profile=profile);r=json.loads((artifact/'current-apps-build.json').read_text())
 require(r.get('schema')==1 and r.get('profile')==c['profile'] and r.get('watch_source')==head,'Current overlay identity/head mismatch')
 require(r.get('configuration')==c,'Current overlay source/version configuration differs')
 require(set(r['files'])==PAYLOADS and set(r['apps'])==set(APPS),'Current payload inventory differs')
 require(r.get('target_validation') is True,'Current target validation missing')
 require(set(r.get('debug',{}))=={n+'.elf' for n in APPS},'Original app ELF inventory differs')
 files={}
 for name,meta in r['files'].items():
  b=(artifact/'files'/name).read_bytes();require(metadata(b)==meta,'Current payload hash/size differs: '+name);files[name]=b
 for name in APPS:
  m=json.loads(files[name+'.json']);a=r['apps'][name]
  require(m['version']==c['app_versions'][name] and a['version']==m['version'],'Current app version mismatch: '+name)
  require(m['file_name']==name+'.elf' and m['entry']=='app_main' and m['architecture']=='xtensa-esp32s3','Current app ABI mismatch')
  compact=a.get('compaction',{})
  require(compact.get('profile')==COMPACTION_PROFILE and compact.get('retained_loader_sections_symbols_relocations_unchanged') is True and compact.get('original_elf_retained') is True and compact.get('options')==list(COMPACTION_OPTIONS) and bool(compact.get('tool')),'Missing current ELF compaction contract: '+name)
  debug=(artifact/'debug'/(name+'.elf')).read_bytes()
  require(metadata(debug)==r['debug'][name+'.elf'] and len(debug)==compact.get('before_bytes') and sha(debug)==compact.get('before_sha256'),'Original app ELF differs: '+name)
  require(compact.get('after_bytes')==len(files[name+'.elf']) and compact.get('after_sha256')==sha(files[name+'.elf']) and len(debug)>=compact['after_bytes'],'Current ELF compaction hashes differ: '+name)
  require(a['sha256']==sha(files[name+'.elf']) and a['size_bytes']==len(files[name+'.elf']),'Current app build record differs')
  require(('-DPORTABLE_LOW_BATTERY' in a['defines'])==(profile=='low-battery'),'Low battery profile enablement differs: '+name)
  require('-DWATCH_ALARM_SLEEP_RESUME' in a['defines'],'Current alarm sleep resume boundary missing: '+name)
  require(('-DWATCH_MOTION_WAKE' if name in CLOCK_APPS else '-DPORTABLE_MOTION_WAKE') in a['defines'],'Current motion wake client missing: '+name)
  require(('-DWATCH_CLOCK_ALARMS' if name in CLOCK_APPS else '-DPORTABLE_ALARM_CLIENT') in a['defines'],'Current CUE client missing: '+name)
  require(('-DPORTABLE_AUDIO_CONTINUOUS_CAPTURE' in a['defines']) == (name == 'audio_spectrum'),'Current continuous capture profile differs: '+name)
  require(('-DPORTABLE_CATALOG_LIMIT=20' in a['defines']) == (name == 'springboard'),'Current launcher catalog profile differs: '+name)
  if name=='audio_spectrum':
   dependencies=a.get('target_dependencies',{})
   require(a.get('host_fixture_excluded') is True and isinstance(dependencies,dict) and bool(dependencies),'Spectrum target input closure missing')
   require(all(isinstance(k,str) and ':' in k and not {'test','tests','fixtures'} & set(Path(k.split(':',1)[1]).parts) for k in dependencies),'Host fixture entered Spectrum build inputs')
  if name not in CLOCK_APPS:require('-DPORTABLE_NOVA_UI' in a['defines'],'Current Nova profile missing: '+name)
 clock=r['clock'];require(clock['watch_source']==head and clock['sources']==c['sources'] and clock['paired_boot_confirmation'] is True,'Current Clock source/profile mismatch')
 require(set(clock['files'])=={n+e for n in CLOCK_APPS for e in ('.elf','.json')},'Current Clock inventory differs')
 for name,meta in clock['files'].items():require(metadata(files[name])==meta,'Current Clock artifact differs: '+name)
 require(clock['headers']==r['service']['points_headers'],'Current Clock/service schema mismatch')
 require(isinstance(clock.get('source_sha256'),dict) and bool(clock['source_sha256']),'Current Clock source hashes missing')
 for name,digest in clock['source_sha256'].items():
  require(not Path(name).is_absolute() and '..' not in Path(name).parts and re.fullmatch('[0-9a-f]{64}',digest) is not None,'Unsafe Clock source hash entry')
  require((Path(root)/name).is_file() and sha((Path(root)/name).read_bytes())==digest,'Current Clock source bytes differ: '+name)
 sdr=r.get('sdr',{});require({k:sdr.get(k) for k in c['sdr']}==c['sdr'],'Current SDR source identity differs')
 built=sdr.get('build',{});require(built.get('source_revision')==c['sdr']['commit'] and built.get('sha256')==sha(files['s3-radio-iq/driver.elf']) and built.get('size_bytes')==len(files['s3-radio-iq/driver.elf']),'Current SDR target custody differs')
 require(re.fullmatch('[0-9a-f]{64}',sdr.get('resource_header_sha256','')) is not None,'SDR resource ABI proof missing')
 iq_manifest=json.loads(files['s3-radio-iq/manifest.json'])
 require(iq_manifest.get('id')==c['sdr']['id'] and iq_manifest.get('version')==c['sdr']['version'] and iq_manifest.get('requires')==[{'capability':'platform.radio.iq.resource','api':1}] and iq_manifest.get('provides')==[{'capability':'radio.iq','api':1}],'SDR capability authority differs')
 hid=r.get('hid',{});require({k:hid.get(k) for k in c['hid']}==c['hid'],'Current HID source identity differs')
 built=hid.get('build',{});require(built.get('source_revision')==c['hid']['commit'] and built.get('sha256')==sha(files['ble-hid/driver.elf']) and built.get('size_bytes')==len(files['ble-hid/driver.elf']),'Current HID target custody differs')
 require(re.fullmatch('[0-9a-f]{64}',hid.get('api_header_sha256','')) is not None,'HID public ABI proof missing')
 hid_manifest=json.loads(files['ble-hid/manifest.json']);require(hid_manifest.get('id')=='ble-hid' and hid_manifest.get('version')==c['hid']['version'] and hid_manifest.get('requires')==[{'capability':cap,'api':1} for cap in ('bluetooth.hci','platform.clock','storage.key-value.bound')] and hid_manifest.get('provides')==[{'capability':'bluetooth.hid','api':1}],'HID capability authority differs')
 ble_components=r.get('ble_components',{})
 for key,folder,provided in (('ble_sensors','ble-sensors','bluetooth.sensors'),('ble_telemetry','ble-telemetry','bluetooth.telemetry'),('telemetry_battery','battery-telem','sensor.telemetry')):
  meta=ble_components.get(key,{});require({k:meta.get(k) for k in c[key]}==c[key],'Current '+folder+' source identity differs')
  built=meta.get('build',{});require(built.get('source_revision')==c[key]['commit'] and built.get('sha256')==sha(files[folder+'/driver.elf']) and built.get('size_bytes')==len(files[folder+'/driver.elf']),'Current '+folder+' target custody differs')
  manifest=json.loads(files[folder+'/manifest.json']);require(manifest.get('id')==c[key]['id'] and manifest.get('version')==c[key]['version'] and manifest.get('provides')==[{'capability':provided,'api':1}],'Current '+folder+' capability authority differs')
 require(json.loads(files['alarm-service/manifest.json'])['version']==c['service_version'],'Current alarm version mismatch')
 require(r['service']['defines']==['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER','-DALARM_VOLUME_CONTROL','-DALARM_DND_CONTROL'],'Wrong current service profile')
 archive=artifact/'current-apps.zip';require(archive.is_file(),'Current archive missing')
 with zipfile.ZipFile(archive) as z:
  names=z.namelist();require(len(names)==len(set(names)),'Duplicate current archive members')
  expected={'current-apps-build.json','source-profile.json'}|{'files/'+n for n in PAYLOADS}|{'debug/'+n+'.elf' for n in APPS}|{p.relative_to(artifact).as_posix() for p in (artifact/'licenses').rglob('*') if p.is_file()}
  require(set(names)==expected,'Current archive inventory differs')
  for name in names:require(z.read(name)==(artifact/name).read_bytes(),'Current archive/member differs: '+name)
 require(json.loads((artifact/'source-profile.json').read_text())==c,'Current source profile differs')
 return files,r

def apply(store,artifact,head,root=ROOT):
 """Input has already passed historical archive and paired Clock verification."""
 files,r=verify(artifact,head,root);before=dict(store)
 require(set(PAYLOADS)-ADDED_PAYLOADS<=set(before),'Current overlay existing file set differs')
 require(not (ADDED_PAYLOADS&set(before)),'Current overlay added files unexpectedly preexist')
 require(json.loads(before['board.json'])==r['baseline_board'],'Current overlay original board differs')
 require(json.loads(files['board.json'])==configure_board(r['baseline_board'],root,motion_model=r.get('motion_model'),radio_model=r.get('radio_model')),'Current Bluetooth board projection differs')
 require(json.loads(before['boot.json'])==r['baseline_boot'],'Unexpected policy change before current overlay')
 after=dict(before);after.update(files);after['boot.json']=encoded(configure_boot(r['baseline_boot']))
 require(set(before)|ADDED_PAYLOADS==set(after),'Current overlay added/removed unexpected store members')
 for name,b in before.items():
  if name not in ALLOWED:require(after[name]==b,'Current overlay changed unrelated payload: '+name)
 require(json.loads(after['boot.json'])==r['boot'],'Current overlay boot proof mismatch')
 # Manifest requirements must match configured grants, with KV namespaces
 # declared once in the manifest and independently scoped in the boot policy.
 for row in r['boot']['app_capabilities']:
  if row['manifest'] not in after:continue
  m=json.loads(after[row['manifest']]);expected={(g['capability'],g['api']) for g in row['grants']}
  require({(q['capability'],q['api']) for q in m['requires']}==expected,'Current manifest/grant mismatch: '+row['manifest'])
 provenance={'schema':1,'profile':PROFILE,'watch_source':head,'sources':r['configuration']['sources'],'configuration':r['configuration'],'build_record':r,'build_record_sha256':sha((Path(artifact)/'current-apps-build.json').read_bytes()),'archive_sha256':sha((Path(artifact)/'current-apps.zip').read_bytes()),'files':{n:metadata(after[n]) for n in sorted(ALLOWED)},'preserved_files':{n:metadata(b) for n,b in sorted(before.items()) if n not in ALLOWED},'catalog':r['catalog'],'all_current_clients_cue_aware':True}
 return after,provenance

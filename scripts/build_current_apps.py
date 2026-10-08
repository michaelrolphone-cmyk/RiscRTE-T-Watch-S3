#!/usr/bin/env python3
"""Build the explicit final current-app cohort, separate from frozen custody lanes."""
import argparse,hashlib,json,os,shlex,shutil,subprocess,sys
from pathlib import Path
from current_apps_overlay import (ROOT,PROFILE,APPS,NON_CLOCK_APPS,CLOCK_APPS,SYSTEM_APPS,UTILITY_APPS,PAYLOADS,NEW_APPS,
                                 RADIO_MODELS,PROFILES,rf_enabled,power_enabled,automatic_low_battery,config,payloads,configure_boot,configure_board,metadata,encoded,require,verify)
from audio_overlay import verify as verify_audio
from compact_current_elf import compact
from build_wifi_common import read_zip,zip_bytes

def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
def clean(path,expected):
 require(git(path,'rev-parse','HEAD')==expected,'Current source pin differs: '+str(path))
 require(not git(path,'status','--porcelain','--untracked-files=no'),'Current source is dirty: '+str(path))
def definitions(name,version,low_battery=False,*,rf_spectrum=False,runtime_features=False):
 require(not rf_spectrum or low_battery,'RF profile requires automatic low battery')
 feature_flags=(['-DPORTABLE_LOW_BATTERY'] if low_battery else [])+(['-DWATCH_RUNTIME_FEATURES','-DWATCH_BLE_BROADCAST'] if runtime_features and name in CLOCK_APPS else ['-DPORTABLE_BLE_BROADCAST'] if runtime_features else [])
 if name in CLOCK_APPS:return feature_flags+['-DWATCH_CLOCK_LAUNCHER','-DWATCH_CLOCK_ALARMS','-DWATCH_CLOCK_POINTS','-DPORTABLE_RTC_UTC8_DENVER','-DWATCH_PAIRED_BOOT_CONFIRM','-DWATCH_QUICK_ACTIONS','-DWATCH_QUICK_RADIOS','-DWATCH_MOTION_WAKE','-DWATCH_ALARM_SLEEP_RESUME']+(['-DWATCH_CLOCK_RETURN'] if name=='clock' else [])
 flags=feature_flags+['-DPORTABLE_TOUCH_ROTATION=0','-DPORTABLE_RTC_UTC8_DENVER','-DPORTABLE_FORCE_FULL_FRAMES',
        '-DPORTABLE_INPUT_NAVIGATION','-DPORTABLE_INPUT_NAVIGATION_LOCAL','-DPORTABLE_APP_SLEEP_LOCAL','-DPORTABLE_ALARM_CLIENT','-DPORTABLE_QUICK_ACTIONS','-DPORTABLE_QUICK_RADIOS','-DPORTABLE_MOTION_WAKE','-DWATCH_ALARM_SLEEP_RESUME']
 flags+=['-DPORTABLE_NOVA_UI']
 if name in ('frequency_generator','audio_spectrum'):flags+=['-DPORTABLE_AUDIO_SESSION']
 if runtime_features and name in ('ble_scanner','ble_touchpad','ble_buttons','waterfall'):flags+=['-DPORTABLE_BLE_FOREGROUND']
 if name in ('lora_messages','ble_scanner','waterfall','ble_touchpad','ble_buttons'):flags+=['-DPORTABLE_RADIO_SESSION','-DPORTABLE_APP_OWNS_TOUCH_CHROME']
 if name=='audio_spectrum':flags+=['-DPORTABLE_APP_OWNS_TOUCH_CHROME','-DPORTABLE_AUDIO_CONTINUOUS_CAPTURE']
 if name=='timecard':flags+=['-DTIMECARD_APP_DATA','-DPORTABLE_APP_OWNS_TOUCH_CHROME']
 if name=='file_browser':flags+=['-DPORTABLE_FILE_BROWSER_APP','-DPORTABLE_APP_OWNS_TOUCH_CHROME']
 if name=='settings':flags+=['-DPORTABLE_SETTINGS_APP','-DPORTABLE_TAP_SETTINGS','-DPORTABLE_SLEEP_SETTINGS','-DPORTABLE_ALARM_SETTINGS','-DPORTABLE_SETTINGS_VERSION="'+version+'"']
 if name=='wifi_settings':flags+=['-DPORTABLE_WIFI_SETTINGS_APP','-DPORTABLE_WIFI_STORAGE_INSTANCE=6','-DPORTABLE_WIFI_INSTANCE=15','-DPORTABLE_WIFI_VERSION="'+version+'"']
 if name in ('ota_update','app_store'):flags+=['-Wno-misleading-indentation','-DPORTABLE_UPDATE_APP','-DPORTABLE_UPDATE_FIRMWARE='+str(int(name=='ota_update')),'-DPORTABLE_WIFI_INSTANCE=15','-DPORTABLE_UPDATE_RTC_UTC_OFFSET_SECONDS=28800']
 if name=='springboard':flags+=['-DPORTABLE_RETAINED_RGB565_HANDOFF','-DPORTABLE_HANDOFF_EAGER_MS=60','-DPORTABLE_CATALOG_LIMIT=20']
 if name=='waterfall' and rf_spectrum:
  if runtime_features:flags+=['-DPORTABLE_RADIO_CONTINUOUS_CAPTURE']
  return flags+['-DRF_STORAGE_INSTANCE=13','-DRF_APP_DATA_INSTANCE=3','-DRF_RETURN_APP="springboard.elf"','-DPORTABLE_APP_LAUNCH_GUARD']
 owner=('BATTERY_RETURN_APP' if name=='battery' else 'LORA_RETURN_APP' if name=='lora_messages' else 'FILE_BROWSER_RETURN_APP' if name=='file_browser' else 'POINTS_RETURN_APP' if name=='points_in_time' else 'WIFI_RETURN_APP' if name=='wifi_settings' else 'UPDATE_RETURN_APP' if name in ('ota_update','app_store') else 'CALCULATOR_RETURN_APP' if name=='calculator' else 'ALARM_RETURN_APP' if name in ('alarms','countdown') else 'PORTABLE_RETURN_APP')
 if name=='battery':flags+=['-DPORTABLE_POWER_STATUS']
 if name=='timecard':return flags
 flags+=['-D'+owner+'="'+('clock.elf' if name=='springboard' else 'springboard.elf')+'"']
 return flags

def application_inputs(name,source,repos,root,out,profile='current'):
 sources=[source,repos['system-apps']/'lib/PortableApps/src/adapter.c',out/('catalog.c' if name=='springboard' else 'empty_catalog.c'),root/'apps/clock/portable_navigation.c',root/'apps/clock/portable_sleep.c']
 sources+=[repos['system-apps']/'lib/PortableApps/src'/n for n in ('quick_actions.c','quick_render.c','quick_session.c','quick_radios.c')]
 if name=='springboard' or (name=='waterfall' and rf_enabled(profile)):sources+=[repos['system-apps']/'lib/NativeApps/src/SingleFloatDivisionCompat.c']
 includes=[repos['system-apps']/'lib/PortableApps/include',repos['system-apps']/'lib/NativeApps/include',repos['system-apps']/'Apps',repos['utilities']/'Apps',repos['utilities']/'lib/Alarm/include',root/'sdk/app',root/'sdk/driver',root/'include']
 if name=='timecard':includes+=[repos['productivity']/'lib/PortableTimecard/include',repos['productivity']/'lib/NativeApps/include']
 if name in ('ble_scanner','ble_touchpad','ble_buttons'):includes+=[repos['utilities']/'lib/Bluetooth/include']
 allowed={'risc_runtime_get_api','memcpy','memset','memcmp','strcmp','strlen','snprintf','malloc','calloc','free','strcpy'}
 if name=='file_browser':allowed|={'strncmp','strrchr','memchr'}
 return sources,includes,allowed

def build(system,utilities,productivity,runtime,baseline,out,root=ROOT,baseline_root=None,motion_model=None,radio_model=None,drivers=None,profile='current'):
 require(motion_model in ('bma423','bma456h'),'Explicit --motion-model required; do not infer from earlier boots')
 require(radio_model in RADIO_MODELS,'Explicit --radio-model required; do not infer RF band')
 root=Path(root).resolve();out=Path(out).resolve();repos={'system-apps':Path(system).resolve(),'utilities':Path(utilities).resolve(),'productivity':Path(productivity).resolve(),'runtime':Path(runtime).resolve()};c=config(root,profile=profile)
 if power_enabled(profile):
  from power_watch_candidate import checked_source
  checked_source(root)
 for name,path in repos.items():clean(path,c['sources'][name]['commit'])
 require(drivers is not None,'Exact SDR driver source required')
 drivers=Path(drivers).resolve();clean(drivers,c['sdr']['commit'])
 require(not out.exists() or not any(out.iterdir()),'Current output must be empty to reject stale files')
 out.mkdir(parents=True,exist_ok=True);files_dir=out/'files';files_dir.mkdir();debug_dir=out/'debug';debug_dir.mkdir()
 # Decode a separately verified immutable baseline only to reuse exact catalog,
 # app identities and existing boot authority. Never modify that archive.
 baseline=Path(baseline)
 if power_enabled(profile):
  from power_repair_profile import baseline_inputs
  raw=baseline_inputs(baseline,root)
 elif baseline_root is not None:
  baseline_root=Path(baseline_root);clean(baseline_root,'2a4fbae8fb2425bf830c302863a5e195106e77c9')
  subprocess.run([sys.executable,'-c',"import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]+'/scripts');from audio_overlay import verify;verify(Path(sys.argv[2]),root=Path(sys.argv[1]))",str(baseline_root.resolve()),str(baseline.resolve())],check=True)
  clean(baseline_root,'2a4fbae8fb2425bf830c302863a5e195106e77c9')
 else:verify_audio(baseline,root=root)
 if not power_enabled(profile):raw=read_zip(baseline)
 store={n[6:]:b for n,b in raw.items() if n.startswith('store/')}
 require(len([n for n in store if n.endswith('.elf') and '/' not in n])==15,'Unexpected baseline app inventory')
 boot=json.loads(store['boot.json']);new_boot=configure_boot(boot,profile)
 catalog=json.loads(raw['shared/catalog.json'])
 require({x['file_name'] for x in catalog}==({n+'.elf' for n in NON_CLOCK_APPS if n not in NEW_APPS}-{'springboard.elf'})|{'clock.elf'},'Baseline catalog inventory differs')
 require(len(catalog)==13 and len({x['icon'] for x in catalog})==13,'Baseline launcher icons collide')
 for name,entry in NEW_APPS.items():catalog.append({**entry,'file_name':name+'.elf'})
 require(len(catalog)==len(APPS)-2 and len(catalog)<=20 and len({x['icon'] for x in catalog})==len(catalog),'Current launcher inventory/icons exceed the reviewed bound')
 registry=json.loads((repos['system-apps']/'lib/PortableApps/catalog-icons.json').read_text())['apps']
 additional=json.loads((repos['system-apps']/'lib/PortableApps/additional-icons.json').read_text())
 for name,entry in NEW_APPS.items():
  if name=='timecard':require(entry['icon']=='solid:f274' and additional.get(entry['icon'])=='calendar-check','Timecard glyph is not in the reviewed subset')
  elif name in ('waterfall','ble_touchpad','ble_buttons'):require(entry['icon']=={'waterfall':'solid:f0ec','ble_touchpad':'solid:f245','ble_buttons':'solid:f11c'}[name] and entry['icon'] in json.loads((repos['system-apps']/'lib/PortableApps/fonts/SOURCES.json').read_text())['icons'],'Waterfall glyph missing from pinned subset')
  else:require(registry.get(name,{}).get('icon')==entry['icon'],'New app icon is not in the reviewed registry: '+name)
 for app_name,entry in registry.items():
  if app_name not in APPS:continue
  delivered=[x for x in catalog if x['file_name']==app_name+'.elf'];require(len(delivered)==1 and delivered[0]['icon']==entry['icon'],'Current icon registry mismatch: '+app_name)
 (out/'catalog.c').write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={'+','.join('{'+','.join('.'+k+'='+json.dumps(v) for k,v in sorted(x.items()))+',.compatible=true}' for x in catalog)+'};\nconst unsigned portable_catalog_count='+str(len(catalog))+';\n')
 (out/'empty_catalog.c').write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[1]={{.compatible=false}};\nconst unsigned portable_catalog_count=0;\n')
 cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc');require(cc,'Pinned TWATCH_CC required')
 compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];require('8.4.0' in compiler,'Wrong target compiler')
 validator=out/'validate-elf'
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-I'+str(repos['system-apps']/'test/native_apps/stubs'),'-I'+str(repos['system-apps']/'lib/elf_loader/include'),str(repos['system-apps']/'lib/elf_loader/src/esp_elf_validate.c'),str(repos['system-apps']/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True)
 def compile_target(name,sources,flags,includes,exports,allowed):
  dependency_proof={}
  if name=='audio_spectrum' or (rf_enabled(profile) and name=='waterfall'):
   for source in sources:
    output=subprocess.check_output([cc,'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM',*flags,*['-I'+str(p) for p in includes],str(source)],text=True)
    for item in shlex.split(output.replace('\\\n',' ').split(':',1)[1]):
     path=Path(item).resolve();require(path.is_file(),'Missing target dependency: '+item)
     require(not {'test','tests','fixtures'} & set(path.parts),'Host fixture entered target dependency closure: '+item)
     owners=[(repo_name,path.relative_to(repo)) for repo_name,repo in {**repos,'watch':root,'generated':out}.items() if path.is_relative_to(repo)]
     require(owners,'Unowned target dependency: '+item)
     repo_name,relative=owners[-1];dependency_proof[repo_name+':'+relative.as_posix()]=metadata(path.read_bytes())
  mapping=out/(name+'.map');mapping.write_text('{ global: '+'; '.join(sorted(exports))+'; local: *; };\n');elf=out/(name+'.elf')
  subprocess.run([cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror',*flags,*['-I'+str(p) for p in includes],*map(str,sources),'-lgcc','-o',str(elf)],check=True)
  if name in APPS:subprocess.run([str(validator),str(elf)],check=True)
  compact_proof=compact(elf,cc,debug_path=debug_dir/(name+'.elf')) if name in APPS else None
  symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True);imports={l.split()[-1] for l in symbols.splitlines() if ' U ' in ' '+l};actual={l.split()[-1] for l in symbols.splitlines() if len(l.split())>=3 and l.split()[-2] in ('T','D','B','R')}
  require(imports<=allowed and actual==exports,'Current ABI imports/exports differ: '+name+' '+str(sorted(imports-allowed)))
  subprocess.run([str(validator),str(elf)],check=True);b=elf.read_bytes();require(b[:7]==b'\x7fELF\x01\x01\x01' and b[16:20]==b'\x03\x00\x5e\x00','Wrong target ELF')
  return b,{**metadata(b),'imports':sorted(imports),'exports':sorted(exports),'defines':flags,'compaction':compact_proof,**({'target_dependencies':dependency_proof,'host_fixture_excluded':True} if dependency_proof else {})}
 record={'schema':1,'profile':c['profile'],'watch_source':git(root,'rev-parse','HEAD'),'configuration':c,'compiler':compiler,'target_validation':True,'baseline_boot':boot,'boot':new_boot,'catalog':catalog,'baseline_sha256':raw['power-baseline-sha256'].decode() if power_enabled(profile) else hashlib.sha256(baseline.read_bytes()).hexdigest(),'apps':{},'providers':{},'files':{}}
 record['motion_model']=motion_model;record['radio_model']=radio_model
 if power_enabled(profile):
  if profile=='runtime-features':
   from runtime_features_profile import runtime_requirements,STORAGE
  else:
   from power_repair_profile import runtime_requirements,STORAGE,cutoff_selection
   record['cutoff_selection']=cutoff_selection(root)
  record['runtime_requirements']=runtime_requirements(root);record['rf_storage']=dict(STORAGE)
  record['baseline_artifact']=metadata(baseline.read_bytes())
 elif rf_enabled(profile):
  from rf_spectrum_profile import runtime_requirements,STORAGE
  record['runtime_requirements']=runtime_requirements(root);record['rf_storage']=dict(STORAGE)
 record['baseline_board']=json.loads(store['board.json']);record['board']=configure_board(record['baseline_board'],root,motion_model=motion_model,radio_model=radio_model)
 (files_dir/'board.json').write_bytes(encoded(record['board']))
 if power_enabled(profile):
  clean(root,record['watch_source'])
  subprocess.run([sys.executable,str(root/'scripts/build_twatch_drivers.py')],check=True)
  from power_repair_profile import driver_custody
  record['power_drivers']=driver_custody(root)
 for driver,folder in [('twatch-ble','ble'),('twatch-imu','imu'),('twatch-gpio','gpio'),('twatch-pmu','pmu'),('twatch-lora','lora')]+([('twatch-panel','panel')] if power_enabled(profile) else []):
  dest=files_dir/folder;dest.mkdir()
  (dest/'driver.elf').write_bytes((root/'dist'/driver/'driver.elf').read_bytes())
  (dest/'manifest.json').write_bytes(encoded(json.loads((root/'drivers'/driver.replace('-','_')/'manifest.json').read_text())))
  subprocess.run([str(validator),str(dest/'driver.elf')],check=True)
 if automatic_low_battery(profile):
  source=root/'drivers/current/twatch_touch';dest=files_dir/'touch';dest.mkdir()
  content,touch_proof=compile_target('twatch-touch-current',[source/'driver.c'],[],[root/'sdk/driver',root/'include'],{'t5_driver_get'},{'memcpy','memset','strcmp','strlen'})
  (dest/'driver.elf').write_bytes(content);(dest/'manifest.json').write_bytes(encoded(json.loads((source/'manifest.json').read_text())))
  record['touch']={**touch_proof,'source_sha256':hashlib.sha256((source/'driver.c').read_bytes()).hexdigest()}
 subprocess.run([sys.executable,str(drivers/'scripts/build_s3_radio_iq_v1.py')],env={**os.environ,'NATIVE_DRIVER_CC':cc},check=True)
 sdr=drivers/'dist/s3-radio-iq-v1';dest=files_dir/'s3-radio-iq';dest.mkdir()
 source_manifest=json.loads((drivers/'Drivers/s3_radio_iq_v1/manifest.json').read_text())
 require(source_manifest['id']==c['sdr']['id'] and source_manifest['version']==c['sdr']['version'],'SDR package identity differs')
 require(json.loads((sdr/'manifest.json').read_text())==source_manifest,'SDR built manifest differs')
 for name in ('driver.elf','manifest.json'):(dest/name).write_bytes((sdr/name).read_bytes())
 subprocess.run([str(validator),str(dest/'driver.elf')],check=True)
 record['sdr']={**c['sdr'],'build':json.loads((sdr/'build-record.json').read_text()),'resource_header_sha256':hashlib.sha256((drivers/'sdk/driver/RiscRadioIqResourceV1.h').read_bytes()).hexdigest()}
 require((drivers/'sdk/driver/RiscRadioIqResourceV1.h').read_bytes()==(repos['runtime']/'sdk/driver/RiscRadioIqResourceV1.h').read_bytes(),'Runtime/driver SDR resource ABI differs')
 subprocess.run([sys.executable,str(drivers/'scripts/build_ble_hid.py')],env={**os.environ,'NATIVE_DRIVER_CC':cc},check=True)
 hid=drivers/'dist/ble-hid';dest=files_dir/'ble-hid';dest.mkdir()
 source_manifest=json.loads((drivers/'Drivers/ble_hid/manifest.json').read_text())
 require(source_manifest['id']==c['hid']['id'] and source_manifest['version']==c['hid']['version'],'HID package identity differs')
 require(json.loads((hid/'manifest.json').read_text())==source_manifest,'HID built manifest differs')
 for name in ('driver.elf','manifest.json'):(dest/name).write_bytes((hid/name).read_bytes())
 subprocess.run([str(validator),str(dest/'driver.elf')],check=True)
 header=drivers/'sdk/driver/RiscBluetoothHidV1.h';require(header.read_bytes()==(repos['utilities']/'lib/Bluetooth/include/RiscBluetoothHidV1.h').read_bytes(),'HID driver/app ABI differs')
 record['hid']={**c['hid'],'build':json.loads((hid/'build-record.json').read_text()),'api_header_sha256':hashlib.sha256(header.read_bytes()).hexdigest()}
 subprocess.run([sys.executable,str(drivers/'scripts/build_ble_sensors.py')],env={**os.environ,'NATIVE_DRIVER_CC':cc},check=True)
 record['ble_components']={}
 for key,identity,folder in (('ble_sensors','ble-sensors','ble-sensors'),('ble_telemetry','ble-telemetry','ble-telemetry'),('telemetry_battery','telemetry-battery','battery-telem')):
  package=drivers/'dist'/identity;dest=files_dir/folder;dest.mkdir()
  source_manifest=json.loads((drivers/'Drivers'/identity.replace('-','_')/'manifest.json').read_text())
  require(source_manifest['id']==c[key]['id'] and source_manifest['version']==c[key]['version'],'BLE component identity differs: '+identity)
  require(json.loads((package/'manifest.json').read_text())==source_manifest,'BLE component built manifest differs: '+identity)
  for filename in ('driver.elf','manifest.json'):(dest/filename).write_bytes((package/filename).read_bytes())
  subprocess.run([str(validator),str(dest/'driver.elf')],check=True)
  record['ble_components'][key]={**c[key],'build':json.loads((package/'build-record.json').read_text())}
 sensor_header=drivers/'sdk/driver/RiscBluetoothSensorsV1.h';require(sensor_header.read_bytes()==(repos['utilities']/'lib/Bluetooth/include/RiscBluetoothSensorsV1.h').read_bytes(),'BLE sensor driver/app ABI differs')
 telemetry_header=drivers/'sdk/driver/RiscTelemetryV1.h';require(telemetry_header.read_bytes()==(repos['utilities']/'lib/Bluetooth/include/RiscTelemetryV1.h').read_bytes(),'Telemetry driver/app ABI differs')
 for name in NON_CLOCK_APPS:
  repo_name='system-apps' if name in SYSTEM_APPS else 'utilities' if name in UTILITY_APPS else 'productivity';repo=repos[repo_name];source=repo/'Apps'/('timecard_portable.c' if name=='timecard' else name+'.c');version=c['app_versions'][name]
  original=json.loads((repo/'Apps'/('native' if name in ('file_browser','timecard') else '')/(name+'.json')).read_text())
  if name=='waterfall' and rf_enabled(profile):
   from rf_spectrum_profile import validate_waterfall_manifest
   validate_waterfall_manifest(original)
  source_version=c.get('source_app_versions',c['app_versions'])[name]
  if name not in ('ota_update','app_store'):require(original['version']==source_version,'App source version differs: '+name)
  else:
   native=repo/'Apps/native'/(name+'.json');require(native.is_file(),'Current native updater manifest missing: '+name)
   require(json.loads(native.read_text())['version']==source_version,'Portable Nova updater manifest differs')
  sources,includes,allowed=application_inputs(name,source,repos,root,out,profile)
  b,meta=compile_target(name,sources,definitions(name,version,automatic_low_battery(profile),rf_spectrum=rf_enabled(profile),runtime_features=profile=='runtime-features'),includes,{'app_main','app_module_init','app_module_fini'},allowed)
  if name in ('lora_messages','ble_scanner','waterfall','ble_touchpad','ble_buttons'):
   require(all(isinstance(q['api'],str) and q['api'].startswith('>=') and q['api'][2:].isdigit() for q in original['requires']),'Unsupported new app API range')
   m={'type':'application','id':name,'version':version,'architecture':'xtensa-esp32s3','file_name':name+'.elf','entry':'app_main','requires':[{'capability':q['capability'],'api':int(q['api'][2:])} for q in original['requires']]}
  else:m=json.loads(encoded(original) if name in NEW_APPS else store[name+'.json'])
  m['version']=version
  if name=='audio_spectrum':
   storage=[q for q in m['requires'] if q['capability']=='storage.key-value'];require(storage==[{'capability':'storage.key-value','api':1}],'Unexpected original Spectrum API')
   storage[0]['api']=2
   m['requires'].append({'capability':'storage.app-data','api':1})
  if name=='timecard':
   navigation=[q for q in m['requires'] if q['capability']=='input.navigation'];require(navigation==[{'capability':'input.navigation','api':1}],'Unexpected Timecard navigation contract')
   m['requires'].remove(navigation[0])
  if name in NEW_APPS:
   for cap,api in [('board.battery',1),('alarm.service',1)]:
    if not any(x['capability']==cap and x['api']==api for x in m['requires']):m['requires'].append({'capability':cap,'api':api})
  for cap,api in [('storage.key-value',1),('rtc.clock',2),('net.wifi',1),('bluetooth.hci',1),('motion.accel',1)]:
   if not any(x['capability']==cap and x['api']==api for x in m['requires']):m['requires'].append({'capability':cap,'api':api})
  if profile=='runtime-features':
   from runtime_features_profile import requirements
   m=requirements(name,m)
  (files_dir/(name+'.elf')).write_bytes(b);(files_dir/(name+'.json')).write_bytes(encoded(m))
  record['apps'][name]={**meta,'version':version,'repository':repo_name,'repository_sha':c['sources'][repo_name]['commit'],'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
  if name=='timecard':
   model_manifest=repo/'Apps/timecard.json';model_source=repo/'Apps/timecard.c'
   model=json.loads(model_manifest.read_text());require(model['version']=='1.0.4','Unexpected authoritative Timecard model version')
   record['apps'][name]['model']={'version':model['version'],'manifest':metadata(model_manifest.read_bytes()),'source':metadata(model_source.read_bytes())}
 service_flags=['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER','-DALARM_VOLUME_CONTROL','-DALARM_DND_CONTROL']
 b,meta=compile_target('alarm-service',[repos['utilities']/'Services/alarm_service/service.c'],service_flags,[repos['utilities']/'lib/Alarm/include',repos['runtime']/'sdk/driver',repos['system-apps']/'lib/PortableApps/include'],{'t5_driver_get'},{'memcpy','memset','memcmp','strcmp','strlen'})
 service_manifest=json.loads((repos['utilities']/'Services/alarm_service/points-manifest.json').read_text());require(service_manifest['version']==c['service_version'],'Wrong current service source version')
 policy=json.loads((repos['utilities']/'Services/alarm_service/points-storage-policy.example.json').read_text())
 actual={x['key']:{'namespace':x['namespace'],'access':x['access']} for x in next(x for x in new_boot['drivers'] if x['manifest']=='alarm-service/manifest.json')['key_value']};require(actual==policy,'Source service policy differs')
 dest=files_dir/'alarm-service';dest.mkdir();(dest/'driver.elf').write_bytes(b);(dest/'manifest.json').write_bytes(encoded(service_manifest))
 record['service']={**meta,'version':service_manifest['version'],'points_headers':{n:hashlib.sha256((repos['utilities']/'lib/Alarm/include'/n).read_bytes()).hexdigest() for n in ('PointsRecords.h','PointsSchedule.h')}}
 if profile=='runtime-features':
  source=repos['utilities']/'Services/telemetry_broadcast'
  service_manifest=json.loads((source/'manifest.json').read_text())
  require(service_manifest['id']==c['telemetry_broadcast']['id'] and service_manifest['version']==c['telemetry_broadcast']['version'],'Telemetry service identity differs')
  b,meta=compile_target('telemetry-broadcast',[source/'service.c'],[],[repos['system-apps']/'lib/PortableApps/include',drivers/'sdk/driver',repos['runtime']/'sdk/driver'],{'t5_driver_get'},{'memcpy','memset','memcmp','strcmp','strlen','memchr'})
  dest=files_dir/'broadcast';dest.mkdir();(dest/'driver.elf').write_bytes(b);(dest/'manifest.json').write_bytes(encoded(service_manifest))
  record['providers']['telemetry-broadcast']={**meta,'version':service_manifest['version']}
 provider_out=out/'provider-build';env={**os.environ,'NATIVE_APP_CC':cc}
 subprocess.run([sys.executable,str(repos['system-apps']/'scripts/build_portable_updates.py'),'--services-only','--rtc-utc-offset-seconds','28800','--output-dir',str(provider_out)],check=True,env=env)
 for kind,short in [('firmware','update-fw'),('apps','update-apps')]:
  src=provider_out/('software-update-'+kind);dest=files_dir/short;dest.mkdir()
  for name in ('driver.elf','manifest.json'):(dest/name).write_bytes((src/name).read_bytes())
  record['providers'][short]=json.loads((src/'build-record.json').read_text())
 from build_clock_app import build as build_clock
 clock_record={'watch_source':record['watch_source'],'sources':c['sources'],'files':{},'paired_boot_confirmation':True,'headers':record['service']['points_headers'],'source_sha256':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for base in (('apps/clock','apps/runtime_features','sdk/app','sdk/driver','include') if profile=='runtime-features' else ('apps/clock','sdk/app','sdk/driver','include')) for p in (root/base).rglob('*') if p.is_file()}}
 clock_manifest='apps/clock/runtime-features-manifest.json' if profile=='runtime-features' else 'apps/clock/power-repair-manifest.json' if power_enabled(profile) else 'apps/clock/rf-spectrum-manifest.json' if rf_enabled(profile) else 'apps/clock/low-battery-manifest.json' if profile=='low-battery' else 'apps/clock/current-manifest.json'
 require(json.loads((root/clock_manifest).read_text())['version']==c['app_versions']['default']==c['app_versions']['clock'],'Current paired Clock version differs')
 for name in CLOCK_APPS:
  build_clock(launcher=True,returning=name=='clock',alarm_system=repos['system-apps'],points_utilities=repos['utilities'],paired=True,current=True,debug_path=debug_dir/(name+'.elf'),low_battery=automatic_low_battery(profile),rf_spectrum=rf_enabled(profile),power_repair=power_enabled(profile),runtime_features=profile=='runtime-features')
  built=root/'dist/update-launcher';subprocess.run([str(validator),str(built/(name+'.uncompacted.elf'))],check=True);subprocess.run([str(validator),str(built/(name+'.elf'))],check=True)
  for ext in ('.elf','.json'):
   b=(built/(name+ext)).read_bytes();(files_dir/(name+ext)).write_bytes(b);clock_record['files'][name+ext]=metadata(b)
  meta=json.loads((built/'build-record.json').read_text())
  require(sorted(meta.get('defines',[]))==sorted(definitions(name,c['app_versions'][name],automatic_low_battery(profile),rf_spectrum=rf_enabled(profile),runtime_features=profile=='runtime-features')),'Actual Clock compiler flags differ from current profile: '+name)
  record['apps'][name]={**meta,'repository':'watch','repository_sha':record['watch_source']}
 record['clock']=clock_record
 for name,path in repos.items():clean(path,c['sources'][name]['commit'])
 clean(drivers,c['sdr']['commit'])
 record['files']={n:metadata((files_dir/n).read_bytes()) for n in sorted(payloads(profile))}
 record['debug']={n+'.elf':metadata((debug_dir/(n+'.elf')).read_bytes()) for n in APPS}
 (out/'current-apps-build.json').write_bytes(encoded(record));(out/'source-profile.json').write_bytes(encoded(c))
 licenses=out/'licenses';licenses.mkdir()
 sdr_license=licenses/'sdr';sdr_license.mkdir()
 (sdr_license/'LICENSE-eSpDR.txt').write_bytes((drivers/'Drivers/s3_radio_iq_v1/LICENSE-eSpDR.txt').read_bytes())
 for name,path in repos.items():
  for relative in git(path,'ls-files').splitlines():
   original=path/relative
   if original.is_file() and not {'test','tests','fixtures'} & set(Path(relative).parts) and original.name.upper().startswith(('LICENSE','COPYING','NOTICE')):
    target=licenses/name/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
 for name in ('NimBLE-LICENSE','NimBLE-NOTICE','NimBLE-SOURCE.json','TinyCrypt-LICENSE'):
  original=drivers/'dist/ble-hid'/name;require(original.is_file(),'HID dependency notice missing: '+name)
  target=licenses/'ble-hid'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
 for identity in ('ble-sensors','ble-telemetry','telemetry-battery'):
  for original in (drivers/'dist'/identity).glob('LICENSE*'):
   target=licenses/identity/original.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
 # Speech detector source attribution and patent grant travel with the ELF.
 voice=repos['utilities']/'lib/VoiceActivity'
 for name in ('LICENSE','AUTHORS','PATENTS','SOURCES.json','PATCHES.md'):
  original=voice/name;require(original.is_file(),'Voice activity notice missing: '+name)
  target=licenses/'voice-activity'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
 # Sensor vendor notices accompany source and binary current deployments.
 for src in (root/'vendor/SensorLib').rglob('*'):
  if src.is_file() and (src.name in ('LICENSE','PROVENANCE.json') or src.name.startswith('NOTICE')):
   target=licenses/'motion'/src.relative_to(root/'vendor/SensorLib');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(src.read_bytes())
 # The explicit app-data image and native backend also distribute LittleFS.
 notices=root/'vendor/app-data-notices';notice_record=json.loads((notices/'SOURCES.json').read_text())
 for item in notice_record['licenses']:
  source=notices/item['file'];require(hashlib.sha256(source.read_bytes()).hexdigest()==item['distributed_sha256'],'App-data license custody differs')
  target=licenses/'app-data'/item['file'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
 (licenses/'app-data/SOURCES.json').write_bytes((notices/'SOURCES.json').read_bytes())
 for source in (root/'licenses').rglob('*'):
  if source.is_file():
   target=licenses/'watch'/source.relative_to(root/'licenses');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
 for name in ('LICENSE-FontAwesome.txt','LICENSE-Orbitron.txt','LICENSE-Rajdhani.txt','SOURCES.json'):
  p=repos['system-apps']/'lib/PortableApps/fonts'/name
  if p.is_file():(licenses/name).write_bytes(p.read_bytes())
 for p in (repos['system-apps']/'lib/PortableApps/settings_fonts').glob('LICENSE-*'):(licenses/('settings-'+p.name)).write_bytes(p.read_bytes())
 members={p.relative_to(out).as_posix():p.read_bytes() for folder in (files_dir,debug_dir,licenses) for p in folder.rglob('*') if p.is_file()}
 for name in ('current-apps-build.json','source-profile.json'):members[name]=(out/name).read_bytes()
 (out/'current-apps.zip').write_bytes(zip_bytes(members))
 verify(out,record['watch_source'],root,profile=profile)
 if power_enabled(profile):checked_source(root,record['watch_source'])
 print(f'Current final cohort:{len(APPS)} rebuilt apps + alarm service +2 update providers + BLE sensor/telemetry providers; exact pins and strict targets verified')
 return record
def main(default_profile='current'):
 p=argparse.ArgumentParser()
 for n in ('system-apps','utilities','productivity','runtime','baseline','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--profile',choices=PROFILES,default=default_profile)
 p.add_argument('--baseline-root',type=Path)
 p.add_argument('--drivers',type=Path,required=True)
 p.add_argument('--motion-model',choices=['bma423','bma456h'],required=True)
 p.add_argument('--radio-model',choices=RADIO_MODELS,default='selectable')
 a=p.parse_args();build(a.system_apps,a.utilities,a.productivity,a.runtime,a.baseline,a.output,baseline_root=a.baseline_root,motion_model=a.motion_model,radio_model=a.radio_model,drivers=a.drivers,profile=a.profile)
if __name__=='__main__':main()

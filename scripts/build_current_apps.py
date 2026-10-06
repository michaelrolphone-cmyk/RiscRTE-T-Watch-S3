#!/usr/bin/env python3
"""Build the explicit final current-app cohort, separate from frozen custody lanes."""
import argparse,hashlib,json,os,shlex,shutil,subprocess,sys
from pathlib import Path
from current_apps_overlay import (ROOT,PROFILE,APPS,NON_CLOCK_APPS,CLOCK_APPS,SYSTEM_APPS,UTILITY_APPS,PAYLOADS,NEW_APPS,
                                 RADIO_MODELS,config,configure_boot,configure_board,metadata,encoded,require,verify)
from audio_overlay import verify as verify_audio
from compact_current_elf import compact
from build_wifi_common import read_zip,zip_bytes

def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
def clean(path,expected):
 require(git(path,'rev-parse','HEAD')==expected,'Current source pin differs: '+str(path))
 require(not git(path,'status','--porcelain','--untracked-files=no'),'Current source is dirty: '+str(path))
def definitions(name,version):
 if name in CLOCK_APPS:return ['-DWATCH_CLOCK_LAUNCHER','-DWATCH_CLOCK_ALARMS','-DWATCH_CLOCK_POINTS','-DPORTABLE_RTC_UTC8_DENVER','-DWATCH_PAIRED_BOOT_CONFIRM','-DWATCH_QUICK_ACTIONS','-DWATCH_QUICK_RADIOS','-DWATCH_MOTION_WAKE']+(['-DWATCH_CLOCK_RETURN'] if name=='clock' else [])
 flags=['-DPORTABLE_TOUCH_ROTATION=0','-DPORTABLE_RTC_UTC8_DENVER','-DPORTABLE_FORCE_FULL_FRAMES',
        '-DPORTABLE_INPUT_NAVIGATION','-DPORTABLE_INPUT_NAVIGATION_LOCAL','-DPORTABLE_APP_SLEEP_LOCAL','-DPORTABLE_ALARM_CLIENT','-DPORTABLE_QUICK_ACTIONS','-DPORTABLE_QUICK_RADIOS','-DPORTABLE_MOTION_WAKE']
 if name!='frequency_generator':flags+=['-DPORTABLE_NOVA_UI']
 if name in ('frequency_generator','audio_spectrum'):flags+=['-DPORTABLE_AUDIO_SESSION']
 if name in ('lora_messages','ble_scanner'):flags+=['-DPORTABLE_RADIO_SESSION','-DPORTABLE_APP_OWNS_TOUCH_CHROME']
 if name=='audio_spectrum':flags+=['-DPORTABLE_APP_OWNS_TOUCH_CHROME','-DPORTABLE_AUDIO_CONTINUOUS_CAPTURE']
 if name=='timecard':flags+=['-DTIMECARD_APP_DATA','-DPORTABLE_APP_OWNS_TOUCH_CHROME']
 if name=='file_browser':flags+=['-DPORTABLE_FILE_BROWSER_APP','-DPORTABLE_APP_OWNS_TOUCH_CHROME']
 if name=='settings':flags+=['-DPORTABLE_SETTINGS_APP','-DPORTABLE_SLEEP_SETTINGS','-DPORTABLE_ALARM_SETTINGS','-DPORTABLE_SETTINGS_VERSION="'+version+'"']
 if name=='wifi_settings':flags+=['-DPORTABLE_WIFI_SETTINGS_APP','-DPORTABLE_WIFI_STORAGE_INSTANCE=6','-DPORTABLE_WIFI_INSTANCE=15','-DPORTABLE_WIFI_VERSION="'+version+'"']
 if name in ('ota_update','app_store'):flags+=['-Wno-misleading-indentation','-DPORTABLE_UPDATE_APP','-DPORTABLE_UPDATE_FIRMWARE='+str(int(name=='ota_update')),'-DPORTABLE_WIFI_INSTANCE=15','-DPORTABLE_UPDATE_RTC_UTC_OFFSET_SECONDS=28800']
 if name=='springboard':flags+=['-DPORTABLE_RETAINED_RGB565_HANDOFF','-DPORTABLE_HANDOFF_EAGER_MS=60']
 owner=('LORA_RETURN_APP' if name=='lora_messages' else 'FILE_BROWSER_RETURN_APP' if name=='file_browser' else 'POINTS_RETURN_APP' if name=='points_in_time' else 'WIFI_RETURN_APP' if name=='wifi_settings' else 'UPDATE_RETURN_APP' if name in ('ota_update','app_store') else 'CALCULATOR_RETURN_APP' if name=='calculator' else 'ALARM_RETURN_APP' if name in ('alarms','countdown') else 'PORTABLE_RETURN_APP')
 if name=='timecard':return flags
 flags+=['-D'+owner+'="'+('clock.elf' if name=='springboard' else 'springboard.elf')+'"']
 return flags

def build(system,utilities,productivity,runtime,baseline,out,root=ROOT,baseline_root=None,motion_model=None,radio_model=None):
 require(motion_model in ('bma423','bma456h'),'Explicit --motion-model required; do not infer from earlier boots')
 require(radio_model in RADIO_MODELS,'Explicit --radio-model required; do not infer RF band')
 root=Path(root).resolve();out=Path(out).resolve();repos={'system-apps':Path(system).resolve(),'utilities':Path(utilities).resolve(),'productivity':Path(productivity).resolve(),'runtime':Path(runtime).resolve()};c=config(root)
 for name,path in repos.items():clean(path,c['sources'][name]['commit'])
 require(not out.exists() or not any(out.iterdir()),'Current output must be empty to reject stale files')
 out.mkdir(parents=True,exist_ok=True);files_dir=out/'files';files_dir.mkdir();debug_dir=out/'debug';debug_dir.mkdir()
 # Decode a separately verified immutable baseline only to reuse exact catalog,
 # app identities and existing boot authority. Never modify that archive.
 baseline=Path(baseline)
 if baseline_root is not None:
  baseline_root=Path(baseline_root);clean(baseline_root,'2a4fbae8fb2425bf830c302863a5e195106e77c9')
  subprocess.run([sys.executable,'-c',"import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]+'/scripts');from audio_overlay import verify;verify(Path(sys.argv[2]),root=Path(sys.argv[1]))",str(baseline_root.resolve()),str(baseline.resolve())],check=True)
  clean(baseline_root,'2a4fbae8fb2425bf830c302863a5e195106e77c9')
 else:verify_audio(baseline,root=root)
 raw=read_zip(baseline);store={n[6:]:b for n,b in raw.items() if n.startswith('store/')}
 require(len([n for n in store if n.endswith('.elf') and '/' not in n])==15,'Unexpected baseline app inventory')
 boot=json.loads(store['boot.json']);new_boot=configure_boot(boot);catalog=json.loads(raw['shared/catalog.json'])
 require({x['file_name'] for x in catalog}==({n+'.elf' for n in NON_CLOCK_APPS if n not in NEW_APPS}-{'springboard.elf'})|{'clock.elf'},'Baseline catalog inventory differs')
 require(len(catalog)==13 and len({x['icon'] for x in catalog})==13,'Baseline launcher icons collide')
 for name,entry in NEW_APPS.items():catalog.append({**entry,'file_name':name+'.elf'})
 require(len(catalog)==len(APPS)-2 and len(catalog)<=17 and len({x['icon'] for x in catalog})==len(catalog),'Current launcher inventory/icons exceed the reviewed bound')
 registry=json.loads((repos['system-apps']/'lib/PortableApps/catalog-icons.json').read_text())['apps']
 additional=json.loads((repos['system-apps']/'lib/PortableApps/additional-icons.json').read_text())
 for name,entry in NEW_APPS.items():
  if name=='timecard':require(entry['icon']=='solid:f274' and additional.get(entry['icon'])=='calendar-check','Timecard glyph is not in the reviewed subset')
  else:require(registry.get(name,{}).get('icon')==entry['icon'],'New app icon is not in the reviewed registry: '+name)
 for app_name,entry in registry.items():
  if app_name not in APPS:continue
  delivered=[x for x in catalog if x['file_name']==app_name+'.elf'];require(len(delivered)==1 and delivered[0]['icon']==entry['icon'],'Current icon registry mismatch: '+app_name)
 (out/'catalog.c').write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={'+','.join('{'+','.join('.'+k+'='+json.dumps(v) for k,v in x.items())+',.compatible=true}' for x in catalog)+'};\nconst unsigned portable_catalog_count='+str(len(catalog))+';\n')
 (out/'empty_catalog.c').write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[1]={{.compatible=false}};\nconst unsigned portable_catalog_count=0;\n')
 cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc');require(cc,'Pinned TWATCH_CC required')
 compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];require('8.4.0' in compiler,'Wrong target compiler')
 validator=out/'validate-elf'
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-I'+str(repos['system-apps']/'test/native_apps/stubs'),'-I'+str(repos['system-apps']/'lib/elf_loader/include'),str(repos['system-apps']/'lib/elf_loader/src/esp_elf_validate.c'),str(repos['system-apps']/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True)
 def compile_target(name,sources,flags,includes,exports,allowed):
  dependency_proof={}
  if name=='audio_spectrum':
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
  return b,{**metadata(b),'imports':sorted(imports),'exports':sorted(exports),'defines':flags,'compaction':compact_proof,**({'target_dependencies':dependency_proof,'host_fixture_excluded':True} if name=='audio_spectrum' else {})}
 record={'schema':1,'profile':PROFILE,'watch_source':git(root,'rev-parse','HEAD'),'configuration':c,'compiler':compiler,'target_validation':True,'baseline_boot':boot,'boot':new_boot,'catalog':catalog,'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),'apps':{},'providers':{},'files':{}}
 record['motion_model']=motion_model;record['radio_model']=radio_model
 record['baseline_board']=json.loads(store['board.json']);record['board']=configure_board(record['baseline_board'],root,motion_model=motion_model,radio_model=radio_model)
 (files_dir/'board.json').write_bytes(encoded(record['board']))
 for driver,folder in [('twatch-ble','ble'),('twatch-imu','imu'),('twatch-gpio','gpio'),('twatch-pmu','pmu'),('twatch-lora','lora')]:
  dest=files_dir/folder;dest.mkdir()
  (dest/'driver.elf').write_bytes((root/'dist'/driver/'driver.elf').read_bytes())
  (dest/'manifest.json').write_bytes(encoded(json.loads((root/'drivers'/driver.replace('-','_')/'manifest.json').read_text())))
  subprocess.run([str(validator),str(dest/'driver.elf')],check=True)
 for name in NON_CLOCK_APPS:
  repo_name='system-apps' if name in SYSTEM_APPS else 'utilities' if name in UTILITY_APPS else 'productivity';repo=repos[repo_name];source=repo/'Apps'/('timecard_portable.c' if name=='timecard' else name+'.c');version=c['app_versions'][name]
  original=json.loads((repo/'Apps'/('native' if name in ('file_browser','timecard') else '')/(name+'.json')).read_text())
  if name not in ('ota_update','app_store'):require(original['version']==version,'App source version differs: '+name)
  else:
   native=repo/'Apps/native'/(name+'.json');require(native.is_file(),'Current native updater manifest missing: '+name)
   require(json.loads(native.read_text())['version']==version,'Portable Nova updater manifest differs')
  sources=[source,repos['system-apps']/'lib/PortableApps/src/adapter.c',out/('catalog.c' if name=='springboard' else 'empty_catalog.c'),root/'apps/clock/portable_navigation.c',root/'apps/clock/portable_sleep.c']
  sources+=[repos['system-apps']/'lib/PortableApps/src'/n for n in ('quick_actions.c','quick_render.c','quick_session.c','quick_radios.c')]
  if name=='springboard':sources+=[repos['system-apps']/'lib/NativeApps/src/SingleFloatDivisionCompat.c']
  includes=[repos['system-apps']/'lib/PortableApps/include',repos['system-apps']/'lib/NativeApps/include',repos['system-apps']/'Apps',repos['utilities']/'Apps',repos['utilities']/'lib/Alarm/include',root/'sdk/app',root/'sdk/driver',root/'include']
  if name=='timecard':includes+=[repos['productivity']/'lib/PortableTimecard/include',repos['productivity']/'lib/NativeApps/include']
  if name=='ble_scanner':includes+=[repos['utilities']/'lib/Bluetooth/include']
  allowed={'risc_runtime_get_api','memcpy','memset','memcmp','strcmp','strlen','snprintf','malloc','calloc','free','strcpy'}
  if name=='file_browser':allowed|={'strncmp','strrchr','memchr'}
  b,meta=compile_target(name,sources,definitions(name,version),includes,{'app_main','app_module_init','app_module_fini'},allowed)
  if name in ('lora_messages','ble_scanner'):
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
 provider_out=out/'provider-build';env={**os.environ,'NATIVE_APP_CC':cc}
 subprocess.run([sys.executable,str(repos['system-apps']/'scripts/build_portable_updates.py'),'--services-only','--rtc-utc-offset-seconds','28800','--output-dir',str(provider_out)],check=True,env=env)
 for kind,short in [('firmware','update-fw'),('apps','update-apps')]:
  src=provider_out/('software-update-'+kind);dest=files_dir/short;dest.mkdir()
  for name in ('driver.elf','manifest.json'):(dest/name).write_bytes((src/name).read_bytes())
  record['providers'][short]=json.loads((src/'build-record.json').read_text())
 from build_clock_app import build as build_clock
 clock_record={'watch_source':record['watch_source'],'sources':c['sources'],'files':{},'paired_boot_confirmation':True,'headers':record['service']['points_headers'],'source_sha256':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for base in ('apps/clock','sdk/app','sdk/driver','include') for p in (root/base).rglob('*') if p.is_file()}}
 require(json.loads((root/'apps/clock/current-manifest.json').read_text())['version']==c['app_versions']['default']==c['app_versions']['clock'],'Current paired Clock version differs')
 for name in CLOCK_APPS:
  build_clock(launcher=True,returning=name=='clock',alarm_system=repos['system-apps'],points_utilities=repos['utilities'],paired=True,current=True,debug_path=debug_dir/(name+'.elf'))
  built=root/'dist/update-launcher';subprocess.run([str(validator),str(built/(name+'.uncompacted.elf'))],check=True);subprocess.run([str(validator),str(built/(name+'.elf'))],check=True)
  for ext in ('.elf','.json'):
   b=(built/(name+ext)).read_bytes();(files_dir/(name+ext)).write_bytes(b);clock_record['files'][name+ext]=metadata(b)
  meta=json.loads((built/'build-record.json').read_text());record['apps'][name]={**meta,'defines':definitions(name,c['app_versions'][name]),'repository':'watch','repository_sha':record['watch_source']}
 record['clock']=clock_record
 for name,path in repos.items():clean(path,c['sources'][name]['commit'])
 record['files']={n:metadata((files_dir/n).read_bytes()) for n in sorted(PAYLOADS)}
 record['debug']={n+'.elf':metadata((debug_dir/(n+'.elf')).read_bytes()) for n in APPS}
 (out/'current-apps-build.json').write_bytes(encoded(record));(out/'source-profile.json').write_bytes(encoded(c))
 licenses=out/'licenses';licenses.mkdir()
 for name,path in repos.items():
  for relative in git(path,'ls-files').splitlines():
   original=path/relative
   if original.is_file() and not {'test','tests','fixtures'} & set(Path(relative).parts) and original.name.upper().startswith(('LICENSE','COPYING','NOTICE')):
    target=licenses/name/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
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
 verify(out,record['watch_source'],root)
 print(f'Current final cohort:{len(APPS)} rebuilt apps + alarm service +2 update providers; exact pins and strict targets verified')
 return record
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for n in ('system-apps','utilities','productivity','runtime','baseline','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--baseline-root',type=Path)
 p.add_argument('--motion-model',choices=['bma423','bma456h'],required=True)
 p.add_argument('--radio-model',choices=RADIO_MODELS,default='selectable')
 a=p.parse_args();build(a.system_apps,a.utilities,a.productivity,a.runtime,a.baseline,a.output,baseline_root=a.baseline_root,motion_model=a.motion_model,radio_model=a.radio_model)

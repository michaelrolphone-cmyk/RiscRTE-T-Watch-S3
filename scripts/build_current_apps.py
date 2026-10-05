#!/usr/bin/env python3
"""Build the explicit final current-app cohort, separate from frozen custody lanes."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from current_apps_overlay import (ROOT,PROFILE,APPS,NON_CLOCK_APPS,CLOCK_APPS,SYSTEM_APPS,UTILITY_APPS,PAYLOADS,
                                 config,configure_boot,metadata,encoded,require,verify)
from audio_overlay import verify as verify_audio
from build_wifi_common import read_zip,zip_bytes

def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
def clean(path,expected):
 require(git(path,'rev-parse','HEAD')==expected,'Current source pin differs: '+str(path))
 require(not git(path,'status','--porcelain','--untracked-files=no'),'Current source is dirty: '+str(path))
def definitions(name,version):
 if name in CLOCK_APPS:return ['-DWATCH_CLOCK_LAUNCHER','-DWATCH_CLOCK_ALARMS','-DWATCH_CLOCK_POINTS','-DPORTABLE_RTC_UTC8_DENVER','-DWATCH_PAIRED_BOOT_CONFIRM']+(['-DWATCH_CLOCK_RETURN'] if name=='clock' else [])
 flags=['-DPORTABLE_TOUCH_ROTATION=0','-DPORTABLE_RTC_UTC8_DENVER','-DPORTABLE_FORCE_FULL_FRAMES',
        '-DPORTABLE_INPUT_NAVIGATION','-DPORTABLE_INPUT_NAVIGATION_LOCAL','-DPORTABLE_APP_SLEEP_LOCAL','-DPORTABLE_ALARM_CLIENT']
 if name!='frequency_generator':flags+=['-DPORTABLE_NOVA_UI']
 if name in ('frequency_generator','audio_spectrum'):flags+=['-DPORTABLE_AUDIO_SESSION']
 if name=='audio_spectrum':flags+=['-DPORTABLE_APP_OWNS_TOUCH_CHROME']
 if name=='settings':flags+=['-DPORTABLE_SETTINGS_APP','-DPORTABLE_SLEEP_SETTINGS','-DPORTABLE_ALARM_SETTINGS','-DPORTABLE_SETTINGS_VERSION="'+version+'"']
 if name=='wifi_settings':flags+=['-DPORTABLE_WIFI_SETTINGS_APP','-DPORTABLE_WIFI_STORAGE_INSTANCE=6','-DPORTABLE_WIFI_INSTANCE=15','-DPORTABLE_WIFI_VERSION="'+version+'"']
 if name in ('ota_update','app_store'):flags+=['-Wno-misleading-indentation','-DPORTABLE_UPDATE_APP','-DPORTABLE_UPDATE_FIRMWARE='+str(int(name=='ota_update')),'-DPORTABLE_WIFI_INSTANCE=15','-DPORTABLE_UPDATE_RTC_UTC_OFFSET_SECONDS=28800']
 if name=='springboard':flags+=['-DPORTABLE_RETAINED_RGB565_HANDOFF','-DPORTABLE_HANDOFF_EAGER_MS=60']
 owner=('POINTS_RETURN_APP' if name=='points_in_time' else 'WIFI_RETURN_APP' if name=='wifi_settings' else 'UPDATE_RETURN_APP' if name in ('ota_update','app_store') else 'CALCULATOR_RETURN_APP' if name=='calculator' else 'ALARM_RETURN_APP' if name in ('alarms','countdown') else 'PORTABLE_RETURN_APP')
 flags+=['-D'+owner+'="'+('clock.elf' if name=='springboard' else 'springboard.elf')+'"']
 return flags

def build(system,utilities,productivity,runtime,baseline,out,root=ROOT):
 root=Path(root);out=Path(out);repos={'system-apps':Path(system),'utilities':Path(utilities),'productivity':Path(productivity),'runtime':Path(runtime)};c=config(root)
 for name,path in repos.items():clean(path,c['sources'][name]['commit'])
 require(not out.exists() or not any(out.iterdir()),'Current output must be empty to reject stale files')
 out.mkdir(parents=True,exist_ok=True);files_dir=out/'files';files_dir.mkdir()
 # Decode a separately verified immutable baseline only to reuse exact catalog,
 # app identities and existing boot authority. Never modify that archive.
 baseline=Path(baseline);verify_audio(baseline,root=root)
 raw=read_zip(baseline);store={n[6:]:b for n,b in raw.items() if n.startswith('store/')}
 require(len([n for n in store if n.endswith('.elf') and '/' not in n])==15,'Unexpected baseline app inventory')
 boot=json.loads(store['boot.json']);new_boot=configure_boot(boot);catalog=json.loads(raw['shared/catalog.json'])
 require({x['file_name'] for x in catalog}==({n+'.elf' for n in NON_CLOCK_APPS}-{'springboard.elf'})|{'clock.elf'},'Visible catalog inventory differs')
 require(len(catalog)==13 and len({x['icon'] for x in catalog})==13,'Current launcher icons collide')
 registry=json.loads((repos['system-apps']/'lib/PortableApps/catalog-icons.json').read_text())['apps']
 for app_name,entry in registry.items():
  delivered=[x for x in catalog if x['file_name']==app_name+'.elf'];require(len(delivered)==1 and delivered[0]['icon']==entry['icon'],'Current icon registry mismatch: '+app_name)
 (out/'catalog.c').write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={'+','.join('{'+','.join('.'+k+'='+json.dumps(v) for k,v in x.items())+',.compatible=true}' for x in catalog)+'};\nconst unsigned portable_catalog_count='+str(len(catalog))+';\n')
 (out/'empty_catalog.c').write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[1]={{.compatible=false}};\nconst unsigned portable_catalog_count=0;\n')
 cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc');require(cc,'Pinned TWATCH_CC required')
 compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];require('8.4.0' in compiler,'Wrong target compiler')
 validator=out/'validate-elf'
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-I'+str(repos['system-apps']/'test/native_apps/stubs'),'-I'+str(repos['system-apps']/'lib/elf_loader/include'),str(repos['system-apps']/'lib/elf_loader/src/esp_elf_validate.c'),str(repos['system-apps']/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True)
 def compile_target(name,sources,flags,includes,exports,allowed):
  mapping=out/(name+'.map');mapping.write_text('{ global: '+'; '.join(sorted(exports))+'; local: *; };\n');elf=out/(name+'.elf')
  subprocess.run([cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror',*flags,*['-I'+str(p) for p in includes],*map(str,sources),'-lgcc','-o',str(elf)],check=True)
  symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True);imports={l.split()[-1] for l in symbols.splitlines() if ' U ' in ' '+l};actual={l.split()[-1] for l in symbols.splitlines() if len(l.split())>=3 and l.split()[-2] in ('T','D','B','R')}
  require(imports<=allowed and actual==exports,'Current ABI imports/exports differ: '+name+' '+str(sorted(imports-allowed)))
  subprocess.run([str(validator),str(elf)],check=True);b=elf.read_bytes();require(b[:7]==b'\x7fELF\x01\x01\x01' and b[16:20]==b'\x03\x00\x5e\x00','Wrong target ELF')
  return b,{**metadata(b),'imports':sorted(imports),'exports':sorted(exports),'defines':flags}
 record={'schema':1,'profile':PROFILE,'watch_source':git(root,'rev-parse','HEAD'),'configuration':c,'compiler':compiler,'target_validation':True,'baseline_boot':boot,'boot':new_boot,'catalog':catalog,'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),'apps':{},'providers':{},'files':{}}
 for name in NON_CLOCK_APPS:
  repo_name='system-apps' if name in SYSTEM_APPS else 'utilities' if name in UTILITY_APPS else 'productivity';repo=repos[repo_name];source=repo/'Apps'/(name+'.c');version=c['app_versions'][name]
  original=json.loads((repo/'Apps'/(name+'.json')).read_text())
  if name not in ('ota_update','app_store'):require(original['version']==version,'App source version differs: '+name)
  else:
   native=repo/'Apps/native'/(name+'.json');require(native.is_file(),'Current native updater manifest missing: '+name)
   require(json.loads(native.read_text())['version']==version,'Portable Nova updater manifest differs')
  sources=[source,repos['system-apps']/'lib/PortableApps/src/adapter.c',out/('catalog.c' if name=='springboard' else 'empty_catalog.c'),root/'apps/clock/portable_navigation.c',root/'apps/clock/portable_sleep.c']
  if name=='springboard':sources+=[repos['system-apps']/'lib/NativeApps/src/SingleFloatDivisionCompat.c']
  includes=[repos['system-apps']/'lib/PortableApps/include',repos['system-apps']/'lib/NativeApps/include',repos['system-apps']/'Apps',repos['utilities']/'Apps',repos['utilities']/'lib/Alarm/include',root/'sdk/app',root/'sdk/driver',root/'include']
  b,meta=compile_target(name,sources,definitions(name,version),includes,{'app_main','app_module_init','app_module_fini'},{'risc_runtime_get_api','memcpy','memset','memcmp','strcmp','strlen','snprintf','malloc','calloc','free','strcpy'})
  m=json.loads(store[name+'.json']);m['version']=version
  (files_dir/(name+'.elf')).write_bytes(b);(files_dir/(name+'.json')).write_bytes(encoded(m))
  record['apps'][name]={**meta,'version':version,'repository':repo_name,'repository_sha':c['sources'][repo_name]['commit'],'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
 service_flags=['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER','-DALARM_VOLUME_CONTROL']
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
  build_clock(launcher=True,returning=name=='clock',alarm_system=repos['system-apps'],points_utilities=repos['utilities'],paired=True,current=True)
  built=root/'dist/update-launcher';subprocess.run([str(validator),str(built/(name+'.elf'))],check=True)
  for ext in ('.elf','.json'):
   b=(built/(name+ext)).read_bytes();(files_dir/(name+ext)).write_bytes(b);clock_record['files'][name+ext]=metadata(b)
  meta=json.loads((built/'build-record.json').read_text());record['apps'][name]={**meta,'defines':definitions(name,c['app_versions'][name]),'repository':'watch','repository_sha':record['watch_source']}
 record['clock']=clock_record
 for name,path in repos.items():clean(path,c['sources'][name]['commit'])
 record['files']={n:metadata((files_dir/n).read_bytes()) for n in sorted(PAYLOADS)}
 (out/'current-apps-build.json').write_bytes(encoded(record));(out/'source-profile.json').write_bytes(encoded(c))
 licenses=out/'licenses';licenses.mkdir()
 for name,path in repos.items():
  for relative in git(path,'ls-files').splitlines():
   original=path/relative
   if original.is_file() and original.name.upper().startswith(('LICENSE','COPYING','NOTICE')):
    target=licenses/name/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes())
 for name in ('LICENSE-FontAwesome.txt','LICENSE-Orbitron.txt','LICENSE-Rajdhani.txt','SOURCES.json'):
  p=repos['system-apps']/'lib/PortableApps/fonts'/name
  if p.is_file():(licenses/name).write_bytes(p.read_bytes())
 for p in (repos['system-apps']/'lib/PortableApps/settings_fonts').glob('LICENSE-*'):(licenses/('settings-'+p.name)).write_bytes(p.read_bytes())
 members={p.relative_to(out).as_posix():p.read_bytes() for folder in (files_dir,licenses) for p in folder.rglob('*') if p.is_file()}
 for name in ('current-apps-build.json','source-profile.json'):members[name]=(out/name).read_bytes()
 (out/'current-apps.zip').write_bytes(zip_bytes(members))
 verify(out,record['watch_source'],root)
 print('Current final cohort:15 rebuilt apps + alarm service +2 update providers; exact pins and strict targets verified')
 return record
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for n in ('system-apps','utilities','productivity','runtime','baseline','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();build(a.system_apps,a.utilities,a.productivity,a.runtime,a.baseline,a.output)

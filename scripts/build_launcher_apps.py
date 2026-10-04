#!/usr/bin/env python3
"""Build original shared apps with their portable client adapter; no firmware UI."""
import argparse,json,os,shutil,subprocess,hashlib
from pathlib import Path
from build_clock_app import build as build_clock
ROOT=Path(__file__).resolve().parents[1]
def build(system,utilities,alarms=False,runtime=None,productivity=None,wifi=False,updates=None):
    if updates is not None and (not wifi or any(n not in ('ota_update','app_store') for n in updates)):raise ValueError("Updates require explicit Wi-Fi baseline and known app names")
    if wifi and not (alarms and runtime and productivity):raise ValueError("Wi-Fi requires the complete Points baseline")
    pins=json.loads((ROOT/('apps/update-sources.json' if updates is not None else 'apps/wifi-sources.json' if wifi else 'apps/points-sources.json' if productivity else 'apps/alarm-sources.json' if alarms else 'apps/shared-sources.json')).read_text())
    for name,repo in [('system-apps',system),('utilities',utilities)]+([('productivity',productivity)] if productivity else []):
        actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
        if actual!=pins[name]['commit'] or subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=repo,text=True).strip():
            raise ValueError('Shared source must be the clean pinned commit: '+name)
    for name,pin in json.loads((system/'lib/PortableApps/SOURCES.json').read_text()).items():
        if hashlib.sha256((system/'lib/PortableApps/include'/name).read_bytes()).hexdigest()!=pin['sha256']:
            raise ValueError('Shared canonical SDK hash mismatch: '+name)
    for relative,watch_path in [('display_time.h','apps/clock/display_time.h'),('twatch_calendar.h','include/twatch_calendar.h')]:
        if (system/'lib/PortableApps/time/denver'/relative).read_bytes()!=(ROOT/watch_path).read_bytes():
            raise ValueError('Shared RTC forward policy differs from deployed Clock: '+relative)
    if (system/'lib/PortableApps/include/PortableTransition.h').read_bytes()!=(ROOT/'apps/clock/transitions/PortableTransition.h').read_bytes():
        raise ValueError('Clock and shared app transition implementations differ')
    if (system/'lib/PortableApps/include/PortableSleepPolicy.h').read_bytes()!=(ROOT/'apps/clock/PortableSleepPolicy.h').read_bytes():
        raise ValueError('Clock and Settings sleep policy differ')
    if alarms and (system/'lib/PortableApps/include/PortableTimeFormat.h').read_bytes()!=(ROOT/'apps/clock/PortableTimeFormat.h').read_bytes():
        raise ValueError('Clock and Settings time-format record differ')
    if (system/'lib/PortableApps/include/RiscKeyValueV1.h').read_bytes()!=(ROOT/'sdk/app/RiscKeyValueV1.h').read_bytes():
        raise ValueError('Clock and Settings key-value ABI differ')
    cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc') or str(Path.home()/'.platformio/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc')
    out=ROOT/('dist/update-launcher' if updates is not None else 'dist/wifi-launcher' if wifi else 'dist/points-launcher' if productivity else 'dist/alarm-launcher' if alarms else 'dist/launcher');out.mkdir(parents=True,exist_ok=True)
    catalog=[{'display_name':'Clock','file_name':'clock.elf','icon':'solid:f017'},
             {'display_name':'Battery','file_name':'battery.elf','icon':'solid:f240'},
             {'display_name':'Settings','file_name':'settings.elf','icon':'solid:f013'}]
    (out/'catalog.c').write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={'+','.join('{'+','.join('.'+k+'='+json.dumps(v) for k,v in e.items())+',.compatible=true}' for e in catalog)+'};\nconst unsigned portable_catalog_count=3;\n')
    catalog += [{'display_name':'Calculator','file_name':'calculator.elf','icon':'solid:f1ec' if updates is not None else 'solid:f00a'},
                {'display_name':'Stopwatch','file_name':'stopwatch.elf','icon':'solid:f2f2'}]
    if alarms:catalog += [{'display_name':'Alarms','file_name':'alarms.elf','icon':'solid:f0f3'},{'display_name':'Countdown','file_name':'countdown.elf','icon':'solid:f254'}]
    if wifi:catalog += [{'display_name':'Wi-Fi','file_name':'wifi_settings.elf','icon':'solid:f1eb'}]
    if updates is not None:catalog += [{'display_name':'Firmware Update' if n=='ota_update' else 'App Store','file_name':n+'.elf','icon':'solid:f021' if n=='ota_update' else 'solid:f019'} for n in updates]
    if productivity:catalog += [{'display_name':'Points in Time','file_name':'points_in_time.elf','icon':'solid:f783' if updates is not None else 'solid:f017'}]
    if updates is not None:
        if len({entry['icon'] for entry in catalog}) != len(catalog):raise ValueError('Every current delivered Watch launcher app requires a distinct icon')
        if not {'solid:f0f3','solid:f254'} <= {entry['icon'] for entry in catalog}:raise ValueError('Alarm bell/hourglass icons missing from current delivered catalog')
    (out/'daily_catalog.c').write_text('#include \"PortableApps.h\"\nconst t5_app_manifest_t portable_catalog[]={'+','.join('{'+','.join('.'+k+'='+json.dumps(v) for k,v in e.items())+',.compatible=true}' for e in catalog)+'};\nconst unsigned portable_catalog_count='+(str(len(catalog)))+';\n')
    (out/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    record={'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],'shared_sources':pins,'apps':{},'touch_rotation':0,'rtc_policy':'fixed-UTC+08-to-America/Denver','full_frames':True,'crown_navigation':'app-local-original-pmu','retained_handoff':True,'handoff_ms':60,'return_targets':{'springboard':'clock.elf','battery':'springboard.elf','settings':'springboard.elf','calculator':'springboard.elf','stopwatch':'springboard.elf'}}
    if alarms:record['return_targets'].update({'alarms':'springboard.elf','countdown':'springboard.elf'})
    if wifi:record['return_targets']['wifi_settings']='springboard.elf'
    if updates is not None:record['return_targets'].update({n:'springboard.elf' for n in updates})
    if productivity:record['return_targets']['points_in_time']='springboard.elf'
    record['daily_apps']={'stopwatch':{'storage_instance':2,'key':'stopwatch','awake_clock':'monotonic-ms','restored_clock':'raw-RTC-seconds','precision':'approximate-after-recovery'},'calculator':{'arithmetic':'fixed-decimal','fractional_digits':6}}
    record['sleep_policy']={'default':'hybrid','application_idle_ms':60000,'light_ms':300000,'scope':'saved Clock mode; other apps always hybrid','choice':'storage.key-value@1','instance_id':1,'key':'sleep_mode','deep_wake':'fresh-default','ulp_program':False}
    build_clock(launcher=True,alarm_system=system if alarms else None,points_utilities=utilities if productivity else None,wifi=wifi,paired=updates is not None)
    clock_record=json.loads((out/'build-record.json').read_text())
    record['apps']['default']={**clock_record,'repository_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
    build_clock(launcher=True,returning=True,alarm_system=system if alarms else None,points_utilities=utilities if productivity else None,wifi=wifi,paired=updates is not None)
    record['apps']['clock']={**json.loads((out/'build-record.json').read_text()),'repository_sha':record['apps']['default']['repository_sha']}
    for name,repo,source in [('springboard',system,system/'Apps/springboard.c'),('battery',utilities,utilities/'Apps/battery.c'),('settings',system,system/'Apps/settings.c'),('calculator',utilities,utilities/'Apps/calculator.c'),('stopwatch',utilities,utilities/'Apps/stopwatch.c')]+([('alarms',utilities,utilities/'Apps/alarms.c'),('countdown',utilities,utilities/'Apps/countdown.c')] if alarms else [])+([('wifi_settings',system,system/'Apps/wifi_settings.c')] if wifi else [])+([('points_in_time',productivity,productivity/'Apps/points_in_time.c')] if productivity else [])+([(n,system,system/'Apps'/(n+'.c')) for n in updates] if updates is not None else []):
        exports=['app_main','app_module_init','app_module_fini']
        mapping=out/(name+'.map');mapping.write_text('{ global: '+'; '.join(exports)+'; local: *; };\n')
        sources=[source,system/'lib/PortableApps/src/adapter.c',out/('daily_catalog.c' if name=='springboard' else 'catalog.c'),ROOT/'apps/clock/portable_navigation.c',ROOT/'apps/clock/portable_sleep.c']
        if name=='springboard':sources.append(system/'lib/NativeApps/src/SingleFloatDivisionCompat.c')
        flags=['-DPORTABLE_TOUCH_ROTATION=0','-DPORTABLE_RTC_UTC8_DENVER','-DPORTABLE_FORCE_FULL_FRAMES','-DPORTABLE_INPUT_NAVIGATION','-DPORTABLE_INPUT_NAVIGATION_LOCAL','-DPORTABLE_APP_SLEEP_LOCAL']
        if alarms:flags.append('-DPORTABLE_ALARM_CLIENT')
        if alarms and name=='settings':flags.append('-DPORTABLE_ALARM_SETTINGS')
        if updates is not None and name in updates:flags.extend(['-Wno-misleading-indentation','-DPORTABLE_UPDATE_APP','-DPORTABLE_UPDATE_FIRMWARE='+str(int(name=='ota_update')),'-DPORTABLE_WIFI_INSTANCE=15','-DPORTABLE_UPDATE_RTC_UTC_OFFSET_SECONDS=28800'])
        if name=='wifi_settings':flags.extend(['-DPORTABLE_WIFI_SETTINGS_APP','-DPORTABLE_WIFI_STORAGE_INSTANCE=6','-DPORTABLE_WIFI_INSTANCE=15','-DPORTABLE_WIFI_VERSION=\"'+json.loads((system/'Apps/wifi_settings.json').read_text())['version']+'\"'])
        if name=='settings':flags.extend(['-DPORTABLE_SETTINGS_APP','-DPORTABLE_SLEEP_SETTINGS','-DPORTABLE_SETTINGS_VERSION=\"'+json.loads((system/'Apps/settings.json').read_text())['version']+'\"'])
        if name=='springboard':flags.extend(['-DPORTABLE_RETAINED_RGB565_HANDOFF','-DPORTABLE_HANDOFF_EAGER_MS=60'])
        flags.append(('-DPOINTS_RETURN_APP=' if name=='points_in_time' else '-DWIFI_RETURN_APP=' if name=='wifi_settings' else '-DUPDATE_RETURN_APP=' if updates is not None and name in updates else '-DPORTABLE_RETURN_APP=')+'"'+('clock.elf' if name=='springboard' else 'springboard.elf')+'"')
        elf=out/(name+'.elf')
        subprocess.run([cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror',*flags,*['-I'+str(x) for x in [system/'lib/PortableApps/include',system/'lib/NativeApps/include',system/'Apps',utilities/'lib/Alarm/include',ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include']],*[str(x) for x in sources],'-lgcc','-o',str(elf)],check=True)
        symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True)
        imports={line.split()[-1] for line in symbols.splitlines() if ' U ' in ' '+line}
        allowed={'risc_runtime_get_api','memcpy','memset','memcmp','strcmp','strlen','snprintf','malloc','free','strcpy'}
        assert imports<=allowed,(name,imports-allowed)
        actual={line.split()[-1] for line in symbols.splitlines() if len(line.split())>=3 and line.split()[-2] in ('T','D','B','R')}
        assert actual==set(exports),(name,actual)
        data=elf.read_bytes();assert data[:7]==b'\x7fELF\x01\x01\x01' and data[16:20]==b'\x03\x00\x5e\x00'
        original=json.loads((ROOT/'apps/clock/manifest.json' if name=='default' else repo/'Apps'/(name+'.json')).read_text())
        requires=[{'capability':'display.output','api':1},{'capability':'input.touch.raw','api':1}]
        if name in ('springboard','settings','stopwatch','alarms','countdown','points_in_time','wifi_settings','ota_update','app_store'):requires.append({'capability':'rtc.clock','api':2})
        requires.append({'capability':'board.battery','api':1})
        if name in ('settings','stopwatch','alarms','countdown','points_in_time','wifi_settings','ota_update','app_store'):requires.append({'capability':'storage.key-value','api':1})
        if name=='wifi_settings' or (updates is not None and name in updates):requires.append({'capability':'net.wifi','api':1})
        if updates is not None and name in updates:requires.append({'capability':'software.update.'+('firmware' if name=='ota_update' else 'apps'),'api':1})
        if alarms:requires.append({'capability':'alarm.service','api':1})
        manifest={'type':'application','id':'twatch-clock' if name=='default' else name,'version':'1.1.0' if updates is not None and name in updates else original['version'],'architecture':'xtensa-esp32s3','file_name':name+'.elf','entry':'app_main','requires':requires}
        (out/(name+'.json')).write_text(json.dumps(manifest,indent=2)+'\n')
        record['apps'][name]={'version':manifest['version'],'sha256':hashlib.sha256(data).hexdigest(),'imports':sorted(imports),'repository_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()}
    validator=out/'validate-elf'
    subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-I'+str(system/'test/native_apps/stubs'),'-I'+str(system/'lib/elf_loader/include'),str(system/'lib/elf_loader/src/esp_elf_validate.c'),str(system/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True)
    for name in ('default','clock','springboard','battery','settings','calculator','stopwatch')+(('alarms','countdown') if alarms else ())+ (('points_in_time',) if productivity else ()) + (('wifi_settings',) if wifi else ()) + (tuple(updates) if updates is not None else ()):
        subprocess.run([str(validator),str(out/(name+'.elf'))],check=True)
    for path in (system/'lib/PortableApps/fonts').glob('*.txt'):
        (out/path.name).write_bytes(path.read_bytes())
    for name,path in [('font-sources.json',system/'lib/PortableApps/fonts/SOURCES.json'),('time-sources.json',system/'lib/PortableApps/time/SOURCES.json')]:
        (out/name).write_bytes(path.read_bytes())
    for name in ('LICENSE-Orbitron.txt','LICENSE-Rajdhani.txt','SOURCES.json'):
        target=out/'settings_fonts'/name;target.parent.mkdir(exist_ok=True)
        target.write_bytes((system/'lib/PortableApps/settings_fonts'/name).read_bytes())
    (out/'RTC_PROVENANCE.json').write_bytes((system/'lib/PortableApps/RTC_PROVENANCE.json').read_bytes())
    if alarms:
        record['alarm_service']={'version':'0.2.1' if productivity else '0.1.0','capability':'alarm.service@1','scope':'explicit-singleton','runtime':pins['runtime']}
    (out/'build-record.json').write_text(json.dumps(record,indent=2)+'\n')
    print((str(11+len(updates)) if updates is not None else 'Eleven' if wifi else 'Ten' if productivity else 'Nine' if alarms else 'Seven')+' real Xtensa applications: ABI/import/export checks passed')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--system-apps',required=True,type=Path);p.add_argument('--utilities',required=True,type=Path);a=p.parse_args();build(a.system_apps.resolve(),a.utilities.resolve())

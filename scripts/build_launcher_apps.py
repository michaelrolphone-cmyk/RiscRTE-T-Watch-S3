#!/usr/bin/env python3
"""Build original shared apps with their portable client adapter; no firmware UI."""
import argparse,json,os,shutil,subprocess,hashlib
from pathlib import Path
from build_clock_app import build as build_clock
ROOT=Path(__file__).resolve().parents[1]
def build(system,utilities):
    pins=json.loads((ROOT/'apps/shared-sources.json').read_text())
    for name,repo in [('system-apps',system),('utilities',utilities)]:
        actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
        if actual!=pins[name]['commit'] or subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=repo,text=True).strip():
            raise ValueError('Shared source must be the clean pinned commit: '+name)
    for name,pin in json.loads((system/'lib/PortableApps/SOURCES.json').read_text()).items():
        if hashlib.sha256((system/'lib/PortableApps/include'/name).read_bytes()).hexdigest()!=pin['sha256']:
            raise ValueError('Shared canonical SDK hash mismatch: '+name)
    for relative,watch_path in [('display_time.h','apps/clock/display_time.h'),('twatch_calendar.h','include/twatch_calendar.h')]:
        if (system/'lib/PortableApps/time/denver'/relative).read_bytes()!=(ROOT/watch_path).read_bytes():
            raise ValueError('Shared RTC forward policy differs from deployed Clock: '+relative)
    cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc') or str(Path.home()/'.platformio/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc')
    out=ROOT/'dist/launcher';out.mkdir(parents=True,exist_ok=True)
    catalog=[{'display_name':'Clock','file_name':'default.elf','icon':'solid:f017'},
             {'display_name':'Battery','file_name':'battery.elf','icon':'solid:f240'},
             {'display_name':'Settings','file_name':'settings.elf','icon':'solid:f013'}]
    (out/'catalog.c').write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={'+','.join('{'+','.join('.'+k+'='+json.dumps(v) for k,v in e.items())+',.compatible=true}' for e in catalog)+'};\nconst unsigned portable_catalog_count=3;\n')
    (out/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    record={'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],'shared_sources':pins,'apps':{},'touch_rotation':180,'rtc_policy':'fixed-UTC+08-to-America/Denver'}
    build_clock(launcher=True)
    clock_record=json.loads((out/'build-record.json').read_text())
    record['apps']['default']={**clock_record,'repository_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
    for name,repo,source in [('springboard',system,system/'Apps/springboard.c'),('battery',utilities,utilities/'Apps/battery.c'),('settings',system,system/'Apps/settings.c')]:
        exports=['app_main','app_module_init','app_module_fini']
        mapping=out/(name+'.map');mapping.write_text('{ global: '+'; '.join(exports)+'; local: *; };\n')
        sources=[source,system/'lib/PortableApps/src/adapter.c',out/'catalog.c']
        if name=='springboard':sources.append(system/'lib/NativeApps/src/SingleFloatDivisionCompat.c')
        flags=['-DPORTABLE_TOUCH_ROTATION=180','-DPORTABLE_RTC_UTC8_DENVER']
        if name=='settings':flags.append('-DPORTABLE_SETTINGS_APP')
        elf=out/(name+'.elf')
        subprocess.run([cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror',*flags,*['-I'+str(x) for x in [system/'lib/PortableApps/include',system/'lib/NativeApps/include',ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include']],*[str(x) for x in sources],'-lgcc','-o',str(elf)],check=True)
        symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True)
        imports={line.split()[-1] for line in symbols.splitlines() if ' U ' in ' '+line}
        allowed={'risc_runtime_get_api','memcpy','memset','memcmp','strcmp','strlen','snprintf','malloc','free','strcpy'}
        assert imports<=allowed,(name,imports-allowed)
        actual={line.split()[-1] for line in symbols.splitlines() if len(line.split())>=3 and line.split()[-2] in ('T','D','B','R')}
        assert actual==set(exports),(name,actual)
        data=elf.read_bytes();assert data[:7]==b'\x7fELF\x01\x01\x01' and data[16:20]==b'\x03\x00\x5e\x00'
        original=json.loads((ROOT/'apps/clock/manifest.json' if name=='default' else repo/'Apps'/(name+'.json')).read_text())
        requires=[{'capability':'display.output','api':1},{'capability':'input.touch.raw','api':1}]
        if name in ('springboard','settings'):requires.append({'capability':'rtc.clock','api':2})
        if name=='battery':requires.append({'capability':'board.battery','api':1})
        manifest={'type':'application','id':'twatch-clock' if name=='default' else name,'version':original['version'],'architecture':'xtensa-esp32s3','file_name':name+'.elf','entry':'app_main','requires':requires}
        (out/(name+'.json')).write_text(json.dumps(manifest,indent=2)+'\n')
        record['apps'][name]={'version':manifest['version'],'sha256':hashlib.sha256(data).hexdigest(),'imports':sorted(imports),'repository_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()}
    validator=out/'validate-elf'
    subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-I'+str(system/'test/native_apps/stubs'),'-I'+str(system/'lib/elf_loader/include'),str(system/'lib/elf_loader/src/esp_elf_validate.c'),str(system/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True)
    for name in ('default','springboard','battery','settings'):
        subprocess.run([str(validator),str(out/(name+'.elf'))],check=True)
    for path in (system/'lib/PortableApps/fonts').glob('*.txt'):
        (out/path.name).write_bytes(path.read_bytes())
    for name,path in [('font-sources.json',system/'lib/PortableApps/fonts/SOURCES.json'),('time-sources.json',system/'lib/PortableApps/time/SOURCES.json')]:
        (out/name).write_bytes(path.read_bytes())
    for name in ('LICENSE-Orbitron.txt','LICENSE-Rajdhani.txt','SOURCES.json'):
        target=out/'settings_fonts'/name;target.parent.mkdir(exist_ok=True)
        target.write_bytes((system/'lib/PortableApps/settings_fonts'/name).read_bytes())
    (out/'RTC_PROVENANCE.json').write_bytes((system/'lib/PortableApps/RTC_PROVENANCE.json').read_bytes())
    (out/'build-record.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Four real Xtensa applications: ABI/import/export checks passed')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--system-apps',required=True,type=Path);p.add_argument('--utilities',required=True,type=Path);a=p.parse_args();build(a.system_apps.resolve(),a.utilities.resolve())

#!/usr/bin/env python3
"""Build original shared apps with their portable client adapter; no firmware UI."""
import argparse,json,os,shutil,subprocess,hashlib
from pathlib import Path
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
    cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc') or str(Path.home()/'.platformio/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc')
    out=ROOT/'dist/launcher';out.mkdir(parents=True,exist_ok=True)
    (out/'catalog.c').write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={ {.display_name="Clock",.file_name="default.elf",.icon="solid:f017",.compatible=true},{.display_name="Battery",.file_name="battery.elf",.icon="solid:f240",.compatible=true}};\nconst unsigned portable_catalog_count=2;\n')
    record={'shared_sources':pins,'apps':{}}
    for name,repo,source in [('springboard',system,system/'Apps/springboard.c'),('battery',utilities,utilities/'Apps/battery.c'),('default',ROOT,ROOT/'apps/clock/main.c')]:
        exports=['app_main'] if name=='default' else ['app_main','app_module_init','app_module_fini']
        mapping=out/(name+'.map');mapping.write_text('{ global: '+'; '.join(exports)+'; local: *; };\n')
        sources=[source,ROOT/'apps/clock/render.c'] if name=='default' else [source,system/'lib/PortableApps/src/adapter.c',out/'catalog.c']
        flags=['-DWATCH_CLOCK_LAUNCHER'] if name=='default' else []
        elf=out/(name+'.elf')
        subprocess.run([cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror',*flags,*['-I'+str(x) for x in [system/'lib/PortableApps/include',system/'lib/NativeApps/include',ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include']],*[str(x) for x in sources],'-lgcc','-o',str(elf)],check=True)
        symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True)
        imports={line.split()[-1] for line in symbols.splitlines() if ' U ' in ' '+line}
        allowed={'risc_runtime_get_api','memcpy','memset','memcmp','strcmp','strlen','snprintf','malloc','free','strcpy'}
        assert imports<=allowed,(name,imports-allowed)
        actual={line.split()[-1] for line in symbols.splitlines() if len(line.split())>=3 and line.split()[-2] in ('T','D','B','R')}
        assert actual==set(exports),(name,actual)
        data=elf.read_bytes();assert data[:7]==b'\x7fELF\x01\x01\x01' and data[16:20]==b'\x03\x00\x5e\x00'
        original=json.loads((ROOT/'apps/clock/manifest.json' if name=='default' else repo/'Apps'/(name+'.json')).read_text())
        requires=[{'capability':'display.output','api':1},{'capability':'input.touch.raw','api':1}]
        if name=='default':requires.append({'capability':'rtc.clock','api':2})
        if name=='battery':requires.append({'capability':'board.battery','api':1})
        manifest={'type':'application','id':'twatch-clock' if name=='default' else name,'version':original['version'],'architecture':'xtensa-esp32s3','file_name':name+'.elf','entry':'app_main','requires':requires}
        (out/(name+'.json')).write_text(json.dumps(manifest,indent=2)+'\n')
        record['apps'][name]={'version':manifest['version'],'sha256':hashlib.sha256(data).hexdigest(),'imports':sorted(imports),'repository_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()}
    (out/'build-record.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Three real Xtensa applications: ABI/import/export checks passed')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--system-apps',required=True,type=Path);p.add_argument('--utilities',required=True,type=Path);a=p.parse_args();build(a.system_apps.resolve(),a.utilities.resolve())

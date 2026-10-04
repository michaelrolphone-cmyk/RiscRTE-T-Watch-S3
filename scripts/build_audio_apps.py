#!/usr/bin/env python3
"""Build catalog-only Springboard and Audio Tools; independently rebuild target bytes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from audio_deployment import ROOT,APPS,app_manifest,baseline,catalog_source,check_elf,compile_definitions,configuration,encoded,require,sha


def git(root,*args):return subprocess.check_output(['git',*args],cwd=root,text=True).strip()


def clean_pin(path,pin):
    require(git(path,'rev-parse','HEAD')==pin['commit'] and not git(path,'status','--porcelain','--untracked-files=no'),'Source must match exact clean pin: '+str(path))


def build(system,utilities,baseline_system,archive,out):
    config=configuration();old_pins=json.loads((ROOT/'apps/wifi-sources.json').read_text())
    for path,pin in ((system,config['sources']['system-apps']),(utilities,config['sources']['utilities']),(baseline_system,old_pins['system-apps'])):clean_pin(path,pin)
    files,_,old_store=baseline(archive.read_bytes());catalog=json.loads(files['shared/catalog.json'])+[config['apps'][n]['catalog'] for n in APPS]
    out.mkdir(parents=True,exist_ok=True);(out/'catalog.json').write_bytes(encoded(catalog));(out/'catalog.c').write_text(catalog_source(catalog));(out/'small_catalog.c').write_text(catalog_source(catalog[:3]))
    cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc');require(cc is not None,'Set pinned TWATCH_CC')
    compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];require('8.4.0' in compiler,'Pinned GCC8.4 required')
    exports={'app_main','app_module_init','app_module_fini'};mapping=out/'exports.map';mapping.write_text('{ global: '+'; '.join(sorted(exports))+'; local: *; };\n')
    evidence=dict(schema=1,sources=config['sources'],springboard_sources=old_pins['system-apps'],watch_source=git(ROOT,'rev-parse','HEAD'),
        minimum_runtime=config['minimum_runtime'],compiler=compiler,apps={},touch_rotation=0,crown_back=True,sleep_policy='hybrid',physical_verification='pending')
    for name in ('springboard',*APPS):
        shared=baseline_system if name=='springboard' else system
        sources={'application':shared/'Apps/springboard.c' if name=='springboard' else utilities/'Apps'/(name+'.c'),
            'adapter':shared/'lib/PortableApps/src/adapter.c','catalog':out/('catalog.c' if name=='springboard' else 'small_catalog.c'),
            'navigation':ROOT/'apps/clock/portable_navigation.c','sleep':ROOT/'apps/clock/portable_sleep.c'}
        if name=='springboard':
            sources['division']=shared/'lib/NativeApps/src/SingleFloatDivisionCompat.c';manifest=json.loads(old_store[name+'.json']);manifest['version']=config['springboard_version'];owner=old_pins['system-apps']['commit']
        else:
            side=json.loads((utilities/'Apps'/(name+'.json')).read_text());require(side['min_firmware_version']==config['minimum_runtime'] and side['version']==config['apps'][name]['version'],'Shared audio version/profile mismatch')
            manifest=app_manifest(name,side['version']);owner=config['sources']['utilities']['commit']
        includes=[shared/'lib/PortableApps/include',shared/'lib/NativeApps/include',utilities/'Apps',utilities/'lib/Alarm/include',ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include']
        elf=out/(name+'.elf');flags=compile_definitions(name)
        subprocess.run([cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared',
            '-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror',*flags,*['-I'+str(p) for p in includes],*map(str,sources.values()),'-lgcc','-o',str(elf)],check=True)
        symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True)
        imports={line.split()[-1] for line in symbols.splitlines() if ' U ' in ' '+line};actual={line.split()[-1] for line in symbols.splitlines() if len(line.split())>=3 and line.split()[-2] in ('T','D','B','R')}
        require(imports<={'risc_runtime_get_api','memcpy','memset','memcmp','strcmp','strlen','snprintf','malloc','free','strcpy'} and actual==exports,'Unexpected target imports/exports: '+name)
        data=elf.read_bytes();check_elf(data);(out/(name+'.json')).write_bytes(encoded(manifest))
        evidence['apps'][name]=dict(version=manifest['version'],repository_sha=owner,sha256=sha(data),size_bytes=len(data),imports=sorted(imports),compile_definitions=flags,source_sha256={role:sha(p.read_bytes()) for role,p in sources.items()})
    (out/'audio-build.json').write_bytes(encoded(evidence));return evidence


def verify_target_bytes(compiled,archive,system,utilities,baseline_system):
    """Rebuild from exact clean sources; reject even self-consistently rehashed ELFs."""
    with tempfile.TemporaryDirectory(prefix='watch-audio-target-rebuild-') as temporary:
        out=Path(temporary);build(system,utilities,baseline_system,archive,out)
        names={n+ext for n in ('springboard',*APPS) for ext in ('.elf','.json')}|{'audio-build.json','catalog.json'}
        for name in sorted(names):require(compiled[name]==(out/name).read_bytes(),'Independent target source rebuild differs: '+name)
    print('Independent clean target rebuild matches every audio/catalog executable and manifest')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('system-apps','utilities','baseline-system-apps','baseline'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'dist/audio-tools');a=p.parse_args()
    s,u,b,z,o=(x.resolve() for x in (a.system_apps,a.utilities,a.baseline_system_apps,a.baseline,a.output));build(s,u,b,z,o)
    verify_target_bytes({p.name:p.read_bytes() for p in o.iterdir() if p.is_file()},z,s,u,b)

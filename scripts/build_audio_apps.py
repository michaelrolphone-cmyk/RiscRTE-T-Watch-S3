#!/usr/bin/env python3
"""Build current Springboard plus Frequency Generator and Audio Spectrum for Watch."""
import argparse,hashlib,io,json,os,shutil,subprocess,tempfile
from pathlib import Path
from audio_overlay import ROOT,APPS,app_manifest,catalog_c,compile_defs,config,encoded,require,sha
from build_update_common import verify as verify_base
from build_wifi_common import read_zip

def git(root,*args): return subprocess.check_output(['git',*args],cwd=root,text=True).strip()

def clean_pin(path,pin):
    require(git(path,'rev-parse','HEAD')==pin['commit'],'Wrong source pin: '+str(path))
    require(not git(path,'status','--porcelain','--untracked-files=no'),'Dirty source checkout: '+str(path))

def baseline(path):
    raw=path.read_bytes();stream=io.BytesIO(raw);stream.name=path.name
    verify_base(stream)
    stream=io.BytesIO(raw);stream.name=path.name;files=read_zip(stream)
    return files,{n[6:]:b for n,b in files.items() if n.startswith('store/')}

def build(system,utilities,archive,out):
    cfg=config()
    clean_pin(system,cfg['sources']['system-apps']);clean_pin(utilities,cfg['sources']['utilities'])
    runtime=json.loads((ROOT/'apps/update-runtime-requirements.json').read_text())
    require(runtime['source_sha']==cfg['sources']['runtime']['commit'] and runtime['firmware_version']==cfg['minimum_runtime'],
            'Watch Runtime does not match Audio Tools prerequisite')
    files,store=baseline(archive)
    catalog=json.loads(files['shared/catalog.json'])+[cfg['apps'][n]['catalog'] for n in APPS]
    require(len({x['icon'] for x in catalog})==len(catalog),'Audio catalog icon collision')
    out.mkdir(parents=True,exist_ok=True)
    (out/'catalog.json').write_bytes(encoded(catalog));(out/'catalog.c').write_text(catalog_c(catalog))
    (out/'small_catalog.c').write_text(catalog_c(catalog[:3]))
    cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc');require(cc,'Pinned GCC8.4 required')
    compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0];require('8.4.0' in compiler,'Pinned GCC8.4 required')
    exports={'app_main','app_module_init','app_module_fini'};mapping=out/'exports.map'
    mapping.write_text('{ global: '+'; '.join(sorted(exports))+'; local: *; };\n')
    evidence={'schema':1,'watch_source':git(ROOT,'rev-parse','HEAD'),'sources':cfg['sources'],
              'minimum_runtime':cfg['minimum_runtime'],'compiler':compiler,'apps':{},
              'touch_rotation':0,'sleep_policy':'hybrid','physical_verification':'pending'}
    for name in ('springboard',*APPS):
        application=system/'Apps/springboard.c' if name=='springboard' else utilities/'Apps'/(name+'.c')
        sources={'application':application,'adapter':system/'lib/PortableApps/src/adapter.c',
                 'catalog':out/('catalog.c' if name=='springboard' else 'small_catalog.c'),
                 'navigation':ROOT/'apps/clock/portable_navigation.c','sleep':ROOT/'apps/clock/portable_sleep.c'}
        if name=='springboard': sources['division']=system/'lib/NativeApps/src/SingleFloatDivisionCompat.c'
        if name=='springboard':
            manifest=json.loads(store['springboard.json']);manifest['version']=cfg['springboard_version']
            source_manifest=json.loads((system/'Apps/springboard.json').read_text())
            require(source_manifest['version']==cfg['springboard_version'],'Springboard version pin mismatch')
            owner=cfg['sources']['system-apps']['commit']
        else:
            side=json.loads((utilities/'Apps'/(name+'.json')).read_text())
            require(side['min_firmware_version']==cfg['minimum_runtime'] and side['version']==cfg['apps'][name]['version'],
                    'Utility audio app version/runtime mismatch: '+name)
            manifest=app_manifest(name,side['version']);owner=cfg['sources']['utilities']['commit']
        includes=[system/'lib/PortableApps/include',system/'lib/NativeApps/include',utilities/'Apps',
                  utilities/'lib/Alarm/include',ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include']
        flags=compile_defs(name);elf=out/(name+'.elf')
        subprocess.run([cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls',
            '-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared',
            '-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),
            '-Wall','-Wextra','-Werror',*flags,*['-I'+str(p) for p in includes],*map(str,sources.values()),
            '-lgcc','-o',str(elf)],check=True,timeout=120)
        symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True)
        imports={line.split()[-1] for line in symbols.splitlines() if ' U ' in ' '+line}
        actual={line.split()[-1] for line in symbols.splitlines() if len(line.split())>=3 and line.split()[-2] in ('T','D','B','R')}
        allowed={'risc_runtime_get_api','memcpy','memset','memcmp','strcmp','strlen','snprintf','malloc','calloc','free','strcpy'}
        require(imports<=allowed and actual==exports,'Unexpected target imports/exports: '+name+' '+str(sorted(imports-allowed)))
        data=elf.read_bytes();require(data[:7]==b'\x7fELF\x01\x01\x01' and data[16:20]==b'\x03\x00\x5e\x00','Not Xtensa ELF: '+name)
        (out/(name+'.json')).write_bytes(encoded(manifest))
        evidence['apps'][name]={'version':manifest['version'],'repository_sha':owner,'sha256':sha(data),
             'size_bytes':len(data),'imports':sorted(imports),'compile_definitions':flags,
             'source_sha256':{role:sha(path.read_bytes()) for role,path in sources.items()}}
    (out/'audio-build.json').write_bytes(encoded(evidence))
    return evidence

def verify_target_bytes(compiled,archive,system,utilities):
    with tempfile.TemporaryDirectory(prefix='watch-audio-rebuild-') as d:
        out=Path(d);build(system,utilities,archive,out)
        names={n+e for n in ('springboard',*APPS) for e in ('.elf','.json')}|{'audio-build.json','catalog.json'}
        for n in names: require(compiled[n]==(out/n).read_bytes(),'Independent Audio Tools rebuild differs: '+n)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--system-apps',required=True,type=Path);p.add_argument('--utilities',required=True,type=Path)
    p.add_argument('--baseline',required=True,type=Path);p.add_argument('--output',type=Path,default=ROOT/'dist/audio-tools');a=p.parse_args()
    build(a.system_apps.resolve(),a.utilities.resolve(),a.baseline.resolve(),a.output.resolve())
    verify_target_bytes({x.name:x.read_bytes() for x in a.output.iterdir() if x.is_file()},a.baseline.resolve(),a.system_apps.resolve(),a.utilities.resolve())
    print('Audio Tools target rebuild verified')

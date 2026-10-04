#!/usr/bin/env python3
"""Build the actual watch default.elf against the pinned generic runtime SDK."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build(launcher=False, returning=False):
    cc = os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc')
    fallback = Path.home()/'.platformio/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc'
    if not cc and fallback.exists():
        cc = str(fallback)
    if not cc:
        raise SystemExit('Set TWATCH_CC to the pinned ESP32-S3 compiler')
    sources = json.loads((ROOT/'sdk/app/SOURCES.json').read_text())
    for name,source in sources.items():
        if hashlib.sha256((ROOT/'sdk/app'/name).read_bytes()).hexdigest()!=source['sha256']:
            raise ValueError('Canonical app SDK hash mismatch')
    out = ROOT/('dist/launcher' if launcher else 'dist/clock')
    out.mkdir(parents=True, exist_ok=True)
    elf = out/('clock.elf' if returning else 'default.elf')
    exports_map=out/'exports.map'
    exports_map.write_text('{ global: app_main; local: *; };\n')
    effect_obj=out/'boot-effect.o'
    subprocess.run([cc.removesuffix('gcc')+'g++','-std=c++11','-Os','-fPIC','-mtext-section-literals','-mlongcalls',
        '-fvisibility=hidden','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-ffreestanding','-fno-builtin',
        '-Wall','-Wextra','-Werror','-I'+str(ROOT/'sdk/driver'),'-c',str(ROOT/'apps/clock/effects/boot.cpp'),'-o',str(effect_obj)],check=True)
    subprocess.run([cc,'-std=c11' ,'-Os','-fPIC','-mtext-section-literals','-mlongcalls',
                    '-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles',
                    '-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(exports_map),'-Wall','-Wextra','-Werror',
                    *(['-DWATCH_CLOCK_LAUNCHER'] if launcher else []),
                    *(['-DWATCH_CLOCK_RETURN'] if returning else []),
                    '-I'+str(ROOT/'sdk/app'),'-I'+str(ROOT/'sdk/driver'),'-I'+str(ROOT/'include'),
                    str(ROOT/'apps/clock/crown.c'),str(ROOT/'apps/clock/nova/nova.c'),str(ROOT/'apps/clock/effects/divdi3.c'),str(effect_obj),
                    '-lgcc','-o',str(elf)],check=True)
    readelf = cc.removesuffix('gcc')+'readelf'
    nm = cc.removesuffix('gcc')+'nm'
    header = subprocess.check_output([readelf,'-h',str(elf)],text=True)
    assert all(s in header for s in ('ELF32','little endian','Xtensa','DYN'))
    symbols = subprocess.check_output([nm,'-D',str(elf)],text=True)
    imports = {line.split()[-1] for line in symbols.splitlines() if ' U ' in ' '+line}
    exports = {line.split()[-1] for line in symbols.splitlines()
               if len(line.split())>=3 and line.split()[-2] in ('T','D','B','R')}
    assert imports <= {'risc_runtime_get_api','memcpy','memset','malloc','free'}, imports
    assert 'risc_runtime_get_api' in imports and exports == {'app_main'}, (imports,exports)
    manifest = json.loads((ROOT/'apps/clock/manifest.json').read_text())
    if returning:
        manifest['id']='twatch-clock-return';manifest['file_name']='clock.elf'
    if launcher:
        manifest['requires'].insert(1,{'capability':'input.touch.raw','api':1})
        manifest['requires'].append({'capability':'storage.key-value','api':1})
    (out/('clock.json' if returning else 'default.json')).write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'build-record.json').write_text(json.dumps({'schema':1,'id':manifest['id'],
        'version':manifest['version'],'architecture':'xtensa-esp32s3','artifact':elf.name,
        'size_bytes':elf.stat().st_size,'sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),
        'sdk':sources,'imports':sorted(imports)},indent=2)+'\n')
    print(f"{elf.name} {manifest['version']}: target ABI, entry and import checks passed")


if __name__ == '__main__':
    build()

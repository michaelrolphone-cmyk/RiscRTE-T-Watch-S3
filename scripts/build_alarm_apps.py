#!/usr/bin/env python3
"""Build explicit alarm-enabled shared apps and original singleton; no flashing."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
from build_launcher_apps import build,ROOT

def build_service(system,utilities,runtime,points=False):
    pins=json.loads((ROOT/('apps/points-sources.json' if points else 'apps/alarm-sources.json')).read_text())
    for name,repo in [('system-apps',system),('utilities',utilities),('runtime',runtime)]:
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()!=pins[name]['commit'] or subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=repo,text=True).strip():
            raise ValueError('Clean exact alarm source required: '+name)
    cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc')
    if not cc:raise ValueError('Set pinned TWATCH_CC')
    out=ROOT/('dist/points-launcher' if points else 'dist/alarm-launcher');out.mkdir(parents=True,exist_ok=True)
    mapping=out/'alarm-service.map';mapping.write_text('{ global: t5_driver_get; local: *; };\n')
    elf=out/'alarm-service.elf'
    subprocess.run([cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror',*(['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER'] if points else []),*['-I'+str(p) for p in [utilities/'lib/Alarm/include',runtime/'sdk/driver',system/'lib/PortableApps/include']],str(utilities/'Services/alarm_service/service.c'),'-lgcc','-o',str(elf)],check=True)
    symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True)
    imports={line.split()[-1] for line in symbols.splitlines() if ' U ' in ' '+line}
    exports={line.split()[-1] for line in symbols.splitlines() if len(line.split())>=3 and line.split()[-2] in ('T','D','B','R')}
    assert imports<={'memcpy','memset','memcmp','strcmp','strlen'} and exports=={'t5_driver_get'}
    data=elf.read_bytes();assert data[:7]==b'\x7fELF\x01\x01\x01' and data[16:20]==b'\x03\x00\x5e\x00'
    subprocess.run([str(out/'validate-elf'),str(elf)],check=True)
    manifest=(utilities/('Services/alarm_service/points-manifest.json' if points else 'Services/alarm_service/manifest.json')).read_bytes();(out/'alarm-service.json').write_bytes(manifest)
    evidence={'source_pins':pins,'service_version':json.loads(manifest)['version'],'source_sha256':hashlib.sha256((utilities/'Services/alarm_service/service.c').read_bytes()).hexdigest(),'elf_sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data),'imports':sorted(imports),'exports':sorted(exports),'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0]}
    (out/'alarm-service-build.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print('Original alarm-service ELF: exact source, target ABI/import/export passed')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--system-apps',type=Path,required=True);p.add_argument('--utilities',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);a=p.parse_args()
    system,utilities,runtime=a.system_apps.resolve(),a.utilities.resolve(),a.runtime.resolve()
    build(system,utilities,alarms=True,runtime=runtime);build_service(system,utilities,runtime)

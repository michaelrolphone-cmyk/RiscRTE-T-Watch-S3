#!/usr/bin/env python3
"""Build the reusable station-management Wi-Fi provider independently."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(output: Path):
    if output.exists():raise FileExistsError(output)
    output.mkdir(parents=True)
    cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc') or str(Path.home()/'.platformio/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc')
    manifest=json.loads((ROOT/'drivers/twatch_wifi/manifest.json').read_text())
    flags=['-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(ROOT/'exports.map'),'-Wall','-Wextra','-Werror','-fstack-usage','-Wframe-larger-than=1536']
    elf=output/'driver.elf';subprocess.run([cc,*flags,'-I'+str(ROOT/'sdk/driver'),'-I'+str(ROOT/'include'),str(ROOT/'drivers/twatch_wifi/driver.c'),'-o',str(elf)],check=True)
    symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True)
    imported={s.split()[-1] for s in symbols.splitlines() if ' U ' in ' '+s}
    exported={s.split()[-1] for s in symbols.splitlines() if len(s.split())>=3 and s.split()[-2] in ('T','D','B','R')}
    assert imported<={'memcpy','memset','strcmp','strlen'} and exported=={'t5_driver_get'}
    raw=elf.read_bytes();assert raw[:7]==b'\x7fELF\x01\x01\x01' and raw[16:20]==b'\x03\x00\x5e\x00'
    manifest.pop('status',None);manifest.pop('physical_verification',None)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    inputs=[*sorted((ROOT/'sdk/driver').glob('*.h')),*sorted((ROOT/'drivers/twatch_wifi').glob('*')),*sorted((ROOT/'include').glob('*.h'))]
    result={'version':manifest['version'],'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'imports':sorted(imported),'exports':sorted(exported),'source_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'tracked_worktree_dirty':bool(subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=no'],text=True).strip()),'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs if p.is_file()},'hardware_tested':False}
    (output/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('version','bytes','sha256')}))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output.resolve())

#!/usr/bin/env python3
"""Compile every source manifest, check ELF ABI/imports, package and hash outputs."""
import hashlib,json,os,shutil,subprocess,zipfile
from pathlib import Path
from generate_board import generate
ROOT=Path(__file__).resolve().parents[1]
def digest(b):return hashlib.sha256(b).hexdigest()
def main():
    cc=os.environ.get('TWATCH_CC') or shutil.which('xtensa-esp32s3-elf-gcc')
    fallback=Path.home()/'.platformio/packages/toolchain-xtensa-esp32s3/bin/xtensa-esp32s3-elf-gcc'
    if not cc and fallback.exists():cc=str(fallback)
    if not cc:raise SystemExit('Set TWATCH_CC to xtensa-esp32s3-elf-gcc')
    nm=cc.removesuffix('gcc')+'nm';readelf=cc.removesuffix('gcc')+'readelf'
    recovery=json.loads((ROOT/'docs/DISPLAY_RECOVERY.json').read_text())
    for name,expected in recovery['source_sha256'].items():
        assert digest((ROOT/name).read_bytes())==expected,('Display baseline source differs',name)
    compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0]
    generate();catalog=[]
    subprocess.run([cc,"-std=c11",f"-I{ROOT}/sdk/driver",f"-I{ROOT}/include","-fsyntax-only",str(ROOT/"tests/abi.c")],check=True)
    for mp in sorted((ROOT/'drivers').glob('*/manifest.json')):
        m=json.loads(mp.read_text());src=list(mp.parent.glob('*.c'));assert len(src)==1,mp
        out=ROOT/'dist'/m['id'];out.mkdir(parents=True,exist_ok=True);elf=out/'driver.elf'
        args=[cc,'-std=c11','-shared','-fPIC','-fvisibility=hidden','-nostdlib','-mlongcalls','-Os','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Wno-misleading-indentation','-Wno-unused-function','-Werror',f'-I{ROOT}/sdk/driver',f'-I{ROOT}/include',f'-I{ROOT}/dist/generated',f'-Wl,--version-script={ROOT}/exports.map','-Wl,-soname,driver.elf',str(src[0]),'-lgcc','-o',str(elf)]
        subprocess.run(args,check=True)
        if m['id']=='twatch-panel' and '8.4.0' in compiler:
            assert elf.stat().st_size==recovery['panel_elf_size_bytes']
            assert digest(elf.read_bytes())==recovery['panel_elf_sha256'],'Panel differs from physically working 0.4.0 executable'
            print('Panel ELF byte-identical to verified 0.4.0 CI baseline')
        header=subprocess.check_output([readelf,'-h',str(elf)],text=True)
        assert 'ELF32' in header and 'little endian' in header and 'Xtensa' in header and 'DYN' in header
        symbols=subprocess.check_output([nm,'-D',str(elf)],text=True)
        imports={line.split()[-1] for line in symbols.splitlines() if ' U ' in ' '+line}
        assert imports <= {'memcpy','memset','strcmp','strlen'},(m['id'],imports)
        exports={line.split()[-1] for line in symbols.splitlines() if len(line.split())>=3 and line.split()[-2] in ('T','D','B','R')}
        assert exports=={'t5_driver_get'},(m['id'],exports)
        cap=m['provides'][0]
        files={'driver.elf':elf.read_bytes(),'provider-abi.v1':f"os-cpu-abi=1\nprovides={cap['capability']}\napi={cap['api']}\n".encode(),'source-manifest.json':(json.dumps(m,indent=2)+'\n').encode()}
        if m['id']=='twatch-board':
            files.update({p.name:p.read_bytes() for p in (ROOT/'hardware').glob('*.json')})
            files['platform-resources.json']=(ROOT/'platform-resources.json').read_bytes()
            files['board-variants.json']=(ROOT/'board.json').read_bytes()
        manifest=dict(schema=1,kind='driver',id=m['id'],version=m['version'],architecture=m['architecture'],artifact='driver.elf',driver_abi=2,provides=m['provides'],requires=[dict(capability=x['capability'],min_api=x['api']) for x in m['requires']],entries=[dict(name=k,size_bytes=len(v),sha256=digest(v),executable=k.endswith('.elf')) for k,v in files.items()])
        if 'hardware_compatibility' in m:manifest['hardware_compatibility']=m['hardware_compatibility']
        (out/'.package.json').write_text(json.dumps(manifest,indent=2)+'\n')
        package=ROOT/'dist'/f"driver-{m['id']}-{m['version']}-xtensa-esp32s3.rte.zip"
        with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_STORED) as z:
            for k,v in {'.package.json':(json.dumps(manifest,indent=2)+'\n').encode(),**files}.items():
                info=zipfile.ZipInfo(k,(2026,1,1,0,0,0));info.external_attr=0o100644<<16;z.writestr(info,v)
        catalog.append(dict(id=m['id'],version=m['version'],kind='driver',architecture=m['architecture'],archive=package.name,size_bytes=package.stat().st_size,sha256=digest(package.read_bytes())))
        print(m['id'],m['version'],'ELF/imports/package OK')
    (ROOT/'dist/catalog.json').write_text(json.dumps(dict(schema=1,packages=catalog),indent=2)+'\n')
    print(f'{len(catalog)} target ELFs and packages built')
if __name__=='__main__':main()

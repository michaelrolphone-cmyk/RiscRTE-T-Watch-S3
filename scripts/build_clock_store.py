#!/usr/bin/env python3
"""Build and unpack-verify a SPIFFS image from one already-verified clock ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile
from verify_clock_deployment import verify

SIZE=0x4f0000


def build(archive,tool,out):
    record=verify(archive)
    out.mkdir(parents=True,exist_ok=True)
    image=out/(archive.stem+'-bootfs.bin')
    with tempfile.TemporaryDirectory() as tmp:
        source=Path(tmp)/'store';source.mkdir()
        expected={}
        with zipfile.ZipFile(archive) as z:
            for name in sorted(n for n in z.namelist() if n.startswith('store/')):
                relative=name.removeprefix('store/')
                if len(('/'+relative).encode())>=32:
                    raise ValueError('SPIFFS object name exceeds the pinned runtime limit')
                data=z.read(name);expected[relative]=data
                path=source/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        options=['-p','256','-b','4096','-s',str(SIZE)]
        subprocess.run([str(tool),'-c',str(source),*options,str(image)],check=True)
        unpacked=Path(tmp)/'unpacked';unpacked.mkdir()
        subprocess.run([str(tool),'-u',str(unpacked),*options,str(image)],check=True)
        actual={str(p.relative_to(unpacked)):p.read_bytes() for p in unpacked.rglob('*') if p.is_file()}
        if actual!=expected or image.stat().st_size!=SIZE:
            raise ValueError('SPIFFS round-trip differs from exact deployment store')
    metadata={'schema':1,'profile':record['profile'],'watch_source_sha':record['source_sha'],
              'deployment_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
              'image':image.name,'sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
              'size_bytes':SIZE,'partition_label':'bootfs','partition_offset':0x310000,
              'page_size':256,'block_size':4096,'tool_sha256':hashlib.sha256(tool.read_bytes()).hexdigest(),
              'files':len(expected),'round_trip_verified':True,
              'warning':'Only for the explicitly matching generic 8MiB partition layout; no firmware or device verification implied'}
    (out/(archive.stem+'-bootfs.json')).write_text(json.dumps(metadata,indent=2)+'\n')
    print('Verified SPIFFS image',image)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--mkspiffs',required=True,type=Path,help='Pinned PlatformIO tool-mkspiffs2.230.0 Arduino ESP32 binary')
    parser.add_argument('--output',type=Path,default=Path('dist/clock-images'))
    args=parser.parse_args()
    build(args.archive.resolve(),args.mkspiffs.resolve(),args.output.resolve())

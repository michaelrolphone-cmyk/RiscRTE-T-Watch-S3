#!/usr/bin/env python3
"""Pack and independently unpack the verified Audio Tools common store."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from audio_overlay import ROOT,PROFILE,verify
from build_wifi_common import read_zip,require,sha
from build_wifi_store import SIZE,OFFSET,TOOL_SHA256,check_tool,check_image

def build(archive,tool,out):
    archive,tool,out=Path(archive),Path(tool).resolve(),Path(out)
    check_tool(tool);record=verify(archive)
    expected={n[6:]:b for n,b in read_zip(archive).items() if n.startswith('store/')}
    require(all(len(('/'+n).encode())<32 for n in expected),'SPIFFS object name exceeds pinned runtime limit')
    require(sum(map(len,expected.values()))<SIZE,'Audio store exceeds bootfs capacity')
    image=out/(archive.stem+'-bootfs.bin');out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        source=Path(d)/'store';source.mkdir()
        for n,b in sorted(expected.items()):
            p=source/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        subprocess.run([str(tool),'-c',str(source),'-p','256','-b','4096','-s',str(SIZE),str(image)],check=True,timeout=60)
    check_image(image,expected,tool)
    meta={'schema':1,'profile':PROFILE,'watch_source_sha':record['source_sha'],'deployment_sha256':sha(archive.read_bytes()),
          'image':image.name,'sha256':sha(image.read_bytes()),'size_bytes':SIZE,'partition_label':'bootfs0',
          'partition_offset':OFFSET,'page_size':256,'block_size':4096,'tool_sha256':TOOL_SHA256,'files':len(expected),
          'payload_bytes':sum(map(len,expected.values())),'round_trip_verified':True,'physical_verification':'pending',
          'layout':'riscrte-paired-16m-v1','store_abi':1,'migration_only':True,'apps':list(record['apps'])}
    image.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n');return meta

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--mkspiffs',required=True,type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'dist/audio-common');a=p.parse_args()
    print(json.dumps(build(a.archive,a.mkspiffs,a.output),indent=2))

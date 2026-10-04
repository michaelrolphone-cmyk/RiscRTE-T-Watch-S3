#!/usr/bin/env python3
"""Create eight verified additive profiles and one common Audio Tools archive."""
import argparse
import io
import json
from pathlib import Path
from audio_deployment import ROOT,PROFILE,build_files,encoded,read_zip,require,sha,verify,zip_bytes
from build_wifi_common import profiles


def build(archives,compiled,head,out):
    require(len(archives)==9,'Eight explicit baselines and one verified common required')
    payload={p.name:p.read_bytes() for p in compiled.iterdir() if p.is_file()};records=[];outputs=[]
    for archive in archives:
        files=build_files(archive.read_bytes(),payload,head);record=json.loads(files['deployment-record.json'])
        require(record['profile'] not in {r['profile'] for r in records},'Duplicate audio profile');records.append(record)
        outputs.append((f"twatch-audio-tools-{head[:8]}-{record['profile']}.zip",zip_bytes(files)))
    require({r['profile'] for r in records}==profiles(ROOT)|{PROFILE},'Missing explicit audio profile')
    common=read_zip(io.BytesIO(next(raw for name,raw in outputs if name.endswith(PROFILE+'.zip'))));expected={n:b for n,b in common.items() if n.startswith('store/')}
    for _,raw in outputs:
        files=read_zip(io.BytesIO(raw));store={n:b for n,b in files.items() if n.startswith('store/')};board=json.loads(store['store/board.json']);board['revision']='wifi-launcher-common';store['store/board.json']=encoded(board)
        require(store==expected,'Audio stores differ beyond baseline board revision')
    out.mkdir(parents=True,exist_ok=True);catalog=[]
    for name,raw in outputs:
        path=out/name;path.write_bytes(raw);record=verify(path,expected_head=head);catalog.append(dict(profile=record['profile'],archive=name,sha256=sha(raw),source_sha=head))
    (out/'catalog.json').write_bytes(encoded(dict(schema=1,deployments=sorted(catalog,key=lambda r:r['profile']))));return catalog


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archives',nargs='+',type=Path);p.add_argument('--compiled',type=Path,default=ROOT/'dist/audio-tools');p.add_argument('--output',type=Path,default=ROOT/'dist/audio-deployments');p.add_argument('--pr-head-sha',required=True);a=p.parse_args()
    print(json.dumps(build(a.archives,a.compiled,a.pr_head_sha,a.output),indent=2))

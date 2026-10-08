#!/usr/bin/env python3
"""Qualify the final17/.73 pair from exact delivered13–15 through both native generations."""
import argparse,json
from pathlib import Path
from bound_preserving_watch_update import arguments,verify_package,ORIGINS
from build_preserving_watch_update import clean,profile,read_origin
from current_apps_overlay import ROOT,encoded,require
from runtime_features_watch_candidate import read_native
from test_preserving_watch_upgrade import prove

def main():
    p=argparse.ArgumentParser(description=__doc__);arguments(p)
    for name in ('installed-runtime','installed-native','origin-image','target','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--origin-version',choices=ORIGINS,required=True)
    a=p.parse_args();require(not a.output.exists(),'Proof output must be new')
    head=clean(ROOT);clean(a.installed_runtime,profile()['runtime_source'])
    bound=verify_package(a.target,a.binding_repository,a.binding,a.runtime,a.native)
    receipt,files,bootfs,payload,ota,native=bound
    origin=read_origin(a.origin_image,a.origin_version)
    installed=read_native(a.installed_native,a.installed_runtime,ROOT)
    proof=prove(origin,native,files,payload,a.runtime,installed_runtime=a.installed_runtime,installed_native=installed,apps_dir=a.target)
    require(verify_package(a.target,a.binding_repository,a.binding,a.runtime,a.native)==bound and clean(ROOT)==head,
            'Bound proof source or exact bytes changed')
    proof['qualification_source']=head
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(encoded(proof))
    print(json.dumps({'output':str(a.output),'source':a.origin_version,'target':ota['version'],
                      'scenarios':len(proof['scenarios']),'processes':len(proof['transactions']),
                      'negative_admissions':len(proof['rejections']),'sanitized':proof['sanitized']}))

if __name__=='__main__':main()

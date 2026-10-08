#!/usr/bin/env python3
"""Exercise the installed updater on the independently bound final17 payload."""
import argparse,json
from pathlib import Path
from bound_preserving_watch_update import arguments,verify_package,ORIGINS
from build_preserving_watch_update import clean,read_origin
from current_apps_overlay import ROOT,encoded,require
from test_preserving_update_service import prove_service

def main():
    p=argparse.ArgumentParser(description=__doc__);arguments(p)
    for name in ('system-apps','origin-image','target','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--origin-version',choices=ORIGINS,required=True)
    a=p.parse_args();head=clean(ROOT)
    bound=verify_package(a.target,a.binding_repository,a.binding,a.runtime,a.native)
    origin=read_origin(a.origin_image,a.origin_version)
    proof=prove_service(a.system_apps,origin,a.target,a.output,expected_target=bound[0]['cohort'])
    require(verify_package(a.target,a.binding_repository,a.binding,a.runtime,a.native)==bound and clean(ROOT)==head,
            'Bound service proof source or bytes changed')
    proof['native_binding']=bound[0];proof['qualification_source']=head
    a.output.write_bytes(encoded(proof))
    print(json.dumps({'cases':len(proof['cases']),'negative_catalog_bindings':len(proof['negative_catalog_bindings']),
                      'output':str(a.output),'source':a.origin_version,'target':proof['target_cohort']['version']}))

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Bind exact paired bytes to the installed catalog/download provider source."""
import argparse,copy,json,os,shlex,subprocess,tempfile
from pathlib import Path
from build_preserving_watch_update import profile,read_origin,clean
from current_apps_overlay import ROOT,encoded,metadata,require
from current_cohort import parse,package
from read_only_spiffs import read_image

ACCEPTED_SYSTEM='3d95c712ed458d3e5092fc8725a16d495dca9e22'
SCENARIOS=('success','cancel','close-retained','changed-origin')


def catalog_binding(catalog,record,payload,origin_version,expected_target=None):
    require(catalog.get('schema')==1 and catalog.get('firmware')==record,
            'Executed catalog differs from the qualified firmware record')
    native=profile()['firmware'] if expected_target is None else {'size_bytes':expected_target['firmware_size'],'sha256':expected_target['firmware_sha256']}
    size=native['size_bytes']
    require(metadata(payload[:size])==native and len(payload)==size+0x510000,
            'Payload does not contain the exact selected native/store pair')
    store=read_image(payload[size:],0x510000);identity=parse(store['cohort.json'])
    if expected_target is None:
        require(identity['runtime_version']==profile()['runtime_version'] and
                identity['version']==profile()['routes'][origin_version], 'Wrong source-bound route')
    else:
        require(identity==expected_target, 'Target differs from independently verified native binding')
    expected_payload,ota=package(identity,payload[:size],payload[size:])
    require(payload==expected_payload and record.get('ota')==ota,
            'Catalog identity or digests differ from the embedded target cohort')
    require(record.get('version')==identity['version'], 'Outer firmware version differs')
    return identity


def negative_bindings(catalog,record,payload,origin_version,expected_target=None):
    results=[]
    for field,value in (('source_revision','0'*40),('runtime_version','0.1.56'),('version','1.0.99')):
        changed=copy.deepcopy(catalog);changed['firmware']['ota'][field]=value
        if field=='version':changed['firmware']['version']=value
        # Reject both a stale release record and a consistently altered record:
        # neither is allowed to describe these exact payload bytes.
        for synchronized in (False,True):
            proposed=changed['firmware'] if synchronized else record
            try:catalog_binding(changed,proposed,payload,origin_version,expected_target)
            except ValueError:pass
            else:raise AssertionError('Mismatched catalog was qualified: '+field)
            results.append({'field':field,'record_also_changed':synchronized,'rejected':True})
    return results


def prove_service(system,origin,target,output,expected_target=None):
    system,target,output=map(lambda p:Path(p).resolve(),(system,target,output))
    require(not output.exists(),'Proof output must be new')
    source=clean(system);origin_version=origin['identity']['version']
    record=json.loads((target/'release-record.json').read_bytes());ota=record['ota']
    payload=target/ota['asset'];raw=payload.read_bytes()
    catalog_raw=(target/'catalog-fixture.json').read_bytes();catalog_value=json.loads(catalog_raw)
    identity=catalog_binding(catalog_value,record,raw,origin_version,expected_target)
    negative=negative_bindings(catalog_value,record,raw,origin_version,expected_target)
    source_hashes={};results=[]
    with tempfile.TemporaryDirectory(prefix='watch-update-service-') as tmp:
        tmp=Path(tmp);origin_file=tmp/'origin.json';origin_file.write_bytes(origin['store']['cohort.json'])
        target_file=tmp/'target.json';target_file.write_bytes(encoded(identity))
        for sanitized in (False,True):
            exe=tmp/('service-san' if sanitized else 'service');dep=tmp/'service.d'
            flags=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie'] if sanitized else []
            subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-Wno-deprecated-declarations',
                            '-MMD','-MF',str(dep),*flags,
                            *['-I'+str(system/path) for path in ('Services/update','lib/PortableApps/include','lib/NativeApps/include')],
                            str(ROOT/'tests/preserving_update_service.cpp'),'-lcrypto','-o',str(exe)],check=True)
            dependencies=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
            for path in map(lambda x:Path(x).resolve(),dependencies):
                if path==ROOT/'tests/preserving_update_service.cpp':continue
                relative=path.relative_to(system).as_posix()
                accepted=subprocess.check_output(['git','-C',str(system),'show',ACCEPTED_SYSTEM+':'+relative])
                require(path.read_bytes()==accepted,'Provider source differs from installed12–15 code: '+relative)
                source_hashes[relative]=metadata(accepted)
            require('Services/update/service.cpp' in source_hashes and 'Services/update/Catalog.h' in source_hashes,
                    'Production service/parser missing from dependency closure')
            for scenario in SCENARIOS:
                process=subprocess.run([str(exe),str(target/'catalog-fixture.json'),str(origin_file),str(payload),str(target_file),scenario],
                                       check=True,capture_output=True,text=True,timeout=30,
                                       env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
                result=json.loads(process.stdout);require(result['scenario']==scenario and result['actual_provider'] and not result['hardware'],
                                                         'Service result scope differs')
                results.append({'sanitized':sanitized,**result})
    require(clean(system)==source and payload.read_bytes()==raw and
            (target/'catalog-fixture.json').read_bytes()==catalog_raw,'Source, catalog or payload changed')
    proof={'schema':1,'scope':'actual-installed-updater-exact-catalog-and-payload',
           'installed_origin':origin['identity'],'installed_update_provider':metadata(origin['store']['update-fw/driver.elf']),
           'selected_source':source,'exact_accepted_production_source':ACCEPTED_SYSTEM,'source_files':source_hashes,
           'catalog':metadata(catalog_raw),'payload':metadata(raw),'target_cohort':identity,
           'cases':results,'negative_catalog_bindings':negative,
           'transport_and_native_bank_are_doubles':True,'physical_tls_network_flash_tested':False,
           'runtime_transaction_proof_required_separately':True,'published':False}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(encoded(proof))
    return proof


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--system-apps',type=Path,required=True)
    p.add_argument('--origin-image',type=Path,required=True)
    p.add_argument('--origin-version',choices=tuple(profile()['origins']),required=True)
    p.add_argument('--target',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();origin=read_origin(a.origin_image,a.origin_version)
    proof=prove_service(a.system_apps,origin,a.target,a.output)
    print(json.dumps({'cases':len(proof['cases']),'output':str(a.output),'source':a.origin_version,'target':proof['target_cohort']['version']}))


if __name__=='__main__':main()

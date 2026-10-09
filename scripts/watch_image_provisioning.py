#!/usr/bin/env python3
"""Freeze and pin the complete initial-only Watch 1.0.17 image deployment.

No private credentials, NVS, hardware operation, release or catalog publication.
The exact Runtime, native binding and complete product graph are verified first.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import watch_native_binding as binding
from check_runtime_store_admission import admit_cohort
from read_only_spiffs import read_image

ROOT=Path(__file__).resolve().parents[1]
REPOSITORY='michaelrolphone-cmyk/RiscRTE-T-Watch-S3'
VERSION='1.0.17'
PAYLOAD_PATH='provisioning/watch-'+VERSION
PAYLOAD_NAMES={'image.bin','seed.zip','LICENSES.zip','binding.json','payload.json','COMPLETE'}
PAYLOAD_MARKER=b'riscrte.watch-image-provisioning.v1\n'
DEPLOYMENT_MARKER=b'riscrte.watch-image-deployment.v1\n'
AUXILIARY_NATIVE={'platformio.ini','partitions-paired-appdata.csv','requirements-ci.txt'}


def require(condition,message):
    if not condition:raise ValueError(message)


def meta(data):return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def exact(left,right):return encoded(left)==encoded(right)


def directory_names(directory,maximum):
    names=set()
    with os.scandir(directory) as entries:
        for entry in entries:
            require(len(names)<maximum,'Directory inventory bound');names.add(entry.name)
    return names


def runtime_tools(runtime):
    runtime=Path(runtime).resolve();contract=binding.contract()
    binding.source(runtime,contract['runtime_source'])
    require(subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=runtime,text=True).strip()==contract['runtime_tree'],'Runtime tree differs')
    sys.path.insert(0,str(runtime/'scripts'))
    import provision_device as device
    import provision_profile as profile
    from store_image_capacity import inspect_image
    require(Path(device.__file__).parent==runtime/'scripts' and Path(profile.__file__).parent==runtime/'scripts','Runtime module path differs')
    return runtime,device,profile,inspect_image


def pinned_binding_source(source):
    require(isinstance(source,str) and re.fullmatch('[0-9a-f]{40}',source),'Full binding source required')
    # Original build commits may be restored from the published Watch-only
    # source bundle after connector publication maps equivalent commit IDs.
    require(subprocess.check_output(['git','cat-file','-t',source],cwd=ROOT,text=True).strip()=='commit','Binding source must be a commit')
    for name in ('scripts/watch_native_binding.py','apps/provisioning-native-117.json'):
        require(subprocess.check_output(['git','show',source+':'+name],cwd=ROOT)==(ROOT/name).read_bytes(),'Binding verifier/source contract differs')


def pinned_packaging_source(source):
    require(isinstance(source,str) and re.fullmatch('[0-9a-f]{40}',source),'Full packaging source required')
    require(subprocess.check_output(['git','cat-file','-t',source],cwd=ROOT,text=True).strip()=='commit','Packaging source must be a commit')
    binding.source(ROOT)
    # Publication adds payloads, instructions and CI receipts. Every executable
    # helper, native harness, configuration and producer must still be the exact
    # committed recipe that generated the payload, including on verification.
    paths=['.',':(exclude)docs/**',':(exclude)provisioning/**',':(exclude).github/**']
    require(subprocess.run(['git','diff','--quiet',source,'--',*paths],cwd=ROOT).returncode==0,'Packaging source differs')


def write_files(directory,files):
    for name,data in sorted(files.items()):
        path=directory/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:require(stream.write(data)==len(data),'Short payload write')


def publish_files(directory,files,profile):
    require('COMPLETE' in files,'Output completion marker required')
    directory.mkdir()
    try:
        payload={name:raw for name,raw in files.items() if name!='COMPLETE'}
        write_files(directory,payload)
        require(all(profile.read(directory/name,32*1024*1024)==raw for name,raw in payload.items()),'Payload readback differs')
        # An interrupted writer must never leave a success marker ahead of the
        # verified files. Consumers still verify every file, hash and receipt.
        write_files(directory,{'COMPLETE':files['COMPLETE']})
        require(profile.read(directory/'COMPLETE',64)==files['COMPLETE'],'Completion readback differs')
    except BaseException:
        shutil.rmtree(directory);raise


def archive_bytes(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(files.items()):
            entry=zipfile.ZipInfo(name,(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
            entry.external_attr=0o100644<<16;archive.writestr(entry,data)
    return out.getvalue()


def unpack(raw,profile):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries=archive.infolist();names=[item.filename for item in entries]
        require(0<len(names)<=64 and len(names)==len(set(names)),'Seed ZIP inventory differs')
        for item in entries:
            profile.relative(item.filename,192)
            require('/' not in item.filename and not item.is_dir() and item.external_attr>>28 in (0,8) and
                    not item.flag_bits&1 and item.compress_type==zipfile.ZIP_DEFLATED and
                    0<item.file_size<=32*1024*1024,'Seed ZIP member refused')
        require(sum(item.file_size for item in entries)<=64*1024*1024,'Seed ZIP size bound')
        files={}
        for item in entries:
            data=bytearray()
            with archive.open(item) as stream:
                while True:
                    chunk=stream.read(min(65536,item.file_size-len(data)+1))
                    if not chunk:break
                    data.extend(chunk)
                    require(len(data)<=item.file_size,'Seed ZIP expanded size differs')
            require(len(data)==item.file_size,'Seed ZIP member size differs')
            files[item.filename]=bytes(data)
        return files


def read_seed(directory,profile):
    directory=profile.safe_path(directory);files={};total=0
    with os.scandir(directory) as entries:
        for entry in entries:
            require(len(files)<64,'Seed directory inventory bound')
            profile.relative(entry.name,192)
            data=profile.read(Path(entry.path),min(32*1024*1024,64*1024*1024-total))
            total+=len(data);files[entry.name]=data
    require(files,'Empty seed directory')
    return files


def checked_seed(seed_files,runtime,device,profile,work):
    seed_path=work/'input-seed';write_files(seed_path,seed_files)
    record,blobs=device.verify_seed(seed_path,work)
    contract=binding.contract()
    require(record['source_sha']==contract['runtime_source'] and record['firmware_version']==contract['runtime_version'] and
            record['target']=='esp32s3-16mb-appdata-iq' and record['store_abi']==2 and
            record['layout']=='riscrte-paired-appdata-v2' and 'extension' not in record,'Stock Watch generic seed differs')
    generic={name:seed_files[name] for name in ('board.json','boot.json','default.elf')}
    require(all(generic[name]==(runtime/'data'/name).read_bytes() for name in ('board.json','boot.json')) and
            read_image(seed_files['bootfs0.bin'],0x510000)==generic,'Exact three-file generic seed required')
    require(b'RISC_PROVISION_IMAGE:1\0' in blobs['firmware.bin'] and b'RISC_PROVISION_IMAGE:1\0' in blobs['firmware.elf'],'Native image provisioning support missing')
    # Recover the stock candidate's source-metadata sidecars from its exact
    # committed Runtime, never by relabeling a candidate or omitting its proof.
    candidate=profile.decode(blobs['candidate.json']);native={name:blobs[name] for name in candidate['assets'] if name in blobs}
    for name in set(candidate['assets'])-set(native):
        require(name in AUXILIARY_NATIVE,'Unexpected stock native sidecar')
        native[name]=profile.read(runtime/name)
    for name,data in native.items():require(meta(data)==candidate['assets'][name],'Native candidate sidecar differs')
    native['candidate.json']=blobs['candidate.json'];native_path=work/'native';write_files(native_path,native)
    binding.native_inputs(runtime,native_path)
    return record,blobs,native_path


def snapshot_product(binding_dir,destination,profile):
    """Bound untrusted inputs before the original exact-byte binder reads them."""
    directory=profile.safe_path(binding_dir);names=directory_names(directory,4)
    require(names=={'store','bootfs.bin','binding.json','LICENSES.zip'},'Binding directory inventory differs')
    fixed={name:profile.read(directory/name,bound) for name,bound in
           (('bootfs.bin',0x510000),('binding.json',512*1024),('LICENSES.zip',2*1024*1024))}
    # The canonical binder accepts only its deterministic stored license ZIP.
    # Refuse compressed inputs before that older verifier can expand a member.
    with zipfile.ZipFile(io.BytesIO(fixed['LICENSES.zip'])) as archive:
        entries=archive.infolist();members=[item.filename for item in entries]
        require(0<len(entries)<=256 and len(members)==len(set(members)) and
                sum(item.file_size for item in entries)<=2*1024*1024,'License ZIP inventory bound')
        for item in entries:
            profile.relative(item.filename,192)
            require(not item.is_dir() and item.external_attr>>28 in (0,8) and not item.flag_bits&1 and
                    item.compress_type==zipfile.ZIP_STORED and 0<item.file_size<=1024*1024,'License ZIP member refused')
    store=profile.safe_path(directory/'store');require(store.is_dir(),'Binding store directory required')
    files={};total=0;paths=0;pending=[store]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                paths+=1;require(paths<=256,'Binding store path count bound')
                path=profile.safe_path(Path(entry.path));name=profile.relative(path.relative_to(store).as_posix(),192)
                if path.is_dir():pending.append(path);continue
                require(len(files)<95,'Binding store file count bound')
                raw=profile.read(path,min(1024*1024,0x510000-total));total+=len(raw);files[name]=raw
    require(len(files)==95,'Complete binding store required')
    write_files(destination,fixed);write_files(destination/'store',files)
    return destination


def checked_product(binding_dir,runtime,native,source,inspect,profile):
    pinned_binding_source(source)
    with tempfile.TemporaryDirectory(prefix='watch17-binding-') as temp:
        frozen=snapshot_product(binding_dir,Path(temp)/'binding',profile)
        receipt,files,image,licenses=binding.verify(frozen,runtime,native,source)
    require(len(files)==95 and sum(name.endswith('.elf') for name in files)==46 and receipt['cohort']['version']==VERSION,'Complete Watch17 store required')
    capacity=inspect(image,0x510000)
    admission=admit_cohort(runtime,(native/'firmware.elf').read_bytes(),files,files)
    require(admission['elf_count']==46 and admission['cohort_validated'] and not admission['hardware_calls'] and not admission['storage_calls'],'Full native product admission failed')
    return receipt,files,image,licenses,capacity,admission


def receipt_for(source,binding_source,product,files,image,licenses,seed_record,seed_files,seed_zip,capacity,admission):
    return {'schema':'riscrte.watch-image-provisioning','schema_version':1,'candidate_version':VERSION,
            'source_revision':source,'binding_source':binding_source,'runtime_source':seed_record['source_sha'],
            'runtime_version':seed_record['firmware_version'],'target':seed_record['target'],'layout':seed_record['layout'],
            'app_stage_source':product['app_stage_source'],'image':meta(image),'seed_zip':meta(seed_zip),
            'licenses_zip':meta(licenses),'native_firmware':meta(seed_files['firmware.bin']),
            'native_elf':meta(seed_files['firmware.elf']),'file_count':len(files),'elf_count':46,
            'files':{name:meta(data) for name,data in sorted(files.items())},'physical_capacity':capacity,'admission':admission,
            'scope':'Initial-only complete Watch1.0.17, including Contexts and qualified RF/Audio cleanup. Hardware provisioning UNRUN; never an existing-device update.'}


def freeze(runtime,binding_dir,binding_source,seed,output,source):
    runtime,device,profile,inspect=runtime_tools(runtime);output=profile.destination(output)
    binding.source(ROOT,source)
    pinned_packaging_source(source)
    seed_files=read_seed(seed,profile)
    with tempfile.TemporaryDirectory(prefix='watch17-provision-') as temp:
        record,blobs,native=checked_seed(seed_files,runtime,device,profile,Path(temp))
        product,files,image,licenses,capacity,admission=checked_product(binding_dir,runtime,native,binding_source,inspect,profile)
    seed_zip=archive_bytes(seed_files)
    receipt=receipt_for(source,binding_source,product,files,image,licenses,record,blobs,seed_zip,capacity,admission)
    payload={'image.bin':image,'seed.zip':seed_zip,'LICENSES.zip':licenses,
             'binding.json':encoded(product),'payload.json':encoded(receipt),'COMPLETE':PAYLOAD_MARKER}
    publish_files(output,payload,profile)
    return receipt


def verify_payload(runtime,payload):
    runtime,device,profile,inspect=runtime_tools(runtime);payload=profile.safe_path(payload)
    require(directory_names(payload,len(PAYLOAD_NAMES))==PAYLOAD_NAMES,'Payload inventory differs')
    frozen={name:profile.read(payload/name,32*1024*1024) for name in PAYLOAD_NAMES}
    require(frozen['COMPLETE']==PAYLOAD_MARKER,'Incomplete payload')
    receipt=profile.decode(frozen['payload.json']);pinned_packaging_source(receipt['source_revision'])
    files=read_image(frozen['image.bin'],0x510000)
    with tempfile.TemporaryDirectory(prefix='watch17-verify-') as temp:
        work=Path(temp);seed_files=unpack(frozen['seed.zip'],profile)
        record,blobs,native=checked_seed(seed_files,runtime,device,profile,work)
        product_path=work/'binding';write_files(product_path/'store',files)
        write_files(product_path,{'bootfs.bin':frozen['image.bin'],'binding.json':frozen['binding.json'],'LICENSES.zip':frozen['LICENSES.zip']})
        product,files,image,licenses,capacity,admission=checked_product(product_path,runtime,native,receipt['binding_source'],inspect,profile)
    expected=receipt_for(receipt['source_revision'],receipt['binding_source'],product,files,image,licenses,
                         record,blobs,frozen['seed.zip'],capacity,admission)
    require(exact(receipt,expected),'Payload receipt differs')
    return receipt,files,frozen


def bind(runtime,payload,revision,output):
    _,_,profile,_=runtime_tools(runtime);output=profile.destination(output)
    receipt,files,frozen=verify_payload(runtime,payload)
    require(re.fullmatch('[0-9a-f]{40}',revision),'Full immutable payload commit required')
    require(subprocess.check_output(['git','cat-file','-t',revision],cwd=ROOT,text=True).strip()=='commit','Payload revision must be a commit')
    tree=subprocess.check_output(['git','ls-tree','-rz',revision,'--',PAYLOAD_PATH],cwd=ROOT)
    entries={}
    for row in tree.split(b'\0'):
        if not row:continue
        properties,name=row.split(b'\t',1);mode,kind,_=properties.split(b' ')
        require(mode==b'100644' and kind==b'blob','Committed payload type differs');entries[name.decode()]=True
    require(set(entries)=={PAYLOAD_PATH+'/'+name for name in PAYLOAD_NAMES},'Committed payload inventory differs')
    for name,data in frozen.items():
        require(subprocess.check_output(['git','show',revision+':'+PAYLOAD_PATH+'/'+name],cwd=ROOT)==data,'Committed payload bytes differ')
    base=f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}/{PAYLOAD_PATH}/'
    inventory={'schema':'riscrte.provisioning-inventory','schema_version':2,'layout':receipt['layout'],'runtime_target':receipt['target'],
               'image':{'url':base+'image.bin',**receipt['image']},
               'files':[{'path':name,**meta(data)} for name,data in sorted(files.items())]}
    profile.verify_inventory(inventory,files)
    deployment={'schema':'riscrte.watch-image-deployment','schema_version':1,'candidate_version':VERSION,
                'payload_revision':revision,'runtime_source':receipt['runtime_source'],'binding_source':receipt['binding_source'],
                'inventory_sha256':meta(profile.encode(inventory))['sha256'],
                'downloads':{name:{'url':base+name,**meta(raw)} for name,raw in sorted(frozen.items())},'scope':receipt['scope']}
    publish_files(output,{'inventory.json':profile.encode(inventory),'deployment.json':encoded(deployment),'COMPLETE':DEPLOYMENT_MARKER},profile)
    return deployment


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):raise ValueError('Immutable download redirect refused')


def verify_endpoints(runtime,deployment):
    _,_,profile,_=runtime_tools(runtime);deployment=profile.safe_path(deployment)
    require(directory_names(deployment,3)=={'inventory.json','deployment.json','COMPLETE'} and
            profile.read(deployment/'COMPLETE',64)==DEPLOYMENT_MARKER,'Deployment inventory differs')
    raw=profile.read(deployment/'inventory.json',128*1024);inventory=profile.decode(raw);profile.validate_inventory(inventory)
    record=profile.decode(profile.read(deployment/'deployment.json',65536))
    require(set(record)=={'schema','schema_version','candidate_version','payload_revision','runtime_source','binding_source','inventory_sha256','downloads','scope'} and
            record['schema']=='riscrte.watch-image-deployment' and type(record['schema_version']) is int and record['schema_version']==1 and
            record['candidate_version']==VERSION and record['runtime_source']==binding.contract()['runtime_source'] and
            record['inventory_sha256']==meta(raw)['sha256'] and set(record['downloads'])==PAYLOAD_NAMES,'Deployment identity differs')
    revision=record['payload_revision'];require(re.fullmatch('[0-9a-f]{40}',revision),'Full payload commit required')
    base=f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}/{PAYLOAD_PATH}/'
    require(inventory['image']==record['downloads']['image.bin'],'Deployment image differs')
    opener=urllib.request.build_opener(NoRedirect)
    with tempfile.TemporaryDirectory(prefix='watch17-https-') as temp:
        payload=Path(temp)
        for name,item in record['downloads'].items():
            require(set(item)=={'url','bytes','sha256'} and item['url']==base+name and
                    type(item['bytes']) is int and 0<item['bytes']<=32*1024*1024 and
                    re.fullmatch('[0-9a-f]{64}',item['sha256']),'Immutable download identity differs')
            with opener.open(item['url'],timeout=60) as response:
                require(response.status==200,'Download HTTP status differs');data=response.read(item['bytes']+1)
            require(meta(data)=={key:item[key] for key in ('bytes','sha256')},'Downloaded payload differs')
            write_files(payload,{name:data})
        receipt,files,_=verify_payload(runtime,payload);profile.verify_inventory(inventory,files)
        require(record['binding_source']==receipt['binding_source'] and record['scope']==receipt['scope'],'Downloaded source binding differs')
    return {'verified_https_files':len(PAYLOAD_NAMES),'payload_revision':revision,'complete_store_files':len(files),
            'target_instructions_executed':False,'device_accessed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runtime',type=Path,required=True)
    commands=parser.add_subparsers(dest='command',required=True)
    item=commands.add_parser('freeze')
    for name in ('binding','seed','output'):item.add_argument('--'+name,type=Path,required=True)
    item.add_argument('--binding-source',required=True);item.add_argument('--source',required=True)
    item=commands.add_parser('verify');item.add_argument('--payload',type=Path,required=True)
    item=commands.add_parser('bind');item.add_argument('--payload',type=Path,required=True);item.add_argument('--revision',required=True);item.add_argument('--output',type=Path,required=True)
    item=commands.add_parser('verify-endpoints');item.add_argument('--deployment',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='freeze':result=freeze(args.runtime,args.binding,args.binding_source,args.seed,args.output,args.source)
    elif args.command=='verify':result=verify_payload(args.runtime,args.payload)[0]
    elif args.command=='bind':result=bind(args.runtime,args.payload,args.revision,args.output)
    else:result=verify_endpoints(args.runtime,args.deployment)
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Package the verified Watch17 native binding as paired OTA and erasing initial bytes."""
import argparse,json,subprocess,sys
from pathlib import Path
from build_preserving_watch_update import clean,profile,write_files
from current_apps_overlay import ROOT,encoded,metadata,require
from current_cohort import package,parse
from current_flash_layout import assemble,APP_DATA_PARTS
from read_only_spiffs import read_image
from rf_watch_candidate import module

BINDING_SOURCE='b6abe35ed3049174e53c89c8adb85edd3860da34'
RUNTIME_SOURCE='b587df55298e0bb8e676b3d59ca13679c0267bf7'
ORIGINS=('1.0.13','1.0.14','1.0.15')


def inputs(binding_repository,binding,runtime,native):
    binding_repository,binding,runtime,native=map(lambda p:Path(p).resolve(),(binding_repository,binding,runtime,native))
    clean(binding_repository,BINDING_SOURCE);clean(runtime,RUNTIME_SOURCE)
    code=('import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
          'from watch_native_binding import verify;'
          'r,files,image,licenses=verify(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]),sys.argv[5]);'
          'print(json.dumps(r,sort_keys=True))')
    receipt=json.loads(subprocess.check_output([sys.executable,'-c',code,str(binding_repository/'scripts'),str(binding),str(runtime),str(native),BINDING_SOURCE],text=True))
    require(receipt['watch_source']==BINDING_SOURCE and receipt['runtime']['source']==RUNTIME_SOURCE and
            receipt['cohort']['version']=='1.0.17' and receipt['cohort']['runtime_version']=='0.1.73',
            'Wrong exact final binding')
    files={p.relative_to(binding/'store').as_posix():p.read_bytes() for p in (binding/'store').rglob('*') if p.is_file()}
    bootfs=(binding/'bootfs.bin').read_bytes()
    require(receipt['files']=={n:metadata(b) for n,b in sorted(files.items())} and
            receipt['bootfs']==metadata(bootfs) and read_image(bootfs,0x510000)==files,'Verified binding changed')
    record=json.loads((native/'candidate.json').read_bytes());blobs={n:(native/n).read_bytes() for n in record['assets']}
    require(metadata((native/'candidate.json').read_bytes())==receipt['runtime']['candidate'] and
            record['assets']==receipt['runtime']['assets'],'Verified native changed')
    for name,data in blobs.items():
        require(record['assets'][name]=={'bytes':len(data),'sha256':metadata(data)['sha256']},'Native member changed')
    payload,ota=package(receipt['cohort'],blobs['firmware.bin'],bootfs)
    return receipt,files,bootfs,payload,ota,{'record':record,'blobs':blobs,'binding':receipt}


def initial_bytes(native_input,bootfs,runtime,files):
    bank=module('bound_initial_bank',Path(runtime)/'scripts/paired_bank_images.py')
    blobs=native_input['blobs'];firmware=blobs['firmware.bin']
    components={n:blobs[n] for n in ('bootloader.bin','partitions.bin','firmware.bin','appdata.bin')}
    components.update({'bootfs.bin':bootfs,'otadata.bin':bank.initial_otadata(),
                       'bank_state.bin':bank.initial_bank_state(firmware,bootfs,app_data=True)})
    deployment={k:native_input['record'][k] for k in ('layout','target','store_abi','flash_bytes')}
    deployment.update(partitions=APP_DATA_PARTS,radio_iq=True)
    require({name:{'offset':v[2],'size':v[3]} for name,v in native_input['record']['partitions'].items() if name!='nvs'}==APP_DATA_PARTS,
            'Bound native geometry differs')
    initial,placement=assemble(components,deployment,True)
    require(initial[0x9000:0xf000]==b'\xff'*0x6000 and read_image(initial[0x2f0000:0x800000],0x510000)==files,
            'Erasing initial image gap/store differs')
    return initial,placement


def verify_package(directory,binding_repository,binding,runtime,native):
    directory=Path(directory)
    require(directory.is_dir() and not directory.is_symlink() and
            not any(p.is_symlink() for p in directory.rglob('*')), 'Package input links are forbidden')
    result=inputs(binding_repository,binding,runtime,native)
    receipt,files,bootfs,payload,ota,native_input=result
    proof=json.loads((directory/'package-proof.json').read_bytes())
    require(proof['native_binding']==receipt and proof['target_cohort']==receipt['cohort'] and
            proof['payload']==metadata(payload) and proof['files']==receipt['files'] and
            proof['compatible_origins']==list(ORIGINS),'Bound package receipt differs')
    actual={p.relative_to(directory/'files').as_posix():p.read_bytes() for p in (directory/'files').rglob('*') if p.is_file()}
    require(actual==files and (directory/'bootfs.bin').read_bytes()==bootfs and (directory/ota['asset']).read_bytes()==payload,
            'Bound package bytes differ')
    record=json.loads((directory/'release-record.json').read_bytes())
    initial_name='twatch-s3-launcher-1.0.17.bin';tag='firmware-v1.0.17'
    expected_image,placement=initial_bytes(native_input,bootfs,runtime,files)
    expected_record={'kind':'firmware','version':'1.0.17','tag':tag,'asset':initial_name,
                     'url':'https://github.com/'+receipt['cohort']['source_repo']+'/releases/download/'+tag+'/'+initial_name,
                     'size':len(expected_image),'sha256':metadata(expected_image)['sha256'],'ota':ota}
    require(record==expected_record,'Bound release record differs')
    image=(directory/initial_name).read_bytes()
    require(len(image)==record['size']==0x1000000 and metadata(image)['sha256']==record['sha256']==proof['initial_image']['sha256'],
            'Outer initial artifact differs')
    require(image==expected_image and proof['initial_component_placement']==placement,
            'Outer initial image or placement differs from verified components')
    require(set(proof)=={'schema','scope','watch_packager_source','native_binding','runtime_source','target_cohort',
                        'payload','files','initial_image','initial_component_placement','compatible_origins',
                        'catalog_limitation','device_accessed','transaction_qualification','initial_image_effect'} and
            proof['schema']==1 and proof['scope']=='exact-native-bound-preserving-update' and
            proof['runtime_source']==RUNTIME_SOURCE and proof['device_accessed'] is False and
            proof['catalog_limitation']==profile()['catalog_limitation'] and
            proof['transaction_qualification']=='Separate exact-byte source/target Runtime proof required' and
            proof['initial_image_effect']=='Full 16 MiB initial image erases all user data. Paired payload is not a serial-flash image.',
            'Bound package scope or qualification claims differ')
    require(json.loads((directory/'catalog-fixture.json').read_bytes())=={'schema':1,'firmware':record,'apps':[]},
            'Executed catalog differs')
    require((directory/'LICENSES.zip').read_bytes()==(Path(binding)/'LICENSES.zip').read_bytes(),
            'Packaged notices differ from verified binding')
    names={ota['asset'],initial_name,'bootfs.bin','package-proof.json','release-record.json','catalog-fixture.json','LICENSES.zip'}
    require({p.name for p in directory.iterdir()}==names|{'files','SHA256SUMS'}, 'Package member inventory differs')
    sums=''.join(metadata((directory/n).read_bytes())['sha256']+'  '+n+'\n' for n in sorted(names))
    require((directory/'SHA256SUMS').read_text()==sums, 'Package checksums differ')
    return result


def build(binding_repository,binding,runtime,native,output):
    head=clean(ROOT);output=Path(output).resolve();require(not output.exists(),'Output must be new')
    receipt,files,bootfs,payload,ota,native_input=inputs(binding_repository,binding,runtime,native)
    initial,placement=initial_bytes(native_input,bootfs,runtime,files)
    name='twatch-s3-launcher-1.0.17.bin';tag='firmware-v1.0.17'
    record={'kind':'firmware','version':'1.0.17','tag':tag,'asset':name,
            'url':'https://github.com/'+receipt['cohort']['source_repo']+'/releases/download/'+tag+'/'+name,
            'size':len(initial),'sha256':metadata(initial)['sha256'],'ota':ota}
    proof={'schema':1,'scope':'exact-native-bound-preserving-update','watch_packager_source':head,
           'native_binding':receipt,'runtime_source':RUNTIME_SOURCE,'target_cohort':receipt['cohort'],
           'payload':metadata(payload),'files':receipt['files'],'initial_image':metadata(initial),
           'initial_component_placement':placement,'compatible_origins':list(ORIGINS),
           'catalog_limitation':profile()['catalog_limitation'],'device_accessed':False,
           'transaction_qualification':'Separate exact-byte source/target Runtime proof required',
           'initial_image_effect':'Full 16 MiB initial image erases all user data. Paired payload is not a serial-flash image.'}
    write_files(output/'files',files)
    parts={ota['asset']:payload,name:initial,'bootfs.bin':bootfs,'package-proof.json':encoded(proof),
           'release-record.json':encoded(record),'catalog-fixture.json':encoded({'schema':1,'firmware':record,'apps':[]}),
           'LICENSES.zip':(Path(binding)/'LICENSES.zip').read_bytes()}
    write_files(output,parts)
    (output/'SHA256SUMS').write_text(''.join(metadata(v)['sha256']+'  '+n+'\n' for n,v in sorted(parts.items())))
    verify_package(output,binding_repository,binding,runtime,native)
    return proof


def arguments(parser):
    for name in ('binding-repository','binding','runtime','native'):parser.add_argument('--'+name,required=True,type=Path)


def main():
    p=argparse.ArgumentParser(description=__doc__);arguments(p);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();r=build(a.binding_repository,a.binding,a.runtime,a.native,a.output)
    print(json.dumps({k:r[k] for k in ('watch_packager_source','target_cohort','payload','initial_image')}))

if __name__=='__main__':main()

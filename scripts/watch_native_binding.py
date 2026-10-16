#!/usr/bin/env python3
"""Bind the frozen23-app stage to one exact supporting native candidate."""
import argparse,io,json,re,subprocess,sys,zipfile
from pathlib import Path
from elftools.elf.elffile import ELFFile

from current_apps_overlay import ROOT,encoded,metadata,require
from current_bootfs import build as pack_store
from current_cohort import create,encode,parse
from read_only_spiffs import read_image
from build_wifi_common import zip_bytes

CONTRACT=ROOT/'apps/provisioning-native-117.json'


def contract():return json.loads(CONTRACT.read_bytes())


def source(path,expected=None):
    path=Path(path).resolve()
    head=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    tree=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD^{tree}'],text=True).strip()
    require(expected is None or head==expected,'Exact source pin differs')
    require(not subprocess.check_output(['git','-C',str(path),'status','--porcelain','--untracked-files=no'],text=True).strip(),
            'Tracked source is dirty')
    return head,tree


def files_at(directory):
    directory=Path(directory)
    require(directory.is_dir() and not directory.is_symlink(),'Real input directory required')
    result={}
    for path in directory.rglob('*'):
        require(not path.is_symlink(),'Input links are forbidden')
        if path.is_file():result[path.relative_to(directory).as_posix()]=path.read_bytes()
    return result


def inventory(files):return {n:metadata(b) for n,b in sorted(files.items())}


def native_inputs(runtime,candidate):
    c=contract();runtime=Path(runtime).resolve();candidate=Path(candidate).resolve()
    require(isinstance(c['runtime_source'],str) and re.fullmatch('[0-9a-f]{40}',c['runtime_source']),
            'Final supporting native source has not been pinned')
    head,tree=source(runtime,c['runtime_source']);require(tree==c['runtime_tree'],'Runtime tree differs')
    # Run the selected Runtime's canonical candidate validator in a separate
    # module process, avoiding imports from a different Runtime generation.
    code=('import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
          'import provision_seed;r,b=provision_seed.candidate(Path(sys.argv[2]),sys.argv[3]);'
          'print(json.dumps(r,sort_keys=True))')
    record=json.loads(subprocess.check_output([sys.executable,'-c',code,str(runtime/'scripts'),str(candidate),head],text=True))
    require(record['source_sha']==head and record['firmware_version']==c['runtime_version'] and
            record['target']==record['build_environment']=='esp32s3-16mb-appdata-iq' and
            record['performance_trace'] is False and record['store_abi']==2 and
            record['layout']=='riscrte-paired-appdata-v2','Unexpected native target or options')
    require(record['native_proof']['app_policy']=={'rows':16,'live_app_grants':16,
            'manifest_requirements':16,'marker':'RISC_APP_POLICY_ROWS:16'},'Watch native policy bound differs')
    blobs=files_at(candidate)
    for name,proof in record['assets'].items():
        require(Path(name).name==name and metadata(blobs[name])=={'size_bytes':proof['bytes'],'sha256':proof['sha256']},
                'Native candidate member differs: '+name)
    elf=ELFFile(io.BytesIO(blobs['firmware.elf']))
    symbols={s.name for s in elf.get_section_by_name('.symtab').iter_symbols()}
    require('esp_dl_image_cache_create' not in symbols and
            '_ZN8RiscBoot7Runtime16reclaimAppImagesEv' not in symbols,
            'Optional app-input cache is not qualified for the Watch model budget')
    return record,blobs,{'source':head,'tree':tree,'candidate':metadata(blobs['candidate.json']),
                        'assets':record['assets'],'native_proof':record['native_proof'],
                        'app_cache_create_symbol_absent':True}


def native_licenses(runtime):
    runtime=Path(runtime);files={}
    names=subprocess.check_output(['git','-C',str(runtime),'ls-files'],text=True).splitlines()
    for name in names:
        path=Path(name)
        if not {'test','tests','fixtures'}&set(path.parts) and path.name.upper().startswith(('LICENSE','COPYING','NOTICE')):
            require((runtime/path).is_file() and not (runtime/path).is_symlink(),'Native notice must be a regular file')
            files['native-runtime/'+name]=(runtime/path).read_bytes()
    require(files,'Native license inventory is empty')
    return files


def read_licenses(raw,runtime):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names=archive.namelist();require(len(names)==len(set(names)),'Duplicate license members')
        expected={**contract()['licenses'],**inventory(native_licenses(runtime))}
        require(set(names)==set(expected),'License inventory differs')
        files={}
        for name in names:
            info=archive.getinfo(name);require(not info.is_dir() and info.file_size==expected[name]['size_bytes'],'License size differs')
            files[name]=archive.read(name);require(metadata(files[name])==expected[name],'License content differs')
    require(raw==zip_bytes(files),'License archive is not deterministic')
    return files


def verify(binding_dir,runtime,native_candidate,expected_watch_source):
    """Read-only product-custody verifier for the provisioning wrapper.

    Returns (receipt, store_files, bootfs_bytes, license_zip_bytes). The caller
    supplies its independently pinned binding recipe source, not a value copied
    out of an untrusted receipt.
    """
    directory=Path(binding_dir).resolve();c=contract()
    require(re.fullmatch('[0-9a-f]{40}',expected_watch_source or ''),'Pinned Watch binding source required')
    receipt=json.loads((directory/'binding.json').read_bytes())
    require(set(receipt)=={'schema','scope','watch_source','contract','app_stage_source','app_stage_build',
            'app_stage_archive','app_stage_configuration','runtime','cohort','files','packing','bootfs',
            'licenses','changed_store_members','app_provider_and_policy_bytes_unchanged','physical_qualification','scope_limit'},
            'Binding receipt fields differ')
    require(receipt['schema']==1 and receipt['scope']=='watch-native-provisioning-binding' and
            receipt['watch_source']==expected_watch_source,'Binding source/scope differs')
    require(receipt['physical_qualification'] is False and receipt['scope_limit']==
            'Packaging custody only; requires separate graph/lifecycle/provisioning proof','Binding overstates qualification')
    require(receipt['contract']==metadata(CONTRACT.read_bytes()) and
            receipt['app_stage_source']==c['app_stage_source'] and
            receipt['app_stage_build']==c['app_stage_build'] and
            receipt['app_stage_archive']==c['app_stage_archive'] and
            receipt['app_stage_configuration']==c['app_stage_configuration'],'Frozen app-stage fingerprint differs')
    native,blobs,native_receipt=native_inputs(runtime,native_candidate)
    require(receipt['runtime']==native_receipt,'Native binding receipt differs')
    files=files_at(directory/'store');require(set(files)==set(c['files']),'Store inventory differs')
    for name,expected in c['files'].items():
        if name!='cohort.json':require(metadata(files[name])==expected,'App/provider/policy bytes changed: '+name)
    identity=create(c['version'],c['runtime_version'],expected_watch_source,blobs['firmware.bin'])
    require(files['cohort.json']==encode(identity) and receipt['cohort']==identity,'Rebound cohort identity differs')
    require('cohort_migration' not in json.loads(files['boot.json']),'Consumed migration must be absent')
    require(receipt['files']==inventory(files) and receipt['changed_store_members']==['cohort.json'] and
            receipt['app_provider_and_policy_bytes_unchanged'] is True,'Only-cohort rebinding proof differs')
    image=(directory/'bootfs.bin').read_bytes();packed,packing=pack_store(files)
    require(image==packed and receipt['packing']==packing and receipt['bootfs']==metadata(image) and
            read_image(image,0x510000)==files and packing['empty_blocks']>=4,'Bound SPIFFS image/capacity differs')
    licenses=(directory/'LICENSES.zip').read_bytes();read_licenses(licenses,runtime)
    require(receipt['licenses']==metadata(licenses),'License archive receipt differs')
    return receipt,files,image,licenses


def build(stage_repository,stage_directory,runtime,native_candidate,output):
    c=contract();stage_repository=Path(stage_repository).resolve();stage_directory=Path(stage_directory).resolve()
    head,_=source(ROOT);source(stage_repository,c['app_stage_source'])
    stage_build=(stage_directory/'contexts-build.json').read_bytes()
    require(metadata(stage_build)==c['app_stage_build'] and
            metadata((stage_directory/'contexts-apps.zip').read_bytes())==c['app_stage_archive'] and
            metadata((stage_directory/'contexts-store.zip').read_bytes())==c['app_stage_store_archive'],
            'App-stage evidence bytes differ')
    files=files_at(stage_directory/'files');require(inventory(files)==c['files'],'App-stage files differ')
    require(parse(files['cohort.json'])==c['app_stage_cohort'],'Original app-stage identity differs')
    native,blobs,native_receipt=native_inputs(runtime,native_candidate)
    identity=create(c['version'],c['runtime_version'],head,blobs['firmware.bin'])
    files['cohort.json']=encode(identity);image,packing=pack_store(files)
    notices=files_at(stage_directory/'licenses');require(inventory(notices)==c['licenses'],'Stage notices differ')
    native_notices=native_licenses(runtime);require(not set(notices)&set(native_notices),'Native license path collision')
    licenses=zip_bytes({**notices,**native_notices})
    receipt={'schema':1,'scope':'watch-native-provisioning-binding','watch_source':head,
             'contract':metadata(CONTRACT.read_bytes()),'app_stage_source':c['app_stage_source'],
             'app_stage_build':c['app_stage_build'],'app_stage_archive':c['app_stage_archive'],
             'app_stage_configuration':c['app_stage_configuration'],'runtime':native_receipt,
             'cohort':identity,'files':inventory(files),'packing':packing,'bootfs':metadata(image),
             'licenses':metadata(licenses),'changed_store_members':['cohort.json'],
             'app_provider_and_policy_bytes_unchanged':True,'physical_qualification':False,
             'scope_limit':'Packaging custody only; requires separate graph/lifecycle/provisioning proof'}
    output=Path(output).absolute();require(not output.exists() and not output.is_symlink(),'Binding output must be new')
    for name,raw in files.items():
        target=output/'store'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    for name,raw in {'bootfs.bin':image,'LICENSES.zip':licenses,'binding.json':encoded(receipt)}.items():(output/name).write_bytes(raw)
    verify(output,runtime,native_candidate,head)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('stage-repository','stage-directory','runtime','native-candidate','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.stage_repository,a.stage_directory,a.runtime,a.native_candidate,a.output),indent=2))


if __name__=='__main__':main()

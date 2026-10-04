#!/usr/bin/env python3
"""Verify hosted paired inputs, then assemble a migration-only16MiB candidate.

No device, release, index or credential operations. Existing8MiB USB images are
not OTA inputs. The complete flash image intentionally consumes the upper bank.
"""
import argparse
import importlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

from build_wifi_common import ROOT, encoded, exact_sha, read_zip, require, sha
from build_wifi_store import SIZE, OFFSET, TOOL_SHA256, check_image
from check_runtime_store_admission import archive_store, unpack_image

FLASH_BYTES = 0x1000000
LAYOUT = 'riscrte-paired-16m-v1'
COMPONENT_OFFSETS = [('bootloader.bin',0), ('partitions.bin',0x8000),
                     ('firmware.bin',0x10000), ('bootfs.bin',OFFSET),
                     ('otadata.bin',0xff0000), ('bank_state.bin',0xff2000)]
JOBS = {'software-checks','alarm-integration','points-integration','wifi-integration',
        'production-store-admission','update-integration','update-cross-layer'}


def git(root,*args):
    return subprocess.check_output(['git',*args],cwd=root,text=True).strip()


def source(root, expected, tree=False):
    require(exact_sha(expected),'Exact source identity required')
    require(git(root,'rev-parse','HEAD^{tree}' if tree else 'HEAD')==expected,
            'Checkout differs from reviewed source: '+str(root))
    require(not git(root,'status','--porcelain','--untracked-files=no'),
            'Modified source checkout: '+str(root))


def receipt(record, raw, head, tree):
    expected={'repository':'michaelrolphone-cmyk/RiscRTE-T-Watch-S3',
              'head':head,'tree':tree,'conclusion':'success','expired':False,
              'artifact_name':'twatch-update-integration-'+head,'artifact_sha256':sha(raw)}
    require(all(record.get(k)==v for k,v in expected.items()),'Exact-head CI receipt mismatch')
    require(all(type(record.get(k)) is int and record[k]>0 for k in ('run_id','artifact_id')),
            'External CI identity missing')
    jobs=record.get('jobs',[])
    require(len(jobs)==len(JOBS) and {j.get('name') for j in jobs}==JOBS and
            all(j.get('conclusion')=='success' for j in jobs),'All seven exact-head jobs must pass')


def runtime_files(raw, runtime_source, root=ROOT):
    pin=json.loads((root/'apps/update-runtime-artifact.json').read_text())
    requirements=json.loads((root/'apps/update-runtime-requirements.json').read_text())
    source(runtime_source,pin['source_sha'])
    require(pin['source_sha']==requirements['source_sha'] and
            pin['artifact_sha256']==sha(raw),'Runtime archive/source differs from committed custody')
    require(pin.get('target')=='esp32s3-16mb-paired' and pin.get('conclusion')=='success' and
            all(type(pin.get(k)) is int and pin[k]>0 for k in ('run_id','artifact_id')),
            'Runtime paired target has no successful external artifact receipt')
    files=read_zip(io.BytesIO(raw))
    expected={'SHA256SUMS','candidate.json','firmware.bin','firmware.elf','bootloader.bin',
              'partitions.bin','partitions-paired.csv','platformio.ini','requirements-ci.txt'}
    require(set(files)==expected,'Unexpected paired Runtime artifact members')
    candidate=json.loads(files['candidate.json'])
    require(all(candidate.get(k)==v for k,v in {
        'schema':1,'source_sha':pin['source_sha'],'firmware_version':requirements['firmware_version'],
        'target':'esp32s3-16mb-paired','layout':LAYOUT,'store_abi':1,'flash_bytes':FLASH_BYTES}.items()),
        'Runtime target/version/layout mismatch')
    require(set(candidate['assets'])==expected-{'SHA256SUMS','candidate.json'},'Runtime asset membership')
    require(set(pin['components'])==expected-{'SHA256SUMS'},'Incomplete pinned Runtime custody')
    for name,info in pin['components'].items():
        require(len(files[name])==info['size_bytes'] and sha(files[name])==info['sha256'],
                'Pinned Runtime component mismatch: '+name)
    for name,info in candidate['assets'].items():
        require(len(files[name])==info['bytes'] and sha(files[name])==info['sha256'],
                'Runtime candidate checksum mismatch: '+name)
    sums=''.join(sha(files[n])+'  '+n+'\n' for n in sorted(expected-{'SHA256SUMS'})).encode()
    require(files['SHA256SUMS']==sums,'Runtime SHA256SUMS mismatch')
    # Use the pinned Runtime's own structural verifier as well as independent
    # committed component custody. No build tree or regenerated native bytes.
    sys.path.insert(0,str(Path(runtime_source).resolve()/'scripts'))
    try:
        proof=importlib.import_module('paired_candidate')
        metadata=importlib.import_module('paired_bank_images')
        proof.partitions(files['partitions.bin'])
        require(proof.native_proof(files['firmware.elf'])==candidate['native_proof'],
                'Linked TLS/rollback proof differs')
        require(sha(files['bootloader.bin'])==metadata.BOOTLOADER_SHA256,'Rollback bootloader mismatch')
        for name in ('firmware.bin','bootloader.bin'):proof.esp_image(files[name])
        for marker in ('RTE_SOURCE='+pin['source_sha'],
                       'RISC_RUNTIME_VERSION:'+requirements['firmware_version'],'RISC_PAIRED_STORE_ABI:1'):
            require(all(marker.encode()+b'\0' in files[n] for n in ('firmware.bin','firmware.elf')),
                    'Runtime compiled source/version/ABI marker missing')
        # Actual ELF-to-BIN relationship; the pinned PlatformIO qio board uses
        # dio in its ESP image header, as its official builder specifies.
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);elf=directory/'firmware.elf';image=directory/'rebuilt.bin'
            elf.write_bytes(files['firmware.elf'])
            subprocess.run([sys.executable,'-m','esptool','--chip','esp32s3','elf2image',
                '--flash_mode','dio','--flash_freq','80m','--flash_size','16MB',
                '--elf-sha256-offset','0xb0','-o',str(image),str(elf)],check=True,timeout=90)
            require(image.read_bytes()==files['firmware.bin'],'Hosted firmware BIN differs from hosted ELF')
    finally:sys.path.pop(0)
    return files,candidate,metadata


def assemble(components):
    require(set(components)=={n for n,_ in COMPONENT_OFFSETS},'Paired component membership')
    require(len(components['bootfs.bin'])==SIZE and len(components['otadata.bin'])==8192 and
            len(components['bank_state.bin'])==8192,'Fixed paired partition sizes')
    limits={'bootloader.bin':0x8000,'partitions.bin':0x9000,'firmware.bin':OFFSET,
            'bootfs.bin':0x800000,'otadata.bin':0xff2000,'bank_state.bin':0xff4000}
    result=bytearray(b'\xff'*FLASH_BYTES);entries=[];cursor=0
    for name,offset in COMPONENT_OFFSETS:
        data=components[name]
        require(data and offset>=cursor and offset+len(data)<=limits[name],'Component crosses partition boundary')
        result[offset:offset+len(data)]=data
        entries.append({'file':'components/'+name,'offset':hex(offset),'size_bytes':len(data),'sha256':sha(data)})
        cursor=offset+len(data)
    cursor=0
    for name,offset in COMPONENT_OFFSETS:
        require(all(b==255 for b in result[cursor:offset]),'Non-erased flash gap')
        require(result[offset:offset+len(components[name])]==components[name],'Component copy differs')
        cursor=offset+len(components[name])
    require(all(b==255 for b in result[cursor:]),'Non-erased final gap')
    require(all(b==255 for b in result[0x800000:0xff0000]),'Inactive firmware/store bank must start erased')
    return bytes(result),entries


def build(runtime,artifact,head,tree,receipt_path,runtime_source,system_apps,utilities,productivity,tool,out,root=ROOT):
    from build_update_common import verify, PROFILE
    from update_test_production_store_runtime import admit_many
    from update_test_production_store_runtime import execute_many
    source(root,tree,True);require(git(root,'rev-parse','HEAD')==head,'Watch receipt head differs')
    pins=json.loads((root/'apps/update-sources.json').read_text())
    for name,path in [('system-apps',system_apps),('utilities',utilities),('productivity',productivity)]:
        source(path,pins[name]['commit'])
    native,candidate,metadata=runtime_files(Path(runtime).read_bytes(),runtime_source,root)
    raw=Path(artifact).read_bytes();ci=json.loads(Path(receipt_path).read_text());receipt(ci,raw,head,tree)
    artifacts=read_zip(io.BytesIO(raw))
    def one(suffix):
        hits=[n for n in artifacts if n.endswith(suffix)]
        require(len(hits)==1,'Expected one hosted member: '+suffix);return hits[0]
    common_name=one('-'+PROFILE+'.zip');image_name=one('-'+PROFILE+'-bootfs.bin')
    common=artifacts[common_name];image=artifacts[image_name]
    image_record=json.loads(artifacts[image_name[:-4]+'.json'])
    stores=[]
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'common.zip';path.write_bytes(common)
        record=verify(path,root=root,expected_head=head);files=read_zip(path)
        for item in record['common_update_launcher']['inputs']:
            original=artifacts[one(item['archive'])]
            require(sha(original)==item['sha256'] and len(original)==item['size_bytes'],'Hosted original ZIP mismatch')
            stores.append((item['archive'],archive_store(original)))
        store={n[6:]:b for n,b in files.items() if n.startswith('store/')}
        expected={'schema':1,'profile':PROFILE,'watch_source_sha':head,'deployment_sha256':sha(common),
                  'sha256':sha(image),'size_bytes':SIZE,'partition_label':'bootfs0','partition_offset':OFFSET,
                  'page_size':256,'block_size':4096,'tool_sha256':TOOL_SHA256,'files':len(store),
                  'payload_bytes':sum(map(len,store.values())),'round_trip_verified':True}
        require(all(image_record.get(k)==v for k,v in expected.items()),'Hosted store record mismatch')
        image_path=Path(temporary)/'bootfs.bin';image_path.write_bytes(image);check_image(image_path,store,tool)
    stores.extend([('common-deployment',store),('hosted-spiffs',unpack_image(image,tool))])
    components={n:native[n] for n in ('bootloader.bin','partitions.bin','firmware.bin')}
    components.update({'bootfs.bin':image,'otadata.bin':metadata.initial_otadata(),
                       'bank_state.bin':metadata.initial_bank_state(native['firmware.bin'],image)})
    metadata.parse_record(components['bank_state.bin'][:96])
    merged,parts=assemble(components);final=unpack_image(merged[OFFSET:OFFSET+SIZE],tool)
    require(final==store,'Final16MiB BIN extracted store differs');stores.append(('final-bin-extraction',final))
    admission=admit_many(runtime_source,stores)
    execution=execute_many(runtime_source,system_apps,utilities,productivity,[stores[-1]])
    name='twatch-s3-paired-updates-'+head[:8]+'.bin'
    report={'schema':1,'kind':'development-full-flash-migration','layout':LAYOUT,'store_abi':1,
        'target':'Original/non-Plus T-Watch-S3,16MiB flash/8MiB OPI PSRAM','watch_source':head,'watch_tree':tree,
        'runtime_source':candidate['source_sha'],'runtime_version':candidate['firmware_version'],
        'runtime_artifact_sha256':sha(Path(runtime).read_bytes()),'ci_receipt':ci,'source_pins':pins,
        'file':name,'bin_sha256':sha(merged),'size_bytes':len(merged),'flash_offset':'0x0',
        'overwrite_bytes':FLASH_BYTES,'flash_capacity_bytes':FLASH_BYTES,'components':parts,
        'common_sha256':sha(common),'bootfs_sha256':sha(image),'runtime_admission':admission,
        'default_clock_execution':execution,'physical_verification':'pending',
        'store':[{'path':n,'size_bytes':len(b),'sha256':sha(b)} for n,b in sorted(store.items())],
        'flash_warning':'One-time full16MiB replacement repartitions flash and overwrites both banks, NVS/settings, saved Wi-Fi credentials, Stopwatch, alarms/countdowns and Points records. Upper8MiB is NOT preserved. Back up first. Existing8MiB factory/Watch1.0 USB images cannot receive this as OTA.'}
    deliver={name:merged,'manifest.json':encoded(report),'provenance/common-deployment.zip':common,
             'provenance/bootfs.json':encoded(image_record),'provenance/watch-ci-receipt.json':encoded(ci),
             'provenance/runtime-candidate.json':native['candidate.json'],
             'MIGRATION.md':(root/'docs/UPDATE_MIGRATION.md').read_bytes(),
             'licenses/RUNTIME-LICENSE':(Path(runtime_source)/'LICENSE').read_bytes()}
    deliver.update({'components/'+n:b for n,b in components.items()})
    deliver.update({n:b for n,b in files.items() if n.startswith(('licenses/','shared/'))})
    deliver['SHA256SUMS']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(deliver.items())).encode()
    output=Path(out);require(not output.exists(),'Use a new output directory; never overwrite prior delivery')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        stage=Path(temporary);archive=stage/(Path(name).stem+'-migration.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for n,b in sorted(deliver.items()):
                entry=zipfile.ZipInfo(n,(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
                entry.external_attr=0o100644<<16;z.writestr(entry,b)
        require(read_zip(archive)==deliver,'Migration archive round-trip differs')
        report.update(migration_zip=archive.name,migration_zip_sha256=sha(archive.read_bytes()))
        (stage/name).write_bytes(merged);(stage/'manifest.json').write_bytes(encoded(report))
        output.mkdir()
        for path in stage.iterdir():path.replace(output/path.name)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime','artifact','receipt','runtime-source','system-apps','utilities','productivity','mkspiffs','output'):
        p.add_argument('--'+n,required=True,type=Path)
    p.add_argument('--pr-head',required=True);p.add_argument('--source-tree',required=True);a=p.parse_args()
    print(json.dumps(build(a.runtime,a.artifact,a.pr_head,a.source_tree,a.receipt,a.runtime_source,
        a.system_apps,a.utilities,a.productivity,a.mkspiffs,a.output),indent=2))

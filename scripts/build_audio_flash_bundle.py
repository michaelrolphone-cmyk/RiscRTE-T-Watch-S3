#!/usr/bin/env python3
"""Exact-CI Audio Tools development image with final source/target/Runtime gates.

No device access or release promotion. This incomplete checkpoint has no pinned
Runtime component descriptor and cannot produce a deliverable; see CHECKPOINT.
"""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile
from audio_deployment import ROOT,APPS,PROFILE,configuration,encoded,read_zip,require,sha,verify
from build_audio_apps import clean_pin,git,verify_target_bytes
from build_wifi_common import profiles
from build_wifi_store import SIZE,OFFSET,TOOL_SHA256,check_image
from build_wifi_flash_bundle import assemble_components,verify_runtime,verify_receipt,verify_watch_source
from check_runtime_store_admission import archive_store,unpack_image,admit_many

JOBS={'software-checks','alarm-integration','points-integration','wifi-integration','production-store-admission','audio-integration'}


def build(runtime,artifact,receipt_path,head,tree,runtime_source,system,utilities,baseline_system,tool,out,root=ROOT):
    config=configuration(root);verify_watch_source(root,tree);require(git(root,'rev-parse','HEAD')==head,'Exact Watch commit required')
    for path,key in ((runtime_source,'runtime'),(system,'system-apps'),(utilities,'utilities')):clean_pin(path,config['sources'][key])
    clean_pin(baseline_system,json.loads((root/'apps/wifi-sources.json').read_text())['system-apps'])
    pin=json.loads((root/'apps/audio-runtime-artifact.json').read_text());require(pin['source_sha']==config['sources']['runtime']['commit'],'Artifact/source Runtime pin mismatch')
    runtime_raw=runtime.read_bytes();require(sha(runtime_raw)==pin['artifact_sha256'],'Wrong immutable Runtime artifact');runtime_files=read_zip(io.BytesIO(runtime_raw));verify_runtime(runtime_files,pin,config['minimum_runtime'])
    raw=artifact.read_bytes();receipt=json.loads(receipt_path.read_text());verify_receipt(receipt,raw,head,tree,required_jobs=JOBS,artifact_prefix='twatch-audio-integration-');artifact_files=read_zip(io.BytesIO(raw))
    names=[n for n in artifact_files if n.endswith('.zip') and '/twatch-audio-tools-' in '/'+n];require(len(names)==9,'Exact CI artifact needs eight profiles and one common')
    reports=[];stores=[];common=None;common_files=None
    with tempfile.TemporaryDirectory(prefix='watch-audio-final-') as temporary:
        work=Path(temporary)
        for index,name in enumerate(names):
            path=work/(str(index)+'.zip');path.write_bytes(artifact_files[name]);record=verify(path,root=root,expected_head=head);reports.append(record);stores.append((name,archive_store(path.read_bytes())))
            if record['profile']==PROFILE:common=path.read_bytes();common_files=read_zip(path)
        require({r['profile'] for r in reports}==profiles(root)|{PROFILE},'Missing or duplicate final profile')
        expected={n[6:]:b for n,b in common_files.items() if n.startswith('store/')}
        for name,store in stores:
            normalized=dict(store);board=json.loads(store['board.json']);board['revision']='wifi-launcher-common';normalized['board.json']=encoded(board);require(normalized==expected,'Final profile differs from common: '+name)
        # Rebuilt target bytes, not self-reported hashes or native replacement,
        # attest the exact executable payload that will reach the device.
        original=work/'baseline.zip';original.write_bytes(common_files['baseline.zip'])
        compiled={n+ext:expected[n+ext] for n in ('springboard',*APPS) for ext in ('.elf','.json')}
        compiled.update({n:common_files[n] for n in ('audio-build.json','catalog.json')})
        verify_target_bytes(compiled,original,system,utilities,baseline_system)
        images=[n for n in artifact_files if n.endswith('-'+PROFILE+'-bootfs.bin')];require(len(images)==1,'Expected one common SPIFFS image')
        image=artifact_files[images[0]];image_record=json.loads(artifact_files[images[0][:-4]+'.json'])
        required=dict(schema=1,profile=PROFILE,watch_source_sha=head,deployment_sha256=sha(common),sha256=sha(image),size_bytes=SIZE,partition_label='bootfs',partition_offset=OFFSET,page_size=256,block_size=4096,tool_sha256=TOOL_SHA256,files=len(expected),payload_bytes=sum(map(len,expected.values())),round_trip_verified=True)
        require(all(image_record.get(k)==v for k,v in required.items()),'Audio SPIFFS custody mismatch')
        image_path=work/'bootfs.bin';image_path.write_bytes(image);check_image(image_path,expected,tool)
        components={n:runtime_files[n] for n in pin['components']};components['bootfs.bin']=image;merged,parts=assemble_components(components)
        final_store=unpack_image(merged[OFFSET:OFFSET+SIZE],tool);require(final_store==expected,'Final BIN extraction differs from reviewed store')
        stores.extend([('hosted-spiffs',unpack_image(image,tool)),('final-bin-extraction',final_store)]);admission=admit_many(runtime_source,stores)
        final_image=work/'final-bootfs.bin';final_image.write_bytes(merged[OFFSET:OFFSET+SIZE]);catalog=work/'catalog.json';catalog.write_bytes(common_files['catalog.json'])
        base=['python3',str(root/'scripts/test_production_store_runtime.py'),'--runtime',str(runtime_source),'--system-apps',str(system),'--utilities',str(utilities),'--image',str(final_image),'--mkspiffs',str(tool)]
        env=dict(os.environ,SANITIZE='1',ADDRESS_SANITIZE='1')
        subprocess.run([*base,'--output',str(work/'clock')],env=env,check=True,timeout=300)
        subprocess.run([*base,'--audio','--baseline-system-apps',str(baseline_system),'--audio-catalog',str(catalog),'--output',str(work/'audio')],env=env,check=True,timeout=600)
        execution={name:(work/name/'provenance.json').read_bytes() for name in ('clock','audio')}
    stem='twatch-s3-'+('-'.join(APPS))+'-'+head[:8];name=stem+'.bin'
    warning='Full lower 8 MiB replacement resets NVS, Settings, Stopwatch, alarms/countdown/Points and Wi-Fi profile. Upper 8 MiB untouched.'
    manifest=dict(schema=1,kind='development-hardware-test',file=name,watch_source=head,watch_tree=tree,source_pins=config['sources'],runtime_version=config['minimum_runtime'],runtime_artifact_sha256=sha(runtime_raw),bin_sha256=sha(merged),size_bytes=len(merged),flash_offset='0x0',overwrite_bytes=0x800000,flash_capacity_bytes=0x1000000,components=parts,ci_receipt=receipt,runtime_admission=admission,store=[dict(path=n,size_bytes=len(b),sha256=sha(b)) for n,b in sorted(expected.items())],physical_verification='pending',flash_warning=warning)
    files={name:merged,'manifest.json':encoded(manifest),'provenance/common-deployment.zip':common,'provenance/runtime-candidate.json':runtime_files['candidate.json'],'provenance/bootfs.json':encoded(image_record),'provenance/watch-ci-receipt.json':encoded(receipt),**{'provenance/'+n+'-final-execution.json':b for n,b in execution.items()},**{'components/'+n:b for n,b in components.items()},**{'reproduce/'+n:runtime_files[n] for n in ('platformio.ini','partitions.csv','requirements-ci.txt')},'licenses/RUNTIME-LICENSE':(runtime_source/'LICENSE').read_bytes()}
    files['FLASHING.md']=(f'# Audio Tools development image\n\nOriginal/non-Plus T-Watch-S3, 16 MiB flash, 8 MiB OPI PSRAM.\n\n{warning}\n\nFlash {name} at 0x0 only after deciding to replace saved state. No device operation was performed. Physical sound levels, sleep/wake/current and durability remain unqualified.\n\nWatch {head}; SHA256 {sha(merged)}.\n').encode()
    files['SHA256SUMS']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    binary=out/name;archive=out/(stem+'-flashing.zip');require(not {p.resolve() for p in (runtime,artifact,receipt_path,tool)} & {binary.resolve(),archive.resolve()},'Output aliases input');out.mkdir(parents=True,exist_ok=True);binary.write_bytes(merged)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(files.items()):
            info=zipfile.ZipInfo(n,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,b)
    require(read_zip(archive)==files,'Final flashing ZIP round-trip mismatch');manifest.update(flashing_zip=archive.name,flashing_zip_sha256=sha(archive.read_bytes()));(out/(stem+'.json')).write_bytes(encoded(manifest));return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime','artifact','receipt','runtime-source','system-apps','utilities','baseline-system-apps','mkspiffs','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--pr-head',required=True);p.add_argument('--source-tree',required=True);a=p.parse_args()
    print(json.dumps(build(a.runtime,a.artifact,a.receipt,a.pr_head,a.source_tree,a.runtime_source,a.system_apps,a.utilities,a.baseline_system_apps,a.mkspiffs,a.output),indent=2))

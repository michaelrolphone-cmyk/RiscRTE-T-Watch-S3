#!/usr/bin/env python3
"""Reversible Audio Tools overlays on the complete, independently pinned Wi-Fi store."""
import io
import json
from pathlib import Path
import struct
from build_wifi_common import ROOT, encoded, exact_sha, read_zip, require, sha, zip_bytes
from build_wifi_common import verify as verify_wifi_common, verify_provenance
from verify_wifi_deployment import verify as verify_wifi_profile

APPS=('frequency_generator',)
BASELINE_CHANGES={'boot.json','springboard.elf','springboard.json'}
PROFILE='audio-tools-common'


def configuration(root=ROOT):
    config=json.loads((root/'apps/audio-sources.json').read_text())
    require(config['schema']==1 and tuple(config['apps'])==APPS,'Audio source inventory differs from reviewed increment')
    for owner in ('system-apps','utilities','runtime'):
        require(exact_sha(config['sources'][owner]['commit']),'Unpinned audio source: '+owner)
    require(config['minimum_runtime']=='0.1.12','Audio lifecycle Runtime floor changed')
    runtime=json.loads((root/'apps/audio-runtime-requirements.json').read_text())
    require(runtime['source_sha']==config['sources']['runtime']['commit'] and
            runtime['firmware_version']==config['minimum_runtime'],'Audio Runtime requirement pin mismatch')
    return config


def baseline(raw,root=ROOT):
    stream=io.BytesIO(raw);stream.name='embedded-baseline.zip'
    files=read_zip(stream);record=json.loads(files['deployment-record.json'])
    if record['profile']=='wifi-launcher-common':verify_wifi_common(stream,root=root)
    else:
        verify_wifi_profile(stream);verify_provenance(files,record,root)
    require(raw==zip_bytes(files),'Noncanonical baseline archive')
    store={n[6:]:b for n,b in files.items() if n.startswith('store/')}
    normalized=dict(store);board=json.loads(normalized['board.json']);board['revision']='wifi-launcher-common';normalized['board.json']=encoded(board)
    from check_runtime_store_admission import preserve_store
    preserve_store(normalized,root/'apps/wifi-store-baseline.json')
    return files,record,store


def app_grants(name):
    require(name in APPS,'Unreviewed Audio Tools app')
    return [dict(capability=c,api=v,instance_id=i) for c,v,i in (
        ('display.output',1,5),('input.touch.raw',1,6),('rtc.clock',2,8),
        ('board.battery',1,4),('audio.output',1,12),('alarm.service',1,0))]


def app_manifest(name,version):
    return dict(type='application',id=name,version=version,architecture='xtensa-esp32s3',
        file_name=name+'.elf',entry='app_main',requires=[dict(capability=g['capability'],api=g['api']) for g in app_grants(name)])


def compile_definitions(name):
    flags=['-DPORTABLE_TOUCH_ROTATION=0','-DPORTABLE_RTC_UTC8_DENVER','-DPORTABLE_FORCE_FULL_FRAMES',
        '-DPORTABLE_INPUT_NAVIGATION','-DPORTABLE_INPUT_NAVIGATION_LOCAL','-DPORTABLE_APP_SLEEP_LOCAL','-DPORTABLE_ALARM_CLIENT',
        '-DPORTABLE_RETURN_APP="'+('clock.elf' if name=='springboard' else 'springboard.elf')+'"']
    return flags+(['-DPORTABLE_RETAINED_RGB565_HANDOFF','-DPORTABLE_HANDOFF_EAGER_MS=60'] if name=='springboard' else ['-DPORTABLE_AUDIO_SESSION'])


def catalog_source(rows):
    return '#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={'+','.join('{'+','.join('.'+k+'='+json.dumps(v) for k,v in e.items())+',.compatible=true}' for e in rows)+'};\nconst unsigned portable_catalog_count='+str(len(rows))+';\n'


def check_elf(data):
    require(len(data)>=20 and data[:7]==b'\x7fELF\x01\x01\x01' and struct.unpack_from('<HH',data,16)==(3,94),'Not a target Xtensa shared ELF')


def entries(files):
    return [dict(path=n,size_bytes=len(b),sha256=sha(b)) for n,b in sorted(files.items())]


def build_files(raw,compiled,head,root=ROOT):
    config=configuration(root);require(exact_sha(head),'Exact Watch source commit required')
    original,old_record,old_store=baseline(raw,root);record=json.loads(compiled['audio-build.json'])
    require(record['sources']==config['sources'] and record['watch_source']==head,'Audio build source pins/head mismatch')
    require(record['minimum_runtime']==config['minimum_runtime'],'Wrong build Runtime floor')
    require(set(record['apps'])=={'springboard',*APPS},'Unexpected compiled app inventory')
    require(record['springboard_sources']==json.loads((root/'apps/wifi-sources.json').read_text())['system-apps'],'Springboard must retain original adapter')
    catalog=json.loads(original['shared/catalog.json'])+[config['apps'][name]['catalog'] for name in APPS]
    require(json.loads(compiled['catalog.json'])==catalog,'Audio catalog dropped/reordered existing app')
    store=dict(old_store)
    for name in ('springboard',*APPS):
        elf=compiled[name+'.elf'];check_elf(elf);info=record['apps'][name]
        owner=record['springboard_sources']['commit'] if name=='springboard' else config['sources']['utilities']['commit']
        require(info['repository_sha']==owner,'Wrong owning source: '+name)
        require(info['sha256']==sha(elf) and info['size_bytes']==len(elf),'Stale target build: '+name)
        require(info['compile_definitions']==compile_definitions(name),'Incorrect Watch compile flags: '+name)
        manifest=json.loads(compiled[name+'.json'])
        if name=='springboard':
            expected=json.loads(old_store['springboard.json']);expected['version']=config['springboard_version']
        else:expected=app_manifest(name,config['apps'][name]['version'])
        require(manifest==expected and info['version']==manifest['version'],'Wrong deployed manifest: '+name)
        store[name+'.elf']=elf;store[name+'.json']=encoded(manifest)
    boot=json.loads(old_store['boot.json']);boot['app_capabilities'] += [dict(manifest=n+'.json',grants=app_grants(n)) for n in APPS]
    store['boot.json']=encoded(boot)
    require({n:b for n,b in store.items() if n in old_store and n not in BASELINE_CHANGES}=={n:b for n,b in old_store.items() if n not in BASELINE_CHANGES},'Unrelated delivered store changed')
    profile=PROFILE if old_record['profile']=='wifi-launcher-common' else old_record['profile']
    files={'baseline.zip':raw,'audio-build.json':compiled['audio-build.json'],'catalog.json':compiled['catalog.json'],
        'runtime-requirements.json':(root/'apps/audio-runtime-requirements.json').read_bytes(),**{'store/'+n:b for n,b in store.items()}}
    out=dict(schema='riscrte.watch-audio-deployment',schema_version=1,source_sha=head,profile=profile,apps=list(APPS),
        minimum_runtime=config['minimum_runtime'],sources=config['sources'],
        baseline=dict(archive_sha256=sha(raw),source_sha=old_record['source_sha'],profile=old_record['profile'],store_files=len(old_store)),
        changed_baseline_store=sorted(BASELINE_CHANGES),added_store=sorted(set(store)-set(old_store)),physical_verification='pending',entries=entries(files))
    files['deployment-record.json']=encoded(out);return files


def verify(path,root=ROOT,expected_head=None):
    raw=path.read_bytes() if isinstance(path,Path) else None;files=read_zip(path);record=json.loads(files['deployment-record.json'])
    require(record['schema']=='riscrte.watch-audio-deployment' and record['schema_version']==1,'Wrong audio deployment identity')
    require(expected_head is None or record['source_sha']==expected_head,'Unexpected audio source head')
    require(record['entries']==entries({n:b for n,b in files.items() if n!='deployment-record.json'}),'Audio deployment membership or checksum mismatch')
    compiled={name+ext:files['store/'+name+ext] for name in ('springboard',*APPS) for ext in ('.elf','.json')}
    compiled.update({n:files[n] for n in ('audio-build.json','catalog.json')})
    require(files==build_files(files['baseline.zip'],compiled,record['source_sha'],root),'Audio overlay differs from exact permitted transformation')
    if raw is not None:require(raw==zip_bytes(files),'Noncanonical audio archive')
    return record

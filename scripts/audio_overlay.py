#!/usr/bin/env python3
"""Verified additive Audio Tools overlay on the current paired update common store."""
import io,json,re,subprocess,zipfile
from pathlib import Path
from build_clock_deployment import ROOT,encoded,sha
from build_update_common import PROFILE as BASE_PROFILE,verify as verify_base
from build_wifi_common import read_zip,require,zip_bytes

PROFILE='audio-tools-common'
APPS=('frequency_generator','audio_spectrum')
CHANGED={'store/board.json','store/boot.json','store/springboard.elf','store/springboard.json','shared/catalog.json'}
ADDED={'store/frequency_generator.elf','store/frequency_generator.json','store/audio_spectrum.elf','store/audio_spectrum.json',
       'store/mic/driver.elf','store/mic/manifest.json','shared/audio-build.json','shared/audio-sources.json'}

def exact_sha(v): return isinstance(v,str) and re.fullmatch('[0-9a-f]{40}',v) is not None

def config(root=ROOT):
    c=json.loads((root/'apps/audio-sources.json').read_text())
    require(c['schema']==1 and tuple(c['apps'])==APPS,'Audio source inventory changed')
    require(c['minimum_runtime']=='0.1.16','Audio Runtime floor changed')
    for v in c['sources'].values(): require(exact_sha(v['commit']),'Unpinned audio source')
    return c

def app_grants(name):
    base=[{'capability':'display.output','api':1,'instance_id':5},
          {'capability':'input.touch.raw','api':1,'instance_id':6},
          {'capability':'rtc.clock','api':2,'instance_id':8},
          {'capability':'board.battery','api':1,'instance_id':4}]
    base.append({'capability':'audio.output' if name=='frequency_generator' else 'audio.input','api':1,
                 'instance_id':12 if name=='frequency_generator' else 13})
    base.append({'capability':'alarm.service','api':1,'instance_id':0})
    return base

def app_manifest(name,version):
    return {'type':'application','id':name,'version':version,'architecture':'xtensa-esp32s3',
            'file_name':name+'.elf','entry':'app_main',
            'requires':[{'capability':g['capability'],'api':g['api']} for g in app_grants(name)]}

def compile_defs(name):
    flags=['-DPORTABLE_TOUCH_ROTATION=0','-DPORTABLE_RTC_UTC8_DENVER','-DPORTABLE_FORCE_FULL_FRAMES',
           '-DPORTABLE_INPUT_NAVIGATION','-DPORTABLE_INPUT_NAVIGATION_LOCAL','-DPORTABLE_APP_SLEEP_LOCAL',
           '-DPORTABLE_ALARM_CLIENT',
           '-DPORTABLE_RETURN_APP="'+('clock.elf' if name=='springboard' else 'springboard.elf')+'"']
    if name in APPS: flags.append('-DPORTABLE_AUDIO_SESSION')
    if name=='springboard': flags += ['-DPORTABLE_RETAINED_RGB565_HANDOFF','-DPORTABLE_HANDOFF_EAGER_MS=60']
    return flags

def catalog_c(rows):
    return '#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[]={'+','.join(
        '{'+','.join('.'+k+'='+json.dumps(v) for k,v in r.items())+',.compatible=true}' for r in rows
    )+'};\nconst unsigned portable_catalog_count='+str(len(rows))+';\n'

def package_mic(root=ROOT):
    catalog=json.loads((root/'dist/catalog.json').read_text())['packages']
    item=next((p for p in catalog if p['id']=='twatch-mic'),None)
    require(item is not None,'Built twatch-mic package missing')
    raw=(root/'dist'/item['archive']).read_bytes()
    require(sha(raw)==item['sha256'],'twatch-mic package hash mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        elf=z.read('driver.elf'); manifest=z.read('source-manifest.json')
    source=json.loads((root/'drivers/twatch_mic/manifest.json').read_text())
    require(json.loads(manifest)==source and item['version']==source['version'],'twatch-mic package/source mismatch')
    return elf,encoded(source)

def common_store(base,root=ROOT):
    raw=base.read_bytes(); stream=io.BytesIO(raw);stream.name='update-common.zip'
    record=verify_base(stream,root=root)
    require(record['profile']==BASE_PROFILE,'Audio overlay requires paired update common baseline')
    stream=io.BytesIO(raw);stream.name='update-common.zip';files=read_zip(stream)
    store={n:b for n,b in files.items() if n.startswith('store/')}
    return files,record,store

def build(base,compiled,head,root=ROOT):
    files,base_record,old=common_store(base,root); cfg=config(root)
    require(base_record['source_sha']==head,'Audio baseline and Watch head differ')
    record=json.loads(compiled['audio-build.json'])
    require(record['watch_source']==head and record['sources']==cfg['sources'],'Audio build source mismatch')
    store=dict(old)
    old_catalog=json.loads(files['shared/catalog.json'])
    wanted=old_catalog+[cfg['apps'][n]['catalog'] for n in APPS]
    require(json.loads(compiled['catalog.json'])==wanted,'Audio catalog mismatch')
    require(len({x['icon'] for x in wanted})==len(wanted),'Audio catalog icon collision')
    for name in ('springboard',*APPS):
        elf=compiled[name+'.elf']; meta=record['apps'][name]
        require(meta['sha256']==sha(elf) and meta['size_bytes']==len(elf),'Stale audio target: '+name)
        manifest=json.loads(compiled[name+'.json'])
        if name=='springboard':
            expected=json.loads(old['store/springboard.json']); expected['version']=cfg['springboard_version']
        else: expected=app_manifest(name,cfg['apps'][name]['version'])
        require(manifest==expected and meta['version']==manifest['version'],'Audio manifest mismatch: '+name)
        store['store/'+name+'.elf']=elf;store['store/'+name+'.json']=encoded(manifest)
    mic_elf,mic_manifest=package_mic(root)
    store['store/mic/driver.elf']=mic_elf;store['store/mic/manifest.json']=mic_manifest
    board=json.loads(store['store/board.json'])
    source_profiles=[]
    for n,b in files.items():
        if n.startswith('sources/') and n.endswith('/source-profile.json'):
            p=json.loads(b); source_profiles.append(next(d for d in p['devices'] if d['instance_id']==13))
    require(len(source_profiles)==8 and all(d==source_profiles[0] for d in source_profiles),'Microphone mapping differs across Watch profiles')
    require(not any(d['instance_id']==13 for d in board['devices']),'Baseline unexpectedly already contains microphone')
    board['devices'].append(source_profiles[0]);board['devices'].sort(key=lambda d:d['instance_id']);board['revision']=PROFILE
    store['store/board.json']=encoded(board)
    boot=json.loads(store['store/boot.json'])
    require(not any(d.get('instance_id')==13 for d in boot['drivers']),'Baseline unexpectedly already starts microphone')
    boot['drivers'].append({'manifest':'mic/manifest.json','instance_id':13})
    for name in APPS:boot['app_capabilities'].append({'manifest':name+'.json','grants':app_grants(name)})
    require(len(boot['app_capabilities'])<=16,'Runtime application policy capacity exceeded')
    store['store/boot.json']=encoded(boot)
    shared={n:b for n,b in files.items() if not n.startswith('store/') and n!='deployment-record.json'}
    shared['shared/catalog.json']=compiled['catalog.json']
    shared['shared/audio-build.json']=compiled['audio-build.json']
    shared['shared/audio-sources.json']=(root/'apps/audio-sources.json').read_bytes()
    out={**shared,**store,'baseline.zip':base.read_bytes()}
    allowed=CHANGED|{n for n in ADDED if n.startswith('store/')}
    changed={n for n in set(old)|set(store) if old.get(n)!=store.get(n)}
    require(changed==allowed,'Audio overlay changed unexpected store paths: '+str(sorted(changed^allowed)))
    rec={'schema':'riscrte.watch-audio-tools-deployment','schema_version':1,'source_sha':head,'profile':PROFILE,
         'base_profile':BASE_PROFILE,'base_sha256':sha(base.read_bytes()),'sources':cfg['sources'],
         'minimum_runtime':cfg['minimum_runtime'],'apps':list(APPS),'changed_store':sorted(CHANGED),
         'added_store':sorted(ADDED & set(store)),'physical_verification':'pending'}
    rec['entries']=[{'path':n,'size_bytes':len(b),'sha256':sha(b)} for n,b in sorted(out.items())]
    out['deployment-record.json']=encoded(rec)
    return out

def verify(path,root=ROOT,expected_head=None):
    p=Path(path); files=read_zip(p); rec=json.loads(files['deployment-record.json'])
    require(rec['schema']=='riscrte.watch-audio-tools-deployment' and rec['profile']==PROFILE,'Wrong audio deployment')
    require(expected_head is None or rec['source_sha']==expected_head,'Unexpected audio source head')
    base=Path('/dev/null')
    class Mem:
        def __init__(self,b): self.b=b
        def read_bytes(self): return self.b
    compiled={n+e:files['store/'+n+e] for n in ('springboard',*APPS) for e in ('.elf','.json')}
    compiled.update({'audio-build.json':files['shared/audio-build.json'],'catalog.json':files['shared/catalog.json']})
    expected=build(Mem(files['baseline.zip']),compiled,rec['source_sha'],root)
    require(files==expected,'Audio deployment differs from exact additive overlay')
    require(p.read_bytes()==zip_bytes(files),'Noncanonical audio archive')
    return rec

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('--compiled',type=Path,required=True);p.add_argument('--head',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    payload={x.name:x.read_bytes() for x in a.compiled.iterdir() if x.is_file()}
    out=build(a.base,payload,a.head);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(zip_bytes(out));verify(a.output,expected_head=a.head);print(a.output)

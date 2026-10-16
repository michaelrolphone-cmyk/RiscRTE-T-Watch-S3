#!/usr/bin/env python3
"""Rebuild only Timecard with its exact published Watch or X4 feature profile.

Reads frozen predecessor artifacts and checks inherited features, original
fonts, and Timecard storage/model contracts. No native build,
other application rebuild, unpublished source export, or firmware delivery.
"""
import argparse, hashlib, importlib.util, json, os, shlex, shutil, subprocess, sys
from pathlib import Path

VERSIONS = {'watch':'0.2.14','x4':'0.2.17'}
PRIOR_VERSIONS = {'watch':'0.2.12','x4':'0.2.15'}
DEVICE = 'x4' if Path(__file__).resolve().parent.parent.name == 'minimal' else 'watch'
ROOT=Path(__file__).resolve().parents[2 if DEVICE=='x4' else 1]
SELECTION=json.loads((ROOT/('minimal/docs/timecard-input-policy/selection.json' if DEVICE=='x4' else 'docs/timecard-input-policy/selection.json')).read_text())
VERSION=VERSIONS[DEVICE]
SELECTED_PRIOR={'watch':'6386c04fcd93e9fabc0e2106130193cdfbda608291134d1aa5998f2bb5beee03','x4':'5f36916c576249ec96cc47bfc10607e05f81e511b372a7dddc4cf514375ad3c4'}
SYSTEM = 'fd4b1e52fe2a49c3c4c22f9ccd4c98a91f88afa0'
PROFILE = '089868395268b696c05651c33816345bfe0425df'
PRODUCTIVITY = '164ea8c4f8bace10148bcfd9b9dcdd97e9fc8e75'
UTILITIES = '4beb9778d300ec9f6b18448e1ec86317e063c98c'
RUNTIMES = {'watch':'64c8e52e46fd91e8fdafd636db04eed88f0c51a9', 'x4':'1c1ed8661ea30d47e7e9707c41d492ce3a2b4d70'}
PRIOR = {'watch':'8d241dc09e9f6181778200527ee3456d40f9542c0aa8c84a113937ae5eb0423d', 'x4':'7b74d87f3a568b4b9d968c1695870ab79a06cac2f5f91099885291b40b69cf71'}
COMMON = ['-DPORTABLE_TEXT_INPUT_POLICY', '-DPORTABLE_TIMECARD_SHARED_TEXT_INPUT', '-DPORTABLE_TEXT_INPUT_CLIENT', '-DPORTABLE_CHECKED_STORAGE_RUNTIME', '-DPORTABLE_NATIVE_CUSTODY_FENCE', '-DPORTABLE_ALARM_TERMINAL_RETENTION', '-DPORTABLE_APP_LAUNCH_GUARD', '-DPORTABLE_APP_HOME_GUARD']
WATCH_ADDITIONS = ['-flto','-DPORTABLE_HOME_APP="springboard.elf"','-DPORTABLE_WATCH_COLOR_ONLY','-DPORTABLE_WATCH_FROZEN_ICONS']
MODELS = ['timecard.c','timecard_appdata_bridge.h','timecard_portable_validation.h','timecard_native_time.h']
EXPORTS = {'app_main','app_module_init','app_module_fini'}
ALLOWED = {'risc_runtime_get_api','memcpy','memset','memcmp','memmove','strcmp','strncmp','strlen','snprintf','malloc','calloc','free','strcpy','memchr','strrchr'}


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(p,*args): return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()
def require(ok,reason):
    if not ok: raise ValueError(reason)
def clean(p,pin):
    require(git(p,'rev-parse','HEAD')==pin and not git(p,'status','--porcelain','--untracked-files=no'),'Wrong or dirty source: '+str(p))
def add_unique(old,extra): return old+[f for f in extra if f not in old]
def flags_only(command): return [f for f in command if f.startswith('-D')]
def normalize_flags(flags): return [Path(f).name if f.endswith(('ContextsFaces.h','watch-alarm-profile.h')) else f for f in flags]


def build(a):
    S,U,T,R,W,O,B,P = [getattr(a,n).resolve() for n in ('system','utilities','productivity','runtime','watch_profile','output','baseline','predecessor_record')]
    VERSION=VERSIONS[a.device]
    root=Path(__file__).resolve().parents[1 if a.device=='watch' else 2]
    require(a.productivity_commit==PRODUCTIVITY,'Unqualified Timecard application source')
    clean(S,SYSTEM);clean(U,UTILITIES);clean(T,a.productivity_commit);clean(R,RUNTIMES[a.device]);clean(W,PROFILE)
    recipe=git(root,'rev-parse','HEAD');clean(root,recipe)
    require(not O.exists(),'Use a fresh output directory')
    predecessor=json.loads(P.read_text())['timecard']
    inherited_optimizations=[f for f in predecessor['command'] if f in ('-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-mno-target-align')]
    require(predecessor['sha256']==PRIOR[a.device],'Wrong predecessor Timecard receipt')
    baseline_elf=B/('timecard.elf' if a.device=='watch' else 'SD/Apps/timecard/timecard.elf')
    baseline_manifest=B/('timecard.json' if a.device=='watch' else 'store/timecard.json')
    require(sha(baseline_elf)==PRIOR[a.device],'Wrong baseline Timecard bytes')
    manifest=json.loads(baseline_manifest.read_text());require(manifest['version']==PRIOR_VERSIONS[a.device],'Wrong prior version')
    require({'capability':'ui.text-input','api':1} not in manifest['requires'],'Already opted in')
    manifest['version']=VERSION;manifest['requires'].append({'capability':'ui.text-input','api':1})
    selected=a.selected_baseline.resolve()
    selected_digest={'watch':'6386c04fcd93e9fabc0e2106130193cdfbda608291134d1aa5998f2bb5beee03','x4':'5f36916c576249ec96cc47bfc10607e05f81e511b372a7dddc4cf514375ad3c4'}
    if a.device=='watch':
        sys.path.insert(0,str(a.watch_tools.resolve()/'scripts'))
        from current_bootfs import read_image
        old=read_image((selected/'components/bootfs.bin').read_bytes(),0x510000)
        current_manifest=json.loads(old['timecard.json']);current_elf=old['timecard.elf']
    else:
        current_manifest=json.loads((selected/'store/timecard.json').read_text())
        row=next(r for r in json.loads((selected/'store/boot.json').read_text())['app_capabilities'] if r['manifest']=='timecard.json')
        current_elf=(selected/'SD'/row['image_source']['path']).read_bytes()
    require(hashlib.sha256(current_elf).hexdigest()==selected_digest[a.device],'Wrong immediate selected predecessor')
    require(current_manifest['version']=={'watch':'0.2.13','x4':'0.2.16'}[a.device],'Wrong immediate selected predecessor version')
    current_manifest['version']=VERSION
    require(manifest==current_manifest,'Immediate predecessor authority or model contract differs')
    models={}
    for n in MODELS:
        reference=subprocess.check_output(['git','-C',str(T),'show','0b8667d64e76a6b4bbd325a1c963405f3af57404:Apps/'+n])
        require((T/'Apps'/n).read_bytes()==reference,'Timecard model/data contract changed: '+n);models[n]=sha(T/'Apps'/n)
    O.mkdir(parents=True);(O/'debug').mkdir()
    cc=os.environ.get('NATIVE_APP_CC') or shutil.which('xtensa-esp32s3-elf-gcc');require(cc,'Set NATIVE_APP_CC')
    compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0]
    require('8.4.0' in compiler and '2021r2-patch5' in compiler,'Wrong compiler')
    sys.path.insert(0,str(a.watch_tools.resolve()/'scripts'))
    from compact_current_elf import compact
    if a.device=='watch':
        from build_contexts_cohort import definitions
        from build_current_apps import application_inputs
        catalog=P.parent/'build/empty_catalog.c'
        require(sha(catalog)==predecessor['target_dependencies']['generated:empty_catalog.c']['sha256'],'Frozen Watch catalog changed')
        shutil.copyfile(catalog,O/'empty_catalog.c')
        alarm=O/'watch-alarm-profile.h'
        alarm.write_text('#include "'+str(U/'lib/Alarm/include/AlarmServiceV1.h')+'"\n#define ALARM_MODE_VISUAL 0u\nstatic inline uint32_t alarm_service_output_modes(const alarm_service_v1*s){return s?ALARM_MODE_BOTH:ALARM_MODE_VISUAL;}\n')
        inherited=[f for f in definitions('timecard',VERSION,W) if f!='-flto']+['-DPORTABLE_ASYNC_RGB565','-include',str(alarm),'-flto']
        require(normalize_flags(inherited)==normalize_flags(predecessor['defines']),'Inherited Watch feature profile differs')
        flags=add_unique(inherited,COMMON+WATCH_ADDITIONS)
        repos={'system-apps':S,'utilities':U,'productivity':T,'runtime':R}
        sources,includes,_=application_inputs('timecard',T/'Apps/timecard_portable.c',repos,W,O,'runtime-features')
        includes += [U/'lib/Contexts/include',R/'sdk/app']
        exports=EXPORTS
        for name,row in predecessor['target_dependencies'].items():
            owner,relative=name.split(':',1)
            if owner=='watch':require(sha(W/relative)==row['sha256'],'Watch input changed: '+relative)
            if owner=='system-apps' and '/fonts/' in relative or owner=='system-apps' and '/settings_fonts/' in relative:
                selected=S/relative
                if relative=='lib/PortableApps/fonts/icons.inc':selected=S/'lib/PortableApps/fonts/watch-240-icons.inc'
                require(sha(selected)==row['sha256'],'Original Watch font differs: '+relative)
    else:
        require(predecessor['application_source']=='d6a9657378fedcdb61d1cea83f2108799e57ccae','Wrong native-time predecessor lineage')
        inherited=predecessor['defines']
        require(inherited==flags_only(predecessor['command']) and '-DPORTABLE_RASTER_SNAPSHOT' in inherited,'Incomplete X4 inherited profile')
        flags=add_unique(inherited,COMMON)
        sdk=O/'sdk/include';sdk.mkdir(parents=True)
        origin=P.parent/'x4-baseline-old-source-receipt.json'
        require(sha(origin)==predecessor['profile_origin_receipt_sha256'],'X4 profile origin receipt changed')
        sdk_record=json.loads(origin.read_text())['sdk_sha256']
        for name,digest in sdk_record.items():
            source=P.parent/'x4-baseline-build-inputs/sdk/include'/name
            require(sha(source)==digest,'Frozen X4 SDK header changed: '+name)
            shutil.copyfile(source,sdk/name)
        for folder in (S/'lib/PortableApps/include',R/'sdk/app',U/'lib/Alarm/include'):
            for source in folder.glob('*.h'):shutil.copyfile(source,sdk/source.name)
        # Current PortableApps contracts override their frozen predecessor headers.
        for name in ('PaperPresentation.h','PaperFrame.h'):
            if (sdk/name).exists():(sdk/name).unlink()
        shutil.copytree(S/'lib/PortableApps/time',O/'sdk/time')
        catalog=O/'catalog.c'
        catalog.write_text('#include "PortableApps.h"\nconst t5_app_manifest_t portable_catalog[1]={{.compatible=false}};\nconst unsigned portable_catalog_count=0;\n')
        includes=[sdk,S/'lib/NativeApps/include',T/'lib/NativeApps/include',T/'lib/Bluetooth/include',T/'lib/Contexts/include',T/'Apps',S/'Apps']
        sources=[T/'Apps/timecard_portable.c',S/'lib/PortableApps/src/adapter.c',*[S/'lib/PortableApps/src'/n for n in ('PortableNativeTimeSource.c','PortableRealtimeClient.c','PortableTimeZone.c','PortableTimeZoneCatalog.c','PortableTimeZonePreference.c')],catalog]
        exports=EXPORTS|{'risc_resident_app_descriptor_v1'}
        for name,digest in predecessor['compiled_dependencies_sha256'].items():
            if name.startswith('System/') and any(t in name for t in ['/fonts/','/paper_fonts/','/settings_fonts/']):
                require(sha(S/name.removeprefix('System/'))==digest,'Original X4 font differs: '+name)
    owners={'system-apps':S,'utilities':U,'productivity':T,'runtime':R,'watch':W,'generated':O}
    deps={}
    for source in sources:
        text=subprocess.check_output([cc,'-std=c11','-Os','-fPIC','-ffreestanding','-fno-builtin','-MM',*flags,*['-I'+str(i) for i in includes],str(source)],text=True)
        for token in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
            p=Path(token).resolve();require(p.is_file() and not {'test','tests','fixtures'}&set(p.parts),'Invalid target source: '+token)
            matches=[(k,p.relative_to(v)) for k,v in owners.items() if p.is_relative_to(v)];require(matches,'Unowned input: '+str(p));owner,rel=matches[-1]
            deps[owner+':'+rel.as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    require(any(n.endswith('PortableTextInputClient.h') for n in deps) and any(n.endswith('RiscTextEntryV1.h') for n in deps),'Shared client missing')
    require(not any('text-faces-' in n for n in deps),'Font subset selected')
    mapping=O/'exports.map';mapping.write_text('{global:'+';'.join(sorted(exports))+';local:*;};\n')
    elf=O/'timecard.elf'
    command=[cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror',*inherited_optimizations,*flags,*['-I'+str(i) for i in includes],*map(str,sources),'-lgcc','-o',str(elf)]
    subprocess.run(command,check=True)
    normalizer=U/'scripts/normalize_xtensa_relocations.py';require(sha(normalizer)=='f71d9ca3b267166bc69d0e4853463774a8dde5384924132e1aca0e0c2f3a965f','Relocation normalizer differs')
    spec=importlib.util.spec_from_file_location('timecard_normalizer',normalizer);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    shutil.copyfile(elf,O/'debug/timecard-linker.elf');normalization=module.normalize(elf)
    validator=O/'validate-elf'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(S/'test/native_apps/stubs'),'-I'+str(S/'lib/elf_loader/include'),str(S/'lib/elf_loader/src/esp_elf_validate.c'),str(S/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True)
    subprocess.run([str(validator),str(elf)],check=True);compaction=compact(elf,cc,debug_path=O/'debug/timecard.elf');subprocess.run([str(validator),str(elf)],check=True)
    symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True)
    imports={l.split()[-1] for l in symbols.splitlines() if ' U ' in ' '+l};actual={l.split()[-1] for l in symbols.splitlines() if len(l.split())>=3 and l.split()[-2] in ('T','D','B','R')}
    require(imports<=ALLOWED and actual==exports,'Unexpected Timecard ABI')
    require(b'ui.text-input\0' in elf.read_bytes(),'Shared service not in target')
    budget=160000 if a.device=='watch' else 300000;require(elf.stat().st_size<=budget,'Timecard component budget exceeded')
    for name,row in deps.items():
        owner,relative=name.split(':',1);require(sha(owners[owner]/relative)==row['sha256'],'Source changed during build')
    for p,pin in [(S,SYSTEM),(U,UTILITIES),(T,a.productivity_commit),(R,RUNTIMES[a.device]),(W,PROFILE),(root,recipe)]:clean(p,pin)
    (O/'timecard.json').write_text(json.dumps(manifest,indent=2)+'\n')
    record=dict(schema='timecard.modal-policy.component.v1',device=a.device,version=VERSION,sha256=sha(elf),bytes=elf.stat().st_size,manifest_sha256=sha(O/'timecard.json'),compiler=compiler,command=command,defines=flags,inherited_defines=inherited,inherited_optimizations=inherited_optimizations,feature_additions=[f for f in flags if f not in inherited],sources={k:git(v,'rev-parse','HEAD') for k,v in owners.items() if k!='generated'},source_roots={k:str(v) for k,v in owners.items()},product_recipe=recipe,build_recipe_sha256=sha(__file__),target_dependencies=deps,original_fonts_retained=True,baseline_features_preserved=True,timecard_model_contracts=models,predecessor_receipt_sha256=sha(P),predecessor_elf_sha256=PRIOR[a.device],imports=sorted(imports),exports=sorted(exports),compaction=compaction,relocation_normalization=normalization,component_budget_bytes=budget,shared_text_input=True,modal_policy=True,immediate_predecessor_elf_sha256=selected_digest[a.device],native_changed=False,hardware_verified=False,canonical_paper_contract_selected=(a.device=='watch'))
    (O/'timecard-build-record.json').write_text(json.dumps(record,indent=2)+'\n')
    print(a.device,'Timecard',VERSION,record['bytes'],record['sha256'])
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',choices=[DEVICE],required=True)
    for n in ['system','utilities','productivity','runtime','watch-profile','watch-tools','baseline','predecessor-record','selected-baseline','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--productivity-commit',required=True);build(p.parse_args())
if __name__=='__main__':main()

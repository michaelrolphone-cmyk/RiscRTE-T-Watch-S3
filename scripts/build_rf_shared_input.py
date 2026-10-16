#!/usr/bin/env python3
"""Rebuild only RF 0.3.4 with its exact published Watch or X4 feature profile.

Reads frozen predecessor artifacts, checks inherited features, original fonts,
model formats and the c12781b2 operation-scoped storage helper. No native build,
other application rebuild, unpublished source export, or firmware delivery.
"""
import argparse, hashlib, importlib.util, json, os, shlex, shutil, subprocess, sys
from pathlib import Path

VERSION = '0.3.4'
DEVICE = 'x4' if Path(__file__).resolve().parent.parent.name == 'minimal' else 'watch'
SYSTEM = '7fb13b09b4dac275a8111b224784f8a472f39264'
PROFILE = '089868395268b696c05651c33816345bfe0425df'
STARTUP = 'c12781b2d4e08772d06078bfff7441276cb5a7a8'
RUNTIMES = {'watch':'64c8e52e46fd91e8fdafd636db04eed88f0c51a9', 'x4':'1c1ed8661ea30d47e7e9707c41d492ce3a2b4d70'}
PRIOR = {'watch':'f05b5ec08db1b1a7f8c7e3133c69b504e8e293d90f76bedcf2d93f0089b1c46b', 'x4':'8dc03063f3c21d55ebba7fb4428363819f60b52a127e1c8b7a56e3d57405dd11'}
COMMON = ['-DPORTABLE_RF_SHARED_TEXT_INPUT', '-DPORTABLE_TEXT_INPUT_CLIENT', '-DPORTABLE_CHECKED_STORAGE_RUNTIME', '-DPORTABLE_NATIVE_CUSTODY_FENCE', '-DPORTABLE_ALARM_TERMINAL_RETENTION', '-DPORTABLE_APP_LAUNCH_GUARD', '-DPORTABLE_APP_HOME_GUARD']
WATCH_ADDITIONS = ['-flto','-DPORTABLE_HOME_APP="springboard.elf"','-DPORTABLE_WATCH_COLOR_ONLY','-DPORTABLE_WATCH_FROZEN_ICONS','-mno-target-align']
MODELS = ['rf_background.h','rf_dsp.h','rf_identity.h','rf_math.h','rf_neural.h','rf_neural_store.h','rf_presentation.h','rf_signature_store.h','rf_signatures.h','rf_store.h','rf_temporal.h','rf_temporal_files.h','rf_temporal_store.h']
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
    S,U,R,W,O,B,P = [getattr(a,n).resolve() for n in ('system','utilities','runtime','watch_profile','output','baseline','predecessor_record')]
    root=Path(__file__).resolve().parents[1 if a.device=='watch' else 2]
    clean(S,SYSTEM);clean(U,a.utilities_commit);clean(R,RUNTIMES[a.device]);clean(W,PROFILE)
    recipe=git(root,'rev-parse','HEAD');clean(root,recipe)
    require(not O.exists(),'Use a fresh output directory')
    predecessor=json.loads(P.read_text())['waterfall']
    require(predecessor['sha256']==PRIOR[a.device],'Wrong predecessor RF receipt')
    baseline_elf=B/('waterfall.elf' if a.device=='watch' else 'SD/Apps/waterfall/waterfall.elf')
    baseline_manifest=B/('waterfall.json' if a.device=='watch' else 'store/waterfall.json')
    require(sha(baseline_elf)==PRIOR[a.device],'Wrong baseline RF bytes')
    manifest=json.loads(baseline_manifest.read_text());require(manifest['version']=='0.3.3','Wrong prior version')
    require({'capability':'ui.text-input','api':1} not in manifest['requires'],'Already opted in')
    manifest['version']=VERSION;manifest['requires'].append({'capability':'ui.text-input','api':1})
    require(sha(U/'Apps/rf_app_data_scope.h')=='5b21f23b2505f12ef38ed1fc0e90b3c665066f639f2ccd8ca90e3b8073f69010','Startup operation-scoped storage fix changed')
    models={}
    for n in MODELS:
        reference=subprocess.check_output(['git','-C',str(U),'show',STARTUP+':Apps/'+n])
        require((U/'Apps'/n).read_bytes()==reference,'RF model/format changed: '+n);models[n]=sha(U/'Apps'/n)
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
        inherited=[f for f in definitions('waterfall',VERSION,W) if f!='-flto']+['-DPORTABLE_ASYNC_RGB565','-include',str(alarm)]
        require(normalize_flags(inherited)==normalize_flags(predecessor['defines']),'Inherited Watch feature profile differs')
        presentation=O/'watch-rf-presentation.h'
        presentation.write_text('#include "'+str(S/'Apps/PaperPresentation.h')+'"\n#define RF_PRESENTATION_H\n')
        flags=add_unique(inherited,COMMON+WATCH_ADDITIONS)+['-include',str(presentation)]
        repos={'system-apps':S,'utilities':U,'runtime':R}
        sources,includes,_=application_inputs('waterfall',U/'Apps/waterfall.c',repos,W,O,'runtime-features')
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
        oldroot=Path(next(x for x in predecessor['command'] if x.endswith('/Apps/waterfall.c'))).parents[1]
        oldsystem=Path(next(x for x in predecessor['command'] if x.endswith('/lib/PortableApps/src/adapter.c'))).parents[3]
        generated=P.parent
        recorded_generated=Path(predecessor['command'][-1]).parent
        sdk=O/'sdk/include';sdk.mkdir(parents=True)
        for f in (generated/'sdk/include').glob('*.h'):
            key=str(recorded_generated/'sdk/include'/f.name)
            if key not in predecessor['dependencies']:continue
            require(sha(f)==predecessor['dependencies'][key],'Frozen generated SDK changed: '+f.name)
            shutil.copyfile(f,sdk/f.name)
        for f in (S/'lib/PortableApps/include').glob('*.h'):shutil.copyfile(f,sdk/f.name)
        shutil.copytree(S/'lib/PortableApps/time',O/'sdk/time')
        catalog=generated/'catalog.c';require(sha(catalog)==predecessor['dependencies'][str(recorded_generated/'catalog.c')],'Frozen X4 catalog changed');shutil.copyfile(catalog,O/'catalog.c')
        inherited=flags_only(predecessor['command']);flags=add_unique(inherited,COMMON)
        replacements=[(str(oldroot),str(U)),(str(oldsystem),str(S)),(str(recorded_generated),str(O))]
        def mapped(s):
            for old,new in replacements:s=s.replace(old,new)
            return s
        sources=[Path(mapped(s)) for s in predecessor['command'] if s.endswith('.c')]
        includes=[Path(mapped(s[2:])) for s in predecessor['command'] if s.startswith('-I')]
        exports=EXPORTS|{'risc_resident_app_descriptor_v1'}
        for name,digest in predecessor['dependencies'].items():
            if str(oldsystem) in name and any(t in name for t in ['/fonts/','/paper_fonts/','/settings_fonts/']):
                require(sha(mapped(name))==digest,'Original X4 font differs: '+name)
    owners={'system-apps':S,'utilities':U,'runtime':R,'watch':W,'generated':O}
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
    elf=O/'waterfall.elf'
    command=[cc,'-std=c11','-Os','-fPIC','-mtext-section-literals','-mlongcalls','-fvisibility=hidden','-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-shared','-Wl,--no-relax','-Wl,--hash-style=sysv','-Wl,--version-script='+str(mapping),'-Wall','-Wextra','-Werror',*flags,*['-I'+str(i) for i in includes],*map(str,sources),'-lgcc','-o',str(elf)]
    subprocess.run(command,check=True)
    normalizer=U/'scripts/normalize_xtensa_relocations.py';require(sha(normalizer)=='f71d9ca3b267166bc69d0e4853463774a8dde5384924132e1aca0e0c2f3a965f','Relocation normalizer differs')
    spec=importlib.util.spec_from_file_location('rf_normalizer',normalizer);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    shutil.copyfile(elf,O/'debug/waterfall-linker.elf');normalization=module.normalize(elf)
    validator=O/'validate-elf'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(S/'test/native_apps/stubs'),'-I'+str(S/'lib/elf_loader/include'),str(S/'lib/elf_loader/src/esp_elf_validate.c'),str(S/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True)
    subprocess.run([str(validator),str(elf)],check=True);compaction=compact(elf,cc,debug_path=O/'debug/waterfall.elf');subprocess.run([str(validator),str(elf)],check=True)
    symbols=subprocess.check_output([cc.removesuffix('gcc')+'nm','-D',str(elf)],text=True)
    imports={l.split()[-1] for l in symbols.splitlines() if ' U ' in ' '+l};actual={l.split()[-1] for l in symbols.splitlines() if len(l.split())>=3 and l.split()[-2] in ('T','D','B','R')}
    require(imports<=ALLOWED and actual==exports,'Unexpected RF ABI')
    require(b'ui.text-input\0' in elf.read_bytes(),'Shared service not in target')
    budget=249392 if a.device=='watch' else 290000;require(elf.stat().st_size<=budget,'RF component budget exceeded')
    for name,row in deps.items():
        owner,relative=name.split(':',1);require(sha(owners[owner]/relative)==row['sha256'],'Source changed during build')
    for p,pin in [(S,SYSTEM),(U,a.utilities_commit),(R,RUNTIMES[a.device]),(W,PROFILE),(root,recipe)]:clean(p,pin)
    (O/'waterfall.json').write_text(json.dumps(manifest,indent=2)+'\n')
    record=dict(schema='rf.shared-input.component.v1',device=a.device,version=VERSION,sha256=sha(elf),bytes=elf.stat().st_size,manifest_sha256=sha(O/'waterfall.json'),compiler=compiler,command=command,defines=flags,inherited_defines=inherited,feature_additions=[f for f in flags if f not in inherited],sources={k:git(v,'rev-parse','HEAD') for k,v in owners.items() if k!='generated'},source_roots={k:str(v) for k,v in owners.items()},product_recipe=recipe,build_recipe_sha256=sha(__file__),target_dependencies=deps,original_fonts_retained=True,baseline_features_preserved=True,rf_models=models,startup_storage_fix_sha256=sha(U/'Apps/rf_app_data_scope.h'),predecessor_receipt_sha256=sha(P),predecessor_elf_sha256=PRIOR[a.device],imports=sorted(imports),exports=sorted(exports),compaction=compaction,relocation_normalization=normalization,component_budget_bytes=budget,shared_text_input=True,native_changed=False,hardware_verified=False,canonical_paper_contract_selected=(a.device=='watch'))
    (O/'waterfall-build-record.json').write_text(json.dumps(record,indent=2)+'\n')
    print(a.device,'RF',VERSION,record['bytes'],record['sha256'])
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',choices=[DEVICE],required=True)
    for n in ['system','utilities','runtime','watch-profile','watch-tools','baseline','predecessor-record','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--utilities-commit',required=True);build(p.parse_args())
if __name__=='__main__':main()

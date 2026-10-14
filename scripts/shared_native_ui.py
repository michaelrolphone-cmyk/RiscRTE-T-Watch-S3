#!/usr/bin/env python3
"""Source-owned preserving T-Watch shared UI integration; no device or publication I/O."""
import argparse, copy, hashlib, io, json, os, re, subprocess, sys, tarfile, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/shared-native-ui'
PINS = json.loads((DOCS / 'source-pins.json').read_text())

def need(ok, why):
    if not ok: raise ValueError(why)
def sha(data): return hashlib.sha256(data).hexdigest()
def encoded(value): return (json.dumps(value, sort_keys=True, indent=2)+'\n').encode()
def git(repo, *args): return subprocess.check_output(['git','-C',str(repo),*args])
def files(root): return {p.relative_to(root).as_posix():p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}
def write(root, data):
    root.mkdir(parents=True, exist_ok=True)
    for name, payload in data.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(payload)
def clean(repo, revision):
    need(git(repo,'rev-parse','HEAD').decode().strip()==revision,'Source HEAD differs: '+str(repo))
    need(not git(repo,'diff','HEAD','--name-only').strip(),'Dirty source: '+str(repo))
def require_final():
    need(PINS['finalized'] is True and re.fullmatch('[0-9a-f]{40}',PINS['system_revision'] or ''),'Final shared System pin pending')
    need(PINS['version']=='1.1.35' and PINS['provisioning_version_reserved']=='1.1.34','Reserved product versions changed')
def verify_wake(store):
    manifest=json.loads(store['default.json']);boot=json.loads(store['boot.json'])
    need(manifest['id']=='twatch-clock','Wrong Home identity')
    requirement={'capability':'runtime.retained-wake','api':1}
    grant={**requirement,'instance_id':0}
    need(manifest['requires'].count(requirement)==1,'Home retained-wake declaration missing/duplicated')
    entries=[x for x in boot['app_capabilities'] if x['manifest']=='default.json']
    need(len(entries)==1 and entries[0]['grants'].count(grant)==1,'Home retained-wake grant missing/duplicated')
    return dict(declaration_present=True,grant_present=True,instance_id=0,unchanged=True)
def verify_baseline(store):
    need({k:sha(v) for k,v in store.items()}==PINS['baseline_files'],'Released 1.1.33 store differs')
    need(len(store)==121 and sum(k.endswith('.elf') for k in store)==59,'Incomplete baseline')
    c=json.loads(store['cohort.json']);need(c['version']=='1.1.33' and c['source_revision']==PINS['baseline_cohort_source'],'Wrong cohort identity')
    return verify_wake(store)
def command(system, bridges, compiler, output, candidate):
    source=json.loads((ROOT/'docs/t054/springboard-command.json').read_text())
    old_system=next(x[:-len('/Apps/springboard.c')] for x in source if x.endswith('/Apps/springboard.c'))
    old_bridges=next(x[:-len('/apps/clock/portable_navigation.c')] for x in source if x.endswith('/apps/clock/portable_navigation.c'))
    result=[x.replace(old_system,str(system)).replace(old_bridges,str(bridges)) for x in source]
    result[0]=str(compiler);result[result.index('-o')+1]=str(output/'springboard.elf')
    mapping=output/'exports.map';mapping.write_text('{global: app_main; app_module_init; app_module_fini;local:*;};\n')
    result=['-Wl,--version-script='+str(mapping) if x.startswith('-Wl,--version-script=') else x for x in result]
    if candidate:result.append('-DPORTABLE_STAGE_PROFILE')
    return result

def _build(args):
    need(not args.output.exists(),'Output must be new')
    candidate=not args.baseline
    cc_version=subprocess.check_output([str(args.compiler),'--version'],text=True).splitlines()[0]
    need(cc_version=='xtensa-esp32s3-elf-gcc (crosstool-NG esp-2021r2-patch5) 8.4.0','Compiler version differs')
    args.output.mkdir(parents=True)
    cmd=command(args.system,args.bridges,args.compiler,args.output,candidate)
    subprocess.run(cmd,check=True)
    sys.path.insert(0,str(args.bridges/'scripts'))
    from compact_current_elf import compact
    from normalize_xtensa_relocations import normalize
    elf=args.output/'springboard.elf'
    normalize(elf);compaction=compact(elf,str(args.compiler),debug_path=args.output/'springboard.debug.elf')
    if args.baseline:need(sha(elf.read_bytes())==PINS['baseline_files']['springboard.elf'],'Baseline Springboard did not reproduce')
    validator=args.output/'validate-elf'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(args.system/'test/native_apps/stubs'),'-I'+str(args.system/'lib/elf_loader/include'),str(args.system/'lib/elf_loader/src/esp_elf_validate.c'),str(args.system/'test/native_apps/validate_test.c'),'-o',str(validator)],check=True)
    subprocess.run([str(validator),str(elf)],check=True)
    syms=subprocess.check_output([str(args.compiler).removesuffix('gcc')+'nm','-D',str(elf)],text=True)
    imports=sorted({l.split()[-1] for l in syms.splitlines() if ' U ' in ' '+l})
    exports=sorted({l.split()[-1] for l in syms.splitlines() if len(l.split())>=3 and l.split()[-2] in ('T','D','B','R')})
    report=dict(baseline=args.baseline,provisional=args.provisional,sha256=sha(elf.read_bytes()),bytes=elf.stat().st_size,imports=imports,exports=exports,command=cmd,compaction=compaction,compiler=cc_version,compiler_sha256=sha(args.compiler.read_bytes()),source_revision=PINS['baseline_system'] if args.baseline else PINS['system_revision'],source_files={k:sha(v) for k,v in files(args.system).items() if not k.startswith(('.git/','build/'))},device_accessed=False)
    (args.output/'build.json').write_bytes(encoded(report));print(json.dumps({k:report[k] for k in ('baseline','provisional','sha256','bytes','imports','exports')},indent=2))

def archive(repo, revision, target):
    target.mkdir(parents=True)
    data=git(repo,'archive',revision)
    with tarfile.open(fileobj=io.BytesIO(data)) as source:source.extractall(target,filter='data')

def build(args):
    clean(args.bridges,PINS['bridge_revision'])
    if args.baseline:clean(args.system,PINS['baseline_system'])
    elif not args.provisional:require_final();clean(args.system,PINS['system_revision'])
    with tempfile.TemporaryDirectory(prefix='shared-ui-source-') as td:
        snapshot=Path(td);selected=copy.copy(args)
        archive(args.bridges,PINS['bridge_revision'],snapshot/'bridges');selected.bridges=snapshot/'bridges'
        if not args.provisional:
            archive(args.system,PINS['baseline_system'] if args.baseline else PINS['system_revision'],snapshot/'system');selected.system=snapshot/'system'
        _build(selected)

def native_stage(args):
    clean(args.runtime,PINS['runtime_revision'])
    expected=git(args.runtime,'show',PINS['baseline_runtime']+':watch-expanded-profile.ini')
    need((ROOT/'native/shared-ui-profile/watch-expanded-profile.ini').read_bytes()==expected,'Expanded profile diverges from released Watch')
    for name in ('watch-expanded-profile.ini','watch-native-ui.ini'):
        data=(ROOT/'native/shared-ui-profile'/name).read_bytes();target=args.runtime/name
        need(not target.exists() or target.read_bytes()==data,'Conflicting native profile '+name);target.write_bytes(data)
    print('Native profiles staged; use PLATFORMIO_SETTING_ENABLE_TELEMETRY=No and pio run -c watch-native-ui.ini -e watch-native-ui -j1')

def compose(args):
    if not args.provisional:require_final()
    need(not args.output.exists(),'Output must be new')
    before=files(args.baseline_store);wake=verify_baseline(before);store=copy.deepcopy(before)
    candidate=(args.springboard/'springboard.elf').read_bytes();need(candidate[:7]==b'\x7fELF\x01\x01\x01','Invalid target ELF')
    store['springboard.elf']=candidate
    manifest=json.loads(before['springboard.json']);manifest['version']=PINS['springboard_manifest_version'];store['springboard.json']=encoded(manifest)
    firmware=args.firmware.read_bytes();need(24<len(firmware)<=0x260000,'Native firmware too large')
    need(set(re.findall(rb'RTE_SOURCE=([^\x00\s]+)',firmware))=={PINS['runtime_revision'].encode()},'Native source marker mismatch')
    cohort=json.loads(before['cohort.json']);cohort.update(version=PINS['version'],source_revision=args.source_revision,runtime_version='0.3.3',firmware_sha256=sha(firmware),firmware_size=len(firmware));store['cohort.json']=encoded(cohort)
    changed=sorted(k for k in store if store[k]!=before[k]);need(changed==PINS['changed_store_files'],'Unexpected store changes '+str(changed))
    need(store['boot.json']==before['boot.json'] and store['default.json']==before['default.json'],'Existing Home policy changed')
    need(store['default.elf']==before['default.elf'],'Existing Home ELF changed')
    verify_wake(store);write(args.output/'store',store)
    sys.path.insert(0,str(ROOT/'scripts'));import current_bootfs
    image,packing=current_bootfs.build(store,size=0x550000)
    from read_only_spiffs import read_image
    need(read_image(image,0x550000)==store,'Packed store roundtrip mismatch');(args.output/'store.bin').write_bytes(image)
    report=dict(version=PINS['version'],baseline=PINS['baseline_version'],changed_store_files=changed,unchanged_files=len(store)-len(changed),elf_count=59,home_policy=wake,packing=packing,store_sha256=sha(image),native_sha256=sha(firmware),provisional=args.provisional,assets_published=False,hardware_tested=False)
    (args.output/'composition.json').write_bytes(encoded(report));print(json.dumps(report,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='action',required=True)
    b=subs.add_parser('build')
    for n in ('system','bridges','compiler','output'):b.add_argument('--'+n,type=Path,required=True)
    b.add_argument('--baseline',action='store_true');b.add_argument('--provisional',action='store_true')
    n=subs.add_parser('native-stage');n.add_argument('--runtime',type=Path,required=True)
    c=subs.add_parser('compose')
    for n in ('baseline-store','springboard','firmware','output'):c.add_argument('--'+n,type=Path,required=True)
    c.add_argument('--source-revision',required=True);c.add_argument('--provisional',action='store_true')
    a=p.parse_args();need(__debug__,'Do not use python -O')
    for k,v in vars(a).items():
        if isinstance(v,Path):setattr(a,k,v.resolve())
    {'build':build,'native-stage':native_stage,'compose':compose}[a.action](a)
if __name__=='__main__':main()

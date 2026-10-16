#!/usr/bin/env python3
"""Execute actual Contexts graph/Clock over the existing lowest-hardware fixture."""
import argparse, hashlib, json, os, shutil, sys
from pathlib import Path
p=argparse.ArgumentParser()
for key in ('watch','runtime','system','utilities','drivers','store','output'):p.add_argument('--'+key,type=Path,required=True)
p.add_argument('--runtime-candidate-sha',help='Early source-compatibility probe only; never final artifact qualification')
for key in ('binding-repository','binding','native-candidate'):p.add_argument('--'+key,type=Path)
p.add_argument('--binding-source')
p.add_argument('--lifecycle-build',type=Path,help='Strict verified Watch18 overlay on the exact baseline binding')
p.add_argument('--enabled',action='store_true')
a=p.parse_args()
a.watch=a.watch.resolve();sys.path.insert(0,str(a.watch/'scripts'))
import runtime_features_store as base
_original_flags=base._flags
base._flags=lambda:[*_original_flags(),'-ffunction-sections','-fdata-sections','-Wl,--gc-sections']
from contexts_profile import configuration
from build_contexts_cohort import clean, optimization_policy, COMPILER_HELPERS
paths={k:getattr(a,k).resolve() for k in ('runtime','system','utilities','drivers')}
runtime,system,utilities,drivers=[paths[k] for k in ('runtime','system','utilities','drivers')]
stream_sources=('src/runtime/streams/AppStreamSessions.cpp','src/runtime/streams/ProviderQueueHost.cpp')
if all((runtime/name).is_file() for name in stream_sources):
    base.RUNTIME_SOURCES=(*base.RUNTIME_SOURCES,*stream_sources)
if a.lifecycle_build:
    from build_lifecycle_routes import configuration as lifecycle_configuration, verify as verify_lifecycle
    c=lifecycle_configuration()
else:
    c=configuration(a.watch)
binding_arguments=(a.binding_repository,a.binding,a.native_candidate,a.binding_source)
bound_receipt=None
if any(binding_arguments):
    base.require(all(binding_arguments) and not a.runtime_candidate_sha,'Complete final binding arguments required without an override')
    clean(a.binding_repository,a.binding_source)
    if a.lifecycle_build:
        base.require(a.binding_source=='b6abe35ed3049174e53c89c8adb85edd3860da34','Wrong baseline binding source')
        bound_receipt=verify_lifecycle(a.lifecycle_build,a.binding,runtime,a.native_candidate,clean(a.watch))
        base.require(bound_receipt['configuration']==c,'Lifecycle build configuration differs')
    else:
        verify_code=('import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                     'import watch_native_binding;r,f,b,l=watch_native_binding.verify(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]),sys.argv[5]);'
                     'print(json.dumps(r,sort_keys=True))')
        bound_receipt=json.loads(base.command([sys.executable,'-c',verify_code,a.binding_repository/'scripts',a.binding,runtime,a.native_candidate,a.binding_source]))
        base.require(bound_receipt['app_stage_configuration']==c,'Native binding selected different app/source bytes')

for key,path in [('runtime',runtime),('system-apps',system),('utilities',utilities)]:
    clean(path,(bound_receipt['runtime']['source'] if bound_receipt else a.runtime_candidate_sha or c['sources'][key]['commit']) if key=='runtime' else c['sources'][key]['commit'])
clean(drivers,c['drivers']['commit'])
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
content=base._files(a.store.resolve())
watch_head=clean(a.watch)
candidate_cohort=json.loads(content['cohort.json'])
if bound_receipt:
    if a.lifecycle_build:
        base.require(bound_receipt['watch_source']==watch_head and candidate_cohort['source_revision']==watch_head and
                     bound_receipt['files']=={n:{'sha256':hashlib.sha256(b).hexdigest(),'size_bytes':len(b)} for n,b in content.items()},
                     'Executed store differs from the exact lifecycle build')
    else:
        base.require(bound_receipt['app_stage_source']==watch_head and bound_receipt['cohort']==candidate_cohort and
                     bound_receipt['files']=={n:{'sha256':hashlib.sha256(b).hexdigest(),'size_bytes':len(b)} for n,b in content.items()},
                     'Executed store differs from the exact native/app binding')
else:
    base.require(candidate_cohort['source_revision']==watch_head,'Candidate is not bound to this Watch source')
source_states={name:base.source_state(path) for name,path in {'watch':a.watch,**paths}.items()}
if a.enabled:base.HERE=a.watch/'tests/contexts_store'
def source_hashes():
    result=base._source_hashes(runtime,system,utilities)
    result.update(base.external_source_hashes(drivers))
    roots=[utilities/'Apps',utilities/'lib',utilities/'Services/contexts',
           a.watch/'tests/contexts_store',a.watch/'scripts']
    for root in roots:
        for path in root.rglob('*'):
            if path.is_file() and path.suffix in ('.c','.cpp','.h','.inc','.json','.py','.sh'):
                result[str(path)]=base.sha(path)
    result[str(a.watch/'apps/contexts-sources.json')]=base.sha(a.watch/'apps/contexts-sources.json')
    return result
before_sources=source_hashes()
host=base._host(runtime,out,utilities,True,True)
destination=out/'host-store';base._write_store(destination,content)
modules=out/'modules';modules.mkdir()
includes=['-I'+str(a.watch/part) for part in ('sdk/app','sdk/driver','include')]
source_manifests,frozen=base.driver_source_manifests(True,drivers,a.watch)
targets={}
for row in json.loads(content['boot.json'])['drivers']:
    manifest=json.loads(content[row['manifest']]);name=manifest['id'];target=destination/Path(row['manifest']).parent/manifest['file_name']
    targets.setdefault(name,[]).append(target)
cc,cxx=os.environ.get('CC','cc'),os.environ.get('CXX','c++')
for name, destinations in targets.items():
    module=modules/(name+'.elf');extra=[];compiler=cc;language='-std=c11'
    if name=='contexts-service':
        source=utilities/'Services/contexts/service.c';inc=['-I'+str(q) for q in (utilities/'Apps',utilities/'lib/Contexts/include',drivers/'sdk/driver')]
        production=source.parent/'manifest.json'
    elif name=='alarm-service':
        source=utilities/'Services/alarm_service/service.c';extra=['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER','-DALARM_VOLUME_CONTROL','-DALARM_DND_CONTROL']
        inc=['-I'+str(q) for q in (utilities/'lib/Alarm/include',runtime/'sdk/driver',system/'lib/PortableApps/include')];production=source.parent/'points-manifest.json'
    elif name=='telemetry-broadcast':
        source=utilities/'Services/telemetry_broadcast/service.c';inc=['-I'+str(q) for q in (system/'lib/PortableApps/include',drivers/'sdk/driver')];production=source.parent/'manifest.json'
    elif name=='s3-radio-iq-v1':
        source=drivers/'Drivers/s3_radio_iq_v1/driver.c';extra=['-DRISC_IQ_HOST_TEST'];inc=['-I'+str(q) for q in (drivers/'sdk/driver',drivers/'test')];production=source.parent/'manifest.json'
    elif name=='ble-hid':
        base.command([sys.executable,drivers/'scripts/build_ble_hid.py','--host',*(['--sanitize'] if os.environ.get('SANITIZE')=='1' else [])])
        built=drivers/('build/ble-hid-san' if os.environ.get('SANITIZE')=='1' else 'build/ble-hid-host')/'driver.so';shutil.copy2(built,module)
        for target in destinations:shutil.copy2(module,target)
        continue
    elif name.startswith('software-update-'):
        source=system/'Services/update/service.cpp';compiler=cxx;language='-std=c++17';extra=['-fno-exceptions','-fno-rtti','-DUPDATE_FIRMWARE='+str(int(name.endswith('firmware')))]
        inc=['-I'+str(system/q) for q in ('lib/PortableApps/include','lib/NativeApps/include')];production=source.parent/name.removeprefix('software-update-')/'manifest.json'
    else:
        production=source_manifests[name];source=list(production.parent.glob('*.c'));assert len(source)==1;source=source[0]
        inc=['-I'+str(drivers/'sdk/driver')] if name in base.EXTERNAL_DRIVERS else includes
    selected=[json.loads(content[row['manifest']]) for row in json.loads(content['boot.json'])['drivers'] if json.loads(content[row['manifest']])['id']==name][0]
    expected=json.loads(production.read_text())
    if a.lifecycle_build and name=='software-update-firmware':
        base.require(c['firmware_update']['source_routes'] and selected['version']=='0.1.5','Missing explicit route selection')
        extra+=['-DUPDATE_SOURCE_ROUTES=1'];expected={**expected,'version':'0.1.5'}
    assert expected==selected,name
    base.command([compiler,language,*base._flags(),'-fPIC','-shared','-fvisibility=hidden',*inc,*extra,source,*(__import__('imu_sources').extra_sources(name)),'-o',module])
    for target in destinations:shutil.copy2(module,target)
clock_includes=['-I'+str(q) for q in (system/'lib/PortableApps/include',utilities/'lib/Alarm/include',utilities/'lib/Contexts/include')]+includes
clock_lto=['-flto',*['-Wl,--undefined='+name for name in COMPILER_HELPERS['default']]]
flags=['WATCH_CLOCK_LAUNCHER','WATCH_CLOCK_ALARMS','WATCH_CLOCK_POINTS','PORTABLE_RTC_UTC8_DENVER','WATCH_PAIRED_BOOT_CONFIRM','WATCH_QUICK_ACTIONS','WATCH_QUICK_RADIOS','WATCH_MOTION_WAKE','WATCH_ALARM_SLEEP_RESUME','WATCH_RUNTIME_FEATURES','WATCH_BLE_BROADCAST','PORTABLE_LOW_BATTERY','WATCH_CONTEXTS_CLIENT']
objects=[]
for name in ('crown.c','nova/nova.c','points_projection.c','effects/divdi3.c'):
    obj=modules/(Path(name).stem+'.o');base.command([cc,'-std=c11',*base._flags(),'-fPIC','-fvisibility=hidden',*clock_includes,*clock_lto,*['-D'+f for f in flags],'-c',a.watch/'apps/clock'/name,'-o',obj]);objects.append(obj)
for name in ('quick_actions.c','quick_render.c','quick_session.c','quick_radios.c'):
    obj=modules/(Path(name).stem+'.o');base.command([cc,'-std=c11',*base._flags(),'-fPIC','-fvisibility=hidden',*clock_includes,*clock_lto,*['-D'+f for f in flags],'-c',system/'lib/PortableApps/src'/name,'-o',obj]);objects.append(obj)
effect=modules/'boot-effect.o';base.command([cxx,'-std=c++11',*base._flags(),'-fPIC','-fvisibility=hidden',*includes,'-c',a.watch/'apps/clock/effects/boot.cpp','-o',effect])
clock=modules/'default.elf';base.command([cxx,'-std=c++11',*base._flags(),'-fPIC','-shared','-fvisibility=hidden',*clock_lto,effect,*objects,'-o',clock]);shutil.copy2(clock,destination/'default.elf')
if a.enabled:
    from build_current_apps import application_inputs
    from build_contexts_cohort import definitions,write_catalog
    from contexts_profile import catalog
    repos={'system-apps':system,'utilities':utilities,'runtime':runtime,'productivity':utilities}
    write_catalog(out,catalog(a.watch))
    for name in ('audio_spectrum','waterfall'):
        sources,inc,_=application_inputs(name,utilities/'Apps'/(name+'.c'),repos,a.watch,out,'runtime-features')
        inc+=[utilities/'lib/Contexts/include']
        flags=definitions(name,c['app_versions'][name],a.watch)
        base.command([cc,'-std=c11',*base._flags(),'-fPIC','-shared','-fvisibility=hidden',*flags,*['-I'+str(i) for i in inc],*sources,'-lm','-o',destination/(name+'.elf')],timeout=180)
results=[]
for scenario in (('enabled-handoff','enabled-sleep','enabled-sleep-refused','enabled-sleep-retained','enabled-close-retained','enabled-capture-retained') if a.enabled else base.SCENARIOS):
    output=base.command([host,destination,scenario],timeout=90)
    prefix='CONTEXTS_ENABLED_RESULT ' if a.enabled else 'UPDATE_CLOCK_RESULT '
    marker=next(line.removeprefix(prefix) for line in output.splitlines() if line.startswith(prefix))
    results.append({**json.loads(marker),'output':output});print(scenario,'PASS',flush=True)
assert {n:b for n,b in base._files(destination).items() if n.endswith('.json')}=={n:b for n,b in content.items() if n.endswith('.json')}
base.require(source_hashes()==before_sources,'Qualification sources changed during execution')
base.require(source_states=={name:base.source_state(path) for name,path in {'watch':a.watch,**paths}.items()},'Qualification source state changed during execution')
record={'schema':2,'mode':'actual Runtime/CpuPort/ProviderGraph and source-compiled providers/Clock over existing lowest-hardware fixture',
        'monitoring_enabled':a.enabled,
        'sanitizer':{'undefined':os.environ.get('SANITIZE','1')!='0','address':os.environ.get('ADDRESS_SANITIZE')=='1'},
        'runtime_candidate_override':a.runtime_candidate_sha,'native_binding':None if a.lifecycle_build else bound_receipt,'lifecycle_build':bound_receipt if a.lifecycle_build else None,'final_artifact_qualification':a.runtime_candidate_sha is None,'candidate_cohort':candidate_cohort,'candidate_store_sha256':base.store_digest(content),
        'candidate_files':{name:{'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)} for name,raw in sorted(content.items())},
        'watch_source':watch_head,'source_pins':c['sources'],'drivers_pin':c['drivers'],'source_states':source_states,
        'source_hashes':before_sources,'runner_sha256':base.sha(Path(__file__)),
        'fixture_sha256':base.sha(base.HERE/'host.cpp'),
        'section_gc':{'compile_flags':['-ffunction-sections','-fdata-sections'],'link_flags':['-Wl,--gc-sections']},
        'optimization':optimization_policy(),'provider_artifacts':len(targets),'provider_selections':len(json.loads(content['boot.json'])['drivers']),
        'startup_monitoring':'enabled with original owner exports and empty native PCM reads' if a.enabled else 'disabled virtual preference; no capture fabricated','scenarios':results,'production_json_substitutions':0,'target_instructions_executed':False,'hardware_qualified':False}
(out/'contexts-graph-proof.json').write_text(json.dumps(record,indent=2)+'\n')

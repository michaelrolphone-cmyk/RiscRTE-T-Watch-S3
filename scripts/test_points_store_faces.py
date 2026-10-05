#!/usr/bin/env python3
"""Real Points save→Runtime bound service→Clock under untouched store policies.

Native architecture replaces target executable bytes, not boot/board policies.
The test adapter drives real Points open_dependencies/load_catalog/save_action;
GUI event dispatch is not emulated. Hardware remains the existing raw model.
"""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'tests/points_store_runtime'

def replace(text, before, after):
    assert before in text, before
    return text.replace(before, after)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime','system-apps','utilities','legacy-utilities','productivity','output'):
        p.add_argument('--'+name,required=True,type=Path)
    inputs=p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--store',type=Path)
    inputs.add_argument('--archive',type=Path)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    paths={k: v.resolve() for k,v in vars(a).items() if v is not None}
    spec=importlib.util.spec_from_file_location('production_store',ROOT/'scripts/test_production_store_runtime.py')
    base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
    if a.archive:
        from check_runtime_store_admission import archive_store, validate_paths
        paths['store']=out/'input-store'
        content=archive_store(paths['archive'].read_bytes());validate_paths(content)
        existing={str(f.relative_to(paths['store'])):f.read_bytes() for f in paths['store'].rglob('*') if f.is_file()}
        assert not existing or existing==content, 'Output contains a different extracted store'
        for name,data in content.items():
            dest=paths['store']/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    hash_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    source_files=[paths['productivity']/'Apps/points_in_time.c',paths['productivity']/'Apps/points_writer.h',
                  paths['utilities']/'lib/Alarm/include/PointsRecords.h',paths['legacy_utilities']/'lib/Alarm/include/PointsRecords.h',
                  HERE/'app.c',HERE/'clock.c',Path(__file__).resolve()]
    inputs_digest={str(f.relative_to(paths['store'])):hash_file(f) for f in paths['store'].rglob('*') if f.is_file()}
    extra_provenance={'productivity':base.source_state(paths['productivity']),
                      'legacy_utilities':base.source_state(paths['legacy_utilities']),
                      'source_sha256':{str(f):hash_file(f) for f in source_files},
                      'archive_sha256':hash_file(paths['archive']) if a.archive else None}
    host=(ROOT/'tests/production_store_runtime/host.cpp').read_text()
    extra=r'''
#include <cstdlib>
#include <dlfcn.h>
#undef dlsym
extern "C" void* dlsym(void*,const char*) noexcept;
namespace {
std::map<std::string,std::vector<uint8_t>> records;
bool written=false;
unsigned cfgServiceReads=0, cfgClockReads=0, snapshots=0;
void (*snapshot)(unsigned*)=nullptr;
int option(const char* name,int fallback){const char* v=getenv(name);return v?atoi(v):fallback;}
}
extern "C" int points_test_case(){return option("POINTS_CASE",1);}
extern "C" int points_test_format(){return option("POINTS_FORMAT",0);}
extern "C" int points_test_written_yet(){return written;}
extern "C" void points_test_written(){
 written=true;
 if(points_test_case()==4)records["5:points_cfg"][60]^=1;
}
static void check_snapshot(){
 assert(snapshot);unsigned s[12]={};snapshot(s);++snapshots;
 unsigned face=option("POINTS_FACE",24), format=points_test_format();
 int c=points_test_case();bool bad=c==4||c==5||(option("POINTS_LEGACY",0)&&(c==2||c==3||c==6||c==7));
 assert(s[0]==face&&s[1]==format&&s[2]==(bad?3u:(c&&c!=8)?1u:2u));
 if(!bad&&c&&c!=8){assert(s[3]==(c==3?4u:2u)&&s[4]>0&&s[10]==(c==3?2u:1u));}
 if(!bad&&c==3){assert(s[5]==2&&s[6]==3&&s[7]==7&&s[8]&&s[9]&&s[11]==4);}
 printf("POINTS SNAPSHOT case=%d legacy=%d face=%u hour24=%u status=%u today=%u ends=%u custom=%u\n",c,option("POINTS_LEGACY",0),s[0],s[1],s[2],s[3],s[10],s[11]);
}
'''
    host=replace(host,'namespace {\nstruct Model',extra+'\nnamespace {\nstruct Model')
    host=replace(host,'m.milliseconds+=ms;assert(m.milliseconds<30000);','m.milliseconds+=ms;assert(m.milliseconds<30000);if(written&&(points_test_case()==4||points_test_case()==5)&&m.milliseconds>1000&&!m.ready)m.registers[0][0x49]|=8;')
    host=replace(host,'if(!strncmp(line,"WATCH_CLOCK ready",17))m.ready=true;', 'if(!strncmp(line,"WATCH_CLOCK ready",17)){check_snapshot();m.ready=true;}')
    start=host.index('int32_t kvGet(');end=host.index('bool bind(',start)
    host=host[:start]+r'''
int32_t kvGet(void*,uint32_t ns,const char* key,void* bytes,uint32_t cap,uint32_t* size){
 assert(ns>=1&&ns<=5&&key&&size);*size=0;
 if(ns==5&&!strcmp(key,"points_cfg")){
   if(written&&m.appLoaded&&!m.firstAppDelay)++cfgClockReads;else ++cfgServiceReads;

 }
 if(written&&m.appLoaded&&!m.firstAppDelay){
   if(ns==1&&(!strcmp(key,"watch_face")||!strcmp(key,"time_format")))++m.appSettingsReads;
   if(ns==5&&!strcmp(key,"points_cfg"))++m.appPointsReads;
 }
 if(written&&points_test_case()==5&&ns==5&&!strcmp(key,"points_cfg"))return RISC_KEY_VALUE_IO;
 auto i=records.find(std::to_string(ns)+":"+key);
 if(i==records.end())return RISC_KEY_VALUE_NOT_FOUND;
 *size=i->second.size();if(cap<*size)return RISC_KEY_VALUE_BUFFER_SMALL;
 memcpy(bytes,i->second.data(),*size);return RISC_KEY_VALUE_OK;
}
int32_t kvPut(void*,uint32_t ns,const char* key,const void* bytes,uint32_t size){
 assert(!(written&&ns==5));++m.storageWrites;const auto* b=(const uint8_t*)bytes;
 records[std::to_string(ns)+":"+key]=std::vector<uint8_t>(b,b+size);return RISC_KEY_VALUE_OK;
}
''' + host[end:]
    host=replace(host,'assert(!strcmp(name,"default.elf"));++m.appLoads;m.appLoaded=true;', 'assert(!strcmp(name,"default.elf")||!strcmp(name,"points_in_time.elf"));++m.appLoads;m.appLoaded=true;m.firstAppDelay=false;')
    host=replace(host,'if(m.appLoaded&&!m.application)m.application=module;', 'if(m.appLoaded){m.application=module;snapshot=(void(*)(unsigned*))dlsym(module,"points_test_snapshot");}')
    host=replace(host,'m.appLoaded=false;', 'm.appLoaded=false;m.application=nullptr;')
    host=replace(host,'m.appLoads==1&&m.appUnloads==1','m.appLoads==3&&m.appUnloads==3')
    host=replace(host,'!m.rtcWrites&&!m.storageWrites&&!m.radioActivity','!m.rtcWrites&&!m.radioActivity')
    host=replace(host,'setvbuf(stdout,nullptr,_IONBF,0);',r'''setvbuf(stdout,nullptr,_IONBF,0);
 unsigned f=option("POINTS_FACE",24),fmt=1-points_test_format();
 if(points_test_case()!=8)records["1:watch_face"]={0x46,1,(uint8_t)f,(uint8_t)(f^0xa5)};
 if(points_test_case()!=8)records["1:time_format"]={0x54,1,(uint8_t)fmt,(uint8_t)(fmt^0xa5)};''')
    host=replace(host,'assert(!risc_test_native_mapping_count());\n  printf("Production default Clock PASS:', 'assert(!risc_test_native_mapping_count());assert(snapshots==1&&cfgServiceReads&&cfgClockReads==1);if(points_test_case()==8)assert(!m.storageWrites&&records.empty());\n  printf("Production default Clock PASS:')
    (out/'host.cpp').write_text(host);base.HERE=out
    original_run=base.run;clock_commands=[];built_app=False
    def run(command,env=None):
        nonlocal built_app
        command=list(map(str,command))
        if str(ROOT/'apps/clock/crown.c') in command:
            command[command.index(str(ROOT/'apps/clock/crown.c'))]=str(HERE/'clock.c')
            command += ['-I'+str(ROOT/'apps/clock'),'-DPOINTS_CLOCK_SOURCE="'+str(ROOT/'apps/clock/crown.c')+'"']
        if any(str(ROOT/'apps/clock'/name) in command for name in ('points_projection.c',)) or str(HERE/'clock.c') in command:
            clock_commands.append(command)
        if str(ROOT/'apps/clock/effects/boot.cpp') in command:clock_commands.append(command)
        if str(out/'host.cpp') in command and not built_app:
            app=out/'app.elf'
            flags=['-O1','-g','-fPIC','-shared','-fvisibility=hidden','-ffunction-sections','-fdata-sections','-Wl,--gc-sections']
            if os.environ.get('SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
            original_run(['cc','-std=c11',*flags,*['-I'+str(x) for x in (paths['system_apps']/'lib/PortableApps/include',paths['system_apps']/'lib/NativeApps/include',paths['utilities']/'lib/Alarm/include',paths['productivity']/'Apps',paths['system_apps']/'Apps',ROOT/'sdk/app',ROOT/'sdk/driver',ROOT/'include')],'-DPOINTS_APP_SOURCE="'+str(paths['productivity']/'Apps/points_in_time.c')+'"','-DPORTABLE_RTC_UTC8_DENVER',HERE/'app.c','-o',app])
            shutil.copy2(app,out/'store-0/points_in_time.elf');built_app=True
        return original_run(command,env)
    base.run=run
    sys.argv=[str(ROOT/'scripts/test_production_store_runtime.py'),'--runtime',str(paths['runtime']),'--system-apps',str(paths['system_apps']),'--utilities',str(paths['utilities']),'--store',str(paths['store']),'--output',str(out)]
    base.main()
    evidence=[]
    for legacy in (False,True):
        if legacy:
            for command in clock_commands:
                original_run([x.replace('-I'+str(paths['utilities']/'lib/Alarm/include'),'-I'+str(paths['legacy_utilities']/'lib/Alarm/include')) for x in command])
            shutil.copy2(out/'modules/default.elf',out/'store-0/default.elf')
        for case in range(9):
            for face in ((0,) if case==8 else range(33) if case==1 else range(24,33)):
                for fmt in ((0,) if case==8 else (0,1)):
                    env={**os.environ,'POINTS_CASE':str(case),'POINTS_FACE':str(face),'POINTS_FORMAT':str(fmt),'POINTS_LEGACY':str(int(legacy))}
                    result=subprocess.run([out/'production-store-test',out/'store-0'],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
                    evidence.append({'case':case,'face':face,'hour24':fmt,'legacy':legacy,'returncode':result.returncode,'output':result.stdout})
                    (out/'points-results.json').write_text(json.dumps(evidence,indent=2)+'\n')
                    if result.returncode:
                        print(result.stdout);raise RuntimeError(evidence[-1])
        print(('Legacy mismatch reproduced' if legacy else 'Matched decoder passed')+': nine data states, all 33 stored face IDs for basic records; nine schedule IDs for every state, both latest time preferences',flush=True)
    (out/'points-results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    assert inputs_digest=={str(f.relative_to(paths['store'])):hash_file(f) for f in paths['store'].rglob('*') if f.is_file()}
    extra_provenance['sources_unchanged']=all(hash_file(f)==extra_provenance['source_sha256'][str(f)] for f in source_files)
    (out/'points-provenance.json').write_text(json.dumps(extra_provenance,indent=2)+'\n')
    print('386 real Runtime/app-save/service/Clock checks passed. Host architecture only; no device or release.')
if __name__=='__main__':main()

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
    p.add_argument("--metadata-legacy-utilities",type=Path)
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
    if a.metadata_legacy_utilities:source_files.append(paths['metadata_legacy_utilities']/'lib/Alarm/include/PointsRecords.h')
    inputs_digest={str(f.relative_to(paths['store'])):hash_file(f) for f in paths['store'].rglob('*') if f.is_file()}
    extra_provenance={'productivity':base.source_state(paths['productivity']),
                      'legacy_utilities':base.source_state(paths['legacy_utilities']),
                      'metadata_legacy_utilities':base.source_state(paths['metadata_legacy_utilities']) if a.metadata_legacy_utilities else None,
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
unsigned scheduleWrites=0,audioOpens=0,audioCloses=0,audioWrites=0,hapticStarts=0;
bool audioOpen=false;
std::map<std::string,std::vector<uint8_t>> originalRecords;
void checksum(std::vector<uint8_t>& b){uint32_t h=2166136261u;for(unsigned i=0;i<60;i++)h=(h^b[i])*16777619u;for(unsigned i=0;i<4;i++)b[60+i]=(uint8_t)(h>>(i*8));}
uint32_t word(const std::vector<uint8_t>& b,unsigned i){return b[i]|(b[i+1]<<8)|(b[i+2]<<16)|((uint32_t)b[i+3]<<24);}
void persisted_records(bool write){
 const char* path=getenv("POINTS_RESTART_FILE");if(!path)return;
 FILE* f=fopen(path,write?"wb":"rb");if(!write&&!f)return;assert(f);
 if(write){for(const auto& v:records){uint32_t k=v.first.size(),n=v.second.size();assert(fwrite(&k,4,1,f)==1&&fwrite(&n,4,1,f)==1);assert(fwrite(v.first.data(),1,k,f)==k&&fwrite(v.second.data(),1,n,f)==n);}}
 else {records.clear();uint32_t k,n;while(fread(&k,4,1,f)==1){assert(k<80&&fread(&n,4,1,f)==1&&n<=64);std::string key(k,'\0');std::vector<uint8_t>b(n);assert(fread(&key[0],1,k,f)==k&&fread(b.data(),1,n,f)==n);records[key]=b;}}
 assert(!ferror(f)&&fclose(f)==0);
}
unsigned cfgServiceReads=0, cfgClockReads=0, snapshots=0;
void (*snapshot)(unsigned*)=nullptr;
int option(const char* name,int fallback){const char* v=getenv(name);return v?atoi(v):fallback;}
}
extern "C" int points_test_case(){return option("POINTS_CASE",1);}
extern "C" int points_test_option(const char* n,int fallback){return option(n,fallback);}
extern "C" int points_test_format(){return option("POINTS_FORMAT",0);}
extern "C" int points_test_written_yet(){return written;}
extern "C" void points_test_written(){
 written=true;
 if(points_test_case()==4)records["5:points_cfg"][60]^=1;
 if(points_test_case()==11||points_test_case()==12){auto& b=records["5:points_meta"];b[3]=points_test_case()==11?'1':'2';b[9]=points_test_case()==11?13:14;checksum(b);}
}
static void check_snapshot(){
 assert(snapshot);unsigned s[14]={};snapshot(s);++snapshots;
 unsigned face=option("POINTS_FACE",24), format=points_test_format();
 int c=points_test_case(),legacy=option("POINTS_LEGACY",0);
 bool custom=c==3||(c>=10&&c<=12),defaults=c==8||c==14;
 bool bad=c==4||c==5||(legacy==1&&(c==2||custom||c==6||c==7));
 unsigned status=bad?3u:c==0||(defaults&&legacy)?2u:1u;
 assert(s[0]==face&&s[1]==format&&s[2]==status);
 if(!bad&&c&& !defaults){assert(s[3]==(custom?4u:2u)&&s[4]>0&&s[10]==(custom?2u:1u));}
 if(!bad&&c==3){assert(s[5]==3&&s[6]==3&&s[7]==7&&s[8]&&s[9]&&s[11]==4);}
 if(!bad&&c==10){assert(s[5]==3&&s[11]==4);if(!legacy)assert(s[12]&&s[9]);else assert(!s[12]&&!s[9]);}
 if(!bad&&(c==11||c==12))assert(!s[8]&&!s[9]&&!s[12]);
 if(defaults&&!legacy){assert(s[5]==1&&s[12]&&s[13]);assert(s[3]==(option("POINTS_DAY",5)<=8?11u:0u));}
 printf("POINTS SNAPSHOT case=%d legacy=%d face=%u hour24=%u status=%u today=%u ends=%u custom=%u\n",c,option("POINTS_LEGACY",0),s[0],s[1],s[2],s[3],s[10],s[11]);
}
'''
    host=replace(host,'namespace {\nstruct Model',extra+'\nnamespace {\nstruct Model')
    host=replace(host,'if(address==0x5a&&reg==12)assert(tx[i]==0); // No haptic GO during empty startup.','')
    host=replace(host,'if(address==0x51&&reg>=2&&reg<=8)++m.rtcWrites;','if(address==0x51&&reg>=2&&reg<=8)++m.rtcWrites;if(address==0x5a&&reg==12&&tx[i]==1)++hapticStarts;')
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
 assert(!(written&&ns==5));if(ns==5)++scheduleWrites;++m.storageWrites;const auto* b=(const uint8_t*)bytes;
 records[std::to_string(ns)+":"+key]=std::vector<uint8_t>(b,b+size);return RISC_KEY_VALUE_OK;
}
''' + host[end:]
    host=replace(host,'assert(!strcmp(name,"default.elf"));++m.appLoads;m.appLoaded=true;', 'assert(!strcmp(name,"default.elf")||!strcmp(name,"points_in_time.elf"));++m.appLoads;m.appLoaded=true;m.firstAppDelay=false;')
    host=replace(host,'if(m.appLoaded&&!m.application)m.application=module;', 'if(m.appLoaded){m.application=module;snapshot=(void(*)(unsigned*))dlsym(module,"points_test_snapshot");}')
    host=replace(host,'m.appLoaded=false;', 'm.appLoaded=false;m.application=nullptr;')
    host=replace(host,'m.appLoads==1&&m.appUnloads==1','m.appLoads==3&&m.appUnloads==3')
    host=replace(host,'!m.rtcWrites&&startupStorageOk()&&!m.radioActivity','!m.rtcWrites&&!m.radioActivity')
    host=replace(host,'setvbuf(stdout,nullptr,_IONBF,0);',r'''setvbuf(stdout,nullptr,_IONBF,0);
 unsigned f=option("POINTS_FACE",24),fmt=points_test_case()==14?points_test_format():1-points_test_format();
 if(points_test_case()!=8||f!=0)records["1:watch_face"]={0x46,1,(uint8_t)f,(uint8_t)(f^0xa5)};
 if(points_test_case()!=8)records["1:time_format"]={0x54,1,(uint8_t)fmt,(uint8_t)(fmt^0xa5)};
 if(points_test_case()!=8&&points_test_case()!=14){std::vector<uint8_t>b(64);memcpy(b.data(),"PTC1",4);b[4]=1;
   if(points_test_case()==9){b[12]=43;b[13]=127;b[14]=12;b[16]=30;}checksum(b);records["5:points_cfg"]=b;}
 if(option("POINTS_RESTART",0))persisted_records(false);originalRecords=records;''')
    host=replace(host,'  printf("Startup storage: writes=%u namespace4_points_occ=%u verified_readbacks=%u namespace5_writes=0\\n",m.storageWrites,m.pointsLedgerPresent,m.pointsLedgerReads);\n','')
    host=replace(host,'assert(!risc_test_native_mapping_count());\n  printf("Production default Clock PASS:', 'assert(!risc_test_native_mapping_count());assert(snapshots==1&&cfgServiceReads&&cfgClockReads==1);if(points_test_case()==8||points_test_case()==14)assert(!scheduleWrites&&!records.count("5:points_cfg")&&!records.count("5:points_meta"));if(points_test_case()==0||points_test_case()==9)assert(records["5:points_cfg"]==originalRecords["5:points_cfg"]);if(points_test_case()==14){bool expect=option("POINTS_EXPECT_CUE",option("POINTS_DAY",5)<=8)&&!option("POINTS_RESTART",0);assert(audioOpens==(expect?1u:0u)&&audioCloses==audioOpens&&!audioOpen&&hapticStarts==audioOpens);if(expect)assert(audioWrites>0);if(option("POINTS_RESTART",0))assert(records==originalRecords);persisted_records(true);}printf("POINTS_STORAGE total=%u schedule_meta=%u audio=%u/%u haptic=%u restart=%d\\n",m.storageWrites,scheduleWrites,audioOpens,audioCloses,hapticStarts,option("POINTS_RESTART",0));\n  printf("Production default Clock PASS:')
    host=replace(host,'const uint8_t date[]={0,0x40,0,4,0,0x10,0x26};',r'''unsigned day=option("POINTS_DAY",5),hour=option("POINTS_HOUR",4)+14,minute=option("POINTS_MINUTE",0);day+=hour/24;hour%=24;
 auto bcd=[](unsigned v){return (uint8_t)((v/10)*16+v%10);};
 const uint8_t date[]={0,bcd(minute),bcd(hour),bcd(day),(uint8_t)((day-4)%7),0x10,0x26};''')
    host=replace(host,'hardware.i2sOpen=[](uint8_t,uint8_t,uint8_t,uint8_t,uint32_t){assert(!"No alarm audio expected");return false;};',r'''hardware.i2sOpen=[](uint8_t,uint8_t,uint8_t,uint8_t,uint32_t rate){
 assert(points_test_case()==14&&!audioOpen&&rate==8000&&!option("POINTS_RESTART",0)&&option("POINTS_EXPECT_CUE",option("POINTS_DAY",5)<=8));
 const auto& b=records.at("4:points_occ");assert(b.size()==64&&b[20]==option("POINTS_SLOT",0)&&b[21]==option("POINTS_EDGE",0)&&b[23]==3);
 assert(word(b,12)==(9770u+option("POINTS_DAY",5)-1)*86400u+(option("POINTS_HOUR",4)+14)*3600u+option("POINTS_MINUTE",0)*60u);++audioOpens;audioOpen=true;return true;};''')
    host=replace(host,'hardware.i2sWrite=[](uint8_t,const int16_t*,size_t,size_t*,uint32_t){assert(!"No alarm audio expected");return false;};','hardware.i2sWrite=[](uint8_t,const int16_t*,size_t n,size_t* done,uint32_t){assert(audioOpen);*done=n;++audioWrites;return true;};')
    host=replace(host,'hardware.i2sClose=[](uint8_t){assert(!"No alarm audio expected");return false;};','hardware.i2sClose=[](uint8_t){assert(audioOpen);audioOpen=false;++audioCloses;return true;};')
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
    for legacy in ((0,1,2) if a.metadata_legacy_utilities else (0,1)):
        if legacy:
            for command in clock_commands:
                original_run([x.replace('-I'+str(paths['utilities']/'lib/Alarm/include'),'-I'+str(paths['legacy_utilities' if legacy==1 else 'metadata_legacy_utilities']/'lib/Alarm/include')) for x in command])
            shutil.copy2(out/'modules/default.elf',out/'store-0/default.elf')
        scenarios=[]
        cases=range(13) if legacy!=2 else (3,8,10,11,12)
        for case in cases:
            for face in ((0,) if case==8 else range(33) if case==1 else range(24,33)):
                for fmt in ((0,) if case==8 else (0,1)):
                    scenarios.append({'POINTS_CASE':case,'POINTS_FACE':face,'POINTS_FORMAT':fmt})
        if not legacy:
            for day in range(5,11):
                # Safe pre-notification probes prove actual service deadlines.
                times=[(4,0,30 if day<=8 else (12-day)*1440+30)]
                if day<=8:times += [(9,11,1),(12,26,1),(14,26,1)]
                for hour,minute,delta in times:
                    scenarios.append({'POINTS_CASE':8,'POINTS_FACE':24,'POINTS_FORMAT':0,'POINTS_DAY':day,'POINTS_HOUR':hour,'POINTS_MINUTE':minute,'POINTS_NEXT_MINUTES':delta})
                # All seven start cues plus the three requested warnings.
                for slot,edge,hour,minute in [(0,0,4,30),(1,0,5,30),(2,0,6,0),(3,0,9,0),(3,2,9,12),(4,0,12,0),(4,2,12,27),(5,0,14,15),(5,2,14,27),(6,0,16,30),(1,1,5,45),(3,1,9,15),(4,1,12,30),(5,1,14,30)]:
                    key=f'{day}-{hour}-{minute}'
                    restart=out/('restart-'+key+'.bin')
                    if restart.exists():restart.unlink()
                    for reboot in (0,1):
                        scenarios.append({'POINTS_CASE':14,'POINTS_FACE':24,'POINTS_FORMAT':0,'POINTS_DAY':day,'POINTS_HOUR':hour,'POINTS_MINUTE':minute,'POINTS_SLOT':slot,'POINTS_EDGE':edge,'POINTS_EXPECT_CUE':int(day<=8 and edge!=1),'POINTS_RESTART':reboot,'POINTS_RESTART_FILE':str(restart)})
        for scenario in scenarios:
            env={**os.environ,**{k:str(v) for k,v in scenario.items()},'POINTS_LEGACY':str(legacy)}
            result=subprocess.run([out/'production-store-test',out/'store-0'],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
            evidence.append({'scenario':scenario,'legacy':legacy,'returncode':result.returncode,'output':result.stdout})
            (out/'points-results.json').write_text(json.dumps(evidence,indent=2)+'\n')
            if result.returncode:
                print(result.stdout);raise RuntimeError(evidence[-1])
        print(f'Decoder {legacy} passed {len(scenarios)} actual-store scenarios',flush=True)
    (out/'points-results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    assert inputs_digest=={str(f.relative_to(paths['store'])):hash_file(f) for f in paths['store'].rglob('*') if f.is_file()}
    extra_provenance['sources_unchanged']=all(hash_file(f)==extra_provenance['source_sha256'][str(f)] for f in source_files)
    (out/'points-provenance.json').write_text(json.dumps(extra_provenance,indent=2)+'\n')
    print(f'{len(evidence)} real Runtime/app-save/service/Clock checks passed. Host architecture only; no device or release.')
if __name__=='__main__':main()

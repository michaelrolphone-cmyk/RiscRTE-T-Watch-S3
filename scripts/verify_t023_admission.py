"""Full store admission with Waveshare's source-bound native composition.
Reuse the shared Watch harness; select only the explicitly wired Wi-Fi atomic endpoint.
"""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
p=argparse.ArgumentParser()
for n in ['runtime','watch','store','output']:p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--baseline-store',type=Path)
p.add_argument('--native-migration',action='store_true')
p.add_argument('--migration-negative',choices=('source','target','owners','snapshot'))
a=p.parse_args();assert not a.migration_negative or a.native_migration
a.runtime=a.runtime.resolve();a.watch=a.watch.resolve();a.output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(a.watch/'scripts'));import check_runtime_store_admission as m
native=(a.runtime/'.pio/build/watch-t023/firmware.elf').read_bytes();profile=a.runtime/'watch-expanded-profile.ini'
package_profile=Path(__file__).resolve().parents[1]/'native/t023-provisioning.ini'
assert (a.runtime/'watch-t023-profile.ini').read_bytes()==package_profile.read_bytes()
assert '-DRISC_NATIVE_PACKAGE_VOLUME=1' in package_profile.read_text()
assert b'RiscPackageVolume' in native
if a.native_migration:
 migration=Path(__file__).resolve().parents[1]/'native/t023-migration-policy.h'
 assert migration.read_bytes()==(a.runtime/'t023-migration-policy.h').read_bytes()
 assert b'watch-t023-home-wifi-133-134' in native
 assert 'RISC_NATIVE_APP_DATA_EXPORT_POLICY_V2_HEADER' in package_profile.read_text()
original_composition=m.native_composition
def composition(runtime,elf,selected,rows):
 saved=m.ROOT;m.ROOT=a.watch
 try:proof=original_composition(runtime,elf,selected,rows)
 finally:m.ROOT=saved
 assert b'RiscPackageVolume' in elf
 proof.update(package_profile_sha256=hashlib.sha256(package_profile.read_bytes()).hexdigest(),package_media='internal-only',owner_installer=True)
 return proof
m.native_composition=composition
commands=[];original_run=subprocess.run
def run(cmd,*args,**kw):
 if isinstance(cmd,list) and cmd and cmd[0]=='c++':cmd=[cmd[0],'-I'+str(a.runtime),'-Wno-unused-function','-Wno-unused-private-field','-Wno-unused-but-set-variable',*cmd[1:],str(a.runtime/'src/runtime/storage/PackageFiles.cpp'),'-Wno-unused-but-set-variable','-Wno-error=misleading-indentation','-Wno-unused-private-field']
 commands.append([str(x) for x in cmd]);return original_run(cmd,*args,**kw)
with tempfile.TemporaryDirectory() as td:
 root=Path(td);(root/'tests').mkdir();shutil.copy(a.watch/'tests/app_data_admission_backend.h',root/'tests')
 s=(a.watch/'tests/runtime_store_admission.cpp').read_text();s='#include "runtime/storage/PackageFiles.h"\n#include "RiscInternalPackageVolumeV1.h"\n'+s
 s=s.replace('bool bind(RiscBoot::Runtime& runtime) {',"""bool bind(RiscBoot::Runtime& runtime) {
 static RiscStorage::PackageFiles files({nullptr,[](void*){++storageCalls;return false;},[](void*){++storageCalls;},[](void*){++storageCalls;return false;},[](void*,uint64_t*,uint64_t*){++storageCalls;return false;}});
 static bool configured=files.configure("/metadata-only-packages");if(!configured)return false;
 static risc_storage_volume_api_v1_download packageVolume;
 auto& async=packageVolume.base.base;async.fs=*risc_storage_volume_fs(files.api());
 auto& volume=async.fs.state.prepared.base.sleep.terminal.power.volume.base;volume.struct_size=sizeof(packageVolume);
 async.async_tag=RISC_STORAGE_ASYNC_TAG;async.async_version=3;
 async.begin=[](void*,uint64_t*)->int32_t{++storageCalls;return RISC_STORAGE_ASYNC_INVALID;};
 async.submit=[](void*,uint64_t,const risc_storage_async_request_v1*,uint64_t*)->int32_t{++storageCalls;return RISC_STORAGE_ASYNC_INVALID;};
 async.collect=[](void*,uint64_t,uint64_t,risc_storage_async_result_v1*)->int32_t{++storageCalls;return RISC_STORAGE_ASYNC_INVALID;};
 async.end=[](void*,uint64_t)->int32_t{++storageCalls;return RISC_STORAGE_ASYNC_INVALID;};
 packageVolume.base.package_tag=RISC_STORAGE_PACKAGE_TAG;packageVolume.base.package_version=1;
 packageVolume.base.submit_package=[](void*,uint64_t,const risc_storage_package_request_v1*,uint64_t*)->int32_t{++storageCalls;return RISC_STORAGE_ASYNC_INVALID;};
 packageVolume.download_tag=RISC_STORAGE_DOWNLOAD_TAG;packageVolume.download_version=2;
 static risc_internal_package_volume_v1 packages{1,sizeof(packages),nullptr,&volume,[](void*){++storageCalls;return false;}};
 if(!runtime.registerPlatform(RISC_INTERNAL_PACKAGE_VOLUME_CAPABILITY,1,RiscBoot::Runtime::Scope::Global,0,&packages))return false;
""")
 if a.native_migration:
  s=s.replace('#undef private', '#undef private\n#include "'+str(a.runtime/'t023-migration-policy.h')+'"')
  mutation={'source':'selected.from.sourceRevision="bad";', 'target':'selected.to.sourceRevision="bad";', 'snapshot':'selected.after="[]";', 'owners':'auto sharing=*selected.sharedKeyValue; static const char* owners[]={"wrong-owner"}; sharing.previousOwners=owners;sharing.previousOwnerCount=1;selected.sharedKeyValue=&sharing;'}
  s=s.replace('RiscBoot::Runtime candidate({});unsigned admitted=0;', 'RiscBoot::Runtime candidate({});unsigned admitted=0; auto selected=RiscUpdate::selectedNativeAppDataExportPolicyV2();'+mutation.get(a.migration_negative,''))
  s=s.replace('runtime.validateCohort(candidate,argv[2],CohortElf::file,&admitted)', 'runtime.validateNativeCohort(candidate,argv[2],CohortElf::file,&admitted,selected)')
 (root/'tests/runtime_store_admission.cpp').write_text(s);m.ROOT=root;subprocess.run=run
 store={p.relative_to(a.store).as_posix():p.read_bytes() for p in a.store.rglob('*') if p.is_file()}
 active={p.relative_to(a.baseline_store).as_posix():p.read_bytes() for p in a.baseline_store.rglob('*') if p.is_file()} if a.baseline_store else store
 result=m.admit_cohort(a.runtime,native,active,store,expected_valid=not bool(a.migration_negative),app_policy_rows=32,native_profile=profile)
 subprocess.run=original_run
(a.output/'admission.json').write_text(json.dumps(dict(result=result,commands=commands),indent=2)+'\n');print(json.dumps(result,indent=2))

"""Witness the two-watch native configuration without weakening older profiles."""
import configparser
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import tarfile

RUNTIME='5323d1e834bdcc8e5e9fb0e8f76c383e46626801'
ARCHIVE_SHA='7431d156c119320837bd60ea9e574dbaf5b679cc93bb6c4b82cb669f3d4bbb72'
ROOT=Path(__file__).resolve().parents[1]
BOUNDS={'RISC_INSTALLED_APP_CAPACITY':64,'RISC_PROVIDER_CAPACITY':40,
        'RISC_APP_POLICY_ROWS':32,'RISC_APP_REQUIREMENT_ROWS':32}

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def source_identity(runtime):
    """Git checkout, or the exact CI-exported public source archive for offline use."""
    runtime=Path(runtime).resolve()
    if (runtime/'.git').exists():
        head=subprocess.check_output(['git','-C',str(runtime),'rev-parse','HEAD'],text=True).strip()
        require(head==RUNTIME,'Wrong Runtime source')
        require(not subprocess.check_output(['git','-C',str(runtime),'status','--porcelain','--untracked-files=no'],text=True).strip(),'Changed Runtime source')
        return {'source':head,'source_evidence':'unchanged exact Git checkout'}
    archive=os.getenv('UNIVERSAL_RUNTIME_SOURCE_ARCHIVE')
    require(bool(archive),'Offline admission needs the exact CI Runtime source archive')
    raw=Path(archive).read_bytes();require(sha(raw)==ARCHIVE_SHA,'Unexpected Runtime source archive')
    count=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
        for member in tar.getmembers():
            if member.isdir():continue
            require(member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts,'Invalid archive member')
            path=runtime/member.name
            require(path.is_file() and not path.is_symlink() and path.read_bytes()==tar.extractfile(member).read(),'Runtime source differs: '+member.name)
            count+=1
    return {'source':RUNTIME,'source_evidence':'exact CI archive byte comparison','archive_sha256':ARCHIVE_SHA,'verified_files':count}

def composition(runtime,native_elf,native_profile,app_policy_rows):
    from check_runtime_store_admission import native_symbol_bytes,native_symbol_allocation
    require(app_policy_rows==32,'Universal native requires 32 policy rows')
    proof=source_identity(runtime)
    require(set(re.findall(rb'RTE_SOURCE=([^\x00\s]+)',native_elf))=={RUNTIME.encode()},'Native source marker mismatch')
    raw=Path(native_profile).read_bytes()
    require(raw==(ROOT/'profiles/universal-native.ini').read_bytes(),'Wrong T-Watch native device profile')
    profile=configparser.ConfigParser(interpolation=None);profile.read_string(raw.decode())
    sec='env:twatch-universal';parent='env:esp32s3-16mb-appdata-universal'
    lines=lambda v:[x.strip() for x in v.splitlines() if x.strip()]
    required=['${'+parent+'.build_flags}','-DRISC_NATIVE_RECOVERY_AXP2101=1','-DRISC_RECOVERY_I2C_PORT=0','-DRISC_RECOVERY_SDA=10','-DRISC_RECOVERY_SCL=11','-DRISC_PERFORMANCE_TRACE=1']
    require(set(profile.sections())=={'platformio',sec} and not profile.defaults() and dict(profile['platformio'])=={'extra_configs':'platformio.ini'} and set(profile[sec])=={'extends','build_flags'} and profile[sec]['extends']==parent and lines(profile[sec]['build_flags'])==required,'Unsupported native profile contents')
    source=Path(runtime)/'platformio.ini';cfg=configparser.ConfigParser(interpolation=None);cfg.read_string(source.read_text())
    ancestor='env:esp32s3-16mb-appdata-iq-tcp-entropy'
    flags=['${'+ancestor+'.build_flags}']+['-D'+k+'='+str(v) for k,v in BOUNDS.items()]+['-DRISC_STAGE_LOGS=1','-DRISC_ENABLE_SDMMC=1','-Wl,-u,risc_sdmmc_host_abi']
    require(cfg[parent]['extends']==ancestor and lines(cfg[parent]['build_flags'])==flags,'Universal base profile changed')
    for name,value in [('risc_app_policy_rows',b'RISC_APP_POLICY_ROWS:32\0'),('risc_app_requirement_rows',b'RISC_APP_REQUIREMENT_ROWS:32\0'),('risc_tcp_listener_abi',b'\x01\0\0\0'),('risc_entropy_abi',b'\x01\0\0\0'),('risc_sdmmc_host_abi',b'\x01\0\0\0')]:
        require(native_symbol_bytes(native_elf,name)==value,'Compiled native marker mismatch: '+name)
    diagnostics={name:native_symbol_allocation(native_elf,name) for name in ('_ZN15RiscDiagnostics11timestampedEPKcz','_ZN8RiscPerf4dataE')}
    proof.update(profile=sec,bounds=BOUNDS,device_profile_sha256=sha(raw),runtime_profile_sha256=sha(source.read_bytes()),diagnostic_allocations=diagnostics,capacity_evidence='source-bound CI build profile; allocated policy/requirement and backend markers',target_instructions_executed=False)
    return proof

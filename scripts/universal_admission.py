"""Complete two-watch cohort admission with the actual compiled native exports.

Older 16/17/24-row admission tools stay unchanged. This helper selects the
source-witnessed 32-row/40-provider profile and reuses their inert I/O fixture.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from check_runtime_store_admission import store_digest,native_symbol_allocation
from universal_native import composition,require
from verify_update_elf import cohort_admission_header
ROOT=Path(__file__).resolve().parents[1]

def compile_harness(runtime,native_elf,native_profile,output,sanitize=False):
    proof=composition(runtime,native_elf,native_profile,32)
    runtime=Path(runtime).resolve();output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    includes=[runtime/p for p in ['src','sdk/app','sdk/driver','sdk/hardware','lib/ArduinoJson/src','test/drivers/stubs','lib/elf_loader/include','test/native_bank_stubs']]+[output.parent]
    sources=[runtime/p for p in ['src/bootstrap/Json.cpp','src/bootstrap/Board.cpp','src/bootstrap/Runtime.cpp','src/runtime/drivers/ProviderGraphV2.cpp','src/runtime/drivers/ProviderModuleV2.cpp','src/ports/esp32s3/CpuPort.cpp','src/runtime/streams/AppStreamSessions.cpp','src/runtime/streams/ProviderQueueHost.cpp']]
    flags=['-D'+k+'='+str(v) for k,v in proof['bounds'].items()]
    flags+=['-DSTORE_ADMISSION_'+s for s in ['APP_DATA','COHORT','CROWN_PROFILE','COLD_BOOT','KV_V2','RUNTIME_FEATURES','RADIO_IQ','IQ_LIFECYCLE','RADIO','HCI','I2S_RX','UPDATE_PLATFORMS']]
    # Diagnostics exist only if linked by the selected native build, not merely
    # because a header was present in an SDK snapshot.
    try:native_symbol_allocation(native_elf,'risc_native_diagnostic_read')
    except ValueError:pass
    else:flags+=['-DSTORE_ADMISSION_DIAGNOSTIC_SOURCE']
    flags+=['-DRISC_PAIRED_APP_DATA=1']
    san=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie'] if sanitize else []
    incs=['-I'+str(p) for p in includes]
    (output.parent/'cohort_elf_admission.h').write_text(cohort_admission_header(runtime,native_elf))
    obj=output.parent/'validate.o'
    subprocess.run(['cc','-std=c11',*san,*incs,'-c',str(runtime/'lib/elf_loader/src/esp_elf_validate.c'),'-o',str(obj)],check=True)
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-Wno-misleading-indentation','-rdynamic',*san,*flags,*incs,*map(str,sources),str(ROOT/'tests/runtime_store_admission.cpp'),str(obj),'-ldl','-o',str(output)],check=True)
    return proof

def admit(harness,active,candidate,expected=True):
    with tempfile.TemporaryDirectory(prefix='universal-store-') as tmp:
        root=Path(tmp)
        for label,store in [('active',active),('candidate',candidate)]:
            for name,data in store.items():
                path=root/label/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        result=subprocess.run([str(harness),str(root/'active'),str(root/'candidate')],capture_output=True,text=True,timeout=90)
        require(result.returncode==0,'Runtime admission process failed: '+result.stderr)
        outcome=json.loads(result.stdout)
        for label,store in [('active',active),('candidate',candidate)]:
            actual={p.relative_to(root/label).as_posix():p.read_bytes() for p in (root/label).rglob('*') if p.is_file()}
            require(actual==store,'Admission altered the supplied store')
    require(outcome['prepared'] and outcome['cohort_validated'] is expected and not outcome['hardware_calls'] and not outcome['storage_calls'],'Runtime rejected cohort: '+str(outcome))
    return dict(outcome,active_store_sha256=store_digest(active),candidate_store_sha256=store_digest(candidate),target_instructions_executed=False)

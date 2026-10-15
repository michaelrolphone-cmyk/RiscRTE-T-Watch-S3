#!/usr/bin/env python3
"""Admit the complete T-Watch store against the exact shared Runtime native ELF."""
import argparse,hashlib,io,json,os,re,struct,subprocess,sys
from pathlib import Path
from watch_app_repair import ROOT,PINS,clean,need,sha,encoded,files,verify_wake
import check_runtime_store_admission as admission
from elftools.elf.elffile import ELFFile

def scheduler_proof(path,compiler):
    native=path.read_bytes();elf=ELFFile(io.BytesIO(native));syms={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
    workers=[s for n,s in syms.items() if 'NativeRadioIq' in n and 'workerRun' in n]
    need(len(workers)==1,'Exact production IQ worker required')
    worker=workers[0];start=worker['st_value'];stop=start+worker['st_size']
    objdump=str(compiler).removesuffix('gcc')+'objdump'
    disassembly=subprocess.check_output([objdump,'-D','-C',f'--start-address={start}',f'--stop-address={stop}',str(path)],text=True)
    targets=[]
    for match in re.finditer(r'l32r\s+a8,\s+([0-9a-f]+)',disassembly):
        address=int(match.group(1),16)
        section=next(s for s in elf.iter_sections() if s['sh_addr']<=address< s['sh_addr']+s['sh_size'])
        targets.append(struct.unpack_from('<I',section.data(),address-section['sh_addr'])[0])
    need(syms['vTaskDelay']['st_value'] in targets and syms['ulTaskGenericNotifyTake']['st_value'] in targets,'Production worker blocking/notify calls absent')
    need(re.search(r'movi(?:\.n)?\s+a10,\s*1\b',disassembly),'Production worker one-tick argument instruction absent')
    return dict(native_elf_sha256=sha(native),worker_address=start,worker_bytes=worker['st_size'],blocking_delay_target_present=True,notification_target_present=True,one_tick_argument_instruction_present=True,disassembly_sha256=sha(disassembly.encode()),scope='Static production-worker target/call evidence; source semantics and timing are covered by the pinned Runtime regression tests, not physical hardware.')

def composition(runtime,native,profile,rows):
    need(rows==32,'Expected 32 app policy rows');clean(runtime,PINS['runtime_revision'])
    need(set(re.findall(rb'RTE_SOURCE=([^\x00\s]+)',native))=={PINS['runtime_revision'].encode()},'Native Runtime identity differs')
    hashes={}
    for name in ('watch-expanded-profile.ini','watch-native-ui.ini'):
        data=(runtime/name).read_bytes();need(data==(ROOT/'native/shared-ui-profile'/name).read_bytes(),'Native profile not product-owned');hashes[name]=sha(data)
    for name in ('platformio.ini','crown-build.ini','crown-wake-profile.ini','watch-file-source-profile.ini','partitions-paired-appdata-expanded.csv'):
        data=(runtime/name).read_bytes();need(data==subprocess.check_output(['git','-C',runtime,'show',PINS['runtime_revision']+':'+name]),'Runtime source changed '+name);hashes[name]=sha(data)
    need(Path(profile)==runtime/'watch-native-ui.ini','Wrong selected native profile')
    for symbol,key in [('risc_app_policy_rows','RISC_APP_POLICY_ROWS'),('risc_app_requirement_rows','RISC_APP_REQUIREMENT_ROWS')]:
        need(admission.native_symbol_bytes(native,symbol)==(key+':32\0').encode(),'Native row marker mismatch')
    for symbol in ('risc_tcp_listener_abi','risc_entropy_abi','risc_file_source_abi'):
        need(admission.native_symbol_bytes(native,symbol)==b'\x01\0\0\0','Native required ABI absent: '+symbol)
    elf=ELFFile(io.BytesIO(native));symbols=elf.get_section_by_name('.symtab');objects={s.name:s['st_size'] for s in symbols.iter_symbols() if s['st_info']['type']=='STT_OBJECT' and s['st_shndx']!='SHN_UNDEF'}
    need(objects.get('_ZN8RiscPerf4dataE')==0xd40,'Expected bounded 64-record/64-counter telemetry')
    from verify_update_elf import verify_native_store_abi
    from watch_app_repair import git
    for name in ('crown-wake-profile.ini','watch-file-source-profile.ini'):
        need(git(runtime,'show',PINS['baseline_runtime']+':'+name)==(runtime/name).read_bytes(),'Released Watch policy changed '+name)
    from importlib.util import spec_from_file_location,module_from_spec
    spec=spec_from_file_location('iq_proof',runtime/'scripts/radio_iq_proof.py');iq=module_from_spec(spec);spec.loader.exec_module(iq)
    radio=iq.prove(native,'esp32s3-16mb-appdata-expanded-iq')
    return dict(profile='watch-native-ui',runtime_commit=PINS['runtime_revision'],bounds={'RISC_INSTALLED_APP_CAPACITY':64,'RISC_PROVIDER_CAPACITY':40,'RISC_APP_POLICY_ROWS':32,'RISC_APP_REQUIREMENT_ROWS':32},store_abi=3,store_size=0x550000,file_source_enabled=True,native_layout=verify_native_store_abi(native,3),source_hashes=hashes,performance_trace_capacity=64,performance_trace_bytes=objects['_ZN8RiscPerf4dataE'],radio_iq=radio,owner_installer=False)

def main():
 p=argparse.ArgumentParser()
 for n in ('runtime','store','baseline-store','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--compiler',type=Path,required=True)
 a=p.parse_args();a.runtime=a.runtime.resolve();a.output.mkdir(parents=True,exist_ok=True)
 native=(a.runtime/'.pio/build/watch-native-ui/firmware.elf').read_bytes()
 active=files(a.baseline_store);store=files(a.store);verify_wake(store)
 need(store['boot.json']==active['boot.json'] and store['default.json']==active['default.json'],'Existing Home wake authority changed')
 admission.native_composition=composition
 result=admission.admit_cohort(a.runtime,native,active,store,app_policy_rows=32,native_profile=a.runtime/'watch-native-ui.ini')
 need(result['elf_count']==59 and result['hardware_calls']==result['storage_calls']==0,'Incomplete or stateful admission')
 result.update(sanitized=os.environ.get('SANITIZE')=='1',producer_sha256=sha(Path(__file__).read_bytes()))
 result['iq_scheduler']=scheduler_proof(a.runtime/'.pio/build/watch-native-ui/firmware.elf',a.compiler)
 (a.output/'admission.json').write_bytes(encoded(result));print(json.dumps(result,indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Exercise the actual released/native-first validators and exact paired bytes."""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path
from check_runtime_store_admission import admit_cohort
from read_only_spiffs import read_image
ROOT=Path(__file__).resolve().parents[1]
BASE='e08609b465d9368d4e6efc45e377adbdbbb706a1'
OLD_SHA='849e57783b25bca4bdb25aa7815867ad06714425f605aefe760d211ea1d21c04'
def sha(data):return hashlib.sha256(data).hexdigest()
def run(*args,**kw):return subprocess.run(list(map(str,args)),check=True,**kw)
def main():
 p=argparse.ArgumentParser()
 for n in ('released-runtime','runtime','released-bin','native-candidate','cohort','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 old=a.released_bin.read_bytes();assert len(old)==0x1000000 and sha(old)==OLD_SHA
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.released_runtime,text=True).strip()==BASE
 candidate=json.loads((a.native_candidate/'candidate.json').read_text());fw=(a.native_candidate/'firmware.bin').read_bytes();elf=(a.native_candidate/'firmware.elf').read_bytes()
 payload=a.cohort.read_bytes();assert payload[:len(fw)]==fw and len(payload)==len(fw)+0x510000
 previous=read_image(old[0x2f0000:0x800000],0x510000);following=read_image(payload[len(fw):],0x510000)
 admission=admit_cohort(a.runtime,elf,previous,following)
 # A current-source check alone cannot establish that released1.0.2 accepts the
 # new dependency/owner policy. The direct old-runtime path must reject it.
 old_rejected=False
 try:admit_cohort(a.released_runtime,(a.native_candidate/'firmware.elf').read_bytes(),previous,following)
 except (ValueError,subprocess.CalledProcessError):old_rejected=True
 assert old_rejected,'SDR must not be advertised as a direct1.0.2 cohort update'
 image=bytearray(old);image[0x9000:0xf000]=b'\xa5'*0x6000;image[0x270000:0x2f0000]=b'\x5a'*0x80000
 initial=out/'released-with-persisted-sentinels.bin';initial.write_bytes(image)
 results=[]
 for stage,runtime,current,kind,input_image,asset in [
   (1,a.released_runtime,'0.1.33','firmware',initial,a.native_candidate/'firmware.bin'),
   (2,a.runtime,'0.1.34','cohort',out/'stage1-success.bin',a.cohort)]:
  build=out/('build-stage'+str(stage));build.mkdir(exist_ok=True)
  (build/'RiscBuildIdentity.h').write_text('#pragma once\n#define RISC_BUILD_VERSION "'+current+'"\n')
  inc=[build,runtime/'test',runtime/'test/native_bank_stubs',runtime/'test/drivers/stubs',runtime/'lib/elf_loader/include',runtime/'src',runtime/'sdk/app',runtime/'sdk/driver',runtime/'sdk/hardware',runtime/'lib/ArduinoJson/src']
  flags=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer'] if os.environ.get('SANITIZE')=='1' else []
  run('cc',*flags,'-std=c11',*['-I'+str(q.resolve()) for q in inc],'-c',runtime/'lib/elf_loader/src/esp_elf_validate.c','-o',build/'validate.o')
  src=[runtime/q for q in ['src/bootstrap/Json.cpp','src/bootstrap/Board.cpp','src/bootstrap/Runtime.cpp','src/runtime/drivers/ProviderGraphV2.cpp','src/runtime/drivers/ProviderModuleV2.cpp','src/runtime/update/PairedBank.cpp','src/runtime/update/StoreAudit.cpp']]
  exe=build/'transaction'
  run('c++',*flags,'-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-Wno-deprecated-declarations','-DRISC_PAIRED_BANKS=1','-DRISC_PAIRED_APP_DATA=1','-rdynamic','-no-pie','-Wl,--wrap=fopen,--wrap=opendir,--wrap=stat,--wrap=lstat',*['-I'+str(q.resolve()) for q in inc],*src,ROOT/'tests/sdr_upgrade/native_transaction.cpp',build/'validate.o','-lcrypto','-ldl','-o',exe)
  for scenario in ['power-begin','power-copy','power-download','cancel','corrupt','power-ready','activation-unknown','rollback','power-selected','success']:
   output=out/f'stage{stage}-{scenario}.bin';proof=output.with_suffix('.json')
   run(exe,input_image,asset,len(fw),kind,scenario,output,proof,timeout=120,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
   if proof.exists():results.append(json.loads(proof.read_text()))
  final=(out/f'stage{stage}-success.bin').read_bytes()
  assert final[0x9000:0xf000]==image[0x9000:0xf000] and final[0x270000:0x2f0000]==image[0x270000:0x2f0000]
 record=dict(schema=1,released_runtime=BASE,released_bin_sha256=sha(old),native_candidate=candidate['source_sha'],native_sha256=sha(fw),cohort_sha256=sha(payload),direct_old_cohort_rejected=old_rejected,staged_graph_admission=admission,transactions=results,physical_flash_tls_spiffs_and_target_instructions_executed=False)
 (out/'upgrade-proof.json').write_text(json.dumps(record,indent=2)+'\n');print('Two-stage source-wired upgrade, persistence, rejection and rollback tests passed')
if __name__=='__main__':main()

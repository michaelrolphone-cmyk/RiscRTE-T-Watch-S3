#!/usr/bin/env python3
"""Package a final pinned T-Watch UI increment locally; never publish or flash."""
import argparse,hashlib,io,json,subprocess,sys,zipfile
from pathlib import Path
from shared_native_ui import PINS,ROOT,clean,encoded,files,need,require_final,sha,verify_baseline,verify_wake
PREFIX='TWatch-1.1.35-Shared-Native-UI'

def make_factory(baseline,firmware,store,runtime,native):
 need(len(baseline)==0x1000000 and sha(baseline)==PINS['baseline_sha256'],'Exact released .33 factory required')
 need(0<len(firmware)<=0x260000 and len(store)==0x550000,'Invalid candidate sizes')
 need(firmware[2:4]==baseline[0x10002:0x10004]==bytes.fromhex('024f'),'Native DIO/80MHz/16MiB profile changed')
 for name,offset in [('bootloader.bin',0),('partitions.bin',0x8000)]:
  data=(native/name).read_bytes();need(baseline[offset:offset+len(data)]==data,'Released bootloader/partition bytes changed: '+name)
 sys.path.insert(0,str(runtime/'scripts'))
 from paired_bank_images import initial_bank_state
 from prepare_preserving_update import layout,pair
 geometry=layout(baseline);need(geometry[0] and geometry[3]==0x550000,'Expected existing ABI3 geometry')
 result=bytearray(baseline);result[0x10000:0x270000]=firmware+b'\xff'*(0x260000-len(firmware));result[0x2f0000:0x840000]=store
 state=initial_bank_state(firmware,store,True,True);result[0xff2000:0xff2000+len(state)]=state
 _,fw,fs=pair(result,0,geometry);need(fw==firmware and fs==store,'Candidate pair mismatch')
 for start,end in ((0,0x10000),(0x270000,0x2f0000),(0x840000,0xff2000),(0xff2000+len(state),0x1000000)):
  need(result[start:end]==baseline[start:end],'Unexpected factory region changed')
 return bytes(result)

def checksums(data):return ''.join(sha(value)+'  '+name+'\n' for name,value in sorted(data.items())).encode()
def archive(path,data):
 data={**data,'SHA256SUMS.txt':checksums(data)}
 with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as out:
  for name,value in sorted(data.items()):
   info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.create_system=3;info.external_attr=0o100644<<16
   out.writestr(info,value,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
 with zipfile.ZipFile(path) as result:
  need(result.testzip() is None,'ZIP CRC failed');need(set(result.namelist())==set(data),'ZIP member set differs')
  for name,value in data.items():need(result.read(name)==value,'ZIP roundtrip differs '+name)

README='''T-Watch 1.1.35 shared native UI preserving update from exact 1.1.33\n\nThis kit never connects to hardware. Do not flash the factory image over an\ninstalled device: it replaces saved data. Preserve NVS, AppData and the SD card.\n\nObtain a fresh full 16 MiB readback using an explicitly authorized device flow.\nRun Python 3: python prepare_preserving_update.py --snapshot DEVICE-READBACK.bin\n --baseline baseline-1.1.33.bin --candidate candidate-1.1.35.bin\n --baseline-sha256 077676642f2a3e938cf6fea497e6322dad198e1c2e98236d9367fb6bb5dcefca\n --output NEW-PLAN-DIRECTORY\n\nThe plan rejects a different active source, partition layout, corrupt readback,\nunconfirmed source or ambiguous OTA selection. Read the generated plan.json.\nStage only its inactive firmware, store and bank-state writes without resetting.\nRead back and verify all three hashes before writing the separate OTA selection\nsector LAST. Verify that sector before resetting. Never erase_flash or write the\nwhole factory image for a preserving update. Failed health confirmation uses the\nexisting bootloader rollback. Source/host tests do not qualify physical hardware.\n'''

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('baseline','baseline-store','runtime','system','target','composition','admission','qualification','preservation','output'):
  p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--source-revision',required=True);a=p.parse_args()
 for name,value in vars(a).items():
  if isinstance(value,Path):setattr(a,name,value.resolve())
 require_final();clean(ROOT,a.source_revision);clean(a.runtime,PINS['runtime_revision']);clean(a.system,PINS['system_revision'])
 need(not a.output.exists(),'Output must be new')
 baseline=a.baseline.read_bytes();before=files(a.baseline_store);verify_baseline(before)
 store_files=files(a.composition/'store');verify_wake(store_files)
 need(set(store_files)==set(before),'Store inventory changed')
 changed=sorted(n for n in before if before[n]!=store_files[n]);need(changed==PINS['changed_store_files'],'Unapproved store delta')
 native=a.runtime/'.pio/build/watch-native-ui';firmware=(native/'firmware.bin').read_bytes();store=(a.composition/'store.bin').read_bytes()
 cohort=json.loads(store_files['cohort.json']);need(cohort['version']==PINS['version'] and cohort['source_revision']==a.source_revision,'Final product source identity differs')
 need(cohort['firmware_sha256']==sha(firmware) and cohort['firmware_size']==len(firmware),'Cohort firmware binding differs')
 target=json.loads((a.target/'build.json').read_text());need(target['source_revision']==PINS['system_revision'] and target['provisional'] is False,'Target not final immutable source')
 need(target['sha256']==sha(store_files['springboard.elf']) and target['imports']==PINS['springboard_imports'] and target['exports']==PINS['springboard_exports'],'Target identity/imports/exports differ')
 composition=json.loads((a.composition/'composition.json').read_text());need(composition['provisional'] is False and composition['store_sha256']==sha(store),'Composition not final')
 from read_only_spiffs import read_image
 need(read_image(store,0x550000)==store_files,'Complete store roundtrip differs')
 admission=json.loads((a.admission/'admission.json').read_text());need(admission['prepared'] and admission['cohort_validated'] and admission['elf_count']==59 and admission['hardware_calls']==admission['storage_calls']==0,'Full no-I/O native admission required')
 need(admission['native_elf_sha256']==sha((native/'firmware.elf').read_bytes()),'Admission ELF differs')
 from check_runtime_store_admission import store_digest
 need(admission['active_store_sha256']==store_digest(before) and admission['candidate_store_sha256']==store_digest(store_files),'Admission store differs')
 qualification=json.loads((a.qualification/'qualification.json').read_text());need(qualification['system_revision']==PINS['system_revision'] and qualification['stage_profile'] is True,'Shared source qualification differs')
 preservation=json.loads((a.preservation/'preservation.json').read_text());need(len(preservation['cases'])==60 and preservation['candidate_native_sha256']==sha(firmware) and preservation['candidate_store_sha256']==sha(store),'Both-bank/torn-write preservation proof differs')
 factory=make_factory(baseline,firmware,store,a.runtime,native)
 a.output.mkdir(parents=True);factory_name=PREFIX+'-factory-erases-data-0x0.bin';(a.output/factory_name).write_bytes(factory)
 helper_names=['prepare_preserving_update.py','paired_bank_images.py','spiffs_image.py']
 kit={name:(a.runtime/'scripts'/name).read_bytes() for name in helper_names}
 for name,data in kit.items():need(data==subprocess.check_output(['git','-C',a.runtime,'show',PINS['runtime_revision']+':scripts/'+name]),'Unpinned update helper')
 kit.update({'baseline-1.1.33.bin':baseline,'candidate-1.1.35.bin':factory,'README.txt':README.encode(),'source-pins.json':encoded(PINS)})
 archive(a.output/(PREFIX+'-Preserving-Update-From-1.1.33.zip'),kit)
 evidence={name:encoded(value) for name,value in [('source-pins.json',PINS),('target.json',target),('composition.json',composition),('admission.json',admission),('qualification.json',qualification),('preservation.json',preservation)]}
 evidence['native-radio-iq-proof.json']=(native/'radio-iq-proof.json').read_bytes()
 archive(a.output/(PREFIX+'-Evidence.zip'),evidence)
 (a.output/'UPDATE-INSTRUCTIONS.txt').write_text(README)
 (a.output/'SHA256SUMS').write_bytes(checksums(files(a.output)))
 print('Final locally packaged artifacts verified. No publication or device access performed.')
if __name__=='__main__':main()

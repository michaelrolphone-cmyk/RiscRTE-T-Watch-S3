#!/usr/bin/env python3
"""Package a final pinned T-Watch UI increment locally; never publish or flash."""
import argparse,hashlib,io,json,subprocess,sys,tempfile,zipfile
from pathlib import Path
from shared_native_ui import PINS,ROOT,clean,encoded,files,need,require_final,sha,verify_baseline,verify_wake
PREFIX='TWatch-1.1.35-Shared-Native-UI'

def verify_store_metadata(before,store,firmware,source_revision):
 manifest=json.loads(before['springboard.json']);manifest['version']=PINS['springboard_manifest_version']
 need(store['springboard.json']==encoded(manifest),'Springboard manifest differs beyond approved version')
 cohort=json.loads(before['cohort.json']);cohort.update(version=PINS['version'],source_revision=source_revision,runtime_version='0.3.3',firmware_sha256=sha(firmware),firmware_size=len(firmware))
 need(store['cohort.json']==encoded(cohort),'Cohort differs beyond approved source/firmware fields')

def verify_native_bin(native):
 import esptool
 need(esptool.__version__=='4.11.0','Exact esptool 4.11.0 required')
 with tempfile.TemporaryDirectory(prefix='watch-native-bin-') as td:
  output=Path(td)/'firmware.bin'
  subprocess.run([sys.executable,'-m','esptool','--chip','esp32s3','elf2image','--flash_mode','dio','--flash_freq','80m','--flash_size','16MB','--elf-sha256-offset','0xb0','-o',str(output),str(native/'firmware.elf')],check=True)
  need(output.read_bytes()==(native/'firmware.bin').read_bytes(),'Native BIN does not match admitted ELF')

def verify_qualification(report,root):
 need(report['system_revision']==PINS['system_revision'] and report['bridge_revision']==PINS['bridge_revision'] and report['stage_profile'] is True,'Shared source qualification differs')
 required={'test_watch_native_springboard.py':108,'test_watch_native_springboard_features.py':72,'test_watch_native_fallback.py':24,'brightness':32,'brightness-sanitized':32,'geometry':7,'geometry-sanitized':7}
 need(set(report['reports'])==set(required),'Incomplete qualification reports')
 for name,count in required.items():
  value=report['reports'][name];rows=value['results'];rows=rows['checks'] if isinstance(rows,dict) else rows
  need(value['cases']==count and len(rows)==count,'Incomplete qualification cases: '+name)
 need(report['reports']['geometry']['results']==report['reports']['geometry-sanitized']['results'],'Sanitized geometry differs')
 names=['test_watch_native_springboard','test_watch_native_springboard_features','test_watch_native_fallback','test_watch_native_input','test_watch_async_canvas','test_watch_canvas_crown_exit','test_navigation_retention_adapter','test_initial_frame_brightness','profile_springboard_full','test_initial_frame_brightness','profile_springboard_full']
 need(set(report['logs_sha256'])=={name+'-'+str(i) for i,name in enumerate(names)},'Incomplete qualification executions')
 for label,digest in report['logs_sha256'].items():need(sha((root/(label+'.log')).read_bytes())==digest,'Qualification log differs: '+label)
 need(report['producer_sha256']==sha((ROOT/'scripts/qualify_shared_native_ui.py').read_bytes()),'Qualification producer differs')

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
 for name in ('baseline','baseline-store','runtime','system','bridges','compiler','target','composition','admission','admission-sanitized','qualification','preservation','output'):
  p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--source-revision',required=True);a=p.parse_args()
 for name,value in vars(a).items():
  if isinstance(value,Path):setattr(a,name,value.resolve())
 require_final();clean(ROOT,a.source_revision);clean(a.runtime,PINS['runtime_revision']);clean(a.system,PINS['system_revision']);clean(a.bridges,PINS['bridge_revision'])
 need(not a.output.exists(),'Output must be new')
 baseline=a.baseline.read_bytes();before=files(a.baseline_store);verify_baseline(before)
 store_files=files(a.composition/'store');verify_wake(store_files)
 need(set(store_files)==set(before),'Store inventory changed')
 changed=sorted(n for n in before if before[n]!=store_files[n]);need(changed==PINS['changed_store_files'],'Unapproved store delta')
 native=a.runtime/'.pio/build/watch-native-ui';firmware=(native/'firmware.bin').read_bytes();store=(a.composition/'store.bin').read_bytes()
 verify_native_bin(native)
 verify_store_metadata(before,store_files,firmware,a.source_revision)
 cohort=json.loads(store_files['cohort.json']);need(cohort['version']==PINS['version'] and cohort['source_revision']==a.source_revision,'Final product source identity differs')
 need(cohort['firmware_sha256']==sha(firmware) and cohort['firmware_size']==len(firmware),'Cohort firmware binding differs')
 target=json.loads((a.target/'build.json').read_text());need(target['source_revision']==PINS['system_revision'] and target['provisional'] is False,'Target not final immutable source')
 need(target['product_source_revision']==a.source_revision and target['bridge_revision']==PINS['bridge_revision'],'Target recipe source differs')
 need(target['compiler_sha256']==sha(a.compiler.read_bytes()),'Target compiler differs')
 need(target['sha256']==sha(store_files['springboard.elf']) and target['imports']==PINS['springboard_imports'] and target['exports']==PINS['springboard_exports'],'Target identity/imports/exports differ')
 with tempfile.TemporaryDirectory(prefix='watch-target-reproduction-') as td:
  rebuilt=Path(td)/'target'
  subprocess.run([sys.executable,str(ROOT/'scripts/shared_native_ui.py'),'build','--system',str(a.system),'--bridges',str(a.bridges),'--compiler',str(a.compiler),'--output',str(rebuilt)],check=True)
  need((rebuilt/'springboard.elf').read_bytes()==store_files['springboard.elf'],'Candidate does not reproduce from exact final source')
 composition=json.loads((a.composition/'composition.json').read_text());need(composition['provisional'] is False and composition['store_sha256']==sha(store),'Composition not final')
 from read_only_spiffs import read_image
 need(read_image(store,0x550000)==store_files,'Complete store roundtrip differs')
 from check_runtime_store_admission import store_digest
 admissions={}
 for label,path in [('normal',a.admission),('sanitized',a.admission_sanitized)]:
  admission=json.loads((path/'admission.json').read_text());need(admission['prepared'] and admission['cohort_validated'] and admission['elf_count']==59 and admission['hardware_calls']==admission['storage_calls']==0,'Full no-I/O native admission required')
  need(admission['sanitized']==(label=='sanitized') and admission['producer_sha256']==sha((ROOT/'scripts/verify_shared_native_ui.py').read_bytes()),'Admission mode/producer differs')
  need(admission['native_elf_sha256']==sha((native/'firmware.elf').read_bytes()),'Admission ELF differs')
  need(admission['active_store_sha256']==store_digest(before) and admission['candidate_store_sha256']==store_digest(store_files),'Admission store differs');admissions[label]=admission
 qualification=json.loads((a.qualification/'qualification.json').read_text());verify_qualification(qualification,a.qualification)
 iq=json.loads((native/'radio-iq-proof.json').read_text())
 need(iq==admissions['normal']['native_composition']['radio_iq']==admissions['sanitized']['native_composition']['radio_iq'],'Native IQ evidence differs from both admissions')
 need(iq['elf_sha256']==sha((native/'firmware.elf').read_bytes()) and iq['target_identity']=='esp32s3-16mb-appdata-expanded-iq','Native IQ source/target differs')
 preservation=json.loads((a.preservation/'preservation.json').read_text());need(len(preservation['cases'])==272 and preservation['candidate_native_sha256']==sha(firmware) and preservation['candidate_store_sha256']==sha(store),'Both-bank/torn-write preservation proof differs')
 with tempfile.TemporaryDirectory(prefix='watch-preservation-reproduction-') as td:
  regenerated=Path(td)/'proof'
  subprocess.run([sys.executable,str(ROOT/'scripts/test_shared_ui_preservation.py'),'--runtime',str(a.runtime),'--baseline',str(a.baseline),'--firmware',str(native/'firmware.bin'),'--store',str(a.composition/'store.bin'),'--output',str(regenerated)],check=True)
  need(json.loads((regenerated/'preservation.json').read_text())==preservation,'Preservation report does not reproduce')
 factory=make_factory(baseline,firmware,store,a.runtime,native)
 a.output.mkdir(parents=True);factory_name=PREFIX+'-factory-erases-data-0x0.bin';(a.output/factory_name).write_bytes(factory)
 helper_names=['prepare_preserving_update.py','paired_bank_images.py','spiffs_image.py']
 kit={name:(a.runtime/'scripts'/name).read_bytes() for name in helper_names}
 for name,data in kit.items():need(data==subprocess.check_output(['git','-C',a.runtime,'show',PINS['runtime_revision']+':scripts/'+name]),'Unpinned update helper')
 kit.update({'baseline-1.1.33.bin':baseline,'candidate-1.1.35.bin':factory,'README.txt':README.encode(),'source-pins.json':encoded(PINS)})
 archive(a.output/(PREFIX+'-Preserving-Update-From-1.1.33.zip'),kit)
 metadata={'version':PINS['version'],'source_revision':a.source_revision,'runtime_revision':PINS['runtime_revision'],'system_revision':PINS['system_revision'],'bridge_revision':PINS['bridge_revision'],'baseline_sha256':sha(baseline),'firmware_sha256':sha(firmware),'native_elf_sha256':sha((native/'firmware.elf').read_bytes()),'store_sha256':sha(store),'factory_sha256':sha(factory),'springboard_sha256':sha(store_files['springboard.elf']),'changed_store_files':changed,'unchanged_store_files':118,'native_bin_reproduced_from_admitted_elf':True,'candidate_reproduced_from_final_source':True,'hardware_tested':False,'device_accessed':False}
 evidence={name:encoded(value) for name,value in [('release.json',metadata),('source-pins.json',PINS),('target.json',target),('composition.json',composition),('admission.json',admissions['normal']),('admission-sanitized.json',admissions['sanitized']),('qualification.json',qualification),('preservation.json',preservation)]}
 evidence.update({name:(native/name).read_bytes() for name in ('firmware.elf','firmware.bin')});evidence['springboard.elf']=store_files['springboard.elf'];evidence['store-SHA256SUMS.txt']=checksums(store_files)
 evidence.update({'qualification-logs/'+label+'.log':(a.qualification/(label+'.log')).read_bytes() for label in qualification['logs_sha256']})
 evidence['native-radio-iq-proof.json']=(native/'radio-iq-proof.json').read_bytes()
 archive(a.output/(PREFIX+'-Evidence.zip'),evidence)
 (a.output/'UPDATE-INSTRUCTIONS.txt').write_text(README)
 (a.output/'release.json').write_bytes(encoded(metadata))
 (a.output/'RELEASE-NOTES.txt').write_text('T-Watch 1.1.35 native-resolution Springboard and shared Runtime repair.\n\nHardware validation is pending. Preserving update kit requires exact installed 1.1.33; read UPDATE-INSTRUCTIONS.txt. The full 16 MiB factory image at offset 0x0 erases saved data.\n\nOnly Springboard ELF/manifest and cohort change in the 121-file, 59-ELF store; all 118 other files and existing Home retained-wake policy are byte-preserved. NVS, AppData, SD data, bootloader and partition layout are preserved by the staged paired-bank update.\n\nShared native UI, fallback and brightness matrices passed at 240x240 and 410x502 with normal/sanitized host checks. Complete-store native admission and 272 both-bank/selector/torn-write preservation fixtures passed. Source tests do not qualify physical hardware.\n\nProduct: '+a.source_revision+'\nRuntime: '+PINS['runtime_revision']+'\nSystem: '+PINS['system_revision']+'\nFactory SHA-256: '+sha(factory)+'\n')
 (a.output/'SHA256SUMS').write_bytes(checksums(files(a.output)))
 print('Final locally packaged artifacts verified. No publication or device access performed.')
if __name__=='__main__':main()

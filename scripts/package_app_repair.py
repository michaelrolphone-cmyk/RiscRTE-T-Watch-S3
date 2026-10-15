#!/usr/bin/env python3
"""Package a qualified official-1.1.36 successor without hardware or publication I/O."""
import argparse,json,re,subprocess,sys,tempfile
from pathlib import Path
from watch_app_repair import ROOT,DOCS,PINS,clean,encoded,files,git,need,require_final,sha,verify_baseline,verify_wake,verify_metadata
from package_shared_native_ui import archive,checksums,verify_native_bin
PREFIX='TWatch-1.1.37-Native-SDR'

def make_factory(baseline,firmware,store,runtime,native):
 need(len(baseline)==0x1000000 and sha(baseline)==PINS['baseline_sha256'],'Exact released .36 factory required')
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

def link_evidence(root,report):
 evidence={}
 for name,app in report['apps'].items():
  history=app['link_attempts'];need(1<=len(history)<=6,'Unbounded compiler attempt history')
  directory=None
  for index,row in enumerate(history,1):
   path=Path(row['log']);folder=path.parent.name
   need(re.fullmatch(re.escape(name)+r'-link-attempts(?:-(?:[2-9]|[1-9][0-9]+))?',folder) is not None,'Unsafe compiler log directory')
   need(path.name==f'attempt-{index:02d}.log' and row['attempt']==index,'Compiler attempt order differs')
   need(directory is None or directory==folder,'Compiler attempt directory differs');directory=folder
   data=(root/folder/path.name).read_bytes();need(sha(data)==row['log_sha256'],'Compiler log hash differs')
   if index==len(history):need(row['returncode']==0 and row['recognized_linker_abort'] is False,'Compiler final attempt did not succeed')
   else:need(row['returncode']!=0 and row['recognized_linker_abort'] is True,'Unrecognized compiler retry')
   evidence[folder+'/'+path.name]=data
  receipt=(root/directory/'receipt.json').read_bytes();saved=json.loads(receipt)
  need(saved['attempts']==history and saved['max_attempts']==6 and isinstance(saved['command'],list) and saved['command'] and all(isinstance(v,str) for v in saved['command']),'Compiler command/history differs')
  evidence[directory+'/receipt.json']=receipt
 return evidence


def verify_replay(root,source,manifest,compiler):
 clean(source,PINS['replay_source_revision'])
 report=json.loads((root/'receipt.json').read_text())
 need(report['product']=='twatch' and report['source_inputs_verified'] is True,'Wrong replay product/source verification')
 need(set(report['apps'])==set(PINS['expected_replayed_apps']),'Incomplete replay')
 need(report['driver_sha256']==sha((source/'scripts/replay_shared_crash_apps.py').read_bytes()),'Replay driver differs')
 need(report['compiler_sha256']==sha(compiler.read_bytes()),'Replay compiler differs')
 spec=source/'docs/shared-app-crashes/replay'
 need(report['spec_sha256']=={n:sha(v) for n,v in files(spec).items()},'Replay specs differ')
 for name,row in report['apps'].items():
  payload=(root/(name+'.elf')).read_bytes();expected=manifest['apps'][name]
  need(row['sha256']==expected['sha256']==sha(payload) and row['bytes']==expected['bytes']==len(payload),'Replay app differs: '+name)
 link_evidence(root,report)
 return report


def release_notes():
 return ('- Renders RF Spectrum and Waterfall plots at the display’s native resolution.\n'
         '- Keeps status text clear of the RF plots.\n')


def instructions():
 return ('T-Watch 1.1.37 native SDR preserving update from exact 1.1.36\n\n'
 'This kit never connects to hardware. The full factory image erases saved data.\n'
 'Obtain a fresh full 16 MiB readback through an explicitly authorized device flow.\n'
 'Run Python 3: python prepare_preserving_update.py --snapshot DEVICE-READBACK.bin\n'
 ' --baseline baseline-1.1.36.bin --candidate candidate-1.1.37.bin\n'
 ' --baseline-sha256 '+PINS['baseline_sha256']+' --output NEW-PLAN-DIRECTORY\n\n'
 'The plan rejects different active firmware/store, layout, corrupt readback,\n'
 'unconfirmed source or ambiguous OTA selection. Read the generated plan.json.\n'
 'Stage only the inactive firmware, store and bank-state writes without resetting.\n'
 'Read back and verify all three hashes, then write the separate OTA selection\n'
 'sector LAST. Verify that sector before resetting. Preserve NVS, AppData, the\n'
 'active pair and SD data if present. Never erase_flash or overwrite the full\n'
 'factory image for a preserving update. Failed health confirmation uses the\n'
 'existing rollback. Non-Plus T-Watch-S3 with BMA423; confirm radio/antenna variant.\n'
 'Source and host tests do not qualify physical hardware.\n')


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('baseline','runtime','composition','admission','admission-sanitized','preservation','renderer','replay','replay-source','compiler','output'):
  p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--source-revision',required=True);a=p.parse_args()
 for name,value in vars(a).items():
  if isinstance(value,Path):setattr(a,name,value.resolve())
 require_final();clean(ROOT,a.source_revision);clean(a.runtime,PINS['runtime_revision']);need(not a.output.exists(),'Output must be new')
 baseline=a.baseline.read_bytes();need(sha(baseline)==PINS['baseline_sha256'],'Wrong official baseline factory')
 from read_only_spiffs import read_image
 before=read_image(baseline[0x2f0000:0x840000],0x550000);verify_baseline(before)
 native=a.runtime/'.pio/build/watch-native-ui';firmware=(native/'firmware.bin').read_bytes();verify_native_bin(native)
 from stage_app_repair_native import NATIVE
 need(sha(firmware)==NATIVE['files']['firmware.bin']['sha256'] and sha((native/'firmware.elf').read_bytes())==NATIVE['files']['firmware.elf']['sha256'],'Published native bytes changed')
 custody=json.loads((native/'native-custody.json').read_text())
 need(custody['native_origin_product_revision']==PINS['baseline_source'] and custody['baseline_native_bytes_preserved'] is True,'Native provenance missing')
 store=(a.composition/'store.bin').read_bytes();store_files=files(a.composition/'store')
 need(read_image(store,0x550000)==store_files,'Complete packed store differs')
 changed=verify_metadata(before,store_files,firmware,a.source_revision);verify_wake(store_files)
 manifest=json.loads((DOCS/'app-manifest.json').read_text());replay=verify_replay(a.replay,a.replay_source,manifest,a.compiler)
 for name in PINS['expected_replayed_apps']:need(store_files[name+'.elf']==(a.replay/(name+'.elf')).read_bytes(),'Packaged app differs from source replay: '+name)
 composition=json.loads((a.composition/'composition.json').read_text())
 need(composition['store_sha256']==sha(store) and composition['native_sha256']==sha(firmware),'Composition identities differ')
 need(composition['packing']['empty_blocks']>=2,'Insufficient existing SPIFFS reserve')
 from check_runtime_store_admission import store_digest
 admissions={}
 for label,path in [('normal',a.admission),('sanitized',a.admission_sanitized)]:
  report=json.loads((path/'admission.json').read_text())
  need(report['prepared'] and report['cohort_validated'] and report['elf_count']==59 and report['hardware_calls']==report['storage_calls']==0,'Complete no-I/O admission required')
  need(report['sanitized']==(label=='sanitized') and report['producer_sha256']==sha((ROOT/'scripts/verify_app_repair_native.py').read_bytes()),'Admission mode/producer differs')
  need(report['native_elf_sha256']==sha((native/'firmware.elf').read_bytes()),'Native admission ELF differs')
  scheduler=report['iq_scheduler']
  need(scheduler['native_elf_sha256']==report['native_elf_sha256'] and all(scheduler[k] is True for k in ('blocking_delay_target_present','notification_target_present','one_tick_argument_instruction_present')),'Production SDR worker target proof absent')
  need(report['active_store_sha256']==store_digest(before) and report['candidate_store_sha256']==store_digest(store_files),'Admission store differs')
  admissions[label]=report
 iq=json.loads((native/'radio-iq-proof.json').read_text())
 need(iq==admissions['normal']['native_composition']['radio_iq']==admissions['sanitized']['native_composition']['radio_iq'],'IQ proof differs')
 proof=json.loads((a.preservation/'preservation.json').read_text())
 need(proof['baseline_version']=='1.1.36' and proof['baseline_sha256']==sha(baseline),'Preservation baseline differs')
 need(len(proof['cases'])==272 and proof['candidate_native_sha256']==sha(firmware) and proof['candidate_store_sha256']==sha(store),'Preservation candidate differs')
 with tempfile.TemporaryDirectory(prefix='watch-repair-preservation-') as td:
  regenerated=Path(td)/'proof'
  subprocess.run([sys.executable,str(ROOT/'scripts/test_app_repair_preservation.py'),'--runtime',str(a.runtime),'--baseline',str(a.baseline),'--firmware',str(native/'firmware.bin'),'--store',str(a.composition/'store.bin'),'--output',str(regenerated)],check=True)
  need(json.loads((regenerated/'preservation.json').read_text())==proof,'Preservation report does not reproduce')
 from qualify_app_repair_renderer import verify as verify_renderer,evidence as renderer_evidence
 renderer=verify_renderer(a.renderer)
 source_renderer=json.loads((DOCS/'source-renderer-qualification.json').read_text())
 factory=make_factory(baseline,firmware,store,a.runtime,native);a.output.mkdir(parents=True)
 factory_name=PREFIX+'-factory-erases-data-0x0.bin';(a.output/factory_name).write_bytes(factory)
 metadata=dict(version=PINS['version'],source_revision=a.source_revision,runtime_revision=PINS['runtime_revision'],runtime_version=PINS['runtime_version'],native_origin_product_revision=PINS['baseline_source'],baseline_native_evidence_sha256=NATIVE['evidence_sha256'],baseline_native_bytes_preserved=True,
               baseline_version=PINS['baseline_version'],baseline_source=PINS['baseline_source'],baseline_sha256=sha(baseline),
               apps_system_revision=PINS['apps_system_revision'],replay_source_revision=PINS['replay_source_revision'],app_manifest_sha256=PINS['app_manifest_sha256'],
               preserved_springboard_system_revision=PINS['preserved_springboard_system_revision'],preserved_springboard_sha256=sha(store_files['springboard.elf']),
               firmware_sha256=sha(firmware),native_elf_sha256=sha((native/'firmware.elf').read_bytes()),store_sha256=sha(store),factory_sha256=sha(factory),
               changed_store_files=changed,unchanged_store_files=121-len(changed),file_count=121,elf_count=59,replayed_apps=len(replay['apps']),replaced_apps=len(PINS['expected_replaced_apps']),sdr_system_revision=PINS['sdr_system_revision'],sdr_utilities_revision=PINS['sdr_utilities_revision'],renderer_checks=renderer['reports'],generic_rf_scene_suite={k:source_renderer['generic_controller'][k] for k in ('passed','total','clean')},twatch_rf_profile_suite={k:source_renderer['product_profiles']['twatch'][k] for k in ('passed','total','remaining_failures')},
               all_replayed_apps_reproduced_from_pinned_sources=True,native_bin_reproduced_from_admitted_elf=True,empty_store_blocks=composition['packing']['empty_blocks'],
               installation_method='preserving-update-from-exact-1.1.36-or-factory-flash',factory_erases_saved_data=True,preserving_update_requires_fresh_full_readback=True,hardware_model='non-Plus T-Watch-S3 with BMA423',radio_antenna_variant_requires_confirmation=True,hardware_tested=False,device_accessed=False)
 (a.output/'release.json').write_bytes(encoded(metadata))
 helpers=('prepare_preserving_update.py','paired_bank_images.py','spiffs_image.py')
 kit={}
 for name in helpers:
  data=(a.runtime/'scripts'/name).read_bytes();need(data==git(a.runtime,'show',PINS['runtime_revision']+':scripts/'+name),'Update helper differs: '+name);kit[name]=data
 kit.update({'baseline-1.1.36.bin':baseline,'candidate-1.1.37.bin':factory,'README.txt':instructions().encode(),'source-pins.json':encoded(PINS)})
 archive(a.output/(PREFIX+'-Preserving-Update-From-1.1.36.zip'),kit)
 evidence={'source-pins.json':encoded(PINS),'app-manifest.json':(DOCS/'app-manifest.json').read_bytes(),'replay.json':encoded(replay),
           'composition.json':encoded(composition),'admission.json':encoded(admissions['normal']),'admission-sanitized.json':encoded(admissions['sanitized']),
           'preservation.json':encoded(proof),'native-radio-iq-proof.json':encoded(iq),'native-custody.json':encoded(custody),'native-baseline.json':(DOCS/'native-baseline.json').read_bytes(),'firmware.bin':firmware,'firmware.elf':(native/'firmware.elf').read_bytes(),
           'springboard.elf':store_files['springboard.elf'],'store-SHA256SUMS.txt':checksums(store_files),'release.json':encoded(metadata)}
 evidence['renderer/renderer.json']=encoded(renderer)
 evidence['renderer/source-qualification.json']=(DOCS/'source-renderer-qualification.json').read_bytes()
 for name,data in renderer_evidence(a.renderer).items():evidence['renderer/'+name]=data
 for name in PINS['expected_replayed_apps']:
  evidence['apps/'+name+'.elf']=store_files[name+'.elf'];evidence['replay-logs/'+name+'.log']=(a.replay/(name+'.log')).read_bytes()
 for name,data in link_evidence(a.replay,replay).items():evidence['replay-logs/'+name]=data
 archive(a.output/(PREFIX+'-Evidence.zip'),evidence)
 notes=release_notes()
 (a.output/'RELEASE-NOTES.txt').write_text(notes);(a.output/'UPDATE-INSTRUCTIONS.txt').write_text(instructions())
 payload=files(a.output);(a.output/'SHA256SUMS').write_bytes(checksums(payload))
 print(json.dumps(metadata,indent=2))


if __name__=='__main__':main()


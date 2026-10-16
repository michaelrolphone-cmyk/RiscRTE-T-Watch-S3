#!/usr/bin/env python3
"""Compose and admit the complete Watch 1.1.18 internal source-Open union.
Inputs remain explicit source-bound components. No upload or flashing occurs.
"""
import argparse,copy,hashlib,json,re,subprocess,sys
from pathlib import Path
from bind_watch_file_source import BASE,GRANT,REQUIREMENT,CHANGED as SOURCE_CHANGED,encoded,sha,require
from current_bootfs import build,read_image
from watch_boot_order_spiffs import build as ordered_build
from check_runtime_store_admission import admit_cohort,native_composition
ROOT=Path(__file__).resolve().parents[1]
BASE_SHA='c33562f158fae21344bfbbfb465cece5a5511616ee1c864555752be8d4fd5946'
BOOTFS=(0x2f0000,0x800000);BANK=(0xff2000,0xff4000);NATIVE=(0x10000,0x2f0000)
RTC_MEMBERS={'settings.elf','settings.json','alarm-service/driver.elf','alarm-service/manifest.json'}
SCANNER_MEMBERS={'ble_scanner.elf','ble_scanner.json'}
CHANGED=SOURCE_CHANGED|RTC_MEMBERS|SCANNER_MEMBERS|{'cohort.json'}
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
def source_union(old,overlay,scanner,rtc):
 new=dict(old)
 require(set(overlay)==SOURCE_CHANGED,'Incomplete source overlay')
 # Merge only the source authority delta into the delivered policy.
 source_boot=json.loads(overlay['boot.json']);boot=json.loads(old['boot.json'])
 expected=copy.deepcopy(boot)
 for app in ['file_browser.json','model_viewer.json']:
  row=next(r for r in expected['app_capabilities'] if r['manifest']==app);row['grants'].append(GRANT)
 require(source_boot==expected,'Source overlay altered unrelated authority')
 for name in SOURCE_CHANGED-{'boot.json'}:new[name]=overlay[name]
 for name in RTC_MEMBERS:new[name]=rtc[name]
 require(set(scanner)==SCANNER_MEMBERS,'Incomplete Scanner overlay')
 before=json.loads(old['ble_scanner.json']);after=json.loads(scanner['ble_scanner.json']);expected_manifest=copy.deepcopy(before)
 expected_manifest['version']='0.2.18';expected_manifest['requires'].append({'capability':'ui.text-input','api':1})
 require(after==expected_manifest,'Scanner manifest changed beyond shared keyboard/version')
 source_row=next(r for r in expected['app_capabilities'] if r['manifest']=='ble_scanner.json');source_row['grants'].append({'capability':'ui.text-input','api':1,'instance_id':0})
 new.update(scanner);new['boot.json']=encoded(expected)
 # The RTC components need no authority change and retain all existing requirements.
 for name,version in [('settings.json','1.3.24'),('alarm-service/manifest.json','0.4.9')]:
  before=json.loads(old[name]);before['version']=version;require(json.loads(new[name])==before,'Unexpected RTC manifest delta: '+name)
 return new

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['baseline-image','runtime','native','source-overlay','scanner-build','rtc-components','output']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--verify-only',action='store_true');a=p.parse_args()
 require(not git(ROOT,'status','--porcelain','--untracked-files=no'),'Dirty product source');revision=git(ROOT,'rev-parse','HEAD')
 previous=a.baseline_image.read_bytes();require(len(previous)==0x1000000 and sha(previous)==BASE_SHA,'Wrong delivered Watch1.1.17 image')
 old=read_image(previous[slice(*BOOTFS)],0x510000);cohort=json.loads(old['cohort.json']);require(cohort['source_revision']==BASE and cohort['version']=='1.1.17','Wrong predecessor cohort')
 require(len(old)==113,'Wrong complete baseline member count')
 overlay={n:(a.source_overlay/n).read_bytes() for n in SOURCE_CHANGED};binding=json.loads((a.source_overlay/'binding-receipt.json').read_text())
 require(binding['overlay_sha256']=={n:sha(overlay[n]) for n in SOURCE_CHANGED},'Source overlay receipt mismatch')
 scanner={n:(a.scanner_build/n).read_bytes() for n in SCANNER_MEMBERS};sr=json.loads((a.scanner_build/'ble_scanner-build-record.json').read_text())
 require(sr['sha256']==sha(scanner['ble_scanner.elf']) and sr['bytes']==len(scanner['ble_scanner.elf']) and sr['manifest_sha256']==sha(scanner['ble_scanner.json']),'Scanner receipt mismatch')
 require(sr['sources']['utilities']=='3385d634db829066e3f7f0d84474df5ed54bf143' and sr['sources']['product-recipe']=='14387b49351eba7539b3e76ea16c99d0b8445e21','Unqualified Scanner source')
 rtc={n:(a.rtc_components/'watch/store'/n).read_bytes() for n in RTC_MEMBERS};rr=json.loads((a.rtc_components/'handoff.json').read_text())
 require(rr['published']['utilities']['commit']=='80efb298c9ca8d0f62f9a31840c9e51d380b40f6' and rr['published']['watch_system']['commit']=='3508092f135d428b5bbccee0546616d046938527','Unqualified RTC source')
 for n,raw in rtc.items():require(rr['artifacts']['watch/store/'+n]['sha256']==sha(raw),'RTC receipt mismatch: '+n)
 new=source_union(old,overlay,scanner,rtc)
 firmware=(a.native/'firmware.bin').read_bytes();native_elf=(a.native/'firmware.elf').read_bytes();require(len(firmware)<NATIVE[1]-NATIVE[0],'Native firmware exceeds partition')
 runtime_head=git(a.runtime,'rev-parse','HEAD');require(set(re.findall(rb'RTE_SOURCE=([^\x00\s]+)',native_elf))=={runtime_head.encode()},'Native source identity mismatch')
 profile=a.runtime/'watch-file-source-profile.ini';require(profile.read_bytes()==(ROOT/'docs/file-source/watch-file-source-profile.ini').read_bytes(),'Native profile differs from product')
 composition=native_composition(a.runtime,native_elf,profile,24)
 versions=set(re.findall(rb'RISC_RUNTIME_VERSION:([^\x00\s]+)',native_elf));require(len(versions)==1,'Missing native version marker')
 cohort.update(version='1.1.18',source_revision=revision,runtime_version=next(iter(versions)).decode(),firmware_size=len(firmware),firmware_sha256=sha(firmware));new['cohort.json']=encoded(cohort)
 require(set(new)==set(old) and {n for n in old if new[n]!=old[n]}==CHANGED,'Unexpected complete-store delta')
 bootfs,packing=ordered_build(new,build);require(packing['empty_blocks']>=2,'Watch store reserve violated')
 sys.path.insert(0,str(a.runtime/'scripts'));from paired_bank_images import initial_bank_state,parse_record
 bank=initial_bank_state(firmware,bootfs,True)
 if not a.verify_only:
  require(not a.output.exists(),'Use new output directory');(a.output/'store').mkdir(parents=True);(a.output/'components').mkdir();(a.output/'receipts').mkdir()
  full=bytearray(previous);full[slice(*NATIVE)]=firmware+b'\xff'*(NATIVE[1]-NATIVE[0]-len(firmware));full[slice(*BOOTFS)]=bootfs;full[slice(*BANK)]=bank
  (a.output/'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin').write_bytes(full)
  for n,raw in new.items():path=a.output/'store'/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
  for n,raw in [('firmware.bin',firmware),('firmware.elf',native_elf),('bootfs.bin',bootfs),('bank_state.bin',bank)]: (a.output/'components'/n).write_bytes(raw)
  for n,record in [('packing',packing),('files-binding',binding),('scanner-build',sr),('rtc-handoff',rr),('native-composition',composition)]: (a.output/'receipts'/(n+'.json')).write_bytes(encoded(record))
 full=(a.output/'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin').read_bytes();require(len(full)==len(previous),'Full image size differs')
 for lo,hi in [(0,NATIVE[0]),(BOOTFS[1],BANK[0]),(BANK[1],0x1000000)]:require(full[lo:hi]==previous[lo:hi],'Preserved partition bytes changed')
 require(full[NATIVE[0]:NATIVE[0]+len(firmware)]==firmware and full[NATIVE[0]+len(firmware):NATIVE[1]]==b'\xff'*(NATIVE[1]-NATIVE[0]-len(firmware)),'Native partition mismatch')
 require(full[slice(*BOOTFS)]==bootfs and read_image(bootfs,0x510000)==new and full[slice(*BANK)]==bank,'Complete image differs from checked components')
 actual={p.relative_to(a.output/'store').as_posix():p.read_bytes() for p in (a.output/'store').rglob('*') if p.is_file()};require(actual==new,'Written store differs')
 rec=parse_record(bank[:96],True);require(rec[3]==len(firmware) and rec[6]==hashlib.sha256(firmware).digest() and rec[7]==hashlib.sha256(bootfs).digest(),'Paired bank digest mismatch')
 admission=admit_cohort(a.runtime,native_elf,old,new,app_policy_rows=24,native_profile=profile);require(admission['prepared'] and admission['cohort_validated'] and admission['elf_count']==55 and admission['hardware_calls']==admission['storage_calls']==0,'Complete candidate admission failed')
 proof={'product':'Watch','version':'1.1.18','product_source':revision,'product_tree':git(ROOT,'rev-parse','HEAD^{tree}'),'runtime_source':runtime_head,'runtime_tree':git(a.runtime,'rev-parse','HEAD^{tree}'),'full_image_sha256':sha(full),'full_image_bytes':len(full),'full_initial_erases_data':True,'changed_store_files':sorted(CHANGED),'preserved_store_files':len(old)-len(CHANGED),'free_spiffs_blocks':packing['empty_blocks'],'existing_app_provider_and_grant_preservation':True,'hardware_verified':False,**admission}
 import os;name='final-sanitized.json' if os.getenv('SANITIZE')=='1' else 'final-normal.json';(a.output/'receipts'/name).write_bytes(encoded(proof));print(json.dumps(proof,indent=2))
if __name__=='__main__':main()

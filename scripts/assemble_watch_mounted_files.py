#!/usr/bin/env python3
"""Compose the existing Watch 1.1.15 image with the qualified mounted Files client."""
import argparse,hashlib,json,os,pathlib,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE='afdab33b66d18d2afc5d9da3abdbcfe90490941a'
BASE_SHA='c96cc199075da214dc17fead513b73570df7a216a32f30cf8e583b6dfc2aedb1'
RUNTIME='267aab6d9382ce4921a1536fab1620749b2f5301'
RUNTIME_TREE='62fe2dfc53169317f91bbc8fadadd9e0bda7e62c'
ELF_SHA='7025c5158323a0b26a62c3608684a3eecdbfd74e42049ba760f57822315307f0'
FIRMWARE_SHA='f9cc819421775cfb9e55a8c7b2c1f2174c9a61b1a85560446cf4f680d14a7726'
# Verified published mounted-browser source; native remains the delivered pair.
FILES_SOURCE='0accd8905b5a64bf5e9269fe92a6e47c9fd1cc90'
FILES_SDK='3b90cd11cf0ff4e8116bb54d2d9eb9c7c67a148b'
FILES_VERSION='1.5.31'
VERSION='1.1.16';IMAGE='WATCH-1.1.16-FULL-INITIAL-ERASES-DATA.bin'
BOOTFS=(0x2f0000,0x800000);BANK=(0xff2000,0xff4000)
PRESERVED=((0,BOOTFS[0]),(BOOTFS[1],BANK[0]),(BANK[1],0x1000000))
CHANGED={'cohort.json','file_browser.json','file_browser.elf'}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def git(p,*args):return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()
def require(ok,message):
 if not ok:raise ValueError(message)
def check_sources(record):
 hashes=record.get("source_sha256",{});require(bool(hashes),"Files build lacks compiled source hashes")
 for name,digest in hashes.items():
  p=pathlib.Path(name);require(p.is_file() and sha(p.read_bytes())==digest,"Compiled Files source changed: "+name)
 return len(hashes)
def changed_store(old,revision,elf,manifest):
 cohort=json.loads(old['cohort.json']);require(cohort['version']=='1.1.15' and cohort['source_revision']==BASE,'Wrong predecessor cohort')
 before=json.loads(old['file_browser.json']);after=json.loads(manifest)
 require(before['version']=='1.5.30' and after==dict(before,version=FILES_VERSION),'Files manifest changed beyond qualified version')
 result=dict(old);cohort.update(version=VERSION,source_revision=revision);result['cohort.json']=encoded(cohort)
 result['file_browser.elf']=elf;result['file_browser.json']=encoded(after)
 return result

def verify(full,previous,old,new,firmware,revision,read_image,parse_record,expected_image,elf,manifest):
 require(len(full)==len(previous)==0x1000000,'Incorrect flash size')
 for begin,end in PRESERVED:require(full[begin:end]==previous[begin:end],'Non-store flash changed')
 require(set(new)==set(old) and {n for n in old if old[n]!=new[n]}==CHANGED,'Unapproved store content change')
 require(new==changed_store(old,revision,elf,manifest),'Unexpected file or cohort change')
 require(read_image(previous[slice(*BOOTFS)],0x510000)==old,'Predecessor decode differs')
 require(read_image(full[slice(*BOOTFS)],0x510000)==new,'Final decode differs')
 require(full[slice(*BOOTFS)]==expected_image,'Incorrect deterministic boot-order layout')
 state=full[slice(*BANK)];record=parse_record(state[:96],True)
 require(record[2]==0 and record[3]==len(firmware) and record[6]==hashlib.sha256(firmware).digest() and record[7]==hashlib.sha256(full[slice(*BOOTFS)]).digest() and state[96:]==b'\xff'*(8192-96),'Incorrect initial bank state or digest')
 return {'full_image_sha256':sha(full),'full_image_bytes':len(full),'preserved_store_files':108,'changed_store_files':sorted(CHANGED),'native_firmware_byte_preserved':True,'other_app_provider_bytes_preserved':True,'boot_policy_and_grants_preserved':True,'unchanged_flash_ranges':[list(x) for x in PRESERVED]}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['baseline-image','runtime','native','files-build','output']:p.add_argument('--'+n,type=pathlib.Path,required=True)
 p.add_argument('--verify-only',action='store_true');p.add_argument('--compose-only',action='store_true');a=p.parse_args()
 require(not git(ROOT,'status','--porcelain','--untracked-files=no'),'Dirty product source');revision=git(ROOT,'rev-parse','HEAD')
 require(git(a.runtime,'rev-parse','HEAD')==RUNTIME and git(a.runtime,'rev-parse','HEAD^{tree}')==RUNTIME_TREE and not git(a.runtime,'status','--porcelain','--untracked-files=no'),'Wrong or dirty Runtime source')
 sys.path[:0]=[str(ROOT/'scripts'),str(a.runtime/'scripts')]
 from current_bootfs import build,read_image
 from watch_boot_order_spiffs import build as ordered_build
 from paired_bank_images import initial_bank_state,parse_record
 from check_runtime_store_admission import admit_cohort
 from compact_current_elf import compact
 previous=a.baseline_image.read_bytes();require(len(previous)==0x1000000 and sha(previous)==BASE_SHA,'Not exact delivered Watch 1.1.15')
 old=read_image(previous[slice(*BOOTFS)],0x510000);require(len(old)==111,'Wrong store file count')
 firmware=(a.native/'firmware.bin').read_bytes();native_elf=(a.native/'firmware.elf').read_bytes()
 require(sha(firmware)==FIRMWARE_SHA and sha(native_elf)==ELF_SHA and previous[0x10000:0x10000+len(firmware)]==firmware,'Native bytes differ from delivered source-qualified pair')
 boot=json.loads(old['boot.json']);require(len(boot['app_capabilities'])==25 and len(boot['drivers'])==30,'Wrong complete boot policy')
 require(json.loads(old['default.json'])['version']=='0.11.5','Clock/wake predecessor changed')
 raw=(a.files_build/'file_browser.elf').read_bytes();manifest=(a.files_build/'file_browser.json').read_bytes();record=json.loads((a.files_build/'file_browser-build-record.json').read_bytes())
 require(record['sources']['system']==FILES_SOURCE and record['sources']['runtime']==FILES_SDK and record['version']==FILES_VERSION and record['bytes']==len(raw) and record['sha256']==sha(raw),'Wrong Files build receipt')
 source_count=check_sources(record)
 row=next(row for row in boot['app_capabilities'] if row['manifest']=='file_browser.json')
 key=lambda x:(x['capability'],x['api'],x['instance_id'])
 require(sorted(record['required_grants'],key=key)==sorted(row['grants'],key=key),'Files authority changed')
 cc=os.environ.get('NATIVE_APP_CC');require(bool(cc),'Set pinned NATIVE_APP_CC')
 with tempfile.TemporaryDirectory(prefix='watch-files-compact-') as tmp:
  elf_path=pathlib.Path(tmp)/'file_browser.elf';elf_path.write_bytes(raw)
  compaction=compact(elf_path,cc,debug_path=pathlib.Path(tmp)/'file_browser.full.elf');elf=elf_path.read_bytes()
 new=changed_store(old,revision,elf,manifest);image,packing=ordered_build(new,build)
 if not a.verify_only:
  require(not a.output.exists(),'Use new output directory')
  result=bytearray(previous);result[slice(*BOOTFS)]=image;result[slice(*BANK)]=initial_bank_state(firmware,image,True)
  a.output.mkdir(parents=True);(a.output/'receipts').mkdir();(a.output/'components').mkdir()
  for name,data in new.items():
   f=a.output/'store'/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
  (a.output/IMAGE).write_bytes(result);(a.output/'components/bootfs.bin').write_bytes(image);(a.output/'components/bank_state.bin').write_bytes(result[slice(*BANK)])
  (a.output/'receipts/packing.json').write_bytes(encoded(packing));(a.output/'receipts/files-build.json').write_bytes(encoded(record));(a.output/'receipts/files-compaction.json').write_bytes(encoded(compaction))
 full=(a.output/IMAGE).read_bytes();proof=verify(full,previous,old,new,firmware,revision,read_image,parse_record,image,elf,manifest)
 require((a.output/'components/bootfs.bin').read_bytes()==full[slice(*BOOTFS)] and (a.output/'components/bank_state.bin').read_bytes()==full[slice(*BANK)],'Component files differ from full image')
 require(json.loads((a.output/'receipts/packing.json').read_bytes())==packing,'Packing receipt differs from deterministic build')
 actual={f.relative_to(a.output/'store').as_posix():f.read_bytes() for f in (a.output/'store').rglob('*') if f.is_file()};require(actual==new,'Written store differs')
 proof.update(product_source=revision,product_version=VERSION,runtime_source=RUNTIME,files_source=FILES_SOURCE,files_version=FILES_VERSION,compiled_source_hashes_verified=source_count,files_compact_sha256=sha(elf),hardware_verified=False,full_initial_erases_data=True)
 if a.compose_only:
  proof['full_admission_pending']=True;(a.output/'receipts/composition.json').write_bytes(encoded(proof));print(json.dumps(proof,indent=2));return
 admission=admit_cohort(a.runtime,native_elf,old,new,app_policy_rows=24,native_profile=a.native/'crown-wake-profile.ini')
 require(admission['prepared'] and admission['cohort_validated'] and admission['elf_count']==54 and admission['hardware_calls']==admission['storage_calls']==0,'Full production admission failed')
 proof.update(admission,product_tree=git(ROOT,'rev-parse','HEAD^{tree}'),baseline_product=BASE,baseline_full_image_sha256=BASE_SHA,sanitizers='ASan+UBSan; LeakSanitizer disabled under ptrace' if os.getenv('SANITIZE')=='1' else 'none')
 name='final-image-admission-sanitizer.json' if os.getenv('SANITIZE')=='1' else 'final-image-admission.json';(a.output/'receipts'/name).write_bytes(encoded(proof));print(json.dumps(proof,indent=2))
if __name__=='__main__':main()

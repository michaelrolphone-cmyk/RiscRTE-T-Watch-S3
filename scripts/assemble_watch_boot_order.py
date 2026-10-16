#!/usr/bin/env python3
"""Watch 1.1.15: packaging-only SPIFFS access-order placement, no device access."""
import argparse,hashlib,json,os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE='b3fd14f78a1100fae5cea2f4b34a7f48b4fa01d9'
BASE_SHA='0a85cc204e53c969af466e5a02f22a2865b4e1ea6efe85d5319c77211b13512d'
RUNTIME='267aab6d9382ce4921a1536fab1620749b2f5301'
RUNTIME_TREE='62fe2dfc53169317f91bbc8fadadd9e0bda7e62c'
ELF_SHA='7025c5158323a0b26a62c3608684a3eecdbfd74e42049ba760f57822315307f0'
FIRMWARE_SHA='f9cc819421775cfb9e55a8c7b2c1f2174c9a61b1a85560446cf4f680d14a7726'
VERSION='1.1.15';IMAGE='WATCH-1.1.15-FULL-INITIAL-ERASES-DATA.bin'
BOOTFS=(0x2f0000,0x800000);BANK=(0xff2000,0xff4000)
PRESERVED=((0,BOOTFS[0]),(BOOTFS[1],BANK[0]),(BANK[1],0x1000000))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def git(p,*args):return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()
def require(ok,message):
 if not ok:raise ValueError(message)
def changed_store(old,revision):
 cohort=json.loads(old['cohort.json']);require(cohort['version']=='1.1.14' and cohort['source_revision']==BASE,'Wrong predecessor cohort')
 result=dict(old);cohort.update(version=VERSION,source_revision=revision);result['cohort.json']=encoded(cohort);return result

def verify(full,previous,old,new,firmware,revision,read_image,parse_record,expected_image):
 require(len(full)==len(previous)==0x1000000,'Incorrect flash size')
 for begin,end in PRESERVED:require(full[begin:end]==previous[begin:end],'Non-store flash changed')
 require(set(new)==set(old) and {n for n in old if old[n]!=new[n]}=={'cohort.json'},'Unapproved store content change')
 require(new==changed_store(old,revision),'Cohort changed beyond product identity')
 require(read_image(previous[slice(*BOOTFS)],0x510000)==old,'Predecessor decode differs')
 require(read_image(full[slice(*BOOTFS)],0x510000)==new,'Final decode differs')
 require(full[slice(*BOOTFS)]==expected_image,'Incorrect deterministic boot-order layout')
 state=full[slice(*BANK)];record=parse_record(state[:96],True)
 require(record[2]==0 and record[3]==len(firmware) and record[6]==hashlib.sha256(firmware).digest() and record[7]==hashlib.sha256(full[slice(*BOOTFS)]).digest() and state[96:]==b'\xff'*(8192-96),'Incorrect initial bank state or digest')
 return {'full_image_sha256':sha(full),'full_image_bytes':len(full),'preserved_store_files':110,'changed_store_files':['cohort.json'],'native_firmware_byte_preserved':True,'all_app_provider_bytes_preserved':True,'boot_policy_and_grants_preserved':True,'unchanged_flash_ranges':[list(x) for x in PRESERVED]}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['baseline-image','runtime','native','output']:p.add_argument('--'+n,type=pathlib.Path,required=True)
 p.add_argument('--verify-only',action='store_true');p.add_argument('--compose-only',action='store_true');a=p.parse_args()
 require(not git(ROOT,'status','--porcelain','--untracked-files=no'),'Dirty product source');revision=git(ROOT,'rev-parse','HEAD')
 require(git(a.runtime,'rev-parse','HEAD')==RUNTIME and git(a.runtime,'rev-parse','HEAD^{tree}')==RUNTIME_TREE and not git(a.runtime,'status','--porcelain','--untracked-files=no'),'Wrong or dirty Runtime source')
 sys.path[:0]=[str(ROOT/'scripts'),str(a.runtime/'scripts')]
 from current_bootfs import build,read_image
 from watch_boot_order_spiffs import build as ordered_build
 from paired_bank_images import initial_bank_state,parse_record
 from check_runtime_store_admission import admit_cohort
 previous=a.baseline_image.read_bytes();require(len(previous)==0x1000000 and sha(previous)==BASE_SHA,'Not exact delivered Watch 1.1.14')
 old=read_image(previous[slice(*BOOTFS)],0x510000);require(len(old)==111,'Wrong store file count');new=changed_store(old,revision)
 firmware=(a.native/'firmware.bin').read_bytes();elf=(a.native/'firmware.elf').read_bytes()
 require(sha(firmware)==FIRMWARE_SHA and sha(elf)==ELF_SHA and previous[0x10000:0x10000+len(firmware)]==firmware,'Native bytes differ from delivered source-qualified pair')
 require(len(json.loads(old['boot.json'])['app_capabilities'])==25 and len(json.loads(old['boot.json'])['drivers'])==30,'Wrong complete boot policy')
 require(json.loads(old['default.json'])['version']=='0.11.5' and json.loads(old['file_browser.json'])['version']=='1.5.30','Wrong predecessor clients')
 image,packing=ordered_build(new,build)
 if not a.verify_only:
  require(not a.output.exists(),'Use new output directory')
  result=bytearray(previous);result[slice(*BOOTFS)]=image;result[slice(*BANK)]=initial_bank_state(firmware,image,True)
  proof=verify(bytes(result),previous,old,new,firmware,revision,read_image,parse_record,image)
  a.output.mkdir(parents=True);(a.output/'receipts').mkdir();(a.output/'components').mkdir()
  for name,raw in new.items():
   f=a.output/'store'/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(raw)
  (a.output/IMAGE).write_bytes(result);(a.output/'components/bootfs.bin').write_bytes(image);(a.output/'components/bank_state.bin').write_bytes(result[slice(*BANK)])
  (a.output/'receipts/packing.json').write_bytes(encoded(packing))
 full=(a.output/IMAGE).read_bytes();proof=verify(full,previous,old,new,firmware,revision,read_image,parse_record,image)
 require((a.output/'components/bootfs.bin').read_bytes()==full[slice(*BOOTFS)] and (a.output/'components/bank_state.bin').read_bytes()==full[slice(*BANK)],'Component files differ from full image')
 require(json.loads((a.output/'receipts/packing.json').read_bytes())==packing,'Packing receipt differs from deterministic build')
 actual={f.relative_to(a.output/'store').as_posix():f.read_bytes() for f in (a.output/'store').rglob('*') if f.is_file()};require(actual==new,'Written store differs')
 if a.compose_only:
  proof.update(product_source=revision,product_version=VERSION,full_admission_pending=True)
  (a.output/'receipts/composition.json').write_bytes(encoded(proof));print(json.dumps(proof,indent=2));return
 admission=admit_cohort(a.runtime,elf,old,new,app_policy_rows=24,native_profile=a.native/'crown-wake-profile.ini')
 require(admission['prepared'] and admission['cohort_validated'] and admission['elf_count']==54 and admission['hardware_calls']==admission['storage_calls']==0,'Full production admission failed')
 proof.update(admission,product_source=revision,product_tree=git(ROOT,'rev-parse','HEAD^{tree}'),product_version=VERSION,baseline_product=BASE,baseline_full_image_sha256=BASE_SHA,runtime_source=RUNTIME,packaging_only=True,hardware_verified=False,full_initial_erases_data=True,sanitizers='ASan+UBSan; LeakSanitizer disabled under ptrace' if os.getenv('SANITIZE')=='1' else 'none')
 name='final-image-admission-sanitizer.json' if os.getenv('SANITIZE')=='1' else 'final-image-admission.json';(a.output/'receipts'/name).write_bytes(encoded(proof));print(json.dumps(proof,indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Reuse the exact published native ELF/BIN with independent source and custody checks."""
import argparse,io,json,subprocess,sys,zipfile
from pathlib import Path
from watch_app_repair import ROOT,PINS,clean,encoded,need,sha
from package_shared_native_ui import verify_native_bin

PIN_PATH=ROOT/'docs/shared-app-repair/native-baseline.json'
NATIVE=json.loads(PIN_PATH.read_text())

def stage(baseline,evidence,runtime):
 clean(runtime,PINS['runtime_revision'])
 need(NATIVE['source_revision']==PINS['baseline_source'],'Native predecessor product differs')
 need(NATIVE['runtime_revision']==PINS['runtime_revision'],'Native Runtime differs')
 need(sha(baseline)==NATIVE['baseline_factory_sha256']==PINS['baseline_sha256'],'Native baseline factory differs')
 need(sha(evidence)==NATIVE['evidence_sha256'],'Published native evidence differs')
 for name,digest in NATIVE['profile_sha256'].items():
  need(sha((ROOT/'native/shared-ui-profile'/name).read_bytes())==digest,'Product native profile differs')
  need(sha((runtime/name).read_bytes())==digest,'Staged native profile differs')
 with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
  need(archive.testzip() is None,'Published evidence ZIP is corrupt')
  payload={name:archive.read(name) for name in NATIVE['files']}
 for name,data in payload.items():
  need(sha(data)==NATIVE['files'][name]['sha256'] and len(data)==NATIVE['files'][name]['bytes'],'Published native artifact differs: '+name)
 original=json.loads(payload['release.json']);source=json.loads(payload['source-pins.json'])
 need(original['source_revision']==NATIVE['source_revision'] and original['runtime_revision']==PINS['runtime_revision'],'Published native source binding differs')
 need(source['runtime_revision']==PINS['runtime_revision'],'Published native source pin differs')
 need(original['native_elf_sha256']==sha(payload['firmware.elf']) and original['firmware_sha256']==sha(payload['firmware.bin']),'Published native hashes differ')
 for name in NATIVE['profile_sha256']:
  old=subprocess.check_output(['git','-C',str(ROOT),'show',NATIVE['source_revision']+':native/shared-ui-profile/'+name])
  need(old==(runtime/name).read_bytes(),'Native profile changed since published build')
 sys.path.insert(0,str(runtime/'scripts'))
 from prepare_preserving_update import layout,pair
 geometry=layout(baseline);_,firmware,_=pair(baseline,0,geometry)
 need(firmware==payload['firmware.bin'],'Published native ELF/BIN differs from baseline factory')
 out=runtime/'.pio/build/watch-native-ui';out.mkdir(parents=True,exist_ok=True)
 staged={'firmware.bin':payload['firmware.bin'],'firmware.elf':payload['firmware.elf'],'radio-iq-proof.json':payload['native-radio-iq-proof.json'],'bootloader.bin':baseline[:0x8000],'partitions.bin':baseline[0x8000:0x9000]}
 for name,data in staged.items():
  target=out/name;need(not target.exists() or target.read_bytes()==data,'Conflicting native artifact: '+name);target.write_bytes(data)
 verify_native_bin(out)
 receipt={'native_origin_product_revision':NATIVE['source_revision'],'runtime_revision':PINS['runtime_revision'],'baseline_evidence_sha256':NATIVE['evidence_sha256'],'baseline_factory_sha256':sha(baseline),'artifacts':{n:{'bytes':len(v),'sha256':sha(v)} for n,v in staged.items()},'profile_sha256':NATIVE['profile_sha256'],'preserved_region_note':'bootloader.bin and partitions.bin contain their complete unchanged factory regions, including padding','native_bin_reproduced_from_admitted_elf':True,'baseline_native_bytes_preserved':True,'hardware_tested':False,'device_accessed':False}
 (out/'native-custody.json').write_bytes(encoded(receipt));return receipt

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for name in ('baseline','evidence','runtime'):parser.add_argument('--'+name,type=Path,required=True)
 a=parser.parse_args();print(json.dumps(stage(a.baseline.read_bytes(),a.evidence.read_bytes(),a.runtime.resolve()),indent=2))
if __name__=='__main__':main()

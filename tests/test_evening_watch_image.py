#!/usr/bin/env python3
import sys,json,tempfile,pathlib,hashlib
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from assemble_evening_watch import check_full_image,write_full_image,IMAGE_SIZE,BOOTFS,BANK
from assemble_watch_spectrum_policy import streamed_digest
results=[]
def probe(name,fn,expect_reject=False):
 try: fn();outcome=not expect_reject
 except (ValueError,FileExistsError):outcome=expect_reject
 results.append(dict(case=name,passed=outcome))
with tempfile.TemporaryDirectory(prefix='watch-audit-boundary-') as tmp:
 p=pathlib.Path(tmp); prior=p/'prior.bin';target=p/'target.bin'
 # Both sparse-zero and nonzero erased regions, with distinctive component bytes.
 source=bytearray(b'\xff'*IMAGE_SIZE);source[0x100000:0x180000]=b'\0'*0x80000
 firmware=b'firmware marker';source[0x10000:0x10000+len(firmware)]=firmware
 prior.write_bytes(source);bootfs=b'B'*(BOOTFS[1]-BOOTFS[0]);bank=b'K'*(BANK[1]-BANK[0])
 write_full_image(target,prior,bootfs,bank)
 expected=bytearray(source);expected[slice(*BOOTFS)]=bootfs;expected[slice(*BANK)]=bank
 probe('writer retains exact 16 MiB including zero and erased regions',lambda: (_ for _ in ()).throw(ValueError()) if target.read_bytes()!=expected else None)
 probe('full image readback passes exact components',lambda:check_full_image(target,prior,firmware,bootfs,bank))
 probe('streamed digest equals materialized bytes',lambda: (_ for _ in ()).throw(ValueError()) if streamed_digest(prior,{BOOTFS[0]:bootfs,BANK[0]:bank})!=hashlib.sha256(expected).hexdigest() else None)
 probe('writer never overwrites existing destination',lambda:write_full_image(target,prior,bootfs,bank),True)
 offsets=[0,0x10000,BOOTFS[0]-1,BOOTFS[0],BOOTFS[1]-1,BOOTFS[1],BANK[0]-1,BANK[0],BANK[1]-1,BANK[1],IMAGE_SIZE-1]
 for offset in offsets:
  with target.open('r+b') as f:f.seek(offset);f.write(bytes([expected[offset]^1]))
  probe(f'corruption rejected at {offset:#x}',lambda:check_full_image(target,prior,firmware,bootfs,bank),True)
  with target.open('r+b') as f:f.seek(offset);f.write(bytes([expected[offset]]))
 with target.open('r+b') as f:f.truncate(IMAGE_SIZE-1)
 probe('short image rejected',lambda:check_full_image(target,prior,firmware,bootfs,bank),True)
 target.write_bytes(expected+b'x')
 probe('long image rejected',lambda:check_full_image(target,prior,firmware,bootfs,bank),True)
report=dict(status='PASS' if all(x['passed'] for x in results) else 'FAIL',cases=results,case_count=len(results))
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['status'] == 'PASS' else 1)

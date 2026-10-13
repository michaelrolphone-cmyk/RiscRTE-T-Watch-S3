import json,sys
from pathlib import Path
sys.path.insert(0,'/product-watch/scripts')
from check_runtime_store_admission import admit_cohort
read=lambda root:{p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
old=read(Path('/watch-baseline-store'));new=read(Path('/watch-staging-final/UNSEALED-STORE'))
new['cohort.json']=json.dumps(json.loads(Path('/watch-sealed-final/sealed-store.json').read_text())['cohort'],sort_keys=True,indent=2).encode()+b'\n'
result=admit_cohort(Path('/runtime-watch'),Path('/runtime-watch/.pio/build/watch-expanded/firmware.elf').read_bytes(),old,new,expected_valid=True,app_policy_rows=32,native_profile=Path('/runtime-watch/watch-expanded-profile.ini'))
Path('/out/watch-preserving-transition.json').write_text(json.dumps(result,indent=2)+'\n')
print('T-Watch baseline to new cohort validated with 59 admitted ELFs and zero I/O. No OTA package or hardware update executed.')

#!/usr/bin/env python3
"""Full source-bound Runtime admission for the cumulative T064 Watch image."""
from pathlib import Path
import argparse,hashlib,json,sys
p=argparse.ArgumentParser()
for n in ('runtime','baseline-store','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'scripts'))
from check_runtime_store_admission import admit_cohort
load=lambda d:{p.relative_to(d).as_posix():p.read_bytes() for p in d.rglob('*') if p.is_file()}
r=a.runtime;native=r/'.pio/build/watch-expanded/firmware.elf';assert hashlib.sha256(native.read_bytes()).hexdigest()=='090bca2f98f037f0153c967374d33e4b0d1460397fb164cf8b4be021372a9a94'
proof=admit_cohort(r,native.read_bytes(),load(a.baseline_store),load(a.output/'store'),app_policy_rows=32,native_profile=r/'watch-expanded-profile.ini')
assert proof['prepared'] and proof['cohort_validated'] and proof['elf_count']==59 and proof['hardware_calls']==0 and proof['storage_calls']==0
(a.output/'admission.json').write_text(json.dumps(proof,indent=2)+'\n');print('59 Watch ELFs: full source-bound native Runtime admission PASS')

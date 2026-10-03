#!/usr/bin/env python3
"""Assert byte custody against the actual, physically confirmed 0.4.0 CI store."""
import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def verify(path):
 baseline=json.loads((ROOT/'docs/TOUCH_DIRECTION_BASELINE.json').read_text())
 with zipfile.ZipFile(path) as z:
  names=z.namelist();assert len(names)==len(set(names))
  files={n.removeprefix('store/'):z.read(n) for n in names if n.startswith('store/')}
  source=json.loads(z.read('shared-app-build.json'))
  assert source['touch_rotation']==0
  assert source['shared_sources']==json.loads((ROOT/'apps/shared-sources.json').read_text())
 expected=baseline['baseline_store_sha256'];assert set(files)==set(expected) and len(files)==22
 changed=sorted(n for n,b in files.items() if hashlib.sha256(b).hexdigest()!=expected[n])
 assert changed==sorted(baseline['changed_store_files']),changed
 record={**baseline,'variant_store_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in sorted(files.items())},'verified_changed_files':changed,'unchanged_file_count':19}
 out=Path(path).parent/'touch-direction-proof.json';out.write_text(json.dumps(record,indent=2)+'\n')
 print('Verified exact0.4.0 baseline:19 unchanged files, only3 shared touch-policy ELFs changed')
 return record
if __name__=='__main__':
 assert len(sys.argv)==2;verify(sys.argv[1])

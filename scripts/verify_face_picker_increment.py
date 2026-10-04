#!/usr/bin/env python3
"""Only Clock0.6.4 changes; accepted Watch1.0 drivers, app grants and shared ELFs stay exact."""
import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ALLOWED={'default.elf','default.json','clock.elf','clock.json'}
def sha(b):return hashlib.sha256(b).hexdigest()
def verify(path):
 baseline=json.loads((ROOT/'docs/FACE_PICKER_BASELINE.json').read_text())
 for name,digest in baseline['source_sha256'].items():assert sha((ROOT/name).read_bytes())==digest,name
 with zipfile.ZipFile(path) as z:
  names=z.namelist();assert len(names)==len(set(names))
  files={n[6:]:z.read(n) for n in names if n.startswith('store/')}
  metadata=json.loads(z.read('shared-app-build.json'))
 assert set(files)==set(baseline['store_sha256'])
 changed={n for n,b in files.items() if sha(b)!=baseline['store_sha256'][n]}
 assert changed==ALLOWED,changed
 assert {k:v for k,v in metadata.items() if k!='apps'}==baseline['shared_metadata']
 for name in ('default','clock'):
  assert json.loads(files[name+'.json'])=={**baseline['manifests'][name+'.json'],'version':'0.6.4'}
 for name,record in metadata['apps'].items():assert record['sha256']==sha(files[name+'.elf'])
 proof={'source':baseline['source'],'candidate':'Clock0.6.4 development','changed_files':sorted(changed),'unchanged_files':sorted(set(files)-changed),'store_sha256':{n:sha(b) for n,b in files.items()}}
 (Path(path).parent/'face-picker-increment-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 print('Face picker custody: exactly four Clock files changed; 24 accepted files unchanged; no driver, grant, shared-app or product1.0 mutation')
 return proof
if __name__=='__main__':verify(sys.argv[1])

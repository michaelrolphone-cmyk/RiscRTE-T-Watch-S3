import json,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from verify_face_picker_increment import verify
class FaceCustody(unittest.TestCase):
 def setUp(self):
  paths=list((ROOT/'dist/launcher-common').glob('*-launcher-common.zip'));self.assertEqual(len(paths),1)
  self.path=paths[0]
  with zipfile.ZipFile(self.path) as z:self.files={n:z.read(n) for n in z.namelist()}
 def test_exact_candidate(self):self.assertEqual(len(verify(self.path)['unchanged_files']),24)
 def reject(self,files):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'bad.zip'
   with zipfile.ZipFile(path,'w') as z:
    for n,b in files.items():z.writestr(n,b)
   with self.assertRaises((AssertionError,KeyError,ValueError)):verify(path)
 def test_every_unchanged_payload_protected(self):
  for n in self.files:
   if n.startswith('store/') and n not in ('store/clock.elf','store/default.elf','store/clock.json','store/default.json'):
    with self.subTest(n=n):files=dict(self.files);files[n]+=b'changed';self.reject(files)
 def test_manifest_versions_and_grants(self):
  for n in ('store/clock.json','store/default.json'):
   for field,value in [('version','0.5.2'),('id','wrong'),('requires',[])]:
    files=dict(self.files);j=json.loads(files[n]);j[field]=value;files[n]=json.dumps(j).encode();self.reject(files)
 def test_unknown_missing_payload_and_hash(self):
  files=dict(self.files);files['store/new.elf']=b'new';self.reject(files)
  files=dict(self.files);del files['store/clock.elf'];self.reject(files)
  files=dict(self.files);files['store/default.elf']+=b'changed';self.reject(files)

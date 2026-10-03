import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_clock_common import build
class CommonLauncher(unittest.TestCase):
 def test_exact_seven_instance_common_store(self):
  paths=sorted((ROOT/'dist/launcher-deployments').glob('*.zip'))
  self.assertEqual(len(paths),8)
  with tempfile.TemporaryDirectory() as tmp:
   row=build(paths,Path(tmp),launcher=True,pr_head_sha='a'*40)
   with zipfile.ZipFile(Path(tmp)/row['archive']) as z:
    record=json.loads(z.read('deployment-record.json'))
    self.assertEqual(record['profile'],'launcher-common')
    self.assertEqual(record['common_launcher']['store_files'],24)
    self.assertEqual(len(record['common_launcher']['inputs']),8)
    self.assertEqual(len([n for n in z.namelist() if n.startswith('store/')]),24)
    self.assertEqual(len(record['drivers']),7)
 def test_different_generation_rejected(self):
  paths=sorted((ROOT/'dist/launcher-deployments').glob('*.zip'))
  with tempfile.TemporaryDirectory() as tmp:
   with zipfile.ZipFile(paths[0]) as z:data={n:z.read(n) for n in z.namelist()}
   record=json.loads(data['deployment-record.json']);record['source_sha']='b'*40
   data['deployment-record.json']=json.dumps(record).encode()
   altered=Path(tmp)/paths[0].name
   with zipfile.ZipFile(altered,'w') as z:
    for n,b in data.items():z.writestr(n,b)
   with self.assertRaisesRegex(ValueError,'provenance differs'):
    build([altered,*paths[1:]],Path(tmp)/'out',launcher=True)

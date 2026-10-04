import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from verify_alarm_deployment import verify
class AlarmAuthority(unittest.TestCase):
 def setUp(self):
  paths=list((ROOT/'dist/alarm-launcher-deployments').glob('*sx1262-915-bma423.zip'));self.assertEqual(len(paths),1)
  self.path=paths[0]
  with zipfile.ZipFile(self.path) as z:self.files={n:z.read(n) for n in z.namelist()}
 def reject(self,name,edit):
  files=dict(self.files);value=json.loads(files[name]);edit(value);files[name]=(json.dumps(value,indent=2)+'\n').encode()
  # Recompute generic custody: policy tests must catch semantic drift even
  # when an incorrect package producer updates all ordinary checksums.
  record=json.loads(files['deployment-record.json'])
  for e in record['entries']:
   data=files[e['path']];e['size_bytes']=len(data);e['sha256']=hashlib.sha256(data).hexdigest()
  files['deployment-record.json']=json.dumps(record).encode()
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'bad.zip'
   with zipfile.ZipFile(path,'w') as z:
    for n,data in files.items():z.writestr(n,data)
   with self.assertRaises((AssertionError,ValueError,KeyError,StopIteration)):verify(path)
 def test_exact_nine_app_five_key_candidate(self):self.assertEqual(verify(self.path)['app_version'],'0.6.1')
 def test_app_authority_is_exact(self):
  self.reject('store/boot.json',lambda d:d['app_capabilities'][0]['grants'].append({'capability':'audio.output','api':1,'instance_id':12}))
  self.reject('store/boot.json',lambda d:d['app_capabilities'][0]['grants'][-2].update(instance_id=4))
  self.reject('store/boot.json',lambda d:d['app_capabilities'].pop())
 def test_provider_mapping_is_exact(self):
  self.reject('store/boot.json',lambda d:d['drivers'][-1]['key_value'][0].update(access='read-write'))
  self.reject('store/boot.json',lambda d:d['drivers'][-1]['key_value'][2].update(namespace=3))
  self.reject('store/boot.json',lambda d:d['drivers'][-1].update(instance_id=99))
 def test_versions_pins_and_physical_closure(self):
  self.reject('store/default.json',lambda d:d.update(version='0.6.0'))
  self.reject('store/pmu/manifest.json',lambda d:d.update(version='0.5.1'))
  self.reject('runtime-requirements.json',lambda d:d.update(source_sha='0'*40))
  self.reject('store/board.json',lambda d:next(x for x in d['devices'] if x['instance_id']==4)['config']['rails'].append({'id':3,'millivolts':3300}))

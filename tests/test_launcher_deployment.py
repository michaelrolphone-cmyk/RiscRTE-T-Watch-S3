import copy,hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from verify_clock_deployment import verify
class Launcher(unittest.TestCase):
 def test_all_profiles(self):
  paths=list((ROOT/'dist/launcher-deployments').glob('*.zip'));self.assertEqual(len(paths),8)
  for path in paths:
   r=verify(path);self.assertEqual(len(r['drivers']),7)
   with zipfile.ZipFile(path) as z:
    self.assertEqual(len([n for n in z.namelist() if n.startswith('store/')]),28)
    boot=json.loads(z.read('store/boot.json'));self.assertEqual(boot['default_app'],'default.elf')
    i2c=[d for d in boot['drivers'] if d['instance_id'] in (2,3)]
    self.assertEqual(len(i2c),2)
    self.assertEqual(i2c[0]['manifest'],i2c[1]['manifest'])
    self.assertNotEqual(i2c[0]['instance_id'],i2c[1]['instance_id'])
    sources=json.loads(z.read('shared-app-build.json'))
    self.assertEqual(sources['shared_sources'],json.loads((ROOT/'apps/shared-sources.json').read_text()))
    board=json.loads(z.read('store/board.json'))
    self.assertEqual({b['instance_id'] for b in board['buses']},{101,102,103})
    self.assertEqual([d['id'] for d in r['drivers']].count('twatch-i2c'),2)
 def test_grant_and_binding_mutations(self):
  path=next((ROOT/'dist/launcher-deployments').glob('*.zip'))
  with zipfile.ZipFile(path) as z:original={n:z.read(n) for n in z.namelist()}
  for field in ('store/boot.json','store/board.json','store/battery.json','settings-time-policy.json','shared/catalog.json'):
   data=dict(original);obj=json.loads(data[field])
   if field=='store/boot.json':obj['app_capabilities'][1]['grants'].append({'capability':'board.battery','api':1,'instance_id':4})
   elif field=='store/board.json':next(d for d in obj['devices'] if d['instance_id']==6)['bindings']['i2c.bus']=2
   elif field=='settings-time-policy.json':obj['fold']='guess'
   elif field=='shared/catalog.json':obj[0]['file_name']='unknown.elf'
   else:obj['requires'].append({'capability':'rtc.clock','api':2})
   data[field]=json.dumps(obj).encode();record=json.loads(data['deployment-record.json'])
   e=next(e for e in record['entries'] if e['path']==field);e.update(size_bytes=len(data[field]),sha256=hashlib.sha256(data[field]).hexdigest())
   data['deployment-record.json']=json.dumps(record).encode()
   with tempfile.TemporaryDirectory() as tmp:
    bad=Path(tmp)/'bad.zip'
    with zipfile.ZipFile(bad,'w') as z:
     for name,body in data.items():z.writestr(name,body)
    with self.assertRaises((ValueError,AssertionError)):verify(bad)

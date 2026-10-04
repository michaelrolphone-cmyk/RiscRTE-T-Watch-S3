import copy,hashlib,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import verify_daily_increment as custody
class DailyCustody(unittest.TestCase):
 def setUp(self):
  paths=list((ROOT/'dist/launcher-common').glob('*-launcher-common.zip'));self.assertEqual(len(paths),1)
  with zipfile.ZipFile(paths[0]) as z:self.files={n:z.read(n) for n in z.namelist()}
  self.baseline=json.loads((ROOT/'docs/DAILY_APPS_BASELINE.json').read_text())
  # Optional local GCC14 smoke fixture only. CI never sets this: production
  # custody and the assembler always require the committed delivered GCC8 hash.
  control=os.environ.get('DAILY_TEST_CONTROL_STORE')
  if control:
   root=Path(control);files={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
   self.assertEqual(set(files),set(self.baseline['baseline_store_sha256']))
   self.baseline['baseline_store_sha256']={n:hashlib.sha256(b).hexdigest() for n,b in files.items()}
 def check(self,files,succeeds=False):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'docs').mkdir();(root/'docs/DAILY_APPS_BASELINE.json').write_text(json.dumps(self.baseline))
   for relative in self.baseline['unchanged_source_sha256']:
    path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.symlink_to(ROOT/relative)
   source=root/'apps/shared-sources.json';source.symlink_to(ROOT/'apps/shared-sources.json')
   path=root/'candidate.zip'
   with zipfile.ZipFile(path,'w') as z:
    for name,data in files.items():z.writestr(name,data)
   with patch.object(custody,'ROOT',root):
    if succeeds:self.assertEqual(custody.verify(path)['unchanged_file_count'],19)
    else:
     with self.assertRaises((AssertionError,KeyError,ValueError)):custody.verify(path)
 def change_json(self,name,change):
  files=dict(self.files);value=json.loads(files[name]);change(value);files[name]=json.dumps(value).encode();self.check(files)
 def test_exact_candidate(self):self.check(self.files,True)
 def test_every_retained_file_is_protected(self):
  for name in set(self.baseline['baseline_store_sha256'])-set(self.baseline['changed_store_files']):
   with self.subTest(name=name):
    files=dict(self.files);files['store/'+name]+=b'changed';self.check(files)
 def test_added_or_missing_file_rejected(self):
  for name in ('clock.elf','calculator.elf','stopwatch.json'):
   files=dict(self.files);files.pop('store/'+name);self.check(files)
  files=dict(self.files);files['store/unknown.elf']=b'bad';self.check(files)
 def test_app_binary_mismatch_rejected(self):
  for name in ('calculator','stopwatch','springboard'):
   files=dict(self.files);files['store/'+name+'.elf']+=b'changed';self.check(files)
 def test_old_manifest_semantic_change_rejected(self):
  self.change_json('store/default.json',lambda x:x.update(id='other'))
  self.change_json('store/clock.json',lambda x:x.update(version='0.5.2'))
  self.change_json('store/springboard.json',lambda x:x.update(version='1.3.7'))
 def test_new_manifest_semantic_change_rejected(self):
  self.change_json('store/calculator.json',lambda x:x.update(version='0.2.0'))
  self.change_json('store/stopwatch.json',lambda x:x['requires'].pop())
  for name in ('calculator','stopwatch'):
   for field,value in [('type','driver'),('architecture','x86_64'),('entry','wrong_entry'),('extra_field',True)]:
    self.change_json('store/'+name+'.json',lambda x:x.update({field:value}))
 def test_board_remapping_and_old_grants_rejected(self):
  self.change_json('store/boot.json',lambda x:x['drivers'][0].update(manifest='pmu/manifest.json'))
  self.change_json('store/boot.json',lambda x:x['app_capabilities'][2]['grants'].append({'capability':'storage.key-value','api':1,'instance_id':2}))
 def test_namespace_collision_rejected(self):
  def change(x):
   for grant in x['app_capabilities'][6]['grants']:
    if grant['capability']=='storage.key-value':grant['instance_id']=1
  self.change_json('store/boot.json',change)
 def test_precision_sleep_return_and_transport_rejected(self):
  self.change_json('shared-app-build.json',lambda x:x.update(full_frames=False))
  self.change_json('shared-app-build.json',lambda x:x['sleep_policy'].update(ulp_program=True))
  self.change_json('shared-app-build.json',lambda x:x['daily_apps']['stopwatch'].update(precision='subsecond-after-recovery'))
  self.change_json('shared-app-build.json',lambda x:x['return_targets'].update(calculator='default.elf'))
if __name__=='__main__':unittest.main()

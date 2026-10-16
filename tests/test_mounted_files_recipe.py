import copy,importlib.util,json,pathlib,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mounted',ROOT/'scripts/assemble_watch_mounted_files.py');recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
class RecipeTest(unittest.TestCase):
 def setUp(self):
  self.old={'cohort.json':recipe.encoded({'version':'1.1.15','source_revision':recipe.BASE,'firmware_sha256':'preserved'}),'file_browser.json':recipe.encoded({'id':'file_browser','version':'1.5.30','requires':[{'api':1,'capability':'file.open'}]}),'file_browser.elf':b'old-files','default.elf':b'current-clock','springboard.elf':b'current-scrolling','boot.json':b'exact policy','drivers.bin':b'exact providers'}
  self.manifest=recipe.encoded(dict(json.loads(self.old['file_browser.json']),version='1.5.31'))
 def test_only_three_files_change(self):
  new=recipe.changed_store(self.old,'product',b'new-files',self.manifest)
  self.assertEqual({p for p in self.old if new[p]!=self.old[p]},recipe.CHANGED)
  self.assertEqual(json.loads(new['cohort.json']),{'version':'1.1.16','source_revision':'product','firmware_sha256':'preserved'})
  self.assertEqual(self.old['default.elf'],new['default.elf'])
 def test_wrong_predecessor_version(self):
  old=copy.deepcopy(self.old);r=json.loads(old['cohort.json']);r['version']='1.1.14';old['cohort.json']=recipe.encoded(r)
  with self.assertRaises(ValueError):recipe.changed_store(old,'p',b'f',self.manifest)
 def test_wrong_predecessor_source(self):
  old=copy.deepcopy(self.old);r=json.loads(old['cohort.json']);r['source_revision']='other';old['cohort.json']=recipe.encoded(r)
  with self.assertRaises(ValueError):recipe.changed_store(old,'p',b'f',self.manifest)
 def test_new_authority_rejected(self):
  m=json.loads(self.manifest);m['requires'].append({'api':1,'capability':'extra'})
  with self.assertRaises(ValueError):recipe.changed_store(self.old,'p',b'f',recipe.encoded(m))
 def test_removed_feature_rejected(self):
  m=json.loads(self.manifest);m['requires']=[]
  with self.assertRaises(ValueError):recipe.changed_store(self.old,'p',b'f',recipe.encoded(m))
 def test_wrong_files_version(self):
  m=json.loads(self.manifest);m['version']='1.5.30'
  with self.assertRaises(ValueError):recipe.changed_store(self.old,'p',b'f',recipe.encoded(m))
 def test_compiled_sources_checked(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'source.c';p.write_bytes(b'compiled bytes');r={'source_sha256':{str(p):recipe.sha(p.read_bytes())}}
   self.assertEqual(recipe.check_sources(r),1);p.write_bytes(b'changed source')
   with self.assertRaises(ValueError):recipe.check_sources(r)
 def test_source_receipt_required(self):
  with self.assertRaises(ValueError):recipe.check_sources({})
if __name__=='__main__':unittest.main()

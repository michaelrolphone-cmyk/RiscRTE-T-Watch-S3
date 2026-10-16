import copy,importlib.util,json,pathlib,unittest
p=pathlib.Path(__file__).resolve().parents[1]/'scripts/bind_watch_file_source.py';spec=importlib.util.spec_from_file_location('binding',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class BindingTest(unittest.TestCase):
 def setUp(self):
  self.old={'boot.json':m.encoded({'drivers':[{'manifest':'shared-keyboard/manifest.json'}],'app_capabilities':[{'manifest':a+'.json','grants':[{'capability':'original','api':1,'instance_id':7}]} for a in ['file_browser','model_viewer','other']]}),'file_browser.elf':b'files-old','model_viewer.elf':b'viewer-old','other.elf':b'unchanged','cohort.json':b'unchanged'}
  for a in ['file_browser','model_viewer']:self.old[a+'.json']=m.encoded({'id':a,'version':'old','requires':[{'capability':'original','api':1}],**({'supported_file_types':['.obj','.stl']} if a=='model_viewer' else {})})
  self.man=[]
  for a,v in [('file_browser','1.5.33'),('model_viewer','1.3.1')]:
   r=json.loads(self.old[a+'.json']);r['version']=v;r['requires'].append(m.REQUIREMENT);self.man.append(m.encoded(r))
 def change(self):return m.changed_store(self.old,b'new-files',self.man[0],b'new-viewer',self.man[1])
 def test_exact_addition(self):
  new=self.change();self.assertEqual({n for n in self.old if self.old[n]!=new[n]},m.CHANGED);before=json.loads(self.old['boot.json']);after=json.loads(new['boot.json']);self.assertEqual(before['drivers'],after['drivers']);self.assertEqual(before['app_capabilities'][2],after['app_capabilities'][2]);self.assertEqual(after['app_capabilities'][0]['grants'],before['app_capabilities'][0]['grants']+[m.GRANT])
 def test_reject_removed_handler(self):
  r=json.loads(self.man[1]);r['supported_file_types']=['.obj'];self.man[1]=m.encoded(r)
  with self.assertRaisesRegex(ValueError,'App changed'):self.change()
 def test_reject_removed_requirement(self):
  r=json.loads(self.man[0]);r['requires']=[m.REQUIREMENT];self.man[0]=m.encoded(r)
  with self.assertRaisesRegex(ValueError,'App changed'):self.change()
 def test_reject_duplicate_grant(self):
  r=json.loads(self.old['boot.json']);r['app_capabilities'][0]['grants'].append(m.GRANT);self.old['boot.json']=m.encoded(r)
  with self.assertRaisesRegex(ValueError,'already present'):self.change()
 def test_required_native_flags(self):
  text=(p.parents[1]/'docs/file-source/watch-file-source-profile.ini').read_text()
  for flag in m.FLAGS:self.assertIn(flag,text)
if __name__=='__main__':unittest.main()

import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import assemble_watch_contexts_input_lifecycle as a
import build_contexts_input_lifecycle as b

class RecipeTest(unittest.TestCase):
 def prior(self):
  return {'contexts.elf':b'old','contexts.json':a.encoded({'version':'0.4.3','requires':[{'capability':'ui.text-input','api':1},{'capability':'radio.iq','api':1}]}),
   'default.elf':b'preserved-clock','lists.elf':b'preserved-lists','audio_spectrum.elf':b'preserved-spectrum','text-input/driver.elf':b'preserved-text','ui-scene/driver.elf':b'preserved-scene',
   'boot.json':b' { "app_capabilities": [{"manifest":"contexts.json","grants":[{"capability":"ui.text-input","api":1,"instance_id":0}]}], "drivers": [] }\n',
   'cohort.json':a.encoded({'version':'1.1.18','source_revision':a.BASE})}
 def component(self,old):
  return {'contexts.elf':b'new','contexts.json':a.encoded(dict(json.loads(old['contexts.json']),version=b.VERSION))}
 def test_exact_delta_and_inherited_bytes(self):
  old=self.prior();frozen=copy.deepcopy(old);new=a.payload(old,self.component(old),'new')
  self.assertEqual(old,frozen);self.assertEqual({n for n in new if old[n]!=new[n]},a.CHANGED)
  for n in set(old)-a.CHANGED:self.assertEqual(old[n],new[n],n)
 def test_boot_bytes_are_identical(self):
  old=self.prior();new=a.payload(old,self.component(old),'new');self.assertEqual(new['boot.json'],old['boot.json'])
 def test_manifest_delta_only_version(self):
  old=self.prior();new=a.payload(old,self.component(old),'new');self.assertEqual(json.loads(new['contexts.json']),dict(json.loads(old['contexts.json']),version='0.4.4'))
 def test_excess_authority_rejected(self):
  old=self.prior();c=self.component(old);m=json.loads(c['contexts.json']);m['requires'].append({'capability':'net.http','api':1});c['contexts.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_removed_authority_rejected(self):
  old=self.prior();c=self.component(old);m=json.loads(c['contexts.json']);m['requires'].pop();c['contexts.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_wrong_baseline_rejected(self):
  old=self.prior();old['cohort.json']=a.encoded({'version':'1.1.18','source_revision':'other'})
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_wrong_previous_version_rejected(self):
  old=self.prior();m=json.loads(old['contexts.json']);m['version']='0.4.2';old['contexts.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_duplicate_inherited_grant_rejected(self):
  old=self.prior();m=json.loads(old['boot.json']);m['app_capabilities'][0]['grants'].append(a.GRANT);old['boot.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_only_original_optin_flag(self):self.assertEqual(b.ADDITIONS,['-DPORTABLE_CONTEXTS_SHARED_TEXT_INPUT'])
 def test_unselected_sources_block_build(self):
  before=b.SELECTION['finalized'];b.SELECTION['finalized']=False
  try:
   with self.assertRaisesRegex(ValueError,'Final published'):b.build(None)
  finally:b.SELECTION['finalized']=before
if __name__=='__main__':unittest.main()

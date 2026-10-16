import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import assemble_watch_timecard_policy as a
import build_timecard_policy as b

class RecipeTest(unittest.TestCase):
 def prior(self):
  return {'board.json':b'{ \"board_id\": \"watch\", \"buses\": [{\"pins\": [1, 2, 3]}] }\n','timecard.elf':b'old','timecard.json':a.encoded({'version':'0.2.13','requires':[{'capability':'ui.text-input','api':1},{'capability':'radio.iq','api':1}]}),
   'default.elf':b'preserved-clock','lists.elf':b'preserved-lists','audio_spectrum.elf':b'preserved-spectrum','text-input/driver.elf':b'preserved-text','ui-scene/driver.elf':b'preserved-scene',
   'boot.json':b' { "app_capabilities": [{"manifest":"timecard.json","grants":[{"capability":"ui.text-input","api":1,"instance_id":0}]}], "drivers": [] }\n',
   'cohort.json':a.encoded({'version':'1.1.18','source_revision':a.BASE})}
 def component(self,old):
  return {'timecard.elf':b'new','timecard.json':a.encoded(dict(json.loads(old['timecard.json']),version=b.VERSION))}
 def test_exact_delta_and_inherited_bytes(self):
  old=self.prior();frozen=copy.deepcopy(old);new=a.payload(old,self.component(old),'new')
  self.assertEqual(old,frozen);self.assertEqual({n for n in new if old[n]!=new[n]},a.CHANGED)
  for n in set(old)-a.CHANGED:self.assertEqual(old[n],new[n],n)
 def test_boot_bytes_are_identical(self):
  old=self.prior();new=a.payload(old,self.component(old),'new');self.assertEqual(new['boot.json'],old['boot.json'])
 def test_manifest_delta_only_version(self):
  old=self.prior();new=a.payload(old,self.component(old),'new');self.assertEqual(json.loads(new['timecard.json']),dict(json.loads(old['timecard.json']),version='0.2.14'))
 def test_excess_authority_rejected(self):
  old=self.prior();c=self.component(old);m=json.loads(c['timecard.json']);m['requires'].append({'capability':'net.http','api':1});c['timecard.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_removed_authority_rejected(self):
  old=self.prior();c=self.component(old);m=json.loads(c['timecard.json']);m['requires'].pop();c['timecard.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_wrong_baseline_rejected(self):
  old=self.prior();old['cohort.json']=a.encoded({'version':'1.1.18','source_revision':'other'})
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_wrong_previous_version_rejected(self):
  old=self.prior();m=json.loads(old['timecard.json']);m['version']='0.2.12';old['timecard.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_duplicate_inherited_grant_rejected(self):
  old=self.prior();m=json.loads(old['boot.json']);m['app_capabilities'][0]['grants'].append(a.GRANT);old['boot.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_board_compaction_preserves_configuration(self):
  old=self.prior();new=a.payload(old,self.component(old),'new');self.assertEqual(json.loads(old['board.json']),json.loads(new['board.json']));self.assertLess(len(new['board.json']),len(old['board.json']))
 def test_policy_optin_is_explicit(self):self.assertIn('-DPORTABLE_TEXT_INPUT_POLICY',b.COMMON)
if __name__=='__main__':unittest.main()

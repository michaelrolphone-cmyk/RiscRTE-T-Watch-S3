import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import assemble_watch_rf_policy as a
import build_rf_policy as b

class RecipeTest(unittest.TestCase):
 def prior(self):
  return {'board.json':b'{ \"board_id\": \"watch\", \"buses\": [{\"pins\": [1, 2, 3]}] }\n','waterfall.elf':b'old','waterfall.json':a.encoded({'version':'0.3.4','requires':[{'capability':'ui.text-input','api':1},{'capability':'radio.iq','api':1}]}),
   'default.elf':b'preserved-clock','lists.elf':b'preserved-lists','audio_spectrum.elf':b'preserved-spectrum','text-input/driver.elf':b'preserved-text','ui-scene/driver.elf':b'preserved-scene',
   'boot.json':b' { "app_capabilities": [{"manifest":"waterfall.json","grants":[{"capability":"ui.text-input","api":1,"instance_id":0}]}], "drivers": [] }\n',
   'cohort.json':a.encoded({'version':'1.1.18','source_revision':a.BASE})}
 def component(self,old):
  return {'waterfall.elf':b'new','waterfall.json':a.encoded(dict(json.loads(old['waterfall.json']),version=b.VERSION))}
 def test_exact_delta_and_inherited_bytes(self):
  old=self.prior();frozen=copy.deepcopy(old);new=a.payload(old,self.component(old),'new')
  self.assertEqual(old,frozen);self.assertEqual({n for n in new if old[n]!=new[n]},a.CHANGED)
  for n in set(old)-a.CHANGED:self.assertEqual(old[n],new[n],n)
 def test_boot_bytes_are_identical(self):
  old=self.prior();new=a.payload(old,self.component(old),'new');self.assertEqual(new['boot.json'],old['boot.json'])
 def test_manifest_delta_only_version(self):
  old=self.prior();new=a.payload(old,self.component(old),'new');self.assertEqual(json.loads(new['waterfall.json']),dict(json.loads(old['waterfall.json']),version='0.3.5'))
 def test_excess_authority_rejected(self):
  old=self.prior();c=self.component(old);m=json.loads(c['waterfall.json']);m['requires'].append({'capability':'net.http','api':1});c['waterfall.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_removed_authority_rejected(self):
  old=self.prior();c=self.component(old);m=json.loads(c['waterfall.json']);m['requires'].pop();c['waterfall.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_wrong_baseline_rejected(self):
  old=self.prior();old['cohort.json']=a.encoded({'version':'1.1.18','source_revision':'other'})
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_wrong_previous_version_rejected(self):
  old=self.prior();m=json.loads(old['waterfall.json']);m['version']='0.3.3';old['waterfall.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_duplicate_inherited_grant_rejected(self):
  old=self.prior();m=json.loads(old['boot.json']);m['app_capabilities'][0]['grants'].append(a.GRANT);old['boot.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_unchanged_metadata_is_byte_preserved_without_pressure(self):
  old=self.prior();new=a.payload(old,self.component(old),'new');self.assertEqual(old['board.json'],new['board.json'])
 def test_compaction_is_lossless_and_bounded_by_floor(self):
  from unittest.mock import patch
  old=self.prior();original=copy.deepcopy(old)
  compact=(json.dumps(json.loads(old['board.json']),separators=(',',':'))+'\n').encode()
  def pack(files,build):return b'image',{'empty_blocks':2 if files['board.json']==compact else 1}
  with patch.object(a,'ordered_build',pack):new,_,p,changes=a.compact_to_floor(old)
  self.assertEqual(old,original);self.assertEqual(p['empty_blocks'],2);self.assertEqual([r['path'] for r in changes],['board.json'])
  self.assertTrue(changes[0]['decoded_equal']);self.assertEqual(json.loads(new['board.json']),json.loads(old['board.json']))
  for n in set(old)-{'board.json'}:self.assertEqual(new[n],old[n])
 def test_packer_reserve_failure_triggers_only_lossless_compaction(self):
  from unittest.mock import patch
  old=self.prior();compact=(json.dumps(json.loads(old['board.json']),separators=(',',':'))+'\n').encode()
  def pack(files,build):
   if files['board.json']!=compact:raise ValueError('Current bootfs lacks SPIFFS free-block reserve')
   return b'image',{'empty_blocks':2}
  with patch.object(a,'ordered_build',pack):new,_,p,changes=a.compact_to_floor(old)
  self.assertEqual(json.loads(new['board.json']),json.loads(old['board.json']));self.assertEqual(p['empty_blocks'],2)
 def test_other_packing_errors_are_not_hidden(self):
  from unittest.mock import patch
  with patch.object(a,'ordered_build',side_effect=ValueError('Unrelated packing error')):
   with self.assertRaisesRegex(ValueError,'Unrelated packing error'):a.compact_to_floor(self.prior())
 def test_compaction_does_nothing_when_floor_met(self):
  from unittest.mock import patch
  old=self.prior()
  with patch.object(a,'ordered_build',lambda files,build:(b'image',{'empty_blocks':2})):new,_,p,changes=a.compact_to_floor(old)
  self.assertEqual(new,old);self.assertEqual(changes,[])
 def test_only_new_feature_flag(self):self.assertEqual(b.COMMON,['-DPORTABLE_TEXT_INPUT_POLICY'])
 def test_policy_optin_is_explicit(self):self.assertIn('-DPORTABLE_TEXT_INPUT_POLICY',b.COMMON)
if __name__=='__main__':unittest.main()

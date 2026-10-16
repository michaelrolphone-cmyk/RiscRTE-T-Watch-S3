import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import assemble_watch_timecard_shared_input as a
from build_timecard_shared_input import COMMON,VERSIONS,add_unique
VERSION=VERSIONS['watch']

class RecipeTest(unittest.TestCase):
 def prior(self):
  return {'timecard.elf':b'old','timecard.json':a.encoded({'version':'0.2.12','requires':[]}),
   'audio_spectrum.elf':b'preserved-spectrum','ui-text/driver.elf':b'preserved-text',
   'boot.json':a.encoded({'app_capabilities':[{'manifest':'timecard.json','grants':[{'capability':'radio.iq','api':1,'instance_id':0}]},{'manifest':'audio_spectrum.json','grants':[a.GRANT]}],'drivers':[{'unchanged':True}]}),
   'cohort.json':a.encoded({'version':'1.1.18','source_revision':a.BASE})}
 def component(self,old):
  m=json.loads(old['timecard.json']);m['version']=VERSION;m['requires'].append({'capability':'ui.text-input','api':1})
  return {'timecard.elf':b'new','timecard.json':a.encoded(m)}
 def test_exact_delta(self):
  old=self.prior();frozen=copy.deepcopy(old);new=a.payload(old,self.component(old),'new')
  self.assertEqual(old,frozen);self.assertEqual({n for n in new if old[n]!=new[n]},a.CHANGED)
  self.assertEqual(new['audio_spectrum.elf'],old['audio_spectrum.elf'])
  self.assertEqual(json.loads(new['boot.json'])['app_capabilities'][1],json.loads(old['boot.json'])['app_capabilities'][1])
 def test_compact_boot_preserves_exact_decoded_tree(self):
  old=self.prior();new=a.payload(old,self.component(old),'new');expected=json.loads(old['boot.json']);expected['app_capabilities'][0]['grants'].append(a.GRANT)
  self.assertEqual(json.loads(new['boot.json']),expected)
  self.assertEqual(new['boot.json'],(json.dumps(expected,sort_keys=True,separators=(',',':'))+'\n').encode())
 def test_excess_authority_rejected(self):
  old=self.prior();c=self.component(old);m=json.loads(c['timecard.json']);m['requires'].append({'capability':'net.http','api':1});c['timecard.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_wrong_baseline_rejected(self):
  old=self.prior();old['cohort.json']=a.encoded({'version':'1.1.18','source_revision':'other'})
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_feature_additions_preserve_order_and_duplicates(self):
  old=['-DPORTABLE_NOVA_UI','-DPORTABLE_APP_LAUNCH_GUARD'];new=add_unique(old,COMMON)
  self.assertEqual(new[:len(old)],old);self.assertEqual(new.count('-DPORTABLE_APP_LAUNCH_GUARD'),1)
if __name__=='__main__':unittest.main()

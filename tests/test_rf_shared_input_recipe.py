import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import assemble_watch_rf_shared_input as a
from build_rf_shared_input import COMMON,VERSION,add_unique

class RecipeTest(unittest.TestCase):
 def prior(self):
  return {'waterfall.elf':b'old','waterfall.json':a.encoded({'version':'0.3.3','requires':[]}),
   'audio_spectrum.elf':b'preserved-spectrum','ui-text/driver.elf':b'preserved-text',
   'boot.json':a.encoded({'app_capabilities':[{'manifest':'waterfall.json','grants':[{'capability':'radio.iq','api':1,'instance_id':0}]},{'manifest':'audio_spectrum.json','grants':[a.GRANT]}],'drivers':[{'unchanged':True}]}),
   'cohort.json':a.encoded({'version':'1.1.18','source_revision':a.BASE})}
 def component(self,old):
  m=json.loads(old['waterfall.json']);m['version']=VERSION;m['requires'].append({'capability':'ui.text-input','api':1})
  return {'waterfall.elf':b'new','waterfall.json':a.encoded(m)}
 def test_exact_delta(self):
  old=self.prior();frozen=copy.deepcopy(old);new=a.payload(old,self.component(old),'new')
  self.assertEqual(old,frozen);self.assertEqual({n for n in new if old[n]!=new[n]},a.CHANGED)
  self.assertEqual(new['audio_spectrum.elf'],old['audio_spectrum.elf'])
  self.assertEqual(json.loads(new['boot.json'])['app_capabilities'][1],json.loads(old['boot.json'])['app_capabilities'][1])
 def test_excess_authority_rejected(self):
  old=self.prior();c=self.component(old);m=json.loads(c['waterfall.json']);m['requires'].append({'capability':'net.http','api':1});c['waterfall.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_wrong_baseline_rejected(self):
  old=self.prior();old['cohort.json']=a.encoded({'version':'1.1.18','source_revision':'other'})
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_feature_additions_preserve_order_and_duplicates(self):
  old=['-DPORTABLE_NOVA_UI','-DPORTABLE_APP_LAUNCH_GUARD'];new=add_unique(old,COMMON)
  self.assertEqual(new[:len(old)],old);self.assertEqual(new.count('-DPORTABLE_APP_LAUNCH_GUARD'),1)
if __name__=='__main__':unittest.main()

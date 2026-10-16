import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import assemble_watch_lists_shared_input as a
from build_lists_shared_input import VERSION,ADDITIONS

class RecipeTest(unittest.TestCase):
 def prior(self):
  return {'lists.elf':b'old','lists.json':a.encoded({'version':'0.1.0','requires':[]}),
   'text-input/driver.elf':b'old-text','text-input/manifest.json':a.encoded({'version':'0.1.6','requires':[{'capability':'ui.scene','api':1}]}),
   'ui-scene/driver.elf':b'old-scene','ui-scene/manifest.json':a.encoded({'version':'0.4.5','requires':[{'capability':'display.output','api':1}]}),
   'audio_spectrum.elf':b'preserved-spectrum','ui-text/driver.elf':b'preserved-text',
   'boot.json':a.encoded({'app_capabilities':[{'manifest':'lists.json','grants':[{'capability':'radio.iq','api':1,'instance_id':0}]},{'manifest':'audio_spectrum.json','grants':[a.GRANT]}],'drivers':[{'unchanged':True}]}),
   'cohort.json':a.encoded({'version':'1.1.18','source_revision':a.BASE})}
 def component(self,old):
  m=json.loads(old['lists.json']);m['version']=VERSION;m['requires'].append({'capability':'ui.text-input','api':1})
  return {'lists.elf':b'new','lists.json':a.encoded(m),'ui-scene/driver.elf':b'new-scene','ui-scene/manifest.json':a.encoded(dict(json.loads(old['ui-scene/manifest.json']),version=a.SCENE_VERSION)),'text-input/driver.elf':b'new-text','text-input/manifest.json':a.encoded(dict(json.loads(old['text-input/manifest.json']),version=a.TEXT_VERSION))}
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
  old=self.prior();c=self.component(old);m=json.loads(c['lists.json']);m['requires'].append({'capability':'net.http','api':1});c['lists.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_wrong_baseline_rejected(self):
  old=self.prior();old['cohort.json']=a.encoded({'version':'1.1.18','source_revision':'other'})
  with self.assertRaises(ValueError):a.payload(old,self.component(old),'new')
 def test_text_host_authority_rejected(self):
  old=self.prior();c=self.component(old);m=json.loads(c['text-input/manifest.json']);m['requires'].append({'capability':'usb.hid','api':1});c['text-input/manifest.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_scene_host_authority_rejected(self):
  old=self.prior();c=self.component(old);m=json.loads(c['ui-scene/manifest.json']);m['requires'].append({'capability':'input.navigation','api':1});c['ui-scene/manifest.json']=a.encoded(m)
  with self.assertRaises(ValueError):a.payload(old,c,'new')
 def test_only_lists_flag_is_added(self):
  self.assertEqual(ADDITIONS,['-DPORTABLE_LISTS_SHARED_TEXT_INPUT'])
if __name__=='__main__':unittest.main()

import copy
import hashlib
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_current_updates import app_compatibility, exact_components, asset
from watch_release_index import update_index


class CurrentUpdates(unittest.TestCase):
 def manifest(self,version):
  return dict(id='audio_spectrum',version=version,type='application',architecture='xtensa-esp32s3',
              file_name='audio_spectrum.elf',entry='app_main',requires=[{'capability':'storage.app-data','api':1}])
 def test_only_the_existing_version_advances(self):
  for previous in ('0.4.0','0.4.1'):
   app_compatibility(self.manifest(previous),self.manifest('0.4.2'))
  for version in ('0.4.0','0.3.0'):
   with self.assertRaises(ValueError):app_compatibility(self.manifest('0.4.0'),self.manifest(version))
  for field,value in [('requires',[]),('file_name','other.elf'),('entry','other'),('id','other'),('grants',[])]:
   changed=self.manifest('0.4.2');changed[field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):app_compatibility(self.manifest('0.4.0'),changed)
 def test_component_hashes_and_bounds(self):
  raw=b'\xff'*0x1000000
  item=dict(file='components/firmware.bin',offset='0x10000',size_bytes=32,sha256=hashlib.sha256(b'\xff'*32).hexdigest())
  m=dict(bin_sha256=hashlib.sha256(raw).hexdigest(),components=[item])
  self.assertEqual(exact_components(raw,m),{'firmware.bin':b'\xff'*32})
  for key,value in [('offset','0x1000000'),('size_bytes',0),('sha256','0'*64)]:
   bad=copy.deepcopy(m);bad['components'][0][key]=value
   with self.assertRaises(ValueError):exact_components(raw,bad)
  with self.assertRaises(ValueError):exact_components(raw,{**m,'components':[item,item]})
 def test_release_records_cannot_rewrite_or_downgrade_versions(self):
  old=asset('app','0.4.1','audio_spectrum.elf',b'old','audio_spectrum');old['manifest']=self.manifest('0.4.1')
  initial={'schema':1,'firmware':None,'apps':[old],'drivers':[]}
  newer=asset('app','0.4.2','audio_spectrum.elf',b'new','audio_spectrum');newer['manifest']=self.manifest('0.4.2')
  updated=update_index(initial,'apps',newer);self.assertEqual(updated['apps'][0]['version'],'0.4.2')
  self.assertEqual(initial['apps'][0]['version'],'0.4.1')
  collision=copy.deepcopy(newer);collision['sha256']='0'*64
  with self.assertRaises(ValueError):update_index(updated,'apps',collision)
  with self.assertRaises(ValueError):update_index(updated,'apps',old)


if __name__=='__main__':unittest.main()

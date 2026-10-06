import copy
import hashlib
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_current_updates import app_compatibility, exact_components, asset
from watch_release_index import update_index,reuse_app_record
import current_flash_layout as layout


class CurrentUpdates(unittest.TestCase):
 def manifest(self,version):
  return dict(id='audio_spectrum',version=version,type='application',architecture='xtensa-esp32s3',
              file_name='audio_spectrum.elf',entry='app_main',requires=[{'capability':'storage.app-data','api':1}])
 def test_only_the_existing_version_advances(self):
  for previous in ('0.4.0','0.4.1'):
   app_compatibility(self.manifest(previous),self.manifest('0.4.2'))
  for version in ('0.4.0','0.3.0'):
   with self.assertRaises(ValueError):app_compatibility(self.manifest('0.4.0'),self.manifest(version))
  app_compatibility(self.manifest('0.4.2'),self.manifest('0.4.2'),allow_same=True)
  with self.assertRaises(ValueError):app_compatibility(self.manifest('0.4.2'),self.manifest('0.4.1'),allow_same=True)
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
 def test_full_initial_image_requires_exact_abi2_placement_and_erased_gaps(self):
  deployment=dict(target='esp32s3-16mb-appdata',layout=layout.APP_DATA_LAYOUT,store_abi=2,flash_bytes=0x1000000,partitions=layout.APP_DATA_PARTS)
  components={'bootloader.bin':b'boot'*8,'partitions.bin':b'part'*8,'firmware.bin':b'firm'*8,
              'bootfs.bin':b'S'*0x510000,'appdata.bin':b'E'*0x80000,'otadata.bin':b'O'*0x2000,'bank_state.bin':b'J'*0x2000}
  digest=lambda b:hashlib.sha256(b).hexdigest()
  with patch.object(layout,'APP_DATA_SHA',digest(components['appdata.bin'])):
   raw,entries=layout.assemble(components,deployment,True);m=dict(bin_sha256=digest(raw),components=entries)
   self.assertEqual(components,exact_components(raw,m,deployment))
   relocated=bytearray(raw);relocated[0x10000:0x10020]=b'\xff'*32;relocated[0x11000:0x11020]=components['firmware.bin']
   bad=copy.deepcopy(m);bad['bin_sha256']=digest(relocated);bad['components'][2]['offset']='0x11000'
   with self.assertRaisesRegex(ValueError,'placement'):exact_components(bytes(relocated),bad,deployment)
   dirty=bytearray(raw);dirty[0x9000]=0;bad={**m,'bin_sha256':digest(dirty)}
   with self.assertRaisesRegex(ValueError,'erased gaps'):exact_components(bytes(dirty),bad,deployment)
   with self.assertRaises(ValueError):exact_components(raw,{**m,'components':entries[:-1]},deployment)
 def test_release_records_cannot_rewrite_or_downgrade_versions(self):
  old=asset('app','0.4.1','audio_spectrum.elf',b'old','audio_spectrum');old['manifest']=self.manifest('0.4.1')
  initial={'schema':1,'firmware':None,'apps':[old],'drivers':[]}
  newer=asset('app','0.4.2','audio_spectrum.elf',b'new','audio_spectrum');newer['manifest']=self.manifest('0.4.2')
  updated=update_index(initial,'apps',newer);self.assertEqual(updated['apps'][0]['version'],'0.4.2')
  self.assertEqual(initial['apps'][0]['version'],'0.4.1')
  collision=copy.deepcopy(newer);collision['sha256']='0'*64
  with self.assertRaises(ValueError):update_index(updated,'apps',collision)
  with self.assertRaises(ValueError):update_index(updated,'apps',old)
 def test_next_cohort_keeps_identical_spectrum_release_and_old_provenance(self):
  old=asset('app','0.4.2','audio_spectrum.elf',b'unchanged','audio_spectrum')
  old.update(manifest=self.manifest('0.4.2'),source_sha='a'*40,minimum_runtime_version='0.1.33')
  proposed={**old,'source_sha':'b'*40,'minimum_runtime_version':'0.1.34'}
  chosen,reused=reuse_app_record(old,proposed)
  self.assertTrue(reused);self.assertEqual(old,chosen)
  index=dict(schema=1,firmware=None,apps=[old],drivers=[])
  self.assertEqual(index,update_index(index,'apps',chosen))
  for key,value in [('sha256','f'*64),('size',88),('manifest',self.manifest('0.4.2')|{'entry':'other'})]:
   changed={**proposed,key:value}
   with self.subTest(key=key),self.assertRaises(ValueError):reuse_app_record(old,changed)
  advanced={**asset('app','0.4.3','audio_spectrum.elf',b'changed','audio_spectrum'),'manifest':self.manifest('0.4.3')}
  chosen,reused=reuse_app_record(old,advanced);self.assertFalse(reused);self.assertEqual(advanced,chosen)


if __name__=='__main__':unittest.main()

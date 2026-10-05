import copy,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from current_flash_layout import APP_DATA_LAYOUT,APP_DATA_PARTS,LEGACY_LAYOUT,LEGACY_PARTS,validate,assemble
from build_update_flash_bundle import assemble as legacy_assemble
class CurrentFlashLayout(unittest.TestCase):
 def spec(self,new):return {'layout':APP_DATA_LAYOUT if new else LEGACY_LAYOUT,'target':'esp32s3-16mb-appdata' if new else 'esp32s3-16mb-paired','store_abi':2 if new else 1,'flash_bytes':0x1000000,'partitions':copy.deepcopy(APP_DATA_PARTS if new else LEGACY_PARTS)}
 def components(self):return {'bootloader.bin':b'boot','partitions.bin':b'table','firmware.bin':b'firmware','bootfs.bin':b'\xee'*0x4f0000,'otadata.bin':b'\xaa'*0x2000,'bank_state.bin':b'\xbb'*0x2000}
 def test_legacy_bytes_are_identical(self):
  parts=self.components();self.assertEqual(assemble(parts,self.spec(False)),legacy_assemble(parts))
  with self.assertRaises(ValueError):assemble({**parts,'appdata.bin':b'data'},self.spec(False))
 def test_explicit_layout_and_geometry(self):
  for new in (False,True):
   self.assertEqual(validate(self.spec(new),new),new)
   with self.assertRaises(ValueError):validate(self.spec(new),not new)
   wrong=self.spec(new);wrong['store_abi']=3
   with self.assertRaises(ValueError):validate(wrong,new)
   wrong=self.spec(new);wrong['partitions']['app0']['size']+=1
   with self.assertRaises(ValueError):validate(wrong,new)
  wrong=self.spec(False);wrong['layout']='unknown'
  with self.assertRaises(ValueError):validate(wrong)
 def test_initial_image_bounds_and_erased_bank(self):
  import hashlib
  parts={**self.components(),'bootfs.bin':b'\xee'*0x510000,'appdata.bin':b'\xcc'*0x80000};digest=hashlib.sha256(parts['appdata.bin']).hexdigest()
  with self.assertRaises(ValueError):assemble(parts,self.spec(True),True)
  with patch('current_flash_layout.APP_DATA_SHA',digest):
   image,entries=assemble(parts,self.spec(True),True)
   self.assertEqual(image[0x270000:0x2f0000],parts['appdata.bin']);self.assertEqual(image[0x800000:0xff0000],b'\xff'*0x7f0000)
   self.assertEqual(len(entries),7)
   too_big={**parts,'firmware.bin':b'\x44'*(0x260001)}
   with self.assertRaises(ValueError):assemble(too_big,self.spec(True),True)
   short={**parts,'appdata.bin':parts['appdata.bin'][:-1]}
   with self.assertRaises(ValueError):assemble(short,self.spec(True),True)
if __name__=='__main__':unittest.main()

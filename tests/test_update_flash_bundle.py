"""Paired assembly boundaries and exact external-custody receipt negatives."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_update_flash_bundle import assemble, receipt, JOBS, FLASH_BYTES
from build_wifi_common import sha

class PairedBundleTests(unittest.TestCase):
 def components(self):
  return {'bootloader.bin':b'loader','partitions.bin':b'partitions','firmware.bin':b'firmware',
          'bootfs.bin':b'\xff'*0x4f0000,'otadata.bin':b'\xff'*8192,'bank_state.bin':b'\xff'*8192}
 def test_full16m_and_erased_inactive(self):
  data,parts=assemble(self.components())
  self.assertEqual(len(data),FLASH_BYTES);self.assertEqual(len(parts),6)
  self.assertEqual(data[0x9000:0xf000],b'\xff'*0x6000)
  self.assertEqual(data[0x800000:0xff0000],b'\xff'*0x7f0000)
  self.assertEqual(data[0x10000:0x10008],b'firmware')
 def test_overlap_and_fixed_partitions(self):
  for name,size in [('bootloader.bin',0x8001),('partitions.bin',0x1001),
                    ('firmware.bin',0x300001),('bootfs.bin',0x4f0001),
                    ('otadata.bin',8193),('bank_state.bin',8191)]:
   with self.subTest(name=name):
    parts=self.components();parts[name]=b'x'*size
    with self.assertRaises(ValueError):assemble(parts)
 def test_unknown_component(self):
  parts=self.components();parts['app1.bin']=b'x'
  with self.assertRaises(ValueError):assemble(parts)
 def test_receipt_requires_every_exact_head_job(self):
  raw=b'actual zip';head='1'*40;tree='2'*40
  good={'repository':'michaelrolphone-cmyk/RiscRTE-T-Watch-S3','head':head,'tree':tree,
        'conclusion':'success','expired':False,'artifact_name':'twatch-update-integration-'+head,
        'artifact_sha256':sha(raw),'run_id':42,'artifact_id':43,
        'jobs':[{'name':n,'conclusion':'success'} for n in sorted(JOBS)]}
  receipt(good,raw,head,tree)
  for key,value in [('head','3'*40),('tree','4'*40),('conclusion','failure'),('expired',True),
                    ('artifact_sha256','0'*64),('artifact_name','twatch-wifi-integration-'+head),
                    ('run_id',True),('artifact_id',0),('jobs',good['jobs'][:-1]),
                    ('jobs',good['jobs'][:-1]+[good['jobs'][0]])]:
   with self.subTest(key=key,value=value):
    bad=copy.deepcopy(good);bad[key]=value
    with self.assertRaises(ValueError):receipt(bad,raw,head,tree)
  for name in JOBS:
   bad=copy.deepcopy(good);next(j for j in bad['jobs'] if j['name']==name)['conclusion']='failure'
   with self.assertRaises(ValueError):receipt(bad,raw,head,tree)

if __name__=='__main__':unittest.main()

"""Paired assembly boundaries and exact external-custody receipt negatives."""
import copy
import json
import tempfile
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_update_flash_bundle import assemble, receipt, JOBS, FLASH_BYTES, require_branch_mode, require_typed_record
from build_wifi_common import sha

class PairedBundleTests(unittest.TestCase):
 def components(self):
  return {'bootloader.bin':b'loader','partitions.bin':b'partitions','firmware.bin':b'firmware',
          'bootfs.bin':b'\xff'*0x4f0000,'otadata.bin':b'\xff'*8192,'bank_state.bin':b'\xff'*8192}
 def test_branch_mode_is_not_an_artifact_choice(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);(root/'apps').mkdir()
   for mode,apps in [('paired',[]),('ota',['ota_update']),('all',['ota_update','app_store'])]:
    (root/'apps/update-lane.json').write_text(json.dumps({'schema':1,'mode':mode}))
    require_branch_mode(root,{'updates':{'apps':apps}})
    for other in [[],['ota_update'],['ota_update','app_store']]:
     if other!=apps:
      with self.assertRaises(ValueError):require_branch_mode(root,{'updates':{'apps':other}})
   (root/'apps/update-lane.json').write_text(json.dumps({'schema':True,'mode':'all'}))
   with self.assertRaises(ValueError):require_branch_mode(root,{'updates':{'apps':['ota_update','app_store']}})
 def test_sidecar_exact_types_and_compatibility(self):
  expected={'schema':1,'image':'bank0.bin','layout':'riscrte-paired-16m-v1','store_abi':1,
            'migration_only':True,'apps':['ota_update'],'round_trip_verified':True,'size_bytes':5177344}
  require_typed_record(dict(expected),expected)
  for field,value in [('schema',True),('store_abi',True),('store_abi',999),('layout','legacy-8m'),
                      ('migration_only',False),('migration_only',1),('apps',[]),('image','wrong.bin'),
                      ('round_trip_verified',1),('size_bytes',5177344.0)]:
   bad=dict(expected);bad[field]=value
   with self.subTest(field=field,value=value),self.assertRaises(ValueError):require_typed_record(bad,expected)
  with self.assertRaises(ValueError):require_typed_record(dict(expected,extra='surprise'),expected)
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

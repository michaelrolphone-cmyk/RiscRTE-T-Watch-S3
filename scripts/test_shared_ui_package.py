#!/usr/bin/env python3
"""Offline deterministic-package and factory custody rejection tests."""
import json,tempfile,unittest,zipfile
from pathlib import Path
import package_shared_native_ui as p

class PackageTests(unittest.TestCase):
 def metadata(self):
  before={'springboard.json':p.encoded({'version':'1.7.12','requires':[]}),'cohort.json':p.encoded({'version':'1.1.33','apps':['default.json','springboard.json']})}
  manifest=json.loads(before['springboard.json']);manifest['version']=p.PINS['springboard_manifest_version']
  cohort=json.loads(before['cohort.json']);cohort.update(version=p.PINS['version'],source_revision='a'*40,runtime_version='0.3.3',firmware_sha256=p.sha(b'firmware'),firmware_size=8)
  return before,{'springboard.json':p.encoded(manifest),'cohort.json':p.encoded(cohort)}
 def test_metadata_exact_transform(self):
  before,after=self.metadata();p.verify_store_metadata(before,after,b'firmware','a'*40)
 def test_extra_manifest_authority_refused(self):
  before,after=self.metadata();m=json.loads(after['springboard.json']);m['requires']=[{'capability':'extra','api':1}];after['springboard.json']=p.encoded(m)
  with self.assertRaisesRegex(ValueError,'manifest'):p.verify_store_metadata(before,after,b'firmware','a'*40)
 def test_changed_cohort_inventory_refused(self):
  before,after=self.metadata();m=json.loads(after['cohort.json']);m['apps']=[];after['cohort.json']=p.encoded(m)
  with self.assertRaisesRegex(ValueError,'Cohort'):p.verify_store_metadata(before,after,b'firmware','a'*40)
 def test_incomplete_qualification_refused(self):
  report={'system_revision':p.PINS['system_revision'],'bridge_revision':p.PINS['bridge_revision'],'stage_profile':True,'reports':{}}
  with self.assertRaisesRegex(ValueError,'Incomplete'):p.verify_qualification(report,Path('/unused'))
 def test_roundtrip_and_checksums(self):
  payload={'README.txt':b'keep NVS and AppData\n','nested/proof.json':b'{}\n'}
  with tempfile.TemporaryDirectory() as td:
   target=Path(td)/'kit.zip';p.archive(target,payload)
   with zipfile.ZipFile(target) as z:
    self.assertEqual(z.read('SHA256SUMS.txt'),p.checksums(payload))
    for name,data in payload.items():self.assertEqual(z.read(name),data)
 def test_reproducible_archive(self):
  with tempfile.TemporaryDirectory() as td:
   a=Path(td)/'a.zip';b=Path(td)/'b.zip'
   p.archive(a,{'b':b'B','a':b'A'});p.archive(b,{'a':b'A','b':b'B'})
   self.assertEqual(a.read_bytes(),b.read_bytes())
 def test_existing_archive_refused(self):
  with tempfile.TemporaryDirectory() as td:
   target=Path(td)/'kit.zip';target.write_bytes(b'preserve existing')
   with self.assertRaises(FileExistsError):p.archive(target,{'a':b'A'})
   self.assertEqual(target.read_bytes(),b'preserve existing')
 def test_nonbaseline_factory_refused(self):
  with self.assertRaisesRegex(ValueError,'Exact released .33'):
   p.make_factory(b'wrong',b'',b'',Path('/unused'),Path('/unused'))
 def test_same_size_wrong_factory_refused(self):
  with self.assertRaisesRegex(ValueError,'Exact released .33'):
   p.make_factory(b'\xff'*0x1000000,b'',b'',Path('/unused'),Path('/unused'))

if __name__=='__main__':unittest.main()

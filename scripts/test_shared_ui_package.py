#!/usr/bin/env python3
"""Offline deterministic-package and factory custody rejection tests."""
import tempfile,unittest,zipfile
from pathlib import Path
import package_shared_native_ui as p

class PackageTests(unittest.TestCase):
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

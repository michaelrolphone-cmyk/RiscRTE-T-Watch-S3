"""Reject stale/corrupt final Clock payloads even when they contain UP NEXT."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_points_paired_clock import FILES, ROOT, sha, verify

class PairedClockCustody(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.service={'source_pins':json.loads((ROOT/'apps/points-sources.json').read_text()),
                      'points_headers':{n:'b'*64 for n in ('PointsRecords.h','PointsSchedule.h')}}
        self.record={'schema':1,'watch_source_sha':'a'*40,'paired_boot_confirmation':True,
            'points_sources':json.loads((ROOT/'apps/points-sources.json').read_text()),
            'headers':dict(self.service['points_headers']),'files':{}}
        for name in FILES:
            data=b'UP NEXT fixture '+name.encode();(self.path/name).write_bytes(data)
            self.record['files'][name]={'sha256':sha(data),'size_bytes':len(data)}
    def write(self):
        (self.path/'points-paired-clock.json').write_text(json.dumps(self.record))
    def test_current_exact_payload(self):
        self.write();files,record=verify(self.path,'a'*40,self.service)
        self.assertEqual(set(files),set(FILES));self.assertEqual(record,self.record)
    def test_stale_sources(self):
        self.record['points_sources']['utilities']['commit']='b'*40;self.write()
        with self.assertRaisesRegex(ValueError,'source pins'):verify(self.path,'a'*40,self.service)
    def test_old_schema(self):
        self.record['headers']['PointsRecords.h']='c'*64;self.write()
        with self.assertRaisesRegex(ValueError,'schema'):verify(self.path,'a'*40,self.service)
    def test_wrong_watch(self):
        self.write()
        with self.assertRaisesRegex(ValueError,'provenance'):verify(self.path,'b'*40,self.service)
    def test_missing_boot_confirmation(self):
        self.record['paired_boot_confirmation']=False;self.write()
        with self.assertRaisesRegex(ValueError,'provenance'):verify(self.path,'a'*40,self.service)
    def test_modified_clock(self):
        self.write();(self.path/'clock.elf').write_bytes(b'UP NEXT corrupt')
        with self.assertRaisesRegex(ValueError,'content'):verify(self.path,'a'*40,self.service)
    def test_missing_clock(self):
        del self.record['files']['clock.elf'];self.write()
        with self.assertRaisesRegex(ValueError,'membership'):verify(self.path,'a'*40,self.service)

if __name__=='__main__':unittest.main()

"""Regression tests for the shared Home device assembler, not hardware tests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from assemble_watch_universal import BASE_SOURCE,APP,PRESERVED,check_native_bytes,rebind
from universal_native import BOUNDS,composition

def fixture():
    elf=b'compiler output';payload=bytearray(256)
    payload[:4]=b'\x32\x54\xcd\xab';payload[144:176]=hashlib.sha256(elf).digest()
    header=bytearray(24);header[0]=0xe9;header[1]=1;header[12]=9;header[23]=1
    raw=header+struct.pack('<II',0x3c000000,len(payload))+payload
    checksum=0xef
    for byte in payload:checksum^=byte
    raw+=b'\0'*((len(raw)+16)//16*16-len(raw)-1)+bytes([checksum])
    raw+=hashlib.sha256(raw).digest()
    return bytes(raw),elf

class Composition(unittest.TestCase):
    def test_correct_native(self):check_native_bytes(*fixture())
    def test_bin_elf_mismatch(self):
        raw,_=fixture()
        with self.assertRaisesRegex(ValueError,'ELF'):check_native_bytes(raw,b'other native')
    def test_corrupt_native(self):
        raw,elf=fixture();bad=bytearray(raw);bad[80]^=1
        with self.assertRaisesRegex(ValueError,'SHA'):check_native_bytes(bytes(bad),elf)
    def test_rehashed_bad_checksum(self):
        raw,elf=fixture();bad=bytearray(raw);bad[-33]^=1;bad[-32:]=hashlib.sha256(bad[:-32]).digest()
        with self.assertRaisesRegex(ValueError,'checksum'):check_native_bytes(bytes(bad),elf)
    def test_wrong_chip(self):
        raw,elf=fixture();bad=bytearray(raw);bad[12]=0
        with self.assertRaises(ValueError):check_native_bytes(bytes(bad),elf)
    def test_appdata_outside_native_range(self):
        self.assertEqual(APP,(0x10000,0x270000))
        self.assertIn((0x270000,0x2f0000),PRESERVED)
    def test_cohort_rebind_does_not_change_payloads(self):
        cohort=dict(version='1.1.17',source_revision=BASE_SOURCE,product='twatch-s3',layout='riscrte-paired-appdata-v2')
        old={'cohort.json':json.dumps(cohort).encode(),'default.elf':b'app','app-data':b'data'}
        new=rebind(old,b'native','a'*40)
        self.assertEqual(new['default.elf'],old['default.elf']);self.assertEqual(new['app-data'],old['app-data'])
        self.assertEqual(json.loads(old['cohort.json']),cohort)
        value=json.loads(new['cohort.json']);self.assertEqual(value['version'],'1.2.0');self.assertEqual(value['firmware_size'],6)
        self.assertEqual(value['firmware_sha256'],hashlib.sha256(b'native').hexdigest())
    def test_wrong_predecessor(self):
        old={'cohort.json':json.dumps(dict(version='1.1.16',source_revision=BASE_SOURCE,product='twatch-s3',layout='riscrte-paired-appdata-v2')).encode()}
        with self.assertRaises(ValueError):rebind(old,b'native','a'*40)
    def test_row_profile_not_silently_downgraded(self):
        self.assertEqual(BOUNDS['RISC_PROVIDER_CAPACITY'],40)
        with self.assertRaisesRegex(ValueError,'32 policy rows'):composition(ROOT,b'',Path('absent'),24)

if __name__=='__main__':unittest.main()

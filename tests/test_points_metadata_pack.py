import io
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from elftools.elf.elffile import ELFFile
from compact_current_elf import evidence
from pack_points_elf_metadata import pack,align


def fixture(gap_end=512,tail_alloc=False):
    names=b'\0.text\0.data\0.extra\0.shstrtab\0'
    tail=gap_end+16
    table=align(tail+16+len(names),4)
    raw=bytearray(table+5*40)
    ident=b'\x7fELF\x01\x01\x01'+b'\0'*9
    struct.pack_into('<16sHHIIIIIHHHHHH',raw,0,ident,3,94,1,128,52,table,0,52,32,2,40,5,4)
    struct.pack_into('<IIIIIIII',raw,52,1,0,0,0,256,256,5,4)
    struct.pack_into('<IIIIIIII',raw,84,1,gap_end,gap_end,gap_end,16,32,6,4)
    raw[128:144]=b'A'*16;raw[gap_end:tail]=b'B'*16
    raw[tail:tail+16]=b'nonallocateddata';raw[tail+16:tail+16+len(names)]=names
    rows=[(0,0,0,0,0,0,0,0,0,0),(1,1,6,128,128,16,0,0,4,0),
          (7,1,3,gap_end,gap_end,16,0,0,4,0),(13,1,2 if tail_alloc else 0,0,tail,16,0,0,4,0),
          (20,3,0,0,tail+16,len(names),0,0,1,0)]
    for index,row in enumerate(rows):struct.pack_into('<10I',raw,table+40*index,*row)
    return bytes(raw)

class MetadataPackTest(unittest.TestCase):
    def test_all_retained_semantics_and_program_headers_equal(self):
        original=fixture();result,proof=pack(original)
        self.assertEqual(evidence(original),evidence(result))
        self.assertEqual(original[52:116],result[52:116])
        self.assertEqual(len(result),528)
        self.assertGreater(proof['bytes_saved'],0)
        a,b=[ELFFile(io.BytesIO(data)) for data in (original,result)]
        for left,right in zip(a.iter_sections(),b.iter_sections()):
            self.assertEqual(left.name,right.name)
            self.assertEqual(left.data(),right.data())
            for field in ('sh_addr','sh_addralign','sh_flags','sh_size'):
                self.assertEqual(left[field],right[field])
            if left['sh_flags']&2:self.assertEqual(left['sh_offset'],right['sh_offset'])
    def test_no_room_refused(self):
        with self.assertRaisesRegex(ValueError,'No unmapped file gap'):
            pack(fixture(gap_end=272))
    def test_allocated_tail_refused(self):
        with self.assertRaisesRegex(ValueError,'Allocated tail'):
            pack(fixture(tail_alloc=True))
    def test_second_application_refused(self):
        result,_=pack(fixture())
        with self.assertRaises(ValueError):pack(result)
    def test_bad_alignment_refused(self):
        with self.assertRaises(ValueError):align(5,3)
    def test_semantic_change_refused(self):
        with patch('pack_points_elf_metadata.evidence',side_effect=[{'before':1},{'after':2}]):
            with self.assertRaisesRegex(ValueError,'retained loader evidence'):pack(fixture())
if __name__=='__main__':unittest.main()

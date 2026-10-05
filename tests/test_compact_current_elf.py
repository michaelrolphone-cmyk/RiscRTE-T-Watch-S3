import tempfile,subprocess,unittest,sys,shutil
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from compact_current_elf import compact,loaded
class CurrentElfCompaction(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.elf=self.root/'fixture.so'
  source=self.root/'fixture.c';source.write_text('extern int puts(const char*); int control_state=50; int get_control(void){return control_state+puts("ready");}\n')
  self.cc=shutil.which('gcc');self.assertIsNotNone(self.cc)
  subprocess.run([self.cc,'-g','-shared','-fPIC',str(source),'-o',str(self.elf)],check=True)
 def test_preserves_loaded_bytes_and_relocations(self):
  before=self.elf.read_bytes();proof=compact(self.elf,self.cc)
  self.assertEqual(loaded(before),loaded(self.elf.read_bytes()));self.assertLessEqual(proof['after_bytes'],proof['before_bytes'])
 def test_altered_loaded_content_rejected(self):
  original=loaded(self.elf.read_bytes())
  with patch('compact_current_elf.evidence',side_effect=[original,{}]),self.assertRaisesRegex(ValueError,'changed retained'):
   compact(self.elf,self.cc)
 def corrupt_after_copy(self,edit):
  real_run=subprocess.run
  def fake_run(*args,**kwargs):
   result=real_run(*args,**kwargs);data=bytearray(self.elf.read_bytes());edit(data);self.elf.write_bytes(data);return result
  with patch('compact_current_elf.subprocess.run',side_effect=fake_run),self.assertRaisesRegex(ValueError,'changed retained'):
   compact(self.elf,self.cc)
 def test_changed_import_rejected(self):
  def edit(data):
   offset=data.index(b'puts\0');data[offset:offset+4]=b'gets'
  self.corrupt_after_copy(edit)
 def test_changed_relocation_rejected(self):
  import io
  from elftools.elf.elffile import ELFFile
  def edit(data):
   elf=ELFFile(io.BytesIO(data));section=next(s for s in elf.iter_sections() if s['sh_type'] in ('SHT_REL','SHT_RELA'));data[section['sh_offset']]^=1
  self.corrupt_after_copy(edit)
 def test_changed_machine_rejected(self):
  self.corrupt_after_copy(lambda data:data.__setitem__(18,data[18]^1))
if __name__=='__main__':unittest.main()

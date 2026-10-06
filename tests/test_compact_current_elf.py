import tempfile,subprocess,unittest,sys,shutil
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from compact_current_elf import compact,loaded,sha,OPTIONS
class CurrentElfCompaction(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.elf=self.root/'fixture.so'
  source=self.root/'fixture.c';source.write_text('extern int puts(const char*); int control_state=50; int get_control(void){return control_state+puts("ready");}\n')
  self.cc=shutil.which('gcc');self.assertIsNotNone(self.cc)
  subprocess.run([self.cc,'-g','-shared','-fPIC',str(source),'-o',str(self.elf)],check=True)
 def test_preserves_loaded_bytes_and_relocations(self):
  before=self.elf.read_bytes();proof=compact(self.elf,self.cc)
  self.assertEqual(loaded(before),loaded(self.elf.read_bytes()));self.assertLessEqual(proof['after_bytes'],proof['before_bytes'])
  self.assertEqual(self.elf.with_suffix('.debug.elf').read_bytes(),before)
  self.assertEqual(proof['before_sha256'],sha(before));self.assertEqual(proof['after_sha256'],sha(self.elf.read_bytes()))
  self.assertEqual(proof['options'],list(OPTIONS));self.assertTrue(proof['original_elf_retained'])
 def test_proof_records_loader_alignment_stride_and_segments(self):
  import io
  from elftools.elf.elffile import ELFFile
  data=self.elf.read_bytes();elf=ELFFile(io.BytesIO(data));proof=loaded(data)
  for name in ('.text','.data','.bss'):
   section=elf.get_section_by_name(name)
   self.assertEqual(proof['sections'][name][4:6],(section['sh_addralign'],section['sh_entsize']))
  self.assertEqual(proof['header']['e_phoff'],elf['e_phoff'])
  self.assertEqual([s[0][2] for s in proof['header']['segments']],[s['p_offset'] for s in elf.iter_segments()])
  self.assertEqual(proof['symbol_sections']['.dynsym'][3:5],(elf.get_section_by_name('.dynsym')['sh_addralign'],elf.get_section_by_name('.dynsym')['sh_entsize']))
 def test_altered_loaded_content_rejected(self):
  original=loaded(self.elf.read_bytes())
  with patch('compact_current_elf.evidence',side_effect=[original,{}]),self.assertRaisesRegex(ValueError,'changed retained'):
   compact(self.elf,self.cc)
 def corrupt_after_copy(self,edit):
  real_run=subprocess.run
  def fake_run(*args,**kwargs):
   result=real_run(*args,**kwargs)
   if '--discard-all' in args[0]:
    target=Path(args[0][-1]);data=bytearray(target.read_bytes());edit(data);target.write_bytes(data)
   return result
  before=self.elf.read_bytes()
  with patch('compact_current_elf.subprocess.run',side_effect=fake_run),self.assertRaisesRegex(ValueError,'changed retained'):
   compact(self.elf,self.cc)
  self.assertEqual(self.elf.read_bytes(),before)
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
 def test_changed_entrypoint_rejected(self):
  self.corrupt_after_copy(lambda data:data.__setitem__(24,data[24]^1))
 def static_relocations(self):
  source=self.root/'static.c';source.write_text('static int counter=4; static __attribute__((noinline)) int private_value(void){return ++counter;} int exported(void){return private_value();}\n')
  subprocess.run([self.cc,'-g','-shared','-fPIC','-Wl,--emit-relocs',str(source),'-o',str(self.elf)],check=True)
 def test_referenced_static_symbols_preserved(self):
  self.static_relocations();before=loaded(self.elf.read_bytes());compact(self.elf,self.cc)
  self.assertEqual(loaded(self.elf.read_bytes()),before)
 def test_changed_static_relocation_target_rejected(self):
  self.static_relocations()
  import io
  from elftools.elf.elffile import ELFFile
  def edit(data):
   elf=ELFFile(io.BytesIO(data))
   for section in elf.iter_sections():
    if section['sh_type'] not in ('SHT_REL','SHT_RELA'):continue
    table=elf.get_section(section['sh_link'])
    if table['sh_type']!='SHT_SYMTAB':continue
    for relocation in section.iter_relocations():
     index=relocation['r_info_sym'];symbol=table.get_symbol(index)
     if symbol['st_info']['bind']=='STB_LOCAL' and index:
      offset=table['sh_offset']+index*table['sh_entsize']+(8 if elf.elfclass==64 else 4)
      data[offset]^=1;return
   self.fail('Fixture has no referenced local static symbol')
  self.corrupt_after_copy(edit)
if __name__=='__main__':unittest.main()

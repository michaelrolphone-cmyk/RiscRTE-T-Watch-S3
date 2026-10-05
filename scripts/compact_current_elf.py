"""Remove two nonloaded Xtensa compiler-property sections from current apps.

The bundled loader's elf_loader.cmake also removes .xt.lit/.xt.prop. Unlike its
strip recipe, retain every debug/source section and all static/dynamic symbols.
Proof normalizes section indices to names and preserves symbol order/identity,
allocated data, relocation bytes and all other retained section contents.
"""
import io,subprocess
from elftools.elf.elffile import ELFFile
REMOVED=frozenset(('.xt.lit','.xt.prop'))

def evidence(data):
 elf=ELFFile(io.BytesIO(data));sections={};symbols={}
 header={key:elf.header[key] for key in ('e_type','e_machine','e_version','e_entry','e_flags','e_ehsize','e_phentsize','e_phnum','e_shentsize')}
 header['ident']={key:elf.header['e_ident'][key] for key in ('EI_CLASS','EI_DATA','EI_VERSION','EI_OSABI','EI_ABIVERSION')}
 for section in elf.iter_sections():
  name=section.name;h=section.header
  if name in REMOVED:
   if h['sh_flags']&2:raise ValueError('Refuse to remove an allocated compiler property section')
   continue
  if h['sh_type'] in ('SHT_SYMTAB','SHT_DYNSYM'):
   rows=[]
   for symbol in section.iter_symbols():
    sh=symbol['st_shndx'];target=elf.get_section(sh).name if isinstance(sh,int) and sh else sh
    if symbol['st_info']['type']=='STT_SECTION' and target in REMOVED:continue
    rows.append((symbol.name,symbol['st_info']['bind'],symbol['st_info']['type'],symbol['st_other']['visibility'],target,symbol['st_value'],symbol['st_size']))
   symbols[name]=rows;continue
  # String-table byte offsets may be repacked, but every symbol above retains
  # its exact full name. Section names/types are keys below. The dynamic string
  # table is allocated and therefore still checked byte-for-byte.
  if name in ('.shstrtab','.strtab'):continue
  link=elf.get_section(h['sh_link']).name if h['sh_link'] else None
  info=elf.get_section(h['sh_info']).name if h['sh_type'] in ('SHT_REL','SHT_RELA') and h['sh_info'] else h['sh_info']
  sections[name]=(h['sh_type'],h['sh_flags'],h['sh_addr'],h['sh_size'],link,info,section.data())
 return {'header':header,'sections':sections,'symbols':symbols}

def loaded(data):
 return evidence(data)

def compact(path,compiler):
 before=path.read_bytes();expected=evidence(before)
 subprocess.run([str(compiler).removesuffix('gcc')+'objcopy','--remove-section=.xt.lit','--remove-section=.xt.prop',str(path)],check=True)
 after=path.read_bytes()
 if evidence(after)!=expected:raise ValueError('Current ELF compaction changed retained sections/symbols/relocations: '+str(path))
 if len(after)>len(before):raise ValueError('Current ELF compaction grew output')
 return {'before_bytes':len(before),'after_bytes':len(after),'removed_sections':sorted(REMOVED),'retained_sections_symbols_relocations_unchanged':True}

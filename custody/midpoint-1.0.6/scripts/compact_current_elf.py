"""Keep loader semantics while moving local symbols/debug metadata to a sidecar.

The full pre-compaction ELF is retained separately. Allocated sections, entrypoint,
imports/exports, global/weak symbols and every retained relocation target are
verified; referenced static symbols are included even when they are local.
"""
import hashlib,io,subprocess,tempfile
from pathlib import Path
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
PROFILE='loader-metadata-v3'
OPTIONS=('--remove-section=.xt.lit','--remove-section=.xt.prop','--discard-all')
REMOVED=frozenset(('.xt.lit','.xt.prop'))

def _metadata(section,elf):
 name=section.name
 candidate=name in REMOVED or name.startswith(('.debug_','.zdebug_'))
 if isinstance(section,RelocationSection) and section['sh_info']:
  target=elf.get_section(section['sh_info']).name
  candidate=candidate or target.startswith(('.debug_','.zdebug_'))
 if candidate and section['sh_flags']&2:raise ValueError('Refuse to remove allocated metadata')
 return candidate

def _symbol(elf,symbol):
 sh=symbol['st_shndx'];target=elf.get_section(sh).name if isinstance(sh,int) and sh else sh
 return (symbol.name,symbol['st_info']['bind'],symbol['st_info']['type'],symbol['st_other']['visibility'],target,symbol['st_value'],symbol['st_size'])

def evidence(data):
 elf=ELFFile(io.BytesIO(data));sections={};symbols={};referenced={};relocations={};symbol_sections={};order=[]
 names=[section.name for section in elf.iter_sections()]
 if len(names)!=len(set(names)):raise ValueError('Duplicate ELF section name')
 header={key:elf.header[key] for key in ('e_type','e_machine','e_version','e_entry','e_flags','e_ehsize','e_phoff','e_phentsize','e_phnum','e_shentsize')}
 header['ident']={key:elf.header['e_ident'][key] for key in ('EI_CLASS','EI_DATA','EI_VERSION','EI_OSABI','EI_ABIVERSION')}
 header['segments']=[]
 for segment in elf.iter_segments():
  h=segment.header;content=bytearray(segment.data())
  # PT_LOAD can include the ELF header. Section-table location/count change
  # after removing metadata; the retained section semantics are checked below.
  # All other bytes, including padding and program headers, stay identical.
  if h['p_type']=='PT_LOAD':
   fields=((40,8),(60,2),(62,2)) if elf.elfclass==64 else ((32,4),(48,2),(50,2))
   for offset,size in fields:
    start=offset-h['p_offset']
    if 0<=start and start+size<=len(content):content[start:start+size]=b'\0'*size
  header['segments'].append((tuple(h[key] for key in ('p_type','p_flags','p_offset','p_vaddr','p_paddr','p_filesz','p_memsz','p_align')),bytes(content)))
 for section in elf.iter_sections():
  if not isinstance(section,RelocationSection) or _metadata(section,elf):continue
  table=elf.get_section(section['sh_link'])
  if table['sh_type'] not in ('SHT_SYMTAB','SHT_DYNSYM'):raise ValueError('Relocation lacks a symbol table')
  rows=[]
  for rel in section.iter_relocations():
   index=rel['r_info_sym'];referenced.setdefault(table.name,set()).add(index)
   symbol=_symbol(elf,table.get_symbol(index))
   rows.append((rel['r_offset'],rel['r_info_type'],rel.entry.get('r_addend'),symbol))
  relocations[section.name]=rows
 for section in elf.iter_sections():
  name=section.name;h=section.header
  if _metadata(section,elf):continue
  order.append(name)
  if h['sh_type'] in ('SHT_SYMTAB','SHT_DYNSYM'):
   if h['sh_type']=='SHT_SYMTAB' and h['sh_flags']&2:raise ValueError('Refuse to compact allocated static symbols')
   link=elf.get_section(h['sh_link']).name if h['sh_link'] else None
   symbol_sections[name]=(h['sh_type'],h['sh_flags'],h['sh_addr'],h['sh_addralign'],h['sh_entsize'],link,h['sh_info'] if h['sh_type']=='SHT_DYNSYM' else None)
   rows=[]
   for index,symbol in enumerate(section.iter_symbols()):
    if h['sh_type']=='SHT_SYMTAB' and symbol['st_info']['bind']=='STB_LOCAL' and index not in referenced.get(name,set()):continue
    rows.append(_symbol(elf,symbol))
   symbols[name]=rows if h['sh_type']=='SHT_DYNSYM' else sorted(rows,key=repr)
   continue
  # Names and required static symbols are checked semantically. Dynamic strings
  # and every other allocated section still compare byte-for-byte.
  if name in ('.shstrtab','.strtab') and not h['sh_flags']&2:
   sections[name]=(h['sh_type'],h['sh_flags'],h['sh_addr'],h['sh_addralign'],h['sh_entsize'],h['sh_link'],h['sh_info']);continue
  link=elf.get_section(h['sh_link']).name if h['sh_link'] else None
  info=elf.get_section(h['sh_info']).name if isinstance(section,RelocationSection) and h['sh_info'] else h['sh_info']
  content=relocations[name] if isinstance(section,RelocationSection) else section.data()
  sections[name]=(h['sh_type'],h['sh_flags'],h['sh_addr'],h['sh_size'],h['sh_addralign'],h['sh_entsize'],link,info,content)
 return {'header':header,'order':order,'sections':sections,'symbols':symbols,'symbol_sections':symbol_sections}

def loaded(data):return evidence(data)
def sha(data):return hashlib.sha256(data).hexdigest()
def compact(path,compiler,debug_path=None):
 path=Path(path);before=path.read_bytes();expected=evidence(before)
 debug_path=Path(debug_path) if debug_path else path.with_suffix('.debug.elf')
 if debug_path.resolve()==path.resolve():raise ValueError('Debug ELF aliases compacted output')
 tool=str(compiler).removesuffix('gcc')+'objcopy'
 version=subprocess.check_output([tool,'--version'],text=True).splitlines()[0]
 with tempfile.TemporaryDirectory(prefix='current-elf-') as temporary:
  candidate=Path(temporary)/path.name;candidate.write_bytes(before)
  subprocess.run([tool,*OPTIONS,str(candidate)],check=True)
  after=candidate.read_bytes()
  if evidence(after)!=expected:raise ValueError('Current ELF compaction changed retained loader sections/symbols/relocations: '+str(path))
  if len(after)>len(before):raise ValueError('Current ELF compaction grew output')
  old=ELFFile(io.BytesIO(before));new=ELFFile(io.BytesIO(after));old_names={s.name for s in old.iter_sections()};new_names={s.name for s in new.iter_sections()}
  removed=old_names-new_names
  for name in removed:
   if not _metadata(old.get_section_by_name(name),old):raise ValueError('Unexpected removed ELF section: '+name)
  debug_path.parent.mkdir(parents=True,exist_ok=True);debug_path.write_bytes(before)
  path.write_bytes(after)
 return {'profile':PROFILE,'before_bytes':len(before),'after_bytes':len(after),'before_sha256':sha(before),'after_sha256':sha(after),
         'removed_sections':sorted(removed),'retained_loader_sections_symbols_relocations_unchanged':True,
         'original_elf_retained':True,'tool':version,'options':list(OPTIONS)}

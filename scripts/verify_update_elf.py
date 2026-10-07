"""Run production OTA ELF admission on the exact packaged application.

Target instructions are never executed. Import availability is witnessed in
the exact native candidate's symbol table; the host does not execute the target
linker's symbol resolver. The full transaction/lifecycle tests are separate.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import struct
import tempfile
from elftools.elf.elffile import ELFFile


def extract(text, signature):
    start=text.index(signature);opening=text.index('{',start);depth=0
    for pos in range(opening,len(text)):
        if text[pos]=='{':depth+=1
        elif text[pos]=='}':
            depth-=1
            if not depth:return text[start:pos+1]
    raise ValueError('Incomplete native admission function')


def public_exports(native):
    if native.elfclass!=32 or not native.little_endian:raise ValueError('Unexpected native ELF word layout')
    symbols={s.name:s for s in native.get_section_by_name('.symtab').iter_symbols()}
    def mapped(address,count):
        for section in native.iter_sections():
            start=section['sh_addr']
            if section['sh_flags']&2 and section['sh_type']!='SHT_NOBITS' and start<=address and address+count<=start+section['sh_size']:
                return section.data()[address-start:address-start+count]
        raise ValueError('Public export address outside native file sections')
    result={}
    for name in ('g_esp_libc_elfsyms','_ZZN8RiscBoot7Runtime3runEvE7symbols'):
        table=symbols.get(name)
        if table is None or table['st_size']%8:raise ValueError('Missing native public export table: '+name)
        rows=mapped(table['st_value'],table['st_size']);ended=False
        for at in range(0,len(rows),8):
            pointer,address=struct.unpack_from('<II',rows,at)
            if not pointer:
                if address or at!=len(rows)-8:raise ValueError('Invalid public export terminator')
                ended=True;break
            text=bytearray()
            for i in range(96):
                byte=mapped(pointer+i,1)[0]
                if not byte:break
                text.append(byte)
            else:raise ValueError('Unterminated public export name')
            symbol=text.decode('ascii')
            if not address or symbol in result:raise ValueError('Missing/duplicate public export address')
            result[symbol]=address
        if not ended:raise ValueError('Public export table lacks terminator')
    return result


def admission_source(text):
    """Preserve the selected Runtime's strict app/driver role implementation."""
    function = extract(text, 'bool admitElf(')
    if 'ElfRole role=' in function:
        # Include the exact production enum; never widen a driver to Either.
        start = text.index('enum class ElfRole ')
        enum = text[start:text.index(';', start) + 1]
        return enum + '\n' + function, 'provider?ElfRole::Driver:ElfRole::Application', 'ElfRole::Driver'
    if 'bool provider=' in function:
        return function, 'provider', 'true'
    raise ValueError('Native candidate source lacks provider ELF admission')


def cohort_admission_header(runtime, native_elf):
    """Compile the production admission function against actual native exports."""
    exported = public_exports(ELFFile(io.BytesIO(native_elf)))
    text = (Path(runtime) / 'src/ports/esp32s3/NativeBankStore.cpp').read_text()
    function, provider_role, _ = admission_source(text)
    return '''#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
#include "private/elf_types.h"
#include "RiscBankStoreV1.h"
extern "C" bool esp_elf_validate_file(const uint8_t*,size_t);
namespace CohortElf {
static uint32_t ticks=0;
static bool operationSafe(){return true;}
static uint32_t millis(){return ticks;}
static void vTaskDelay(unsigned n){ticks+=n;}
static uintptr_t elf_find_sym_default(const char* name){
 static const char* exports[]={''' + ','.join(json.dumps(s) for s in sorted(exported)) + '''};
 for(const char* symbol:exports)if(!strcmp(name,symbol))return 1;return 0;
}
''' + extract(text, 'bool allowedImport(') + '\n' + function + '''
static bool file(void* context,const char* path,bool provider){
 std::ifstream input(path,std::ios::binary);if(!input)return false;
 std::vector<uint8_t> bytes(std::istreambuf_iterator<char>(input),{});
 if(!admitElf(bytes.data(),bytes.size(),''' + provider_role + '''))return false;
 ++*static_cast<unsigned*>(context);return true;
}
}
'''


def verify(runtime, native_elf, app_elf, provider=False):
    runtime=Path(runtime);native=ELFFile(io.BytesIO(native_elf));app=ELFFile(io.BytesIO(app_elf))
    defined={s.name for s in native.get_section_by_name('.symtab').iter_symbols() if s.name and s['st_shndx']!='SHN_UNDEF'}
    imports=sorted({s.name for section in app.iter_sections() if section['sh_type'] in ('SHT_DYNSYM','SHT_SYMTAB') for s in section.iter_symbols() if s.name and s['st_shndx']=='SHN_UNDEF'})
    if not set(imports)<=defined:raise ValueError('App import missing from native candidate: '+str(set(imports)-defined))
    exported=public_exports(native)
    if not set(imports)<=set(exported):raise ValueError('App import absent from compiled public resolver tables')
    path=runtime/'src/ports/esp32s3/NativeBankStore.cpp';text=path.read_text()
    function = extract(text, 'bool admitElf(')
    driver_role = None
    if 'bool provider=' in function or 'ElfRole role=' in function:
        function, _, driver_role = admission_source(text)
    source='''#include <cassert>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
#include "private/elf_types.h"
#include "RiscBankStoreV1.h"
extern "C" bool esp_elf_validate_file(const uint8_t*,size_t);
static bool safe=true; static uint32_t ticks=0; static const char* missing=nullptr;
static bool operationSafe(){return safe;}
static uint32_t millis(){return ticks;}
static void vTaskDelay(unsigned n){ticks+=n;}
static const char* imports[]={'''+','.join(json.dumps(s) for s in imports)+'''};
static uintptr_t elf_find_sym_default(const char* name){
 if(missing&&!strcmp(name,missing))return 0;
 for(const char* symbol:imports)if(!strcmp(name,symbol))return 1;return 0;
}
'''+extract(text,'bool allowedImport(')+'\n'+function+'''
int main(int argc,char**argv){
 assert(argc==2);std::ifstream f(argv[1],std::ios::binary);assert(f);
 std::vector<uint8_t> data(std::istreambuf_iterator<char>(f),{});
 assert(admitElf(data.data(),data.size()));
 safe=false;assert(!admitElf(data.data(),data.size()));safe=true;
 for(const char* symbol:imports){missing=symbol;assert(!admitElf(data.data(),data.size()));}
 missing=nullptr;assert(admitElf(data.data(),data.size()));
}
'''
    if provider:
        if driver_role is None:raise ValueError('Native source lacks provider ELF admission')
        source=source.replace('admitElf(data.data(),data.size())','admitElf(data.data(),data.size(),'+driver_role+')')
    with tempfile.TemporaryDirectory(prefix='watch-update-elf-') as directory:
        root=Path(directory);(root/'check.cpp').write_text(source);(root/'app.elf').write_bytes(app_elf)
        includes=['-I'+str(runtime/'test/native_bank_stubs'),'-I'+str(runtime/'lib/elf_loader/include'),'-I'+str(runtime/'sdk/driver')]
        subprocess.run(['cc','-std=c11',*includes,'-c',str(runtime/'lib/elf_loader/src/esp_elf_validate.c'),'-o',str(root/'validate.o')],check=True)
        subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',*includes,str(root/'check.cpp'),str(root/'validate.o'),'-o',str(root/'check')],check=True)
        subprocess.run([str(root/'check'),str(root/'app.elf')],check=True)
    digest=lambda data:hashlib.sha256(data).hexdigest()
    return dict(native_bank_source_sha256=digest(path.read_bytes()),native_elf_sha256=digest(native_elf),
                app_elf_sha256=digest(app_elf),imports=imports,production_native_admission=True,
                all_imports_defined_in_native_candidate=True,compiled_public_exports={name:hex(exported[name]) for name in imports},
                each_missing_import_rejected=True,provider=provider,
                target_instructions_executed=False,target_symbol_resolver_host_executed=False)

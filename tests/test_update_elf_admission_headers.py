"""Extracted admission keeps canonical helpers and strict production roles."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_update_elf as admission

ALLOWED = 'bool allowedImport(const char*name){return RiscPackages::ordinaryImport(name);}'
ENUM = 'enum class ElfRole {Application,Driver,Either};'
FUNCTION = '''bool admitElf(const uint8_t*bytes,size_t n,ElfRole role=ElfRole::Application,
 const RuntimeProviders::NativeProviderPolicyV1*policy=nullptr){
 if(policy&&!RuntimeProviders::nativeProviderImageValid(*policy,bytes,n))return false;
 return RiscPackages::admitElf(bytes,n,role,policy!=nullptr,{esp_elf_validate_file,
  [](const char*name){return allowedImport(name)&&elf_find_sym_default(name);},
  operationSafe,[](){vTaskDelay(1);},[]()->uint32_t{return millis();}});
}'''
SOURCE = ALLOWED + '\n' + ENUM + '\n' + FUNCTION
HELPER = '#include "runtime/packages/ElfAdmission.h"'
POLICY = '#include "runtime/drivers/NativeProviderPolicyValidationV1.h"'


class Symbol(dict):
    def __init__(self, name, section):
        super().__init__(st_shndx=section)
        self.name = name


class SymbolTable(dict):
    def __init__(self, symbols):
        super().__init__(sh_type='SHT_DYNSYM')
        self.symbols = symbols

    def iter_symbols(self):
        return iter(self.symbols)


class AdmissionHeaders(unittest.TestCase):
    def test_legacy_source_does_not_require_new_headers(self):
        legacy = 'bool allowedImport(const char*name){return name!=nullptr;}\n'
        legacy += 'bool admitElf(const void*bytes,int n,bool provider=false){return provider;}'
        self.assertEqual(admission.admission_includes(legacy), '')
        self.assertEqual(admission.admission_source(legacy)[1:], ('provider', 'true'))

    def test_cohort_preserves_exact_wrappers_and_driver_role(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            source = runtime / 'src/ports/esp32s3/NativeBankStore.cpp'
            source.parent.mkdir(parents=True)
            source.write_text(SOURCE)
            with patch.object(admission, 'ELFFile'), patch.object(admission, 'public_exports', return_value={'memcpy': 1}):
                header = admission.cohort_admission_header(runtime, b'native')
        for exact in (HELPER, POLICY, ALLOWED, ENUM, FUNCTION):
            self.assertIn(exact, header)
        self.assertLess(header.index(HELPER), header.index('namespace CohortElf'))
        self.assertIn('provider?ElfRole::Driver:ElfRole::Application', header)
        self.assertNotIn('provider?ElfRole::Either', header)

    def test_standalone_uses_same_headers_source_and_negative_checks(self):
        native = Mock()
        native.get_section_by_name.return_value = SymbolTable([Symbol('memcpy', 1)])
        app = Mock()
        app.iter_sections.return_value = [SymbolTable([Symbol('memcpy', 'SHN_UNDEF')])]
        for provider in (False, True):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temp:
                runtime = Path(temp)
                source = runtime / 'src/ports/esp32s3/NativeBankStore.cpp'
                source.parent.mkdir(parents=True)
                source.write_text(SOURCE)
                compiled = []

                def run(command, **kwargs):
                    if command[0] == 'c++':
                        self.assertIn('-I' + str(runtime / 'src'), command)
                        compiled.append(Path(next(part for part in command if part.endswith('check.cpp'))).read_text())

                with patch.object(admission, 'ELFFile', side_effect=[native, app]), \
                        patch.object(admission, 'public_exports', return_value={'memcpy': 1}), \
                        patch.object(admission.subprocess, 'run', side_effect=run):
                    proof = admission.verify(runtime, b'native', b'application', provider=provider)
                self.assertEqual(len(compiled), 1)
                for exact in (HELPER, POLICY, ALLOWED, ENUM, FUNCTION):
                    self.assertIn(exact, compiled[0])
                call = 'admitElf(data.data(),data.size()' + (',ElfRole::Driver)' if provider else ')')
                self.assertIn('safe=false;assert(!' + call + ')', compiled[0])
                self.assertIn('missing=symbol;assert(!' + call + ')', compiled[0])
                self.assertTrue(proof['each_missing_import_rejected'])
                self.assertEqual(proof['provider'], provider)


if __name__ == '__main__':
    unittest.main()

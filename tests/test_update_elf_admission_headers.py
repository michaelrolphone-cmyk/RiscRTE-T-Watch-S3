"""Extracted admission keeps canonical helpers and strict production roles."""
from pathlib import Path
import struct
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


def native_fixture(abi=3, *, allocated=True, section_type=1, machine=94,
                   symbol_count=1, symbol_section=1, offset=0, symbol_size=None):
    """Minimal real ELF32 fixture; no compiler or target execution involved."""
    marker = ('RISC_PAIRED_STORE_ABI:' + str(abi)).encode() + b'\0'
    names = b'\0.rodata\0.symtab\0.strtab\0.shstrtab\0'
    strings = b'\0risc_paired_store_abi\0'
    rows = [bytes(16)] + [struct.pack('<IIIBBH', 1, 0x3c000000 + offset,
            len(marker) if symbol_size is None else symbol_size, 0x11, 0, symbol_section)
            for _ in range(symbol_count)]
    raw = bytearray(bytes(52))
    sections = [bytes(40)]
    for name, kind, flags, address, data, link, info, size in (
            ('.rodata', section_type, 2 if allocated else 0, 0x3c000000, marker, 0, 0, 0),
            ('.symtab', 2, 0, 0, b''.join(rows), 3, 1, 16),
            ('.strtab', 3, 0, 0, strings, 0, 0, 0),
            ('.shstrtab', 3, 0, 0, names, 0, 0, 0)):
        raw.extend(bytes((-len(raw)) % 4))
        at = len(raw)
        raw.extend(data)
        sections.append(struct.pack('<10I', names.index(name.encode()), kind, flags,
                                    address, at, len(data), link, info, 4, size))
    raw.extend(bytes((-len(raw)) % 4))
    at = len(raw)
    raw.extend(b''.join(sections))
    ident = b'\x7fELF\x01\x01\x01' + bytes(9)
    raw[:52] = struct.pack('<16sHHIIIIIHHHHHH', ident, 2, machine, 1, 0, 0, at, 0,
                          52, 0, 0, 40, len(sections), 4)
    return bytes(raw)


class NativeStoreAbi(unittest.TestCase):
    def test_exact_allocated_native_marker_for_each_explicit_abi(self):
        for abi in (1, 2, 3):
            proof = admission.verify_native_store_abi(native_fixture(abi), abi)
            self.assertEqual(proof['store_abi'], abi)
            self.assertEqual(proof['marker_address'], 0x3c000000)
            self.assertEqual(proof['marker_bytes'], 24)

    def test_old_wrong_ambiguous_or_unallocated_native_markers_are_rejected(self):
        for raw in (native_fixture(1), native_fixture(2), native_fixture(allocated=False),
                    native_fixture(section_type=8), native_fixture(machine=3),
                    native_fixture(symbol_count=0), native_fixture(symbol_count=2),
                    native_fixture(symbol_section=0), native_fixture(offset=-1),
                    native_fixture(offset=1), native_fixture(symbol_size=23)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                admission.verify_native_store_abi(raw, 3)

    def test_old_owner_and_unknown_markers_cannot_hide_in_other_sections(self):
        for marker in (b'RISC_PAIRED_STORE_ABI:1\0', b'RISC_PAIRED_STORE_ABI:2\0',
                       b'RISC_PAIRED_STORE_ABI:4\0', b'RISC_OWNER_INSTALLER:1\0',
                       b'RTE_OWNER_MAINTENANCE=1\0'):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'Conflicting or owner'):
                admission.verify_native_store_abi(native_fixture() + marker, 3)

    def test_debug_only_abi3_cannot_replace_old_allocated_marker(self):
        with self.assertRaisesRegex(ValueError, 'allocated store ABI differs'):
            admission.verify_native_store_abi(native_fixture(2) + b'RISC_PAIRED_STORE_ABI:3\0', 3)

    def test_unknown_abi_is_rejected(self):
        for abi in (0, 4, True, '3'):
            with self.assertRaisesRegex(ValueError, 'Unsupported native store ABI'):
                admission.verify_native_store_abi(native_fixture(), abi)

    def test_explicit_abi_is_checked_before_any_header_or_target_admission(self):
        with patch.object(admission, 'verify_native_store_abi', side_effect=ValueError('wrong ABI')) as check:
            with self.assertRaisesRegex(ValueError, 'wrong ABI'):
                admission.cohort_admission_header('/unused', b'native', store_abi=3)
            check.assert_called_once_with(b'native', 3)
            with self.assertRaisesRegex(ValueError, 'wrong ABI'):
                admission.verify('/unused', b'native', b'app', store_abi=3)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Unit negatives for effective inputs and controlled-process admission."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_idf61_build as producer
import native_idf61_provenance as provenance


class ProvenanceContracts(unittest.TestCase):
    def test_profile_redefinition_undef_and_injection_rejected(self):
        expected = {'RISC_INSTALLED_APP_CAPACITY': '64'}
        flags = ['gcc', '-DRISC_INSTALLED_APP_CAPACITY=64']
        self.assertEqual(provenance.compiler_definitions(flags, expected), expected)
        for extra in (['-URISC_INSTALLED_APP_CAPACITY'], ['-D', 'RISC_INSTALLED_APP_CAPACITY=1'], ['@/tmp/flags'], ['-Wp,-URISC_INSTALLED_APP_CAPACITY']):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                provenance.compiler_definitions(flags + extra, expected)

    def test_only_locked_response_bytes_are_consumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blobs = {'response_cflags': b'-DRISC_INSTALLED_APP_CAPACITY=64'}
            rows = {'response_cflags': {'path': 'toolchain/cflags'}}
            expanded = provenance.expand_response_files(['gcc', '@toolchain/cflags'], root, root, blobs, rows)
            provenance.compiler_definitions(expanded, {'RISC_INSTALLED_APP_CAPACITY': '64'})
            for raw in (b'@/tmp/unlocked', b'@toolchain/cflags'):
                with self.assertRaises(ValueError):
                    provenance.expand_response_files(['@toolchain/cflags'], root, root, {'response_cflags': raw}, rows)

    def test_effective_configs_reject_stale_header_json_and_security(self):
        def header(values):
            return ''.join('#define CONFIG_' + key + ' ' + ('1' if value is True else str(value)) + '\n' for key, value in values.items()).encode()
        blobs = {'sdkconfig': ''.join('CONFIG_' + key + '=' + ('y' if value is True else str(value)) + '\n' for key, value in provenance.APP_CONFIG.items()).encode(),
                 'sdkconfig_json': json.dumps(provenance.APP_CONFIG).encode(), 'sdkconfig_header': header(provenance.APP_CONFIG),
                 'bootloader_sdkconfig': json.dumps(provenance.BOOT_CONFIG).encode(), 'bootloader_sdkconfig_header': header(provenance.BOOT_CONFIG)}
        provenance.effective_sdkconfig(blobs)
        for key in provenance.APP_CONFIG:
            values = dict(provenance.APP_CONFIG); values[key] = False if values[key] is True else 123
            with self.subTest(key=key), self.assertRaises(ValueError):
                provenance.effective_sdkconfig({**blobs, 'sdkconfig_json': json.dumps(values).encode()})
        for where in ('sdkconfig_header', 'bootloader_sdkconfig_header'):
            for forbidden in provenance.FORBIDDEN_CONFIG:
                for suffix in ('', ' 0', ' 1'):
                    with self.subTest(where=where, flag=forbidden, suffix=suffix), self.assertRaises(ValueError):
                        provenance.effective_sdkconfig({**blobs, where: blobs[where] + ('#define CONFIG_' + forbidden + suffix + '\n').encode()})
        with self.assertRaises(ValueError):
            provenance.effective_sdkconfig({**blobs, 'sdkconfig_header': blobs['sdkconfig_header'] + b'#undef CONFIG_SPIRAM_MODE_OCT\n'})

    def test_detached_receipts_are_not_build_proof(self):
        for proof in (None, {}, {'fresh_build': True, 'same_process_qualification': True}):
            with self.assertRaisesRegex(ValueError, 'fresh controlled build'):
                producer.validate_build_proof(proof, {}, Path('.'), Path('/compiler'))

    def test_injected_build_environment_is_removed(self):
        bad = {name: '/injected' for name in ('CC','CXX','CFLAGS','CPPFLAGS','CPATH','CPLUS_INCLUDE_PATH','LDFLAGS','LD_PRELOAD','PYTHONPATH','CMAKE_TOOLCHAIN_FILE','RISC_SOURCE_SHA','X4_VERSION','IDF_EXTRA_ACTIONS_PATH','XTENSA_GNU_CONFIG','XTENSA_CORE')}
        with mock.patch.dict(os.environ, bad):
            clean = producer.clean_environment(Path('/sdk'), Path('/compiler/bin/xtensa-esp-elf-gcc'))
        self.assertFalse(set(bad) & set(clean))
        self.assertEqual(clean['CCACHE_DISABLE'], '1')
        self.assertEqual(clean['IDF_PATH'], '/sdk')

    def test_build_outputs_and_producer_must_not_escape_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); product = root / 'product'; product.mkdir()
            sources = {'product': product}
            producer.validate_layout(sources, root / 'build', root / 'output', product)
            for build, out, selected in ((product / 'build', root / 'output', product), (root / 'build', product / 'output', product), (root / 'build', root / 'build/out', product), (root / 'build', root / 'output', root / 'wrong')):
                with self.subTest(build=build, output=out, selected=selected), self.assertRaises(ValueError):
                    producer.validate_layout(sources, build, out, selected)

    def test_target_build_is_always_single_job(self):
        sources = {role: Path('/' + role) for role in ('runtime', 'product', 'sdk')}
        commands = producer.build_commands(sources, Path('/new-build'), 'a'*40, Path('/tools/cmake'))
        self.assertEqual(commands[0][-1], 'reconfigure')
        self.assertEqual(commands[1], ['/tools/cmake', '--build', '/new-build', '--', '-j1'])
        self.assertIn('SDKCONFIG=/new-build/sdkconfig', commands[0])
        self.assertEqual(producer.clean_environment(Path('/sdk'), Path('/gcc'))['CMAKE_BUILD_PARALLEL_LEVEL'], '1')

    def test_stale_or_empty_dependency_records_are_rejected(self):
        valid = 'obj/a.o: #deps 1, deps mtime 42 (VALID)\n    /source/a.c\n\n'
        objects, headers = producer.dependency_rows(valid, Path('/build'))
        self.assertEqual(objects, {Path('/build/obj/a.o')})
        self.assertEqual(headers, {Path('/source/a.c')})
        for text in ('', valid.replace('VALID', 'STALE'), 'unsupported\n'):
            with self.assertRaises(ValueError):
                producer.dependency_rows(text, Path('/build'))

    def test_compiler_child_discovery_uses_clean_build_environment(self):
        with mock.patch.dict(os.environ, {'GCC_EXEC_PREFIX': '/injected', 'COMPILER_PATH': '/injected'}):
            env = producer.clean_environment(Path('/sdk'), Path('/compiler/bin/xtensa-esp-elf-gcc'))
            with mock.patch.object(producer, 'run', return_value='/compiler/libexec/cc1\n') as query:
                self.assertEqual(producer.compiler_child(Path('/compiler/bin/xtensa-esp-elf-gcc'), 'cc1', env), '/compiler/libexec/cc1')
            self.assertIs(query.call_args.kwargs['env'], env)
            self.assertNotIn('GCC_EXEC_PREFIX', env)
            self.assertNotIn('COMPILER_PATH', env)
        with mock.patch.object(producer, 'run', return_value='cc1\n'), self.assertRaises(ValueError):
            producer.compiler_child(Path('/compiler/bin/xtensa-esp-elf-gcc'), 'cc1', env)

    def test_exact_compiler_family_and_xtensa_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'bin').mkdir(); (root / 'lib').mkdir()
            compiler = root / 'bin/xtensa-esp-elf-gcc'
            for filename in provenance.COMPILER_FAMILY_NAMES.values():
                (root / 'bin' / filename).write_bytes(filename.encode())
            (root / 'lib/xtensa_esp32s3.so').write_bytes(b'S3 config')
            def probe(args, **kwargs):
                self.assertNotIn('XTENSA_GNU_CONFIG', kwargs['env'])
                return {'--version': 'GCC15.2.0 esp-15.2.0_20251204\n', '-dumpmachine': 'xtensa-esp-elf\n', '-print-multi-directory': 'esp32s3\n'}[args[-1]]
            with mock.patch.dict(os.environ, {'XTENSA_GNU_CONFIG': '/wrong'}), mock.patch.object(provenance.subprocess, 'check_output', probe):
                family = provenance.compiler_family(compiler)
            self.assertEqual(set(family), {'gcc','g++','s3-gcc','s3-g++','xtensa-config'})
            wrapper = str(root / 'bin/xtensa-esp32s3-elf-gcc')
            self.assertEqual(provenance.compiler_command([wrapper,'-c','file.c'],compiler,family), 's3-gcc')
            self.assertEqual(provenance.compiler_command([str(compiler),'-mdynconfig=xtensa_esp32s3.so','-c','file.c'],compiler,family), 'gcc')
            for args in ([str(compiler),'-c','file.c'], ['/other/xtensa-esp32s3-elf-gcc','-c','file.c'],
                         ['ccache',wrapper,'-c','file.c'], [wrapper,'-mdynconfig=xtensa_esp32.so'],
                         [wrapper,'-Wa,--dynconfig=other'], [wrapper,'-B/other-tools'], [wrapper,'--specs=evil'],
                         [wrapper,'@unlocked'], [str(compiler),'-mdynconfig=xtensa_esp32s3.so','-mdynconfig=xtensa_esp32.so']):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    provenance.compiler_command(args,compiler,family)
            for result in ('wrong-compiler 8.4.0', 'riscv32-esp-elf', 'esp32'):
                with mock.patch.object(provenance.subprocess, 'check_output', return_value=result), self.assertRaises(ValueError):
                    provenance.compiler_family(compiler)

    def test_ninja_phony_alias_requires_exact_graph_and_retains_real_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / 'esp-idf/esp_system/ld/sections.ld'
            real.parent.mkdir(parents=True); real.write_bytes(b'actual linker script')
            archive = root / 'runtime.a'; archive.write_bytes(b'actual linked archive')
            rows = {
                '__ldgen_output_sections.ld': '__ldgen_output_sections.ld:\n  input: phony\n    CMakeFiles/__ldgen_output_sections.ld\n    runtime.a\n  outputs:\n    app.elf\n',
                'CMakeFiles/__ldgen_output_sections.ld': 'CMakeFiles/__ldgen_output_sections.ld:\n  input: phony\n    esp-idf/esp_system/ld/sections.ld\n    || runtime.a\n  outputs:\n    __ldgen_output_sections.ld\n',
            }
            paths, aliases = producer.ninja_input_paths('__ldgen_output_sections.ld\n', root, rows.__getitem__)
            self.assertEqual(paths, {real, archive})
            self.assertEqual(set(aliases), set(rows))
            self.assertEqual(aliases['__ldgen_output_sections.ld']['query'], rows['__ldgen_output_sections.ld'])
            # An extension/SDK-looking name is never sufficient: the actual
            # graph must say phony, with the exact queried target identity.
            for bad in (rows['__ldgen_output_sections.ld'].replace('input: phony', 'input: CUSTOM_COMMAND'),
                        rows['__ldgen_output_sections.ld'].replace('__ldgen_output_sections.ld:', 'different:'),
                        rows['__ldgen_output_sections.ld'].replace('  outputs:', '  unknown:')):
                with self.subTest(query=bad), self.assertRaises(ValueError):
                    producer.ninja_input_paths('__ldgen_output_sections.ld\n', root, lambda _: bad)
            # A removed real linker input cannot hide behind a phony wrapper.
            real.unlink()
            missing = 'esp-idf/esp_system/ld/sections.ld'
            rows[missing] = missing + ':\n  input: CUSTOM_COMMAND\n    template.in\n  outputs:\n    app.elf\n'
            with self.assertRaisesRegex(ValueError, 'Missing non-phony'):
                producer.ninja_input_paths('__ldgen_output_sections.ld\n', root, rows.__getitem__)

    def test_ninja_phony_cycles_external_missing_and_empty_order_only_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = {'a': 'a:\n  input: phony\n    b\n  outputs:\n',
                    'b': 'b:\n  input: phony\n    a\n  outputs:\n'}
            with self.assertRaisesRegex(ValueError, 'Cyclic'):
                producer.ninja_input_paths('a\n', root, rows.__getitem__)
            with self.assertRaisesRegex(ValueError, 'Missing external'):
                producer.ninja_input_paths('/nonexistent-external-source-header\n', root, rows.__getitem__)
            # Empty order-only phony nodes have no file semantics. Their exact
            # graph evidence remains recorded, rather than invented bytes.
            paths, aliases = producer.ninja_input_paths('empty\n', root, lambda _: 'empty:\n  input: phony\n  outputs:\n')
            self.assertEqual(paths, set()); self.assertEqual(aliases['empty']['inputs'], [])

    def test_map_must_match_output_and_singleton_elf_address(self):
        symbol = {'st_value': 0x40370000, 'st_shndx': 1}
        class Symbol(dict):
            name = 'call_start_cpu0'
        class Table:
            def iter_symbols(self):
                return [Symbol(symbol)]
        class Elf:
            def __init__(self, stream): pass
            def get_section_by_name(self, name): return Table()
        valid = b'Memory Configuration\nLinker script and memory map\nLOAD sdk/lib.a\n 0x40370000 call_start_cpu0\nOUTPUT(bootloader.elf elf32-xtensa-le)\nCross Reference Table\n'
        with mock.patch('elftools.elf.elffile.ELFFile', Elf):
            self.assertEqual(producer.map_inputs(valid, Path('/build'), Path('/build/bootloader.elf'), b'elf'), {Path('/build/sdk/lib.a')})
            for bad in (valid.replace(b'bootloader.elf', b'other.elf'), valid.replace(b'0x40370000', b'0x40370004'), valid.replace(b'OUTPUT(', b' 0x40370004 call_start_cpu0\nOUTPUT('), valid.replace(b'Linker script and memory map', b'invalid')):
                with self.subTest(raw=bad), self.assertRaises(ValueError):
                    producer.map_inputs(bad, Path('/build'), Path('/build/bootloader.elf'), b'elf')
            # A duplicate address elsewhere is not admitted from cross references.
            outside = valid + b' 0x40370004 call_start_cpu0\n'
            producer.map_inputs(outside, Path('/build'), Path('/build/bootloader.elf'), b'elf')

    def test_mutated_controlled_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'file'; path.write_bytes(b'original')
            proof = producer.BuildProof(); proof.token = producer._TOKEN; proof.sources = {}; proof.build = Path(tmp); proof.compiler = Path('/compiler')
            proof.files = {str(path): {**producer.file_row(path), 'kind': 'generated'}}; proof.report = {'test': True}
            self.assertEqual(producer.validate_build_proof(proof, {}, Path(tmp), Path('/compiler')), {'test': True})
            path.write_bytes(b'mutated')
            with self.assertRaisesRegex(ValueError, 'input changed'):
                producer.validate_build_proof(proof, {}, Path(tmp), Path('/compiler'))


if __name__ == '__main__':
    unittest.main()

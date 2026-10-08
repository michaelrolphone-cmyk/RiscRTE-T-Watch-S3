"""Real compiler regressions for shadow inputs and false provenance receipts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lifecycle_source_custody import SourceCustody, provider_command, PROVIDER_FLAGS, verify_dependencies


class SourceCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='watch18-custody-test-')
        self.base = Path(self.temporary.name)
        self.repo = self.base / 'source'; self.repo.mkdir()
        self.out = self.base / 'build'; self.out.mkdir()
        (self.repo / 'include').mkdir(); (self.repo / 'shadow').mkdir()
        (self.repo / '.gitignore').write_text('shadow/\n*.gch\n*.pch\n')
        (self.repo / 'include/value.h').write_text('#define VALUE 4\n')
        (self.repo / 'app.c').write_text('#include <value.h>\nint value(void) {return VALUE;}\n')
        self.git('init', '-q'); self.git('add', '.')
        self.git('-c', 'user.name=Custody Test', '-c', 'user.email=custody@example.invalid', 'commit', '-qm', 'Pinned fixture')
        self.pin = self.git('rev-parse', 'HEAD').strip()
        self.command = ['cc', '-std=c11', '-I' + str(self.repo / 'shadow'), '-I' + str(self.repo / 'include'),
                        '-c', str(self.repo / 'app.c'), '-o', str(self.out / 'app.o')]

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True)

    def guard(self, generated=None):
        return SourceCustody({'fixture': self.repo}, {'fixture': self.pin}, generated or {})

    def test_clean_compile_and_verification(self):
        guard = self.guard(); proof = guard.compile(self.command)
        self.assertEqual(set(proof), {'fixture:app.c', 'fixture:include/value.h'})
        self.assertTrue((self.out / 'app.o').is_file())
        verify_dependencies(guard, self.command, proof)

    def test_ignored_header_shadow_is_rejected_before_compile(self):
        (self.repo / 'shadow/value.h').write_text('#define VALUE 99\n')
        self.assertEqual(self.git('status', '--porcelain'), '')
        with self.assertRaisesRegex(ValueError, 'not in pinned source'):
            self.guard().compile(self.command)
        self.assertFalse((self.out / 'app.o').exists())

    def test_changed_tracked_header_is_rejected(self):
        (self.repo / 'include/value.h').write_text('#define VALUE 99\n')
        with self.assertRaisesRegex(ValueError, 'differs from pinned source'):
            self.guard().compile(self.command)

    def test_ignored_valid_precompiled_header_is_rejected(self):
        header = self.repo / 'include/value.h'
        subprocess.run(['cc', '-x', 'c-header', str(header), '-o', str(header) + '.gch'], check=True)
        self.assertEqual(self.git('status', '--porcelain'), '')
        with self.assertRaisesRegex(ValueError, 'Precompiled compiler input'):
            self.guard().compile(self.command)
        self.assertFalse((self.out / 'app.o').exists())

    def test_unused_ignored_pch_is_rejected(self):
        (self.repo / 'shadow/unused.pch').write_bytes(b'unqualified')
        with self.assertRaisesRegex(ValueError, 'Precompiled compiler input'):
            self.guard()

    def test_recorded_provenance_cannot_omit_or_invent_dependencies(self):
        guard = self.guard(); proof = guard.check(self.command)
        omitted = dict(proof); omitted.pop('fixture:include/value.h')
        invented = {**proof, 'fixture:unused.h': proof['fixture:include/value.h']}
        wrong_hash = json.loads(json.dumps(proof)); wrong_hash['fixture:include/value.h']['sha256'] = '0' * 64
        for bad in [omitted, invented, wrong_hash]:
            with self.subTest(receipt=bad), self.assertRaisesRegex(ValueError, 'Recorded compiler dependency custody'):
                verify_dependencies(guard, self.command, bad)

    def test_exact_generated_input_and_rewrite_rejection(self):
        header = self.out / 'generated.h'; raw = b'#define GENERATED_VALUE 7\n'; header.write_bytes(raw)
        command = self.command[:1] + ['-include', str(header)] + self.command[1:]
        guard = self.guard({header: raw}); proof = guard.check(command)
        self.assertIn('generated:generated.h', proof)
        header.write_bytes(b'#define GENERATED_VALUE 8\n')
        with self.assertRaisesRegex(ValueError, 'Generated compiler input changed'):
            verify_dependencies(guard, command, proof)

    def test_linked_header_is_rejected(self):
        (self.repo / 'shadow/value.h').symlink_to(self.repo / 'include/value.h')
        with self.assertRaisesRegex(ValueError, 'Linked compiler input'):
            self.guard().check(self.command)

    def test_cpp17_dependency_branch_is_checked(self):
        (self.repo / 'app.cpp').write_text('#if __cplusplus >= 201703L\n#include <new_language.h>\n#endif\nint value() {return 1;}\n')
        self.git('add', 'app.cpp'); self.git('-c', 'user.name=Custody Test', '-c', 'user.email=custody@example.invalid', 'commit', '-qm', 'Language fixture')
        self.pin = self.git('rev-parse', 'HEAD').strip()
        (self.repo / 'shadow/new_language.h').write_text('#define UNPINNED 1\n')
        command = ['c++', '-std=c++17', '-I' + str(self.repo / 'shadow'), '-c', str(self.repo / 'app.cpp'), '-o', str(self.out / 'app.o')]
        with self.assertRaisesRegex(ValueError, 'not in pinned source'):
            self.guard().compile(command)
        self.assertFalse((self.out / 'app.o').exists())

    def test_provider_requires_exact_cpp17_record_flags(self):
        command = provider_command('/tool/gcc', self.repo, self.out, PROVIDER_FLAGS)
        self.assertIn('-std=c++17', command)
        with self.assertRaisesRegex(ValueError, 'provider compiler flags differ'):
            provider_command('/tool/gcc', self.repo, self.out, ['-std=c++11', *PROVIDER_FLAGS[1:]])


if __name__ == '__main__':
    unittest.main()

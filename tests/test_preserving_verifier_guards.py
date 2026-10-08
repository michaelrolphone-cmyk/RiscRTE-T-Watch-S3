"""Compiler-selected inputs must remain pinned even when Git hides a shadow."""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from qualified_source_custody import run_qualified


@unittest.skipUnless(shutil.which('c++') and shutil.which('git'), 'C++ and Git required')
class CompilerCustody(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='preserving-custody-')
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Custody test')
        self.git('config', 'user.email', 'custody-test@example.invalid')
        self.header = self.root / 'test/native_bank_stubs/fixture.h'
        self.header.parent.mkdir(parents=True)
        self.header.write_text('#define VALUE 0\n')
        self.main = self.root / 'main.cpp'
        self.main.write_text('#include <fixture.h>\nint main(){return VALUE;}\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Pinned compiler fixtures')
        self.pin = self.git('rev-parse', 'HEAD').strip()
        self.command = ['c++', '-std=c++17', '-Werror',
                        '-I' + str(self.root / 'test'), '-I' + str(self.header.parent),
                        str(self.main), '-o', str(self.base / 'program')]

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True)

    def compile(self, generated=None):
        run_qualified(self.command, sources={self.root: self.pin}, generated=generated)

    def test_pinned_closure_compiles(self):
        self.compile()
        self.assertTrue((self.base / 'program').is_file())

    def test_untracked_shadow_rejected_even_when_clean_accepts(self):
        (self.root / 'test/fixture.h').write_text('#define VALUE 7\n')
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=no'), '')
        with self.assertRaisesRegex(ValueError, 'not in pinned source'):
            self.compile()
        self.assertFalse((self.base / 'program').exists())

    def test_ignored_shadow_rejected_even_when_git_status_is_empty(self):
        (self.root / 'test/fixture.h').write_text('#define VALUE 7\n')
        (self.root / '.git/info/exclude').write_text('/test/fixture.h\n')
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=all'), '')
        with self.assertRaisesRegex(ValueError, 'not in pinned source'):
            self.compile()

    def test_modified_tracked_header_rejected(self):
        self.header.write_text('#define VALUE 7\n')
        with self.assertRaisesRegex(ValueError, 'differs from pinned source'):
            self.compile()

    def test_ignored_precompiled_header_cannot_override_tracked_header(self):
        original = self.header.read_bytes()
        self.header.write_text('#define VALUE 7\n')
        precompiled = pathlib.Path(str(self.header) + '.gch')
        subprocess.run(['c++', '-std=c++17', '-x', 'c++-header', str(self.header), '-o', str(precompiled)], check=True)
        self.header.write_bytes(original)
        (self.root / '.git/info/exclude').write_text('*.gch\n')
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=all'), '')
        with self.assertRaisesRegex(ValueError, 'Precompiled compiler input is not qualified'):
            self.compile()
        self.assertFalse((self.base / 'program').exists())

    def test_linked_header_rejected(self):
        target = self.base / 'copied.h'
        target.write_bytes(self.header.read_bytes())
        self.header.unlink()
        self.header.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Linked compiler input'):
            self.compile()

    def test_source_revision_change_rejected(self):
        self.git('commit', '--allow-empty', '-qm', 'Different source')
        with self.assertRaisesRegex(ValueError, 'source revision differs'):
            self.compile()

    def test_outside_source_header_requires_exact_generated_allowance(self):
        generated = self.base / 'generated'
        generated.mkdir()
        header = generated / 'fixture.h'
        header.write_text('#define VALUE 9\n')
        self.command.insert(1, '-I' + str(generated))
        with self.assertRaisesRegex(ValueError, 'outside pinned sources'):
            self.compile()
        self.compile({header: header.read_bytes()})
        with self.assertRaisesRegex(ValueError, 'Generated compiler input changed'):
            self.compile({header: b'#define VALUE 10\n'})

    def test_every_translation_unit_is_checked(self):
        second = self.root / 'other.cpp'
        second.write_text('int other(){return 0;}\n')
        self.git('add', 'other.cpp')
        self.git('commit', '-qm', 'Second translation unit')
        self.pin = self.git('rev-parse', 'HEAD').strip()
        self.command.insert(-2, str(second))
        self.compile()
        (self.root / 'test/fixture.h').write_text('#define VALUE 7\n')
        with self.assertRaisesRegex(ValueError, 'not in pinned source'):
            self.compile()


if __name__ == '__main__':
    unittest.main()

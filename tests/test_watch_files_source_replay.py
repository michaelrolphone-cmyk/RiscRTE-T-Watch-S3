"""Contract tests for the source-only retained Watch Files replay entry point."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import rebuild_watch_files_from_source as replay


class SourceReplayTests(unittest.TestCase):
    def test_exact_public_pins(self):
        self.assertEqual(replay.PINS, {
            'system_predecessor': 'e3fd26c2257cef91c8f6a7b98065b52f1db7a54d',
            'system': '66282802bb498590fcbab4eba871ff40cc3ddafd',
            'watch': 'e0b43ef70f312cc512861926109ebe99f41c964d',
            'utilities': 'fc0bdbbbc600ce891e60c44d091fce0586ade7d8',
            'runtime': '3b90cd11cf0ff4e8116bb54d2d9eb9c7c67a148b',
        })

    def test_source_guard_rejects_wrong_pin(self):
        with patch.object(replay, 'git', return_value='wrong'):
            with self.assertRaisesRegex(ValueError, 'Wrong source pin'):
                replay.check_source(Path('/source'), 'expected')

    def test_source_guard_rejects_dirty_or_untracked(self):
        for dirty in (' M file.c', 'M  file.c', '?? shadow.h'):
            with self.subTest(dirty=dirty), patch.object(replay, 'git', side_effect=['pin', dirty]):
                with self.assertRaisesRegex(ValueError, 'not clean'):
                    replay.check_source(Path('/source'), 'pin')
        with patch.object(replay, 'git', side_effect=['pin', '']):
            replay.check_source(Path('/source'), 'pin')

    def test_output_rejects_existing_and_source_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'fresh'):
                replay.check_output(root, [])
            with self.assertRaisesRegex(ValueError, 'outside'):
                replay.check_output(root / 'source' / 'out', [root / 'source'])
            with self.assertRaisesRegex(ValueError, 'outside'):
                replay.check_output(root / 'out', [root / 'out' / 'source'])
            replay.check_output(root / 'out', [root / 'source'])

    def test_compiler_identity(self):
        cc = Path('/tools/xtensa-esp32s3-elf-gcc')
        good = 'xtensa-esp32s3-elf-gcc (crosstool-NG esp-2021r2-patch5) 8.4.0\n'
        with patch.object(replay.subprocess, 'check_output', side_effect=[good, 'xtensa-esp32s3-elf\n']):
            self.assertIn('8.4.0', replay.check_compiler(cc))
        for version, target in ((good, 'xtensa-esp32-elf'), ('gcc 12.0', 'xtensa-esp32s3-elf')):
            with patch.object(replay.subprocess, 'check_output', side_effect=[version, target]):
                with self.assertRaisesRegex(ValueError, 'Wrong target compiler'):
                    replay.check_compiler(cc)

    def test_relocation_is_exact_and_adds_only_policy(self):
        old, new, oldout, newout = map(Path, ('/source old', '/source new', '/old out', '/new out'))
        command = ['compiler', '-I/source old/include', '/source old/Apps/file.c',
                   '/source older/unchanged.c', '/watch/portable_sleep.c',
                   '/old out/sharing-objects/WebDavCore.o', '-Wl,--version-script=/old out/exports.map',
                   '-DPORTABLE_FILE_PEER', '-lgcc', '-o', '/old out/file_browser.elf']
        expected = ['compiler', '-I/source new/include', '/source new/Apps/file.c',
                    '/source older/unchanged.c', '/watch/portable_sleep.c',
                    '/new out/sharing-objects/WebDavCore.o', '-Wl,--version-script=/new out/exports.map',
                    '-DPORTABLE_FILE_PEER', '-lgcc', replay.POLICY, '-o', '/new out/file_browser.elf']
        self.assertEqual(replay.final_command(command, old, new, oldout, newout), expected)
        self.assertNotIn(replay.POLICY, command)
        with self.assertRaises(ValueError):
            replay.final_command(expected, old, new, oldout, newout)

    def test_rejects_provisional_or_wrong_selection(self):
        selection = json.loads((ROOT / 'docs/files-input-policy/selection.json').read_text())
        for key, value in (('source_publication', 'local-provisional'), ('finalized', False),
                           ('finalized', 1), ('schema', 'unknown'), ('version', '1.5.34')):
            changed = dict(selection, **{key: value})
            with self.subTest(key=key, value=value), patch.object(Path, 'read_text', return_value=json.dumps(changed)):
                with self.assertRaisesRegex(ValueError, 'Public Files selection differs'):
                    replay.selected_inputs()

    def test_all_eleven_public_object_pins(self):
        pins = replay.selected_inputs()
        objects = {name: value for name, value in pins.items() if name.startswith('sharing-objects/')}
        self.assertEqual(len(objects), 11)
        self.assertEqual(set(Path(name).name for name in objects), {
            'PortableFileSharing.o', 'WebDavRemoteVolume.o', 'PortablePeerFiles.o', 'WebDavSharing.o',
            'WebDavCore.o', 'WebDavSession.o', 'sha2.o', 'WebDavProperties.o', 'WebDavClient.o',
            'WebDavVolume.o', 'WebDavDigest.o'})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for name in [*objects, 'empty_catalog.c', 'exports.map']:
                path = out / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            def digest(path):
                return pins[Path(path).relative_to(out).as_posix()]
            with patch.object(replay, 'sha', side_effect=digest):
                self.assertEqual(replay.verify_generated(out), objects)
            with patch.object(replay, 'sha', return_value='modified'):
                with self.assertRaisesRegex(ValueError, 'Fresh sharing objects differ'):
                    replay.verify_generated(out)
            (out / 'sharing-objects/sha2.o').unlink()
            with patch.object(replay, 'sha', side_effect=digest):
                with self.assertRaises(ValueError):
                    replay.verify_generated(out)

    def test_target_hash_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            elf = Path(tmp) / 'file_browser.elf'
            elf.write_bytes(b'x' * replay.TARGETS['final'][0])
            with self.assertRaisesRegex(ValueError, 'differs'):
                replay.verify_target(elf, 'final')
            with patch.object(replay, 'sha', return_value=replay.TARGETS['final'][1]):
                replay.verify_target(elf, 'final')
                with self.assertRaises(ValueError):
                    replay.verify_target(elf, 'predecessor')

    def test_cli_requires_sources_not_artifacts(self):
        names = {action.dest for action in replay.parser()._actions}
        self.assertEqual(names, {'help', 'cc', 'host_cc', 'output', *replay.PINS})
        script = (ROOT / 'scripts/rebuild_watch_files_from_source.py').read_text()
        self.assertNotIn('/workspace/', script)
        self.assertNotIn('file_browser-build-record.json', script)
        self.assertNotIn('boot.json', script)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/rebuild_watch_files_from_source.py'),
                                 '--help'], capture_output=True, text=True, cwd=tempfile.gettempdir())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--system-predecessor', result.stdout)

    def test_compile_failure_never_accepts_stale_elf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'file_browser.elf').write_bytes(b'rejected')
            failure = subprocess.CompletedProcess(['cc'], 1, stdout='ordinary compiler error')
            with patch.object(replay.subprocess, 'run', return_value=failure) as run:
                with self.assertRaisesRegex(ValueError, 'compilation failed'):
                    replay.compile_target(['cc'], out)
                self.assertEqual(run.call_count, 1)
            self.assertFalse((out / 'file_browser.elf').exists())
            self.assertEqual((out / 'rejected-link-1.elf').read_bytes(), b'rejected')


if __name__ == '__main__':
    unittest.main()

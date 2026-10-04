import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reuse', ROOT / 'scripts/build_reader_usb_reuse.py')
reuse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reuse)


class SourceCustody(unittest.TestCase):
    def test_source_pin_and_dirty_selected_file(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(['git', 'init', '-q', repo], check=True)
            (repo / 'driver.c').write_text('original\n')
            subprocess.run(['git', '-C', repo, 'add', 'driver.c'], check=True)
            subprocess.run(['git', '-C', repo, '-c', 'user.name=Test', '-c',
                'user.email=test@example.invalid', 'commit', '-qm', 'fixture'], check=True)
            sha = reuse.git(repo, 'rev-parse', 'HEAD').decode().strip()
            reuse.validate_source(repo, sha, ['driver.c'])
            with self.assertRaises(ValueError):
                reuse.validate_source(repo, '0' * 40, ['driver.c'])
            (repo / 'driver.c').write_text('modified\n')
            with self.assertRaises(ValueError):
                reuse.validate_source(repo, sha, ['driver.c'])
            rows = reuse.stage(repo, ['driver.c'], repo / 'evidence')
            self.assertEqual((repo / 'evidence/driver.c').read_bytes(), b'original\n')
            self.assertEqual(rows[0]['sha256'], reuse.digest(b'original\n'))

    def test_stage_refuses_parent_escape(self):
        with self.assertRaises(ValueError):
            reuse.stage(Path('.'), ['../driver.c'], Path('.'))

    def test_scope_excludes_other_usb_classes_and_board_power(self):
        pin = json.loads(reuse.PIN.read_text())
        self.assertEqual({item['source'] for item in pin['modules']}, {
            'usb_host_v2', 'usb_hid', 'usb_hid_keyboard', 'usb_hid_gamepad',
            'usb_xinput_gamepad', 'usb_hid_text_input', 'usb_ui_navigation'})
        self.assertEqual(len(pin['reader_commit']), 40)
        self.assertEqual(len(pin['runtime_commit']), 40)


if __name__ == '__main__':
    unittest.main()

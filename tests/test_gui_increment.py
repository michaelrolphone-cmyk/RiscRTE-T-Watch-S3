import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_gui_increment import verify

class GuiCustody(unittest.TestCase):
    def setUp(self):
        paths = list((ROOT / 'dist/launcher-common').glob('*-launcher-common.zip'))
        self.assertEqual(len(paths), 1)
        with zipfile.ZipFile(paths[0]) as z:
            self.files = {n: z.read(n) for n in z.namelist()}

    def check(self, files, succeeds=False):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'candidate.zip'
            with zipfile.ZipFile(path, 'w') as z:
                for n, data in files.items(): z.writestr(n, data)
            if succeeds:
                result = verify(path)
                self.assertEqual(result['unchanged_file_count'], 13)
            else:
                with self.assertRaises(AssertionError): verify(path)

    def test_exact_candidate(self): self.check(self.files, True)

    def test_physical_driver_change_rejected(self):
        self.files['store/pmu/driver.elf'] += b'changed'
        self.check(self.files)

    def test_board_change_rejected(self):
        self.files['store/board.json'] += b' '
        self.check(self.files)

    def test_added_provider_rejected(self):
        self.files['store/navigation/driver.elf'] = b'bad'
        self.check(self.files)

    def test_partial_frame_policy_rejected(self):
        source = json.loads(self.files['shared-app-build.json'])
        source['full_frames'] = False
        self.files['shared-app-build.json'] = json.dumps(source).encode()
        self.check(self.files)

    def test_navigation_provider_grant_rejected(self):
        boot = json.loads(self.files['store/boot.json'])
        boot['app_capabilities'][1]['grants'].append({'capability':'input.navigation','api':1,'instance_id':9})
        self.files['store/boot.json'] = json.dumps(boot).encode()
        self.check(self.files)

    def test_remapped_physical_driver_rejected(self):
        boot = json.loads(self.files['store/boot.json'])
        boot['drivers'][0]['manifest'] = 'pmu/manifest.json'
        self.files['store/boot.json'] = json.dumps(boot).encode()
        self.check(self.files)

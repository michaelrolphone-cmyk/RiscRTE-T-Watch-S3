"""Explicit source-bound native limits never silently widen historical checks."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_runtime_store_admission as admission

HEAD = '3b90cd11cf0ff4e8116bb54d2d9eb9c7c67a148b'
PROFILE = '''[platformio]
extra_configs = platformio.ini
[env:crown-recovery-qualification]
extends = env:esp32s3-16mb-appdata-iq-sharing
build_flags =
  ${env:esp32s3-16mb-appdata-iq-sharing.build_flags}
  -DRISC_NATIVE_RECOVERY_AXP2101=1
  -DRISC_RECOVERY_I2C_PORT=0
  -DRISC_RECOVERY_SDA=10
  -DRISC_RECOVERY_SCL=11
'''
SOURCE = '''[env:esp32s3-16mb-appdata-iq-sharing]
extends = env:esp32s3-16mb-appdata-iq-tcp-entropy
build_flags =
  ${env:esp32s3-16mb-appdata-iq-tcp-entropy.build_flags}
  -DRISC_INSTALLED_APP_CAPACITY=64
  -DRISC_PROVIDER_CAPACITY=32
  -DRISC_APP_POLICY_ROWS=24
  -DRISC_APP_REQUIREMENT_ROWS=24
'''
MARKERS = {'risc_app_policy_rows': b'RISC_APP_POLICY_ROWS:24\0',
           'risc_app_requirement_rows': b'RISC_APP_REQUIREMENT_ROWS:24\0',
           'risc_tcp_listener_abi': b'\x01\0\0\0', 'risc_entropy_abi': b'\x01\0\0\0'}


class NativeComposition(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = self.root / 'crown-build.ini'
        self.profile.write_text(PROFILE)
        (self.root / 'platformio.ini').write_text(SOURCE)
        self.native = b'RTE_SOURCE=' + HEAD.encode() + b'\0RISC_APP_POLICY_ROWS:24\0'
        self.status = ''
        self.git_source = SOURCE.encode()
        self.markers = dict(MARKERS)
        self.git = patch.object(admission.subprocess, 'check_output', side_effect=self.git_output)
        self.git.start()
        self.addCleanup(self.git.stop)
        self.marker = patch.object(admission, 'native_symbol_bytes', side_effect=lambda image, name: self.markers[name])
        self.marker.start()
        self.addCleanup(self.marker.stop)

    def git_output(self, command, **kwargs):
        if 'rev-parse' in command:
            return HEAD + '\n'
        if 'status' in command:
            return self.status
        if 'show' in command:
            return self.git_source
        self.fail('Unexpected git command: ' + repr(command))

    def check(self, rows=24):
        return admission.native_composition(self.root, self.native, self.profile, rows)

    def test_exact_profile_and_optional_stack_report(self):
        for suffix in ('', '  -fstack-usage\n'):
            self.profile.write_text(PROFILE + suffix)
            proof = self.check()
            self.assertEqual(proof['bounds'], {'RISC_INSTALLED_APP_CAPACITY': 64,
                'RISC_PROVIDER_CAPACITY': 32, 'RISC_APP_POLICY_ROWS': 24, 'RISC_APP_REQUIREMENT_ROWS': 24})
            self.assertIn('no native capacity marker', proof['capacity_evidence'])
            self.assertEqual(proof['runtime_commit'], HEAD)

    def test_profile_override_or_wrong_parent_rejected(self):
        for text in (PROFILE + '  -DRISC_PROVIDER_CAPACITY=40\n',
                     PROFILE.replace('extends = env:esp32s3-16mb-appdata-iq-sharing', 'extends = env:other'),
                     PROFILE + 'board = different\n'):
            self.profile.write_text(text)
            with self.assertRaisesRegex(ValueError, 'Unsupported or modified'):
                self.check()

    def test_source_identity_missing_wrong_or_conflicting_rejected(self):
        for native in (b'no source marker', b'RTE_SOURCE=' + b'a' * 40 + b'\0',
                       self.native + b'RTE_SOURCE=' + b'b' * 40 + b'\0'):
            self.native = native
            with self.assertRaisesRegex(ValueError, 'RTE_SOURCE'):
                self.check()

    def test_dirty_runtime_or_changed_profile_rejected(self):
        self.status = ' M src/bootstrap/Runtime.cpp\n'
        with self.assertRaisesRegex(ValueError, 'unchanged Runtime'):
            self.check()
        self.status = ''
        self.git_source = b'different committed profile'
        with self.assertRaisesRegex(ValueError, 'differs from the source identity'):
            self.check()

    def test_unsupported_source_bounds_rejected(self):
        for text in (SOURCE.replace('CAPACITY=32', 'CAPACITY=40'),
                     SOURCE.replace('REQUIREMENT_ROWS=24', 'REQUIREMENT_ROWS=16')):
            (self.root / 'platformio.ini').write_text(text)
            self.git_source = text.encode()
            with self.assertRaisesRegex(ValueError, 'unsupported composition'):
                self.check()

    def test_mismatched_native_rows_rejected(self):
        for name in ('risc_app_policy_rows', 'risc_app_requirement_rows'):
            self.markers = dict(MARKERS)
            self.markers[name] = self.markers[name].replace(b':24', b':16')
            with self.assertRaisesRegex(ValueError, 'Native row bounds differ'):
                self.check()
        with self.assertRaisesRegex(ValueError, '24 policy rows'):
            self.check(rows=16)

    def test_unselected_native_sharing_backend_rejected(self):
        for name in ('risc_tcp_listener_abi', 'risc_entropy_abi'):
            self.markers = dict(MARKERS)
            self.markers[name] = b'\0\0\0\0'
            with self.assertRaisesRegex(ValueError, 'sharing backend selection differs'):
                self.check()

    def test_explicit_profile_flags_and_unchanged_historical_defaults(self):
        for relative in ('src/ports/esp32s3/CpuPort.h', 'src/bootstrap/Runtime.h',
                         'src/bootstrap/AppPolicyLimits.h'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('')
        elf = Mock()
        elf.get_section_by_name.return_value = None
        with patch.object(admission.subprocess, 'run') as run, \
                patch('verify_update_elf.cohort_admission_header', return_value='// production header'), \
                patch('elftools.elf.elffile.ELFFile', return_value=elf):
            admission.compile_harness(self.root, self.root / 'matched', True, self.native, 24,
                                      native_profile=self.profile)
            command = run.call_args.args[0]
            for define in ('RISC_INSTALLED_APP_CAPACITY=64', 'RISC_PROVIDER_CAPACITY=32',
                           'RISC_APP_REQUIREMENT_ROWS=24', 'RISC_APP_POLICY_ROWS=24'):
                self.assertIn('-D' + define, command)
            self.assertEqual(command.count('-DRISC_APP_POLICY_ROWS=24'), 1)
            self.assertIn('-DSTORE_ADMISSION_CROWN_PROFILE', command)
            admission.compile_harness(self.root, self.root / 'historical')
            historical = run.call_args.args[0]
            self.assertNotIn('-DRISC_PROVIDER_CAPACITY=32', historical)
            self.assertNotIn('-DRISC_INSTALLED_APP_CAPACITY=64', historical)
            self.assertNotIn('-DRISC_APP_REQUIREMENT_ROWS=24', historical)
            self.assertNotIn('-DSTORE_ADMISSION_CROWN_PROFILE', historical)


if __name__ == '__main__':
    unittest.main()

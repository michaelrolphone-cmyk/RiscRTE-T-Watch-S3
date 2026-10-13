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
WAKE_PROFILE = '''[platformio]
extra_configs =
  platformio.ini
  crown-build.ini
[env:crown-wake-profile]
extends = env:crown-recovery-qualification
build_flags =
  ${env:crown-recovery-qualification.build_flags}
  -DRISC_STAGE_LOGS=1
  -DRISC_PERFORMANCE_TRACE=1
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
        self.git_profiles = {'crown-build.ini': PROFILE.encode(), 'crown-wake-profile.ini': WAKE_PROFILE.encode()}
        self.markers = dict(MARKERS)
        self.git = patch.object(admission.subprocess, 'check_output', side_effect=self.git_output)
        self.git.start()
        self.addCleanup(self.git.stop)
        self.marker = patch.object(admission, 'native_symbol_bytes', side_effect=lambda image, name: self.markers[name])
        self.marker.start()
        self.addCleanup(self.marker.stop)

    def git_output(self, command, **kwargs):
        self.assertEqual(kwargs.get('env', {}).get('GIT_NO_LAZY_FETCH'), '1')
        if 'rev-parse' in command:
            return HEAD + '\n'
        if 'status' in command:
            return self.status
        if 'show' in command:
            name = command[-1].split(':', 1)[1]
            return self.git_source if name == 'platformio.ini' else self.git_profiles[name]
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

    def wake_profile(self):
        self.profile = self.root / 'crown-wake-profile.ini'
        self.profile.write_text(WAKE_PROFILE)

    def test_source_bound_wake_observers_keep_all_original_bounds(self):
        self.wake_profile()
        with patch.object(admission, 'native_symbol_allocation', return_value={'address': 0x3fc90000, 'bytes': 128}) as allocation:
            proof = self.check()
        self.assertEqual(proof['profile'], 'env:crown-wake-profile')
        self.assertEqual(proof['diagnostic_flags'], {'RISC_STAGE_LOGS': 1, 'RISC_PERFORMANCE_TRACE': 1})
        self.assertEqual(proof['bounds']['RISC_PROVIDER_CAPACITY'], 32)
        self.assertEqual(proof['crown_profile_sha256'], admission.sha(PROFILE.encode()))
        self.assertEqual(proof['wake_profile_sha256'], admission.sha(WAKE_PROFILE.encode()))
        self.assertEqual(allocation.call_count, 2)

    def test_wake_profile_rejects_extra_missing_or_changed_flags(self):
        self.wake_profile()
        for text in (WAKE_PROFILE + '  -DRISC_PROVIDER_CAPACITY=40\n',
                     WAKE_PROFILE.replace('RISC_STAGE_LOGS=1', 'RISC_STAGE_LOGS=0'),
                     WAKE_PROFILE.replace('  -DRISC_PERFORMANCE_TRACE=1\n', ''),
                     WAKE_PROFILE.replace('extends = env:crown-recovery-qualification', 'extends = env:other'),
                     WAKE_PROFILE.replace('  crown-build.ini\n', '  unchecked.ini\n')):
            self.profile.write_text(text)
            with self.assertRaisesRegex(ValueError, 'Unsupported or modified wake'):
                self.check()

    def test_wake_profile_requires_committed_inputs_and_enabled_allocations(self):
        self.wake_profile()
        for name in ('crown-build.ini', 'crown-wake-profile.ini'):
            saved = self.git_profiles[name]
            self.git_profiles[name] = b'other committed profile'
            with self.assertRaisesRegex(ValueError, 'differs from the source identity'):
                self.check()
            self.git_profiles[name] = saved
        with patch.object(admission, 'native_symbol_allocation', side_effect=ValueError('Missing diagnostic allocation')):
            with self.assertRaisesRegex(ValueError, 'Missing diagnostic allocation'):
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


EXPANDED_PROFILE = r'''[platformio]
extra_configs =
  platformio.ini
  crown-build.ini
  crown-wake-profile.ini
  watch-file-source-profile.ini
[env:watch-expanded]
extends = env:watch-file-source
board_build.partitions = partitions-paired-appdata-expanded.csv
build_unflags =
  -std=gnu++11
  -DRISC_PROVIDER_CAPACITY=32
  -DRISC_OWNER_INSTALLER=1
  -Wl,-u,risc_owner_maintenance_target
  -DRISC_TARGET=\"esp32s3-16mb-appdata-iq\"
build_flags =
  ${env:watch-file-source.build_flags}
  -DRISC_TARGET=\"esp32s3-16mb-appdata-expanded-iq\"
  -DRISC_PAIRED_APP_DATA_EXPANDED=1
  -DRISC_PROVIDER_CAPACITY=40
'''


class ExpandedNativeComposition(unittest.TestCase):
    git_output = NativeComposition.git_output
    check = NativeComposition.check

    def setUp(self):
        NativeComposition.setUp(self)
        self.profile = self.root / 'watch-expanded-profile.ini'
        self.profile.write_text(EXPANDED_PROFILE)
        source = (ROOT / 'docs/file-source/watch-file-source-profile.ini').read_bytes()
        self.git_profiles.update({'watch-expanded-profile.ini': EXPANDED_PROFILE.encode(),
                                  'watch-file-source-profile.ini': source,
                                  'partitions-paired-appdata-expanded.csv': b'committed table\n'})
        for name, raw in self.git_profiles.items():
            (self.root / name).write_bytes(raw)
        self.native += b'RISC_PAIRED_STORE_ABI:3\0'
        self.markers['risc_file_source_abi'] = b'\x01\0\0\0'
        self.abi = patch('verify_update_elf.verify_native_store_abi',
                         return_value={'store_abi': 3, 'marker_symbol': 'risc_paired_store_abi'})
        self.abi_check = self.abi.start()
        self.addCleanup(self.abi.stop)
        self.allocation = patch.object(admission, 'native_symbol_allocation',
                                       return_value={'address': 0x3fc90000, 'bytes': 128})
        self.allocation.start()
        self.addCleanup(self.allocation.stop)

    def test_exact_expanded_profile_retains_recovery_and_bounded_rows(self):
        proof = self.check()
        self.abi_check.assert_called_once_with(self.native, 3)
        self.assertEqual(proof['profile'], 'env:watch-expanded')
        self.assertEqual(proof['bounds'], {'RISC_INSTALLED_APP_CAPACITY': 64,
            'RISC_PROVIDER_CAPACITY': 40, 'RISC_APP_POLICY_ROWS': 24, 'RISC_APP_REQUIREMENT_ROWS': 24})
        self.assertEqual((proof['store_abi'], proof['store_size'], proof['layout']),
                         (3, 0x550000, 'riscrte-paired-appdata-v3'))
        self.assertFalse(proof['owner_installer'])
        self.assertTrue(proof['file_source_enabled'])
        self.assertEqual(proof['crown_profile_sha256'], admission.sha(PROFILE.encode()))
        self.assertEqual(proof['wake_profile_sha256'], admission.sha(WAKE_PROFILE.encode()))

    def test_reject_missing_changed_or_extra_expanded_flags(self):
        for text in (EXPANDED_PROFILE.replace('  -DRISC_OWNER_INSTALLER=1\n', ''),
                     EXPANDED_PROFILE.replace('  -DRISC_PROVIDER_CAPACITY=32\n', ''),
                     EXPANDED_PROFILE.replace('  -std=gnu++11\n', ''),
                     EXPANDED_PROFILE + '  -URISC_OWNER_INSTALLER\n',
                     EXPANDED_PROFILE + '  -URISC_TARGET\n',
                     EXPANDED_PROFILE + '  -URISC_PROVIDER_CAPACITY\n',
                     EXPANDED_PROFILE.replace('CAPACITY=40', 'CAPACITY=64'),
                     EXPANDED_PROFILE.replace('env:watch-file-source\n', 'env:crown-wake-profile\n'),
                     EXPANDED_PROFILE.replace('partitions-paired-appdata-expanded.csv', 'partitions-paired-appdata.csv'),
                     EXPANDED_PROFILE + '  -DRISC_APP_POLICY_ROWS=32\n',
                     EXPANDED_PROFILE + '  -DRISC_NATIVE_RECOVERY_AXP2101=0\n'):
            self.profile.write_text(text)
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'modified expanded'):
                self.check()

    def test_reject_any_uncommitted_selected_profile_or_table(self):
        for name in ('watch-expanded-profile.ini', 'watch-file-source-profile.ini',
                     'partitions-paired-appdata-expanded.csv'):
            saved = self.git_profiles[name]
            self.git_profiles[name] = b'other committed bytes'
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'differs from the source identity'):
                self.check()
            self.git_profiles[name] = saved

    def test_reject_inherited_recovery_or_file_source_change(self):
        path = self.root / 'crown-build.ini'
        path.write_text(PROFILE.replace('RISC_NATIVE_RECOVERY_AXP2101=1', 'RISC_NATIVE_RECOVERY_AXP2101=0'))
        with self.assertRaisesRegex(ValueError, 'modified native crown'):
            self.check()
        path.write_text(PROFILE)
        path = self.root / 'watch-file-source-profile.ini'
        path.write_bytes(self.git_profiles[path.name].replace(b'RISC_NATIVE_FILE_SOURCE=1', b'RISC_NATIVE_FILE_SOURCE=0'))
        with self.assertRaisesRegex(ValueError, 'modified native source'):
            self.check()

    def test_reject_wrong_abi_and_unsupported_rows(self):
        self.abi_check.side_effect = ValueError('Native allocated store ABI differs')
        with self.assertRaisesRegex(ValueError, 'store ABI differs'):
            self.check()
        self.abi_check.side_effect = None
        with self.assertRaisesRegex(ValueError, '24 policy rows'):
            self.check(rows=32)
        self.markers['risc_app_requirement_rows'] = b'RISC_APP_REQUIREMENT_ROWS:32\0'
        with self.assertRaisesRegex(ValueError, 'Native row bounds differ'):
            self.check()

    def test_abi3_cannot_silently_select_historical_or_profileless_admission(self):
        self.profile = self.root / 'crown-build.ini'
        with self.assertRaisesRegex(ValueError, 'explicit expanded Watch profile'):
            self.check()
        with self.assertRaisesRegex(ValueError, 'explicit expanded Watch profile'):
            admission.compile_harness(self.root, self.root / 'admit', True, self.native, 24)

    def test_host_compiles_selected_geometry_and_exact_capacities(self):
        for relative in ('src/ports/esp32s3/CpuPort.h', 'src/bootstrap/Runtime.h',
                         'src/bootstrap/AppPolicyLimits.h'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('')
        elf = Mock()
        elf.get_section_by_name.return_value = None
        with patch.object(admission.subprocess, 'run') as run, \
                patch('verify_update_elf.cohort_admission_header', return_value='// production header') as header, \
                patch('elftools.elf.elffile.ELFFile', return_value=elf):
            admission.compile_harness(self.root, self.root / 'matched', True, self.native, 24,
                                      native_profile=self.profile)
        command = run.call_args.args[0]
        for define in ('RISC_PAIRED_APP_DATA=1', 'RISC_PAIRED_APP_DATA_EXPANDED=1',
                       'RISC_INSTALLED_APP_CAPACITY=64', 'RISC_PROVIDER_CAPACITY=40',
                       'RISC_APP_REQUIREMENT_ROWS=24', 'RISC_APP_POLICY_ROWS=24',
                       'STORE_ADMISSION_CROWN_PROFILE', 'STORE_ADMISSION_FILE_SOURCE'):
            self.assertEqual(command.count('-D' + define), 1)
        self.assertNotIn('-DRISC_PROVIDER_CAPACITY=32', command)
        header.assert_called_once_with(self.root, self.native, store_abi=3)

    def test_expanded_decode_is_explicit_and_historical_default_is_unchanged(self):
        store = {name: b'fixture' for name in ('boot.json', 'board.json', 'default.json', 'default.elf')}
        with patch.object(admission, 'read_image', return_value=store) as read:
            admission.unpack_image(b'expanded', expected_size=0x550000)
            read.assert_called_with(b'expanded', 0x550000)
            admission.unpack_image(b'old')
            read.assert_called_with(b'old', 0x4f0000)
        with self.assertRaisesRegex(ValueError, 'Unknown SPIFFS geometry'):
            admission.unpack_image(b'unknown', expected_size=0x560000)


if __name__ == '__main__':
    unittest.main()

"""Original historical custody and narrowly pinned live-successor regressions."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_lifecycle_source_snapshot import BASE, CURRENT, verify


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class LifecycleSourceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='watch-snapshot-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git('init', '-q')
        self.write('seed', b'public prerequisite\n')
        self.prerequisite = self.commit('Public prerequisite')
        self.changed = 'apps/clock/watch_motion_client.h'
        self.unchanged = 'include/stable.h'
        self.selected = 'scripts/original.py'
        self.historical = b'original motion client\n'
        self.current = b'approved motion client\n'
        self.write(self.changed, self.historical)
        self.write(self.unchanged, b'stable input\n')
        self.write(self.selected, b'original builder\n')
        original = self.commit('Original Watch source')
        ref = 'refs/watch-custody/1.0.18/app-build'
        self.git('update-ref', ref, original)
        bundle = BASE / 'watch-sources.bundle'
        (self.root / bundle).parent.mkdir(parents=True)
        self.git('bundle', 'create', str(self.root / bundle), ref, '^' + self.prerequisite)
        raw = (self.root / bundle).read_bytes()
        self.record = {
            'schema': 1,
            'dependency_sources_included': False,
            'provisioning_payloads_included': False,
            'separate_model_header_or_provisioning_payloads_included': False,
            'bundle': {'file': bundle.name, 'size_bytes': len(raw), 'sha256': sha(raw)},
            'heads': {'app-build': {'bundle_ref': ref, 'commit': original,
                                  'tree': self.git('rev-parse', original + '^{tree}').strip()}},
            'selected_source_files': {self.selected: 'app-build'},
            'target_watch_inputs': {self.changed: sha(self.historical),
                                    self.unchanged: sha(b'stable input\n')},
        }
        self.write(self.changed, self.current)
        source = self.commit('Delivered successor')
        self.successors = {'schema': 1, 'target_watch_inputs': {
            self.changed: {'source_commit': source, 'sha256': sha(self.current)}}}
        self.write('mounted-files', b'unrelated authorized product change\n')
        self.commit('Later mounted Files product')
        self.save_records()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True,
                                       stderr=subprocess.PIPE)

    def write(self, name, raw):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def commit(self, message):
        self.git('add', '.')
        self.git('-c', 'user.name=Snapshot Test', '-c', 'user.email=snapshot@example.invalid',
                 'commit', '-qm', message)
        return self.git('rev-parse', 'HEAD').strip()

    def save_records(self):
        self.write(BASE / 'source-custody.json', json.dumps(self.record).encode())
        self.write(CURRENT, json.dumps(self.successors).encode())

    def verify(self):
        with contextlib.redirect_stdout(io.StringIO()):
            verify(self.root)

    def test_original_evidence_and_inherited_successor_both_pass(self):
        original_receipt = (self.root / BASE / 'source-custody.json').read_bytes()
        original_bundle = (self.root / BASE / 'watch-sources.bundle').read_bytes()
        self.verify()
        self.assertEqual((self.root / BASE / 'source-custody.json').read_bytes(), original_receipt)
        self.assertEqual((self.root / BASE / 'watch-sources.bundle').read_bytes(), original_bundle)

    def test_historical_only_snapshot_still_passes_without_successors(self):
        self.write(self.changed, self.historical)
        self.successors['target_watch_inputs'] = {}
        self.save_records()
        self.verify()

    def test_removing_required_successor_rejects_current_product(self):
        self.successors['target_watch_inputs'] = {}
        self.save_records()
        with self.assertRaisesRegex(ValueError, 'Current target input differs'):
            self.verify()

    def test_reverting_selected_successor_to_historical_bytes_is_rejected(self):
        self.write(self.changed, self.historical)
        with self.assertRaisesRegex(ValueError, 'Current target input differs'):
            self.verify()

    def test_current_successor_mutation_is_rejected(self):
        self.write(self.changed, b'unrecorded change\n')
        with self.assertRaisesRegex(ValueError, 'Current target input differs'):
            self.verify()

    def test_unchanged_historical_input_mutation_is_rejected(self):
        self.write(self.unchanged, b'unrecorded change\n')
        with self.assertRaisesRegex(ValueError, 'Current target input differs'):
            self.verify()

    def test_rehashing_historical_receipt_to_current_is_rejected(self):
        self.record['target_watch_inputs'][self.changed] = sha(self.current)
        self.save_records()
        with self.assertRaisesRegex(ValueError, 'Original target input differs'):
            self.verify()

    def test_rehashing_successor_and_live_input_cannot_replace_pinned_source(self):
        changed = b'forged current bytes\n'
        self.write(self.changed, changed)
        self.successors['target_watch_inputs'][self.changed]['sha256'] = sha(changed)
        self.save_records()
        with self.assertRaisesRegex(ValueError, 'Current successor source hash differs'):
            self.verify()

    def test_extra_successor_cannot_expand_input_scope(self):
        item = copy.deepcopy(self.successors['target_watch_inputs'][self.changed])
        self.successors['target_watch_inputs']['unrelated.h'] = item
        self.save_records()
        with self.assertRaisesRegex(ValueError, 'not an original target input'):
            self.verify()

    def test_successor_requires_exact_commit_not_mutable_ref(self):
        self.successors['target_watch_inputs'][self.changed]['source_commit'] = 'HEAD'
        self.save_records()
        with self.assertRaisesRegex(ValueError, 'requires an exact source commit'):
            self.verify()

    def test_nonancestor_source_is_rejected(self):
        tree = self.git('rev-parse', 'HEAD^{tree}').strip()
        other = self.git('-c', 'user.name=Snapshot Test', '-c', 'user.email=snapshot@example.invalid',
                         'commit-tree', tree, '-m', 'Unrelated source').strip()
        self.successors['target_watch_inputs'][self.changed]['source_commit'] = other
        self.save_records()
        with self.assertRaisesRegex(ValueError, 'not in this checkout history'):
            self.verify()

    def test_redundant_successor_cannot_silently_repin_unchanged_input(self):
        original = self.record['heads']['app-build']['commit']
        self.successors['target_watch_inputs'][self.unchanged] = {
            'source_commit': original, 'sha256': sha(b'stable input\n')}
        self.save_records()
        with self.assertRaisesRegex(ValueError, 'Redundant current successor'):
            self.verify()

    def test_selected_original_source_mutation_is_rejected(self):
        self.write(self.selected, b'modified original builder\n')
        with self.assertRaisesRegex(ValueError, 'Selected original source differs'):
            self.verify()

    def test_missing_or_linked_current_input_is_rejected(self):
        path = self.root / self.changed
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing or linked custody file'):
            self.verify()
        self.write('shadow.h', self.current)
        path.symlink_to(self.root / 'shadow.h')
        with self.assertRaisesRegex(ValueError, 'Missing or linked custody file'):
            self.verify()

    def test_linked_parent_directory_is_rejected(self):
        (self.root / 'apps').rename(self.root / 'shadow-apps')
        (self.root / 'apps').symlink_to(self.root / 'shadow-apps', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Missing or linked custody file'):
            self.verify()

    def test_bundle_hash_and_original_tree_mutations_are_rejected(self):
        original = copy.deepcopy(self.record)
        for key, message in [('bundle', 'Original source bundle bytes differ'),
                             ('tree', 'Original source tree differs')]:
            with self.subTest(key=key):
                self.record = copy.deepcopy(original)
                if key == 'bundle':
                    self.record['bundle']['sha256'] = '0' * 64
                else:
                    self.record['heads']['app-build']['tree'] = '0' * 40
                self.save_records()
                with self.assertRaisesRegex(ValueError, message):
                    self.verify()


if __name__ == '__main__':
    unittest.main()

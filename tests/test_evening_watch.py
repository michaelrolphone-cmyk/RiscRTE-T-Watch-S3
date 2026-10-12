#!/usr/bin/env python3
"""Recipe mutation tests. They do not claim hardware or target execution."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from assemble_evening_watch import checked_bytes, seal_store, validate_store, SELECTION
from check_runtime_store_admission import store_digest
from assemble_watch_points_union import encoded, sha
from assemble_watch_spectrum_policy import strict_json


class EveningWatchRecipe(unittest.TestCase):
    def setUp(self):
        self.files = {
            'cohort.json': encoded(dict(version='1.1.18', source_revision='a'*40, firmware_sha256='f'*64)),
            'waterfall.json': encoded(dict(version='0.3.4', requires=[])),
            'one.elf': b'untouched-app-and-font-bytes',
            'boot.json': b'{"grants":[]}\n',
        }
        self.selection = copy.deepcopy(SELECTION)
        self.selection['baseline'].update(store_files=4, elf_count=1,
            compiled_recipe_commit='a'*40, candidate_store_sha256=store_digest(self.files))

    def test_exact_only_cohort_delta(self):
        new = seal_store(self.files, 'b'*40, self.selection)
        self.assertEqual({n for n in new if new[n] != self.files[n]}, {'cohort.json'})
        expected = strict_json(self.files['cohort.json'])
        expected.update(version='1.1.19', source_revision='b'*40)
        self.assertEqual(strict_json(new['cohort.json']), expected)

    def test_original_input_not_mutated(self):
        original = dict(self.files)
        seal_store(self.files, 'b'*40, self.selection)
        self.assertEqual(self.files, original)

    def test_changed_app_rejected(self):
        self.files['one.elf'] += b'changed'
        with self.assertRaises(ValueError): validate_store(self.files, self.selection)

    def test_changed_boot_authority_rejected(self):
        self.files['boot.json'] = b'{"grants":["unexpected"]}'
        with self.assertRaises(ValueError): validate_store(self.files, self.selection)

    def test_missing_app_rejected(self):
        del self.files['one.elf']
        with self.assertRaises(ValueError): validate_store(self.files, self.selection)

    def test_added_app_rejected(self):
        self.files['extra.elf'] = b'x'
        with self.assertRaises(ValueError): validate_store(self.files, self.selection)

    def test_wrong_baseline_revision_rejected(self):
        self.files['cohort.json'] = encoded(dict(version='1.1.18', source_revision='c'*40))
        self.selection['baseline']['candidate_store_sha256'] = store_digest(self.files)
        with self.assertRaises(ValueError): validate_store(self.files, self.selection)

    def test_wrong_baseline_version_rejected(self):
        self.files['cohort.json'] = encoded(dict(version='1.1.17', source_revision='a'*40))
        self.selection['baseline']['candidate_store_sha256'] = store_digest(self.files)
        with self.assertRaises(ValueError): validate_store(self.files, self.selection)

    def test_blocked_rf_successor_rejected(self):
        self.files['waterfall.json'] = encoded(dict(version='0.3.5', requires=[]))
        self.selection['baseline']['candidate_store_sha256'] = store_digest(self.files)
        with self.assertRaises(ValueError): validate_store(self.files, self.selection)

    def test_watch_sd_assumption_rejected(self):
        self.selection['preservation']['watch_has_sd'] = True
        with self.assertRaises(ValueError): validate_store(self.files, self.selection)

    def test_invalid_source_identity_rejected(self):
        for revision in ['b'*39, 'B'*40, 'z'*40, '']:
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                seal_store(self.files, revision, self.selection)

    def test_exact_component_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'component'
            path.write_bytes(b'known')
            self.assertEqual(checked_bytes(path, sha(b'known'), 'test'), b'known')
            with self.assertRaises(ValueError): checked_bytes(path, sha(b'changed'), 'test')

    def test_duplicate_metadata_rejected(self):
        with self.assertRaises(ValueError): strict_json(b'{"version":"1","version":"2"}')


if __name__ == '__main__': unittest.main(verbosity=2)

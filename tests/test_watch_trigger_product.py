import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import watch_product_trigger as trigger


class AutomaticProductGate(unittest.TestCase):
    def setUp(self):
        self.source = '6' * 40
        self.product = {'schema': 2, 'repository': trigger.REPOSITORY,
                        'version': '1.0.2', 'tag': 'firmware-v1.0.2',
                        'accepted_bin_sha256': 'a' * 64}
        self.current = json.dumps(self.product).encode()
        self.release = Mock(return_value={'tag_name': 'firmware-v1.0.2', 'draft': False,
                                         'prerelease': False, 'target_commitish': self.source})
        self.tag = Mock(return_value=self.source)
        self.original = Mock(return_value=self.current)

    def decide(self, event='workflow_run', current=None):
        return trigger.should_promote(event, self.current if current is None else current,
                                      self.release, self.tag, self.original)

    def test_unchanged_published_configuration_skips_using_release_source(self):
        self.assertFalse(self.decide())
        self.tag.assert_called_once_with('firmware-v1.0.2')
        self.original.assert_called_once_with(self.source)

    def test_multicommit_push_does_not_consult_head_parent(self):
        # A changed HEAD parent is irrelevant: compare to the published source.
        self.product['accepted_bin_sha256'] = 'b' * 64
        self.assertTrue(self.decide(current=json.dumps(self.product).encode()))
        self.original.assert_called_once_with(self.source)

    def test_formatting_alone_does_not_repromote(self):
        self.original.return_value = json.dumps(self.product, sort_keys=True, indent=4).encode()
        self.assertFalse(self.decide())

    def test_scalar_type_changes_are_not_hidden_by_python_equality(self):
        changed = dict(self.product, schema=2.0)
        self.assertTrue(self.decide(current=json.dumps(changed).encode()))

    def test_new_version_and_unpublished_draft_continue_existing_verification(self):
        for release in (None, {'draft': True}):
            with self.subTest(release=release):
                self.release.return_value = release
                self.assertTrue(self.decide())
        self.tag.assert_not_called()
        self.original.assert_not_called()

    def test_pr_and_manual_paths_always_verify_without_remote_gate(self):
        for event in ('pull_request', 'workflow_dispatch'):
            self.assertTrue(self.decide(event))
        self.release.assert_not_called()
        self.tag.assert_not_called()
        self.original.assert_not_called()

    def test_unexpected_event_invalid_identity_or_duplicate_json_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            self.decide('push')
        for change in ({'version': '../other'}, {'tag': 'firmware-v1.0.3'},
                       {'repository': 'other/repo'}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'identity'):
                self.decide(current=json.dumps({**self.product, **change}).encode())
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.decide(current=b'{"version":"1.0.2","version":"1.0.3"}')

    def test_wrong_release_kind_or_unpinned_tag_fails_closed(self):
        for change in ({'tag_name': 'firmware-v9.0.0'}, {'prerelease': True},
                       {'target_commitish': 'main'}, {'draft': None}):
            original = {'tag_name': 'firmware-v1.0.2', 'draft': False,
                        'prerelease': False, 'target_commitish': self.source}
            self.release.return_value = {**original, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.decide()

    def test_missing_tag_or_source_never_becomes_a_skip(self):
        self.tag.return_value = 'not-a-commit'
        with self.assertRaises(ValueError):
            self.decide()
        self.tag.return_value = self.source
        self.original.side_effect = subprocess.CalledProcessError(128, 'git show')
        with self.assertRaises(subprocess.CalledProcessError):
            self.decide()

    def test_only_missing_release_404_is_allowed_to_continue(self):
        with patch.object(trigger.subprocess, 'run', return_value=Mock(
                returncode=1, stderr='gh: Not Found (HTTP 404)', stdout='')):
            self.assertIsNone(trigger.release_lookup('firmware-v1.0.2'))
        for error in ('gh: Forbidden (HTTP 403)', 'network unavailable'):
            with patch.object(trigger.subprocess, 'run', return_value=Mock(
                    returncode=1, stderr=error, stdout='')):
                with self.assertRaises(RuntimeError):
                    trigger.release_lookup('firmware-v1.0.2')

    def test_workflow_gates_artifact_steps_and_publication(self):
        text = (Path(__file__).resolve().parents[1] / '.github/workflows/watch-product.yml').read_text()
        self.assertIn("promote: ${{ steps.promotion.outputs.proceed }}", text)
        self.assertIn("needs.verify.outputs.promote == 'true'", text)
        self.assertIn("WATCH_PRODUCT_EVENT: ${{ github.event_name }}", text)
        self.assertIn('run: python scripts/watch_product_trigger.py', text)
        self.assertEqual(text.count("if: steps.promotion.outputs.proceed == 'true'"), 6)


if __name__ == '__main__':
    unittest.main()

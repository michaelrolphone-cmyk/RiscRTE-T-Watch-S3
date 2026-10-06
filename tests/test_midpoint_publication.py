"""Source-only publication boundaries; no compiler, firmware fixtures or writes to GitHub.

The evidence tests mutate the frozen, independently produced JSON proofs. The
coordinator tests mock byte derivation and every external operation; their tiny
in-memory records are not firmware acceptance evidence. Optionally set
MIDPOINT_ARTIFACT_DIR to a directory containing the original bridge.zip,
ordinary.zip and native.zip to exercise full offline derivation as well.
"""
import copy
from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timedelta
import io
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import publish_midpoint_test as midpoint
import publish_sdr_test as sdr
import publish_watch_product as pub
from watch_release_index import EMPTY_INDEX, update_index


def read_json(path):
    return midpoint.decode(path.read_bytes())


def changed(document, path, value):
    result = copy.deepcopy(document)
    target = result
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return result


def coordinator_fixture():
    """Metadata only, deliberately isolated from the real artifact verifier."""
    def record(version):
        return pub.record('firmware', '', version, 'twatch-s3-launcher-' + version + '.bin',
                          b'coordinator-test-only', source_sha=midpoint.SOURCE,
                          hardware_qualified=False)
    expected = update_index(copy.deepcopy(EMPTY_INDEX), 'firmware', record('1.0.3'))
    expected['services'] = [{'id': 'preserved-service'}]
    expected['providers'] = [{'id': 'preserved-provider'}]
    final = record('1.0.6')
    final['ota'] = {'asset': 'twatch-s3-cohort-1.0.6.bin', 'sha256': 'a' * 64}
    index = update_index(expected, 'firmware', final)
    acceptance = {'ota': final['ota'], 'installed_catalog': {'accepted': True},
                  'inputs': {'ordinary': {'role': 'ordinary'}, 'native': {'role': 'native'}},
                  'evidence': {role: {'path': 'release/midpoint-test-evidence/' + role + '.json'}
                               for role in ('build', 'normal', 'sanitized', 'execution', 'ci')}}
    assets = {'PUBLICATION.txt': midpoint.NOTICE.encode()}
    bridge = ({'native': {'SHA256SUMS': b'', 'release-record.json': pub.encoded(expected['firmware'])}},
              b'original bridge instructions')
    return acceptance, expected, index, assets, bridge


class SourceCustodyTests(unittest.TestCase):
    def test_freeze_cannot_replace_existing_canonical_acceptance(self):
        self.assertTrue(midpoint.ACCEPTANCE.is_file())
        with self.assertRaisesRegex(ValueError, 'Refusing to replace'):
            midpoint.freeze(object())

    def test_frozen_derivation_sources_equal_exact_accepted_commit(self):
        guards = midpoint.source_guards()
        self.assertEqual(set(guards), set(midpoint.SOURCE_FILES))
        for path, digest in guards.items():
            self.assertEqual(digest, pub.sha((ROOT / path).read_bytes()), path)
        self.assertIn('release/sdr-test-acceptance.json', guards)
        self.assertIn('apps/midpoint-origin-baseline.json', guards)

    def test_changed_derivation_source_refused_even_when_publisher_is_clean(self):
        name = 'scripts/midpoint_upgrade.py'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / name).parent.mkdir(parents=True)
            (root / name).write_bytes((ROOT / name).read_bytes() + b'\n# altered\n')
            with patch.object(midpoint, 'ROOT', root), patch.object(midpoint, 'SOURCE_FILES', (name,)):
                with self.assertRaisesRegex(ValueError, 'Frozen derivation source changed'):
                    midpoint.source_guards()

    def test_original_hosted_input_requires_exact_role_source_and_ci_identity(self):
        for role, prefix in (('ordinary', 'twatch-next-cohort-'), ('native', 'twatch-native-runtime-')):
            item = dict(repository=pub.REPOSITORY, source_sha=midpoint.SOURCE,
                        name=prefix + midpoint.SOURCE, sha256='a' * 64,
                        artifact_id=1, run_id=2, run_attempt=3)
            self.assertEqual(midpoint.validate_input(role, item), item)
            for key, values in {'repository': ['other/repo'], 'source_sha': ['b' * 40],
                                'name': ['repacked-midpoint'], 'sha256': ['not-a-sha', 'a' * 63],
                                'artifact_id': [0, True, '1'], 'run_id': [-1, False],
                                'run_attempt': [0, '3']}.items():
                for value in values:
                    with self.subTest(role=role, field=key, value=value), self.assertRaises(ValueError):
                        midpoint.validate_input(role, {**item, key: value})

    def test_original_zip_digest_is_checked_without_remote_reads(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            data = {role: ('original-' + role).encode() for role in ('bridge', 'ordinary', 'native')}
            acceptance = {'inputs': {role: {'sha256': pub.sha(data[role])} for role in ('ordinary', 'native')}}
            bridge = root / 'bridge-acceptance.json'
            bridge.write_bytes(pub.encoded({'sha256': pub.sha(data['bridge'])}))
            stack.enter_context(patch.object(sdr, 'ACCEPTANCE', bridge))
            remote = stack.enter_context(patch.object(pub, 'gh', side_effect=AssertionError('Unexpected network access')))
            for role, raw in data.items():
                (root / (role + '.zip')).write_bytes(raw)
            self.assertEqual(midpoint.original_inputs(acceptance, root), data)
            for role in data:
                path = root / (role + '.zip')
                path.write_bytes(data[role] + b'changed')
                with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'Original hosted ZIP hash differs'):
                    midpoint.original_inputs(acceptance, root)
                path.write_bytes(data[role])
            remote.assert_not_called()


class FrozenEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.acceptance = midpoint.validate_acceptance(read_json(midpoint.ACCEPTANCE))
        cls.raw = midpoint.read_evidence(cls.acceptance)
        cls.proofs = {role: midpoint.decode(raw) for role, raw in cls.raw.items()}
        cls.build = cls.proofs['build']

    def verify_proof(self, proof):
        midpoint.verify_transactions(proof, self.acceptance['ota'], self.build['files'])

    def assert_proof_changes_rejected(self, edits):
        for role in ('normal', 'sanitized'):
            for path, value in edits:
                with self.subTest(role=role, path=path, value=value), self.assertRaises(ValueError):
                    self.verify_proof(changed(self.proofs[role], path, value))

    def test_acceptance_evidence_and_real_proofs_have_one_source_identity(self):
        self.assertEqual(set(self.raw), {'build', 'normal', 'sanitized', 'execution', 'ci'})
        self.assertEqual(self.acceptance['derivation_sources'], midpoint.source_guards())
        self.assertFalse(self.acceptance['hosted_midpoint_artifact'])
        self.assertFalse(self.acceptance['physical_qualification'])
        self.assertEqual(self.build['watch_source'], midpoint.SOURCE)
        self.assertEqual(self.build['ota'], self.acceptance['ota'])
        midpoint.verify_build_admissions(self.build)
        for role in ('normal', 'sanitized'):
            self.verify_proof(self.proofs[role])
            self.assertEqual(self.proofs[role]['policy'], self.build['policy'])
            self.assertEqual(self.proofs[role]['runtime_evidence'], self.build['runtime_evidence'])
            self.assertEqual(self.proofs['execution']['runs'][role]['proof_sha256'], pub.sha(self.raw[role]))
        self.assertEqual(self.proofs['execution']['runs']['sanitized']['environment']['SANITIZE'], '1')

    def test_acceptance_cannot_substitute_origin_source_route_or_evidence(self):
        edits = [(('source_sha',), 'b' * 40), (('version',), '1.0.5'), (('schema',), True),
                 (('midpoint_source',), sdr.BASELINE['source_sha']),
                 (('midpoint_initial_sha256',), '0' * 64), (('native_source',), sdr.RUNTIME),
                 (('bridge_acceptance_sha256',), '0' * 64), (('hosted_midpoint_artifact',), True),
                 (('physical_qualification',), True), (('not_before',), '2026-10-06T00:00:00Z'),
                 (('inputs', 'native', 'run_attempt'), self.acceptance['inputs']['native']['run_attempt'] + 1),
                 (('evidence', 'normal', 'path'), '../normal.json'), (('evidence', 'normal', 'sha256'), ''),
                 (('derivation_sources',), {})]
        with patch.object(midpoint, 'source_guards', return_value=self.acceptance['derivation_sources']):
            for path, value in edits:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    midpoint.validate_acceptance(changed(self.acceptance, path, value))
            for role in self.raw:
                value = copy.deepcopy(self.acceptance)
                del value['evidence'][role]
                with self.subTest(missing=role), self.assertRaises(ValueError):
                    midpoint.validate_acceptance(value)

    def test_each_evidence_file_hash_is_checked_before_use(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(midpoint, 'ROOT', Path(tmp)):
            for role, raw in self.raw.items():
                path = Path(tmp) / self.acceptance['evidence'][role]['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            for role, raw in self.raw.items():
                path = Path(tmp) / self.acceptance['evidence'][role]['path']
                path.write_bytes(raw + b' ')
                with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'Committed evidence changed'):
                    midpoint.read_evidence(self.acceptance)
                path.write_bytes(raw)

    def test_historical_scope_and_wrong_origins_or_sources_are_refused(self):
        self.assert_proof_changes_rejected([
            (('scope',), 'historical-input-harness-self-test-only'), (('final_artifact_acceptance',), False),
            (('profile',), 'ordinary'), (('version',), '1.0.5'),
            (('source_initial_image_sha256',), '0' * 64),
            (('source_cohort', 'source_revision'), sdr.BASELINE['source_sha']),
            (('source_cohort', 'version'), '1.0.4'),
            (('target_cohort', 'source_revision'), 'a' * 40),
            (('target_cohort', 'runtime_version'), '0.1.34'),
            (('target_cohort', 'firmware_sha256'), '0' * 64),
            (('ota', 'sha256'), '0' * 64)])

    def test_build_admission_elf_and_store_hashes_cannot_be_substituted(self):
        edits = []
        for name in ('bridge_retained_store_self_admission', 'installed_runtime_admission', 'target_self_admission'):
            edits.extend([((name, 'native_elf_sha256'), '0' * 64),
                          ((name, 'active_store_sha256'), '0' * 64),
                          ((name, 'candidate_store_sha256'), '0' * 64),
                          ((name, 'target_instructions_executed'), True),
                          ((name, 'elf_count'), 0), ((name, 'prepared'), False)])
        for path, value in edits:
            with self.subTest(path=path), self.assertRaises(ValueError):
                midpoint.verify_build_admissions(changed(self.build, path, value))

    def test_original_and_bridge_admissions_require_exact_graph_hashes_and_elf_counts(self):
        edits = [(('original_runtime_boot_admission', 'store_sha256'), '0' * 64),
                 (('original_runtime_boot_admission', 'store_files'), 72),
                 (('original_runtime_boot_admission', 'prepared'), False)]
        for name in ('bridge_retained_store_self_admission', 'bridge_runtime_admission', 'target_self_admission'):
            edits.extend([((name, 'active_store_sha256'), '0' * 64),
                          ((name, 'candidate_store_sha256'), '0' * 64), ((name, 'elf_count'), 0),
                          ((name, 'cohort_validated'), False), ((name, 'prepared'), False),
                          ((name, 'hardware_calls'), 1), ((name, 'storage_calls'), 1),
                          ((name, 'error'), 'failed')])
        self.assert_proof_changes_rejected(edits)

    def test_missing_duplicate_or_renamed_transactions_and_rejections_are_refused(self):
        for role in ('normal', 'sanitized'):
            original = self.proofs[role]
            for name in ('bridge_transactions', 'final_transactions', 'rejections'):
                rows = original[name]
                for replacement in (rows[:-1], rows + [rows[-1]], rows[:-1] + [rows[0]]):
                    with self.subTest(role=role, list=name, length=len(replacement)), self.assertRaises(ValueError):
                        self.verify_proof(changed(original, (name,), replacement))
                key = 'scenario' if name == 'rejections' else 'label'
                with self.subTest(role=role, list=name, mutation='renamed'), self.assertRaises(ValueError):
                    self.verify_proof(changed(original, (name, 0, key), 'unexercised-scenario'))
        self.assert_proof_changes_rejected([(('rejections', 0, 'cohort_validated'), True)])

    def test_preserved_data_requires_flags_and_real_sentinel_hashes(self):
        edits = []
        for name in ('bridge_transactions', 'final_transactions'):
            edits.extend([((name, 0, 'nvs_appdata_preserved'), False),
                          ((name, 0, 'previous_pair_preserved'), False), ((name, 0, 'target_executed'), True),
                          ((name, 0, 'nvs_sha256'), '0' * 64), ((name, 0, 'appdata_sha256'), '0' * 64),
                          ((name, 0, 'snapshot_sha256'), ''), ((name, 0, 'native_bytes'), 1)])
        edits.append((('final_transactions', 0, 'payload_bytes'), 1))
        self.assert_proof_changes_rejected(edits)

    def test_runtime_version_source_bank_and_healthy_restart_must_match_each_scenario(self):
        edits = []
        for name in ('bridge_transactions', 'final_transactions'):
            edits.extend([((name, 0, 'executing_runtime_source'), '0' * 40),
                          ((name, 0, 'executing_runtime_version'), '0.1.99'),
                          ((name, 0, 'build_runtime_version'), '0.1.99'),
                          ((name, 0, 'active_bank'), 2), ((name, 0, 'target_bank'), 2),
                          ((name, 0, 'scenario'), 'boot-healthy'), ((name, 0, 'host_idf_valid_state'), True)])
        self.assert_proof_changes_rejected(edits)
        for role in ('normal', 'sanitized'):
            for name in ('bridge_transactions', 'final_transactions'):
                proof = copy.deepcopy(self.proofs[role])
                row = proof[name][0]
                # A self-consistent runtime identity from the other stage still
                # cannot stand in for the runtime that exercised this scenario.
                version, source = ('0.1.34', sdr.RUNTIME) if name == 'bridge_transactions' else ('0.1.35', midpoint.NATIVE_SOURCE)
                row.update(executing_runtime_version=version, build_runtime_version=version,
                           executing_runtime_source=source)
                with self.subTest(role=role, list=name, mutation='wrong-real-runtime'), self.assertRaises(ValueError):
                    self.verify_proof(proof)

    def test_host_proofs_cannot_claim_device_health_execution_or_publication(self):
        self.assert_proof_changes_rejected([((key,), True) for key in
            ('physical_flash_tls_spiffs_and_target_instructions_executed',
             'device_health_confirmation_executed', 'publication_performed')])

    def test_original_ci_snapshots_are_bound_to_exact_run_attempt_and_zip(self):
        inputs = {'bridge': read_json(sdr.ACCEPTANCE), **self.acceptance['inputs']}
        for role, item in inputs.items():
            snapshot = self.proofs['ci']['inputs'][role]
            midpoint.verify_ci_snapshot(item, snapshot)
            edits = [(('run', 'run_attempt'), item['run_attempt'] + 1),
                     (('run', 'head_sha'), '0' * 40), (('run', 'conclusion'), 'failure'),
                     (('run', 'path'), '.github/workflows/unreviewed.yml'),
                     (('artifact', 'expired'), True), (('artifact', 'digest'), 'sha256:' + '0' * 64),
                     (('artifact', 'id'), item['artifact_id'] + 1),
                     (('artifact', 'name'), 'repacked-midpoint'),
                     (('artifact', 'created_at'), '2000-01-01T00:00:00Z')]
            for path, value in edits:
                with self.subTest(role=role, path=path), self.assertRaises(ValueError):
                    midpoint.verify_ci_snapshot(item, changed(snapshot, path, value))


class PublicationGateTests(unittest.TestCase):
    def setUp(self):
        self.acceptance, self.expected, self.index, self.assets, self.bridge = coordinator_fixture()
        self.predecessor = 'd' * 40
        self.source = 'c' * 40

    def confirmation(self):
        return midpoint.confirmation(self.acceptance, self.predecessor)

    def transition(self, *, current=None, parent=None, confirmation=None, index=None):
        midpoint.check_transition(self.acceptance, self.expected, self.index if index is None else index,
                                  self.predecessor, self.predecessor if parent is None else parent,
                                  self.expected if current is None else current,
                                  self.confirmation() if confirmation is None else confirmation)

    def test_exact_confirmation_binds_origin_ota_acceptance_and_index_commit(self):
        self.transition()
        text = self.confirmation()
        for value in (midpoint.midpoint.MIDPOINT_SOURCE, 'Runtime 0.1.34', 'healthy Clock', 'retained data',
                      self.acceptance['ota']['sha256'], pub.sha(pub.encoded(self.acceptance)), self.predecessor):
            self.assertIn(value, text)
        for wrong in ('', 'healthy', text + ' ', midpoint.confirmation(self.acceptance, 'e' * 40)):
            with self.subTest(confirmation=wrong), self.assertRaisesRegex(ValueError, 'operator-confirmed'):
                self.transition(confirmation=wrong)
        for predecessor in ('', 'd' * 39, 'D' * 40):
            with self.subTest(predecessor=predecessor), self.assertRaises(ValueError):
                midpoint.confirmation(self.acceptance, predecessor)

    def test_no_skipped_bridge_changed_index_or_rewrite(self):
        for version in ('1.0.2', '1.0.4', '1.0.5', '1.0.6'):
            wrong = copy.deepcopy(self.expected)
            wrong['firmware']['version'] = version
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.transition(current=wrong)
        with self.assertRaisesRegex(ValueError, 'commit changed'):
            self.transition(parent='e' * 40)
        wrong = copy.deepcopy(self.expected)
        wrong['providers'] = []
        with self.assertRaisesRegex(ValueError, 'Exact native bridge index'):
            self.transition(current=wrong)
        wrong = copy.deepcopy(self.index)
        wrong['services'] = []
        with self.assertRaisesRegex(ValueError, 'Only monotonic firmware'):
            self.transition(index=wrong)

    def publishing(self, *, mutate=True, event='workflow_dispatch', ref='refs/heads/main',
                   repository=pub.REPOSITORY, default_sha=None, dirty=False, changed_committed=None,
                   canonical=True, now=None, confirmation=None, parents=None, bridge='published',
                   collision=None, catalog=True):
        calls = []
        now = now or datetime.fromisoformat(midpoint.NOT_BEFORE.replace('Z', '+00:00'))

        class FrozenTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now if tz is not None else now.replace(tzinfo=None)

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            acceptance = root / 'release/midpoint-test-acceptance.json'
            acceptance.parent.mkdir()
            acceptance.write_bytes(pub.encoded(self.acceptance if canonical else {**self.acceptance, 'changed': True}))
            bridge_acceptance = root / 'release/sdr-test-acceptance.json'
            bridge_acceptance.write_bytes(sdr.ACCEPTANCE.read_bytes())
            product = root / 'release/product.json'
            product.write_bytes(pub.CONFIG.read_bytes())
            for item in self.acceptance['evidence'].values():
                path = root / item['path']
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b'{}\n')
            for owner, name, value in ((midpoint, 'ROOT', root), (midpoint, 'ACCEPTANCE', acceptance),
                                       (sdr, 'ACCEPTANCE', bridge_acceptance), (pub, 'CONFIG', product),
                                       (midpoint, 'datetime', FrozenTime)):
                stack.enter_context(patch.object(owner, name, value))
            stack.enter_context(patch.object(midpoint, 'verify', return_value=(
                self.expected, self.index, copy.deepcopy(self.assets), copy.deepcopy(self.bridge))))
            stack.enter_context(patch.object(midpoint, 'verify_input_ci'))
            stack.enter_context(patch.object(sdr, 'verify_ci'))
            stack.enter_context(patch.object(pub, 'verify_watch_ancestry'))

            def command(*args):
                if args == ('git', 'rev-parse', 'HEAD'):
                    return self.source.encode()
                if args == ('git', 'status', '--porcelain', '--untracked-files=no'):
                    return b' M scripts/publish_midpoint_test.py\n' if dirty else b''
                if args[:2] == ('git', 'show') and args[2].startswith('HEAD:'):
                    path = args[2][5:]
                    return (root / path).read_bytes() + (b'altered' if path == changed_committed else b'')
                if args == ('git', 'show', midpoint.SOURCE + ':release/product.json'):
                    return product.read_bytes()
                raise AssertionError('Unexpected command: ' + repr(args))

            stack.enter_context(patch.object(pub, 'command', side_effect=command))
            stack.enter_context(patch.object(pub, 'api', side_effect=lambda path:
                {'default_branch': 'main'} if path == 'repos/' + pub.REPOSITORY else
                {'sha': self.source if default_sha is None else default_sha}))
            stack.enter_context(patch.dict(os.environ, GITHUB_EVENT_NAME=event, GITHUB_REF=ref,
                                           GITHUB_REPOSITORY=repository))
            stack.enter_context(patch.object(pub, 'current_release_index', side_effect=parents or
                [(self.predecessor, self.expected), (self.predecessor, self.expected)]))
            stack.enter_context(patch.object(midpoint, 'verify_catalog', return_value=
                self.acceptance['installed_catalog'] if catalog else {'accepted': False}))
            stack.enter_context(patch.object(pub, 'release_by_tag', return_value=
                None if bridge == 'missing' else {'draft': bridge == 'draft'}))

            def preflight(releases, output, **kwargs):
                tag = releases[0]['tag']
                calls.append(('preflight', tag, kwargs['prerelease']))
                if tag == collision:
                    raise ValueError('Immutable uploaded asset collision: ' + tag)

            stack.enter_context(patch.object(pub, 'release_preflight', side_effect=preflight))
            stack.enter_context(patch.object(pub, 'publish_one', side_effect=lambda release, output, **kwargs:
                calls.append(('release', release['tag'], release['latest'], kwargs['prerelease']))))
            stack.enter_context(patch.object(pub, 'publish_index', side_effect=lambda index, **kwargs:
                calls.append(('index', index['firmware']['version'], kwargs['expected_parent'], kwargs['expected_current']))))
            # A new external path added to the coordinator must be explicitly
            # mocked above; no test may accidentally fall through to gh or git.
            stack.enter_context(patch.object(pub, 'gh', side_effect=AssertionError('Unexpected gh call')))
            stack.enter_context(patch.object(pub.subprocess, 'run', side_effect=AssertionError('Unexpected subprocess')))
            stack.enter_context(patch.object(pub.subprocess, 'check_output', side_effect=AssertionError('Unexpected subprocess')))
            try:
                with redirect_stdout(io.StringIO()):
                    midpoint.publish(self.acceptance, {}, {}, self.predecessor,
                                     self.confirmation() if confirmation is None else confirmation,
                                     root / 'installed-system', mutate=mutate)
            except ValueError:
                self.assertFalse(any(call[0] in ('release', 'index') for call in calls),
                                 'Guard failure must occur before every external mutation')
                raise
        return calls

    def test_only_106_release_then_index_with_bridge_read_only_and_no_latest(self):
        calls = self.publishing()
        self.assertEqual(calls, [('preflight', 'firmware-v1.0.3', True),
                                 ('preflight', 'firmware-v1.0.6', True),
                                 ('release', 'firmware-v1.0.6', False, True),
                                 ('index', '1.0.6', self.predecessor, self.expected)])

    def test_read_only_preflight_never_publishes_even_after_time_gate(self):
        self.assertEqual(self.publishing(mutate=False), [('preflight', 'firmware-v1.0.3', True),
                                                         ('preflight', 'firmware-v1.0.6', True)])

    def test_automatic_events_wrong_repository_nondefault_and_stale_default_refuse_before_writes(self):
        for kwargs in [*({'event': event} for event in ('push', 'pull_request', 'workflow_run', 'schedule', 'repository_dispatch')),
                       {'ref': 'refs/heads/task'}, {'repository': 'other/repo'}, {'default_sha': 'f' * 40}]:
            with self.subTest(**kwargs), self.assertRaisesRegex(ValueError, 'manual dispatch'):
                self.publishing(**kwargs)

    def test_dirty_uncommitted_acceptance_or_evidence_refuses_before_writes(self):
        with self.assertRaisesRegex(ValueError, 'Dirty publisher source'):
            self.publishing(dirty=True)
        paths = ['release/midpoint-test-acceptance.json', 'release/sdr-test-acceptance.json']
        paths.extend(item['path'] for item in self.acceptance['evidence'].values())
        for path in paths:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'must be committed'):
                self.publishing(changed_committed=path)
        with self.assertRaisesRegex(ValueError, 'Canonical committed acceptance'):
            self.publishing(canonical=False)

    def test_time_gate_refuses_one_microsecond_early_and_allows_exact_boundary(self):
        boundary = datetime.fromisoformat(midpoint.NOT_BEFORE.replace('Z', '+00:00'))
        with self.assertRaisesRegex(ValueError, 'not allowed before'):
            self.publishing(now=boundary - timedelta(microseconds=1))
        self.assertEqual(self.publishing(now=boundary)[-1][0], 'index')
        self.assertEqual(len(self.publishing(mutate=False, now=boundary - timedelta(days=1))), 2)

    def test_missing_operator_confirmation_catalog_acceptance_and_bridge_refuse_before_writes(self):
        with self.assertRaisesRegex(ValueError, 'operator-confirmed'):
            self.publishing(confirmation='')
        with self.assertRaisesRegex(ValueError, 'catalog check changed'):
            self.publishing(catalog=False)
        for state in ('missing', 'draft'):
            with self.subTest(bridge=state), self.assertRaisesRegex(ValueError, 'bridge must already be published'):
                self.publishing(bridge=state)

    def test_bridge_or_midpoint_asset_collision_refuses_before_writes(self):
        for tag in ('firmware-v1.0.3', 'firmware-v1.0.6'):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, 'collision'):
                self.publishing(collision=tag)

    def test_prepublication_races_refuse_before_release_creation(self):
        for parent, current in [('e' * 40, self.expected), (self.predecessor, self.index),
                                (self.predecessor, {**self.expected, 'providers': []})]:
            with self.subTest(parent=parent, version=current['firmware']['version']), self.assertRaises(ValueError):
                self.publishing(parents=[(self.predecessor, self.expected), (parent, current)])

    def test_index_compare_and_swap_rejects_late_race_before_git_writes(self):
        with patch.object(pub, 'current_release_index', return_value=('e' * 40, self.expected)), \
             patch.object(pub, 'command') as command, patch.object(pub.subprocess, 'check_output') as git:
            with self.assertRaisesRegex(ValueError, 'predecessor changed'):
                pub.publish_index(self.index, expected_parent=self.predecessor, expected_current=self.expected)
            command.assert_not_called()
            git.assert_not_called()


class WorkflowBoundaryTests(unittest.TestCase):
    def test_publication_workflow_is_manual_default_branch_and_defaults_to_read_only(self):
        text = (ROOT / '.github/workflows/midpoint-test-publication.yml').read_text()
        trigger = re.search(r'^on:\n(.*?)(?=^[^\s#])', text, re.M | re.S).group(1)
        self.assertEqual(re.findall(r'^  ([a-z_]+):', trigger, re.M), ['workflow_dispatch'])
        self.assertIn('default: preflight', trigger)
        self.assertIn('options: [preflight, publish]', trigger)
        self.assertIn('expected_index_commit:', trigger)
        self.assertIn('operator_confirmation:', trigger)
        self.assertIn("if: github.ref == format('refs/heads/{0}', github.event.repository.default_branch)", text)
        self.assertIn('group: twatch-driver-publication', text)
        self.assertIn('cancel-in-progress: false', text)
        self.assertIn('ref: ' + midpoint.SYSTEM_SOURCE, text)
        self.assertIn('test_midpoint_publication.py', text)
        self.assertIn('"$MIDPOINT_ACTION"', text)
        self.assertIn('--expected-index-commit "$MIDPOINT_PREDECESSOR"', text)
        self.assertIn('--operator-confirmation "$MIDPOINT_CONFIRMATION"', text)

    def test_pull_request_checks_are_read_only_and_frozen_product_stays_102(self):
        text = (ROOT / '.github/workflows/midpoint-publication-checks.yml').read_text()
        self.assertIn('contents: read', text)
        self.assertNotIn('contents: write', text)
        self.assertNotIn('python scripts/publish_midpoint_test.py', text)
        self.assertIn('python -m unittest discover -s tests -p test_midpoint_publication.py', text)
        self.assertEqual(read_json(pub.CONFIG)['version'], '1.0.2')


@unittest.skipUnless(os.environ.get('MIDPOINT_ARTIFACT_DIR'), 'Optional original hosted ZIPs were not supplied')
class ActualArtifactIntegrationTests(unittest.TestCase):
    def test_full_offline_derivation_matches_every_frozen_output(self):
        acceptance = midpoint.validate_acceptance(read_json(midpoint.ACCEPTANCE))
        with patch.object(pub, 'gh', side_effect=AssertionError('Offline integration must not use GitHub')), \
             patch.object(pub, 'publish_one', side_effect=AssertionError('Integration must not publish')), \
             patch.object(pub, 'publish_index', side_effect=AssertionError('Integration must not publish')):
            raw = midpoint.original_inputs(acceptance, os.environ['MIDPOINT_ARTIFACT_DIR'])
            expected, index, assets, _ = midpoint.verify(acceptance, raw, midpoint.read_evidence(acceptance))
        self.assertEqual(expected['firmware']['version'], '1.0.3')
        self.assertEqual(index['firmware']['version'], '1.0.6')
        self.assertEqual(set(assets), set(acceptance['derived_assets']))
        for name, data in assets.items():
            self.assertEqual(midpoint.midpoint.metadata(data), acceptance['derived_assets'][name])
        for key in ('apps', 'drivers', 'services', 'providers'):
            self.assertEqual(index.get(key), expected.get(key))


if __name__ == '__main__':
    unittest.main()

import copy
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import current_cohort as cohort
from current_bootfs import build
import publish_sdr_test as sdr
import publish_watch_product as pub
from watch_release_index import EMPTY_INDEX, update_index


def fixture():
    source = 'a' * 40
    fw = b'\xe9' + b'native-fixture' * 8
    old_identity = cohort.create('1.0.2', '0.1.33', sdr.BASELINE['source_sha'], b'old-native' * 8)
    identity = cohort.create('1.0.4', '0.1.34', source, fw)
    old_app = {'version': '1.4.9', 'file_name': 'springboard.elf', 'type': 'application'}
    boot = {'app_capabilities': [{'manifest': 'springboard.json'}], 'drivers': []}
    old_members = {'cohort.json': cohort.encode(old_identity), 'boot.json': pub.encoded(boot),
                   'springboard.json': pub.encoded(old_app), 'springboard.elf': b'old-launcher',
                   'existing-provider/driver.elf': b'unchanged-provider'}
    old_store, _ = build(old_members, cohort.STORE_SIZE)
    boot = copy.deepcopy(boot)
    boot['app_capabilities'].append({'manifest': 'waterfall.json'})
    boot['drivers'].append({'manifest': 's3-radio-iq/manifest.json'})
    boot['cohort_migration'] = {'schema': 1, 'from': {'product': 'twatch-s3', 'version': '1.0.2',
        'source_revision': sdr.BASELINE['source_sha']}, 'to': {'product': 'twatch-s3', 'version': '1.0.4'},
        'shared_key_value': [{'application_id': 'waterfall', 'api': 1, 'namespace': 1}]}
    members = {**old_members, 'cohort.json': cohort.encode(identity), 'boot.json': pub.encoded(boot),
               'springboard.json': pub.encoded({**old_app, 'version': '1.4.10'}),
               'springboard.elf': b'new-launcher', 'waterfall.json': b'{}', 'waterfall.elf': b'app',
               's3-radio-iq/driver.elf': b'driver', 's3-radio-iq/manifest.json': b'{}'}
    store, _ = build(members, cohort.STORE_SIZE)
    payload, ota = cohort.package(identity, fw, store)
    fulls = []
    for data in (old_store, store):
        image = bytearray(b'\xff' * 0x1000000)
        image[0x10000:0x10000 + len(fw)] = fw
        image[0x2f0000:0x800000] = data
        fulls.append(bytes(image))
    old = pub.record('firmware', '', '1.0.2', 'twatch-s3-launcher-1.0.2.bin', b'unused')
    old.update(sha256=sdr.BASELINE['release_bin_sha256'], size=0x1000000,
               component_versions={'springboard': '1.4.9', 'runtime': '0.1.33'},
               ota={'store_sha256': pub.sha(old_store)})
    base = update_index(copy.deepcopy(EMPTY_INDEX), 'firmware', old)
    base['services'] = [{'id': 'untouched'}]
    bridge = pub.record('firmware', '', '1.0.3', 'twatch-s3-launcher-1.0.3.bin', fulls[0],
                        source_sha=source, hardware_qualified=False,
                        component_versions={'springboard': '1.4.9', 'runtime': '0.1.34'},
                        native_bridge={'retained_cohort_version': '1.0.2', 'retained_store_sha256': pub.sha(old_store)})
    bridge['ota'] = {'asset': 'riscrte-runtime-0.1.34.bin', 'size': len(fw), 'sha256': pub.sha(fw),
                     'kind': 'runtime-image', 'runtime_version': '0.1.34', 'store_abi': 2, 'layout': cohort.LAYOUT,
                     'url': f'https://github.com/{pub.REPOSITORY}/releases/download/firmware-v1.0.3/riscrte-runtime-0.1.34.bin'}
    final = pub.record('firmware', '', '1.0.4', 'twatch-s3-launcher-1.0.4.bin', fulls[1],
                       source_sha=source, hardware_qualified=False,
                       component_versions={'springboard': '1.4.10', 'runtime': '0.1.34'}, ota=ota)
    index1 = update_index(base, 'firmware', bridge)
    index2 = update_index(index1, 'firmware', final)
    files = {}
    for record, initial, data in ((bridge, fulls[0], fw), (final, fulls[1], payload)):
        assets = {record['asset']: initial, record['ota']['asset']: data,
                  'release-record.json': pub.encoded(record), 'radio-iq-proof.json': b'{}', 'LICENSES.zip': b'license-fixture'}
        assets['SHA256SUMS'] = ''.join(f'{pub.sha(b)}  {n}\n' for n, b in sorted(assets.items())).encode()
        files.update({'sdr-upgrade/' + record['tag'] + '/' + n: b for n, b in assets.items()})
    proof = dict(watch_source=source, source_release_sha256=sdr.BASELINE['release_bin_sha256'],
                 source_cohort=old_identity, target_cohort=identity, native_sha256=pub.sha(fw),
                 cohort_sha256=pub.sha(payload), cohort_bytes=len(payload),
                 configuration={'sources': {'runtime': {'commit': sdr.RUNTIME}, 'system-apps': {'commit': 'b' * 40}},
                                'app_versions': {'springboard': '1.4.10'}},
                 both_catalogs_accepted_by_installed_provider=True, monotonic_catalog_stages=True,
                 initial_image_is_destructive=True, ordinary_payloads_exclude_nvs_appdata_bootloader_partitions=True,
                 bridge_initial_image_sha256=pub.sha(fulls[0]), initial_image_sha256=pub.sha(fulls[1]),
                 files={n: {'size_bytes': len(b), 'sha256': pub.sha(b)} for n, b in members.items()})
    files['sdr-upgrade/sdr-build-proof.json'] = pub.encoded(proof)
    files['sdr-upgrade/release-index.stage1-native.json'] = pub.encoded(index1)
    files['sdr-upgrade/release-index.stage2-cohort.json'] = pub.encoded(index2)
    files['sdr-upgrade/INSTALL.txt'] = b'Use built-in Firmware Update twice. Initial images are destructive.\n'
    files['current-launcher-catalog-proof.json'] = pub.encoded({'watch_source': source, 'entries': 18,
        'system_source': 'b' * 40, 'tests': [{'sanitized': False}, {'sanitized': True}]})
    test = dict(native_candidate=sdr.RUNTIME, native_sha256=pub.sha(fw), cohort_sha256=pub.sha(payload),
                released_bin_sha256=sdr.BASELINE['release_bin_sha256'], direct_old_cohort_rejected=True,
                staged_graph_admission={'cohort_validated': True}, physical_flash_tls_spiffs_and_target_instructions_executed=False,
                transactions=[dict(nvs_appdata_preserved=True, previous_pair_preserved=True, target_executed=False,
                                   native_bytes=len(fw), payload_bytes=n) for n in (len(fw), len(fw), len(payload), len(payload))])
    for name in ('sdr-upgrade-test', 'sdr-upgrade-test-san'):
        files[name + '/upgrade-proof.json'] = pub.encoded(test)
    raw = pub.archive(files)
    a = dict(schema=1, repository=pub.REPOSITORY, source_sha=source, sha256=pub.sha(raw),
             run_id=21, run_attempt=2, artifact_id=42, name='twatch-sdr-upgrade-' + source,
             base_index_commit=sdr.BASELINE['index_source'], base_index=base)
    return a, raw, files, {'native': index1, 'cohort': index2}


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.raw, cls.files, cls.indexes = fixture()

    def test_complete_exact_artifact_and_preserved_102(self):
        before = copy.deepcopy(self.a['base_index'])
        indexes, assets, install = sdr.verify_bundle(self.a, self.raw)
        self.assertEqual(indexes, self.indexes)
        self.assertEqual(self.a['base_index'], before)
        self.assertEqual(indexes['cohort']['services'], before['services'])
        with tempfile.TemporaryDirectory() as tmp:
            releases = sdr.stage_releases(self.a, assets, install, Path(tmp))
            self.assertEqual({r['tag'] for r in releases.values()}, {'firmware-v1.0.3', 'firmware-v1.0.4'})
            self.assertTrue(all(not r['latest'] for r in releases.values()))
            self.assertIn('destructive', (Path(tmp) / 'firmware-v1.0.3/PUBLICATION.txt').read_text())
            self.assertFalse((Path(tmp) / 'firmware-v1.0.2').exists())

    def rejected_edit(self, name, edit, error):
        files = self.files.copy()
        value = json.loads(files[name]); edit(value); files[name] = pub.encoded(value)
        raw = pub.archive(files)
        with self.assertRaisesRegex(ValueError, error):
            sdr.verify_bundle({**self.a, 'sha256': pub.sha(raw)}, raw)

    def test_mixed_source(self):
        self.rejected_edit('sdr-upgrade/sdr-build-proof.json', lambda p: p.update(watch_source='c' * 40), 'Mixed source')

    def test_wrong_launcher(self):
        self.rejected_edit('current-launcher-catalog-proof.json', lambda p: p.update(entries=16), '18-entry')

    def test_omitted_preservation_proof(self):
        self.rejected_edit('sdr-upgrade-test-san/upgrade-proof.json', lambda p: p.update(transactions=[]), 'preservation')

    def test_changed_existing_rows(self):
        self.rejected_edit('sdr-upgrade/release-index.stage2-cohort.json', lambda p: p.update(services=[]), 'existing catalog')

    def test_wrong_outer_hash(self):
        with self.assertRaisesRegex(ValueError, 'ZIP hash'):
            sdr.verify_bundle({**self.a, 'sha256': '0' * 64}, self.raw)

    def test_malformed_and_unsafe_zip(self):
        for name in ('../escape', '/absolute', 'sdr-upgrade/../escape'):
            raw = pub.archive({name: b'x'})
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unsafe'):
                sdr.verify_bundle({**self.a, 'sha256': pub.sha(raw)}, raw)
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            sdr.decode(b'{"schema":1,"schema":2}')

    def test_mixed_asset_even_with_reaccepted_outer_hash(self):
        files = self.files.copy(); files['sdr-upgrade/firmware-v1.0.3/riscrte-runtime-0.1.34.bin'] += b'corrupt'
        raw = pub.archive(files)
        with self.assertRaisesRegex(ValueError, 'checksums'):
            sdr.verify_bundle({**self.a, 'sha256': pub.sha(raw)}, raw)

    def test_wrong_baseline(self):
        a = copy.deepcopy(self.a); a['base_index']['firmware']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '1.0.2 predecessor'):
            sdr.validate_acceptance(a)

    def test_monotonic_stages_and_explicit_confirmation(self):
        base = self.a['base_index']; first = self.indexes['native']; sha = 'd' * 40
        sdr.check_transition(self.a, self.indexes, 'native', self.a['base_index_commit'], self.a['base_index_commit'], base)
        text = sdr.confirmation(self.a, sha)
        sdr.check_transition(self.a, self.indexes, 'cohort', sha, sha, first, text)
        self.assertIn(self.a['sha256'], text)
        with self.assertRaisesRegex(ValueError, 'operator-confirmed'):
            sdr.check_transition(self.a, self.indexes, 'cohort', sha, sha, first)
        with self.assertRaisesRegex(ValueError, 'operator-confirmed'):
            sdr.check_transition(self.a, self.indexes, 'cohort', sha, sha, first, 'healthy')
        with self.assertRaisesRegex(ValueError, 'operator-confirmed'):
            sdr.check_transition(self.a, self.indexes, 'cohort', sha, sha, first, sdr.confirmation(self.a, 'e' * 40))
        with self.assertRaisesRegex(ValueError, 'predecessor index'):
            sdr.check_transition(self.a, self.indexes, 'cohort', sha, sha, base, text)
        with self.assertRaisesRegex(ValueError, 'predecessor index'):
            sdr.check_transition(self.a, self.indexes, 'cohort', sha, sha, self.indexes['cohort'], text)

    def test_wrong_predecessor_and_no_stage1_health_claim(self):
        for parent, current, text in [('e' * 40, self.a['base_index'], ''),
                                      (self.a['base_index_commit'], self.indexes['native'], ''),
                                      (self.a['base_index_commit'], self.a['base_index'], 'healthy')]:
            with self.assertRaises(ValueError):
                sdr.check_transition(self.a, self.indexes, 'native', self.a['base_index_commit'], parent, current, text)

    def test_index_compare_and_swap_refuses_race_without_write(self):
        with patch.object(pub, 'current_release_index', return_value=('e' * 40, self.a['base_index'])), \
             patch.object(pub, 'command') as command, patch.object(pub.subprocess, 'check_output') as git:
            with self.assertRaisesRegex(ValueError, 'predecessor changed'):
                pub.publish_index(self.indexes['native'], expected_parent=self.a['base_index_commit'], expected_current=self.a['base_index'])
            command.assert_not_called(); git.assert_not_called()

    def test_committed_acceptance_matches_build_custody(self):
        accepted = sdr.validate_acceptance(json.loads((ROOT / 'release/sdr-test-acceptance.json').read_text()))
        custody = json.loads((ROOT / 'release/sdr-test-build-custody.json').read_text())
        self.assertEqual(custody['watch_source'], accepted['source_sha'])
        self.assertEqual(custody['artifact_id'], accepted['artifact_id'])
        self.assertEqual(custody['artifact_zip_sha256'], accepted['sha256'])
        self.assertEqual(custody['runtime_source'], sdr.RUNTIME)
        self.assertEqual(custody['hosted_native_sha256'], custody['path_mapped_local_native_sha256'])
        self.assertTrue(custody['firmware_bytes_identical_after_path_mapping'])
        self.assertTrue(custody['native_static_memory_layout_unchanged'])
        self.assertFalse(custody['physical_qualification'])
        self.assertTrue(all(p['passed'] for p in custody['exact_hosted_rechecks'].values()))

    def test_sdr_workflow_manual_only_and_frozen_product(self):
        workflow = (ROOT / '.github/workflows/sdr-test-publication.yml').read_text()
        self.assertIn('  workflow_dispatch:', workflow)
        self.assertNotIn('  push:', workflow); self.assertNotIn('  workflow_run:', workflow)
        self.assertNotIn('  pull_request:', workflow)
        self.assertIn('group: twatch-driver-publication', workflow)
        self.assertEqual(json.loads(pub.CONFIG.read_text())['version'], '1.0.2')

    def publishing(self, stage, confirmation='', current=None, event='workflow_dispatch', parents=None):
        calls = []
        commit = self.a['base_index_commit'] if stage == 'native' else 'd' * 40
        current = current or (self.a['base_index'] if stage == 'native' else self.indexes['native'])
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            path = Path(tmp) / 'acceptance.json'; path.write_bytes(pub.encoded(self.a))
            stack.enter_context(patch.object(sdr, 'ACCEPTANCE', path))
            stack.enter_context(patch.object(sdr, 'verify_ci'))
            stack.enter_context(patch.object(pub, 'verify_watch_ancestry'))
            def command(*args):
                if args[1] == 'rev-parse': return self.a['source_sha'].encode()
                if args[1] == 'status': return b''
                return path.read_bytes() if args[2] == 'HEAD:release/sdr-test-acceptance.json' else pub.CONFIG.read_bytes()
            stack.enter_context(patch.object(pub, 'command', side_effect=command))
            stack.enter_context(patch.object(pub, 'api', side_effect=lambda p: {'default_branch': 'main'} if p == 'repos/' + pub.REPOSITORY else {'sha': self.a['source_sha']}))
            stack.enter_context(patch.dict(os.environ, GITHUB_EVENT_NAME=event, GITHUB_REPOSITORY=pub.REPOSITORY, GITHUB_REF='refs/heads/main'))
            stack.enter_context(patch.object(pub, 'current_release_index', side_effect=parents or [(commit, current), (commit, current)]))
            stack.enter_context(patch.object(pub, 'release_by_tag', return_value={'draft': False}))
            stack.enter_context(patch.object(pub, 'release_preflight', side_effect=lambda *a, **k: calls.append('preflight')))
            stack.enter_context(patch.object(pub, 'publish_one', side_effect=lambda r, p, **k: calls.append(('release', r['tag'], k['prerelease']))))
            stack.enter_context(patch.object(pub, 'publish_index', side_effect=lambda i, **k: calls.append(('index', i['firmware']['version'], k['expected_parent']))))
            try:
                sdr.publish(self.a, self.raw, stage, commit, confirmation, mutate=True)
            except ValueError:
                self.assertFalse(any(isinstance(c, tuple) for c in calls), 'Failure must precede writes')
                raise
        return calls

    def test_publication_selects_only_one_stage_in_release_then_index_order(self):
        self.assertEqual(self.publishing('native')[-2:], [('release', 'firmware-v1.0.3', True),
            ('index', '1.0.3', self.a['base_index_commit'])])
        self.assertEqual(self.publishing('cohort', sdr.confirmation(self.a, 'd' * 40))[-2:],
            [('release', 'firmware-v1.0.4', True), ('index', '1.0.4', 'd' * 40)])

    def test_premature_stage2_refuses_before_any_publication(self):
        with self.assertRaisesRegex(ValueError, 'operator-confirmed'):
            self.publishing('cohort')
        with self.assertRaisesRegex(ValueError, 'predecessor index'):
            self.publishing('cohort', sdr.confirmation(self.a, 'd' * 40), current=self.a['base_index'])

    def test_automatic_events_refuse_before_any_publication(self):
        for event in ('push', 'pull_request', 'workflow_run'):
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, 'manual dispatch'):
                self.publishing('native', event=event)

    def test_catalog_race_before_asset_creation_refuses(self):
        with self.assertRaisesRegex(ValueError, 'predecessor commit'):
            self.publishing('native', parents=[(self.a['base_index_commit'], self.a['base_index']),
                                               ('e' * 40, self.a['base_index'])])

    def test_self_consistent_changed_provider_still_refused(self):
        files = self.files.copy()
        index_name = 'sdr-upgrade/release-index.stage2-cohort.json'
        index = json.loads(files[index_name]); record = index['firmware']
        directory = 'sdr-upgrade/firmware-v1.0.4/'
        original = files[directory + record['ota']['asset']]
        native = original[:record['ota']['firmware_size']]
        members = sdr.read_image(original[len(native):], cohort.STORE_SIZE)
        members['existing-provider/driver.elf'] = b'not-approved'
        store, _ = build(members, cohort.STORE_SIZE)
        payload, record['ota'] = cohort.package(cohort.parse(members['cohort.json']), native, store)
        full = bytearray(files[directory + record['asset']]); full[0x2f0000:0x800000] = store
        record['sha256'] = pub.sha(full)
        files[directory + record['asset']] = bytes(full)
        files[directory + record['ota']['asset']] = payload
        files[directory + 'release-record.json'] = pub.encoded(record)
        files[index_name] = pub.encoded(index)
        assets = {n.removeprefix(directory): b for n, b in files.items() if n.startswith(directory)}
        files[directory + 'SHA256SUMS'] = ''.join(f'{pub.sha(b)}  {n}\n' for n, b in sorted(assets.items()) if n != 'SHA256SUMS').encode()
        proof_name = 'sdr-upgrade/sdr-build-proof.json'; proof = json.loads(files[proof_name])
        proof.update(initial_image_sha256=pub.sha(full), cohort_sha256=pub.sha(payload),
                     files={n: {'size_bytes': len(b), 'sha256': pub.sha(b)} for n, b in members.items()})
        files[proof_name] = pub.encoded(proof)
        raw = pub.archive(files)
        with self.assertRaisesRegex(ValueError, 'provider/store bytes changed'):
            sdr.verify_bundle({**self.a, 'sha256': pub.sha(raw)}, raw)


class CITests(unittest.TestCase):
    def setUp(self):
        self.a = dict(run_id=21, run_attempt=2, artifact_id=42, source_sha='a' * 40, name='twatch-sdr-upgrade-' + 'a' * 40, sha256='f' * 64)
        self.run = dict(id=21, run_attempt=2, head_sha='a' * 40, status='completed', conclusion='success',
                        path='.github/workflows/drivers.yml', repository={'full_name': pub.REPOSITORY},
                        run_started_at='2026-10-06T09:00:00Z', updated_at='2026-10-06T10:00:00Z')
        self.item = dict(id=42, name=self.a['name'], expired=False, workflow_run={'id': 21, 'head_sha': 'a' * 40},
                         digest='sha256:' + self.a['sha256'], created_at='2026-10-06T09:30:00Z')

    def test_exact_accepted_attempt(self):
        with patch.object(pub, 'api', side_effect=[self.run, self.item]): sdr.verify_ci(self.a)

    def test_wrong_run_attempt_source_workflow_status(self):
        for key, value in [('run_attempt', 1), ('head_sha', 'b' * 40), ('conclusion', 'failure'),
                           ('status', 'in_progress'), ('path', '.github/workflows/other.yml')]:
            with self.subTest(key=key), patch.object(pub, 'api', side_effect=[{**self.run, key: value}, self.item]), self.assertRaises(ValueError):
                sdr.verify_ci(self.a)

    def test_mixed_or_expired_artifact_and_previous_attempt_time(self):
        for key, value in [('id', 43), ('name', 'other'), ('expired', True), ('digest', 'sha256:' + '0' * 64),
                           ('created_at', '2026-10-06T08:59:00Z'), ('workflow_run', {'id': 20, 'head_sha': 'a' * 40})]:
            with self.subTest(key=key), patch.object(pub, 'api', side_effect=[self.run, {**self.item, key: value}]), self.assertRaises(ValueError):
                sdr.verify_ci(self.a)


if __name__ == '__main__':
    unittest.main()

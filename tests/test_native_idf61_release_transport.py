import copy
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('transport', ROOT / 'scripts/transport_native_idf61_release.py')
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        sources = {role: {'revision': format(i + 1, '040x'), 'tree': format(i + 11, '040x'), 'submodules': []} for i, role in enumerate(sorted(t.ROLES))}
        self.contract = dict(schema=1, finalized=True, publication_enabled=False, product='twatch',
            repository=t.PRODUCTS['twatch'][0], version='1.1.40', release_tag='test-native-idf61-1.1.40',
            release_branch='work/native-idf-6.1', runtime_repository='michaelrolphone-cmyk/RiscRTE',
            runtime_tag='firmware-v0.4.0', runtime_revision=sources['runtime']['revision'],
            runtime_release_revision=sources['runtime']['revision'], runtime_run_id=123, runtime_run_attempt=2,
            runtime_artifact_id=456, candidate_version='1.1.40', sources={role: pin['revision'] for role, pin in sources.items()},
            evidence_asset='Runtime-0.4.0-Watch-1.1.40-Native-IDF61-Evidence.zip')
        self.files = {'candidate/' + name: (name + ' exact bytes').encode() for name in t.FILES}
        native_files = {}
        for key, name, path in [('firmware_bin', 'firmware.bin', 'riscrte_native.bin'), ('bootloader', 'bootloader.bin', 'bootloader/bootloader.bin'), ('partitions', 'partitions.bin', 'partition_table/partition-table.bin')]:
            data = self.files['candidate/' + name]; self.files['build/' + path] = data
            native_files[key] = dict(path=path, **t.record(data))
        baseline = dict(product='twatch', elf_count=59, store_file_count=121)
        self.files['metadata/released-baseline.json'] = t.encoded(baseline)
        self.contract['baseline_contract_sha256'] = t.digest(self.files['metadata/released-baseline.json'])
        lock = dict(schema=1, publication_enabled=False, candidate_version='1.1.40', sources=sources,
                    native_files=native_files, baseline_contract_sha256=self.contract['baseline_contract_sha256'])
        proof = dict(fresh_build=True, same_process_qualification=True, detached_receipt_is_attestation=False,
                     compile_jobs=1, sources=sources, artifacts={key: {field: row[field] for field in ('bytes', 'sha256')} for key, row in native_files.items()})
        self.q = dict(schema=1, status='software-qualified-candidate-hardware-pending', **t.LIMITS,
            input_lock=lock, controlled_build=proof, baseline_contract=baseline, unchanged_store_payloads=120,
            native=dict(arduino_core_linked=False, ordinary_app_payloads_rebuilt=False, unselected_usb_host_controller=False, elf_bin_identical=True),
            preservation_software_model=dict(passed=True, cases=496, nvs_and_appdata_preserved=True, bootloader_compatibility_tested=False, hardware_tested=False))
        for field, sanitized in [('admission', False), ('admission_sanitized', True)]:
            self.q[field] = dict(elf_count=59, sanitized=sanitized, hardware_calls=0, storage_calls=0, target_instructions_executed=False)
        self.files['metadata/workflow.yml'] = b'reviewed workflow bytes'
        self.files['metadata/ci-run.json'] = t.encoded(dict(GITHUB_REPOSITORY=self.contract['runtime_repository'],
            GITHUB_SHA=self.contract['runtime_revision'], GITHUB_REF='refs/heads/work/native-idf-6.1', GITHUB_RUN_ID='123',
            GITHUB_RUN_ATTEMPT='2', GITHUB_WORKFLOW_REF='michaelrolphone-cmyk/RiscRTE/.github/workflows/native-idf6.yml@refs/heads/work/native-idf-6.1',
            GITHUB_WORKFLOW_SHA=self.contract['runtime_revision'], PRODUCT='twatch'))
        custody = t.encoded(dict(schema=1, sources={role: dict(clean=True, **pin) for role, pin in sources.items()}))
        self.files['metadata/sources-before.json'] = custody; self.files['metadata/sources-after.json'] = custody
        self.seal()

    def tearDown(self):
        self.tmp.cleanup()

    def seal(self, update_q=True):
        if update_q:
            lock_data = t.encoded(self.q['input_lock'])
            self.files['candidate/source-lock.json'] = lock_data
            self.files['build/native-build-evidence/source-lock.json'] = lock_data
            self.q['input_lock_sha256'] = t.digest(lock_data)
            self.files['build/native-build-evidence/build-closure.json'] = t.encoded(self.q['controlled_build'])
            self.q['artifacts'] = {name: t.record(self.files['candidate/' + name]) for name in t.FILES}
            self.files['candidate/qualification.json'] = t.encoded(self.q)
        self.contract['qualification_sha256'] = t.digest(self.files['candidate/qualification.json'])
        self.contract['candidate_artifacts'] = self.q['artifacts']
        self.files['candidate/SHA256SUMS'] = ''.join(t.digest(self.files['candidate/' + name]) + '  ' + name + '\n' for name in sorted(t.CANDIDATE_FILES - {'SHA256SUMS'})).encode()
        self.archive = self.root / 'evidence.zip'
        with zipfile.ZipFile(self.archive, 'w') as z:
            for name, data in self.files.items(): z.writestr(name, data)
        self.contract['evidence_sha256'] = t.digest(self.archive.read_bytes())
        row = dict(id=456, name='native-idf6-twatch-' + self.contract['runtime_revision'], **t.record(self.archive.read_bytes()),
                   job_id=789, job_name='T-Watch', sources=self.q['input_lock']['sources'], members={name: t.record(data) for name, data in self.files.items()})
        self.manifest = dict(schema=1, enabled=True, repository=self.contract['runtime_repository'], version='0.4.0',
            tag='firmware-v0.4.0', publication_branch='work/native-idf-6.1', source_sha=self.contract['runtime_revision'],
            source_workflow_sha256=t.digest(self.files['metadata/workflow.yml']), run_id=123, run_attempt=2, workflow_id=100,
            artifacts=dict(generic={}, twatch=row, waveshare={}, x4={}))
        self.save_manifest()

    def save_manifest(self):
        self.manifest_path = self.root / 'runtime-manifest.json'
        self.manifest_path.write_bytes(t.encoded(self.manifest))
        self.contract['runtime_manifest_sha256'] = t.digest(self.manifest_path.read_bytes())
        self.contract_path = self.root / 'contract.json'; self.contract_path.write_bytes(t.encoded(self.contract))

    def run_transport(self):
        self.contract_path.write_bytes(t.encoded(self.contract))
        t.transport(self.contract_path, self.manifest_path, self.archive, 'a' * 40, self.root / 'out')

    def test_exact_copy_and_custody(self):
        self.run_transport(); out = self.root / 'out'
        self.assertEqual((out / 'TWatch-1.1.40-Native-IDF61-Evidence.zip').read_bytes(), self.archive.read_bytes())
        self.assertEqual((out / 'TWatch-1.1.40-Native-IDF61-factory-erases-data-0x0.bin').read_bytes(), self.files['candidate/factory-candidate-erases-data-0x0.bin'])
        self.assertIn(b'erases internal saved settings', (out / 'RELEASE-NOTES.txt').read_bytes())
        t.verify_output(out, t.digest((out / 'SHA256SUMS').read_bytes()), 'a' * 40)

    def test_disabled_contract(self):
        self.contract['finalized'] = False
        with self.assertRaisesRegex(ValueError, 'not finalized'): self.run_transport()

    def test_outer_sha(self):
        self.contract['evidence_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'digest differs'): self.run_transport()

    def test_manifest_sha(self):
        self.contract['runtime_manifest_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'digest differs'): self.run_transport()

    def test_run_attempt(self):
        self.manifest['run_attempt'] = 3; self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'run/attempt'): self.run_transport()

    def test_inventory(self):
        del self.manifest['artifacts']['twatch']['members']['metadata/workflow.yml']; self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'inventory'): self.run_transport()

    def test_unsafe_zip(self):
        for name in ['../escape', '/absolute', 'a/../b', 'a//b', 'a\\b', 'a:b']:
            with self.subTest(name=name), zipfile.ZipFile(self.archive, 'w') as z: z.writestr(name, b'x')
            with self.assertRaises(ValueError): t.archive_members(self.archive)

    def test_duplicate_zip(self):
        with warnings.catch_warnings(), zipfile.ZipFile(self.archive, 'w') as z:
            warnings.simplefilter('ignore'); z.writestr('same', b'a'); z.writestr('same', b'b')
        with self.assertRaisesRegex(ValueError, 'Duplicate ZIP'): t.archive_members(self.archive)

    def test_symlink_zip(self):
        info = zipfile.ZipInfo('link'); info.create_system = 3; info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(self.archive, 'w') as z: z.writestr(info, 'target')
        with self.assertRaisesRegex(ValueError, 'Nonregular'): t.archive_members(self.archive)

    def test_duplicate_json(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'): t.decode(b'{"a":1,"a":2}')

    def test_hardware_claim(self):
        self.q['hardware_tested'] = True; self.seal()
        with self.assertRaisesRegex(ValueError, 'limit changed'): self.run_transport()

    def test_detached_receipt(self):
        self.q['controlled_build']['same_process_qualification'] = False; self.seal()
        with self.assertRaisesRegex(ValueError, 'controlled single-job'): self.run_transport()

    def test_parallel_build(self):
        self.q['controlled_build']['compile_jobs'] = 2; self.seal()
        with self.assertRaisesRegex(ValueError, 'controlled single-job'): self.run_transport()

    def test_unadmitted_elf(self):
        self.q['admission_sanitized']['elf_count'] = 58; self.seal()
        with self.assertRaisesRegex(ValueError, 'ELF admission'): self.run_transport()

    def test_dirty_source(self):
        row = t.decode(self.files['metadata/sources-after.json']); row['sources']['runtime']['clean'] = False
        self.files['metadata/sources-after.json'] = t.encoded(row); self.seal()
        with self.assertRaisesRegex(ValueError, 'source custody'): self.run_transport()

    def test_changed_native_input(self):
        self.files['build/riscrte_native.bin'] = b'changed'; self.seal()
        with self.assertRaisesRegex(ValueError, 'native input'): self.run_transport()

    def test_stale_payload(self):
        self.files['candidate/firmware.bin'] = b'replaced payload'; self.seal()
        with self.assertRaisesRegex(ValueError, 'Payload/linked build'): self.run_transport()

    def test_extra_candidate(self):
        self.files['candidate/update.zip'] = b'unapproved'; self.seal()
        with self.assertRaisesRegex(ValueError, 'output set'): self.run_transport()

    def test_late_mutation_and_extra_output(self):
        self.run_transport(); out = self.root / 'out'; expected = t.digest((out / 'SHA256SUMS').read_bytes())
        (out / 'extra').write_bytes(b'unexpected')
        with self.assertRaisesRegex(ValueError, 'asset set'): t.verify_output(out, expected, 'a' * 40)

    def test_workflow_creates_exact_tag_before_release(self):
        workflows = sorted((ROOT / 'release').glob('*-native-idf61-release.yml'))
        if not workflows:
            workflows = [ROOT / '.github/workflows/native-idf61-release.yml']
        self.assertIn(len(workflows), (1, 2))
        for workflow in workflows:
            text = workflow.read_text()
            self.assertIn('-f "ref=refs/tags/$RELEASE_TAG" -f "sha=$GITHUB_SHA"', text)
            self.assertLess(text.index('gh api --method POST'), text.index('gh release create'))
            self.assertIn('--verify-tag --target "$GITHUB_SHA"', text)

    def test_no_overwrite(self):
        (self.root / 'out').mkdir()
        with self.assertRaisesRegex(ValueError, 'must be new'): self.run_transport()


if __name__ == '__main__': unittest.main()

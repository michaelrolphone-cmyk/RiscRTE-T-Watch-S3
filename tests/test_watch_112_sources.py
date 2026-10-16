"""Original-source mapping and reconstruction archive custody."""
import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import reconstruct_watch_112_sources as rebuild
import publish_watch_product as pub


class ReconstructWatch112Tests(unittest.TestCase):
    @staticmethod
    def transport_parts():
        return tuple(ROOT / 'release/complete-1.0.12' / name for name in rebuild.BUILD_INPUT_PART_NAMES)

    def test_all_original_source_bundles_are_pinned(self):
        files = rebuild.members(ROOT / 'release/complete-1.0.12/source-custody.zip', rebuild.CUSTODY_SHA)
        mapping = rebuild.validate_mapping(files)
        self.assertEqual(len(mapping['sources']), 5)
        self.assertEqual(mapping['built_watch_commit'], 'f3f8755619e94d0078ef16d43d9c6039bee46b8d')
        self.assertTrue(all(v['bundle_prerequisite_commit'] != v['built_commit'] for v in mapping['sources']))
        self.assertEqual(next(v for v in mapping['sources'] if v['repository'].endswith('/RiscRTE'))['built_commit'],
                         '2abc312217fadb04ac0d9c994ecb38edc15edf6a')

    def test_all_historical_build_inputs_are_supplied(self):
        raw = rebuild.build_inputs_bytes(self.transport_parts())
        files = rebuild.archive_members(raw, rebuild.BUILD_INPUTS_SHA)
        self.assertEqual(len(files), 6)
        self.assertEqual(rebuild.sha(files['rf-1.0.8-apps.zip']),
                         'fad1e9dcadd862b6f1c14753253010ae61f85fbe896dbeb1c20e87fb4fb28339')
        import json
        descriptor = json.loads((ROOT / 'apps/runtime-features-1.0.11-origin.json').read_text())
        for name, expected in descriptor['assets'].items():
            raw = files['accepted-1.0.11/' + name]
            self.assertEqual({'size_bytes': len(raw), 'sha256': rebuild.sha(raw)}, expected)

    def test_transport_preserves_original_zip_and_rejects_reordered_or_truncated_parts(self):
        parts = self.transport_parts()
        raw = rebuild.build_inputs_bytes(parts)
        self.assertEqual(len(raw), 13171498)
        self.assertEqual(rebuild.sha(raw), rebuild.BUILD_INPUTS_SHA)
        with self.assertRaisesRegex(ValueError, 'Compressed reconstruction input custody'):
            rebuild.build_inputs_bytes(tuple(reversed(parts)))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'reconstruction-inputs.zip'
            path.write_bytes(raw)
            self.assertEqual(rebuild.build_inputs_bytes(path), raw)
            truncated = Path(temporary) / 'truncated.part1'
            truncated.write_bytes(parts[0].read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, 'Compressed reconstruction input custody'):
                rebuild.build_inputs_bytes((truncated, parts[1]))

    def test_transport_bounds_both_part_reads_and_decompression(self):
        with tempfile.TemporaryDirectory() as temporary:
            parts = tuple(Path(temporary) / name for name in ('part1', 'part2'))
            parts[0].write_bytes(b'0' * (rebuild.BUILD_INPUTS_GZIP_SIZE // 2 + 2))
            parts[1].write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'exceeds size limit'):
                rebuild.build_inputs_bytes(parts)
            compressed = gzip.compress(b'0' * (rebuild.BUILD_INPUTS_SIZE + 1), mtime=0)
            midpoint = (len(compressed) + 1) // 2
            parts[0].write_bytes(compressed[:midpoint])
            parts[1].write_bytes(compressed[midpoint:])
            # Isolate the expansion bound from the independently checked gzip hash.
            with patch.object(rebuild, 'BUILD_INPUTS_GZIP_SHA', rebuild.sha(compressed)), \
                 patch.object(rebuild, 'BUILD_INPUTS_GZIP_SIZE', len(compressed)), \
                 self.assertRaisesRegex(ValueError, 'Expanded reconstruction input size'):
                rebuild.build_inputs_bytes(parts)

    def test_hydration_writes_exact_published_zip_from_transport(self):
        custody = ROOT / 'release/complete-1.0.12/source-custody.zip'
        mapping = rebuild.validate_mapping(rebuild.members(custody, rebuild.CUSTODY_SHA))
        trees = {row['repository'].split('/')[1]: row['tree'] for row in mapping['sources']}
        def git(root, *args):
            if args == ('rev-parse', 'HEAD^{tree}'):
                return trees[root.name]
            self.assertEqual(args, ('status', '--porcelain'))
            return ''
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(rebuild, 'fetch'), patch.object(rebuild, 'run'), \
             patch.object(rebuild, 'git', side_effect=git):
            output = Path(temporary) / 'reconstructed'
            rebuild.hydrate(output, custody, self.transport_parts())
            raw = rebuild.build_inputs_bytes(self.transport_parts())
            self.assertEqual((output / 'reconstruction-inputs.zip').read_bytes(), raw)
            for name, expected in rebuild.archive_members(raw, rebuild.BUILD_INPUTS_SHA).items():
                self.assertEqual((output / 'inputs' / name).read_bytes(), expected)

    def test_archive_tampering_and_unsafe_members_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'inputs.zip'
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'custody differs'):
                rebuild.members(path, rebuild.BUILD_INPUTS_SHA)
            raw = pub.archive({'../escape': b'no'})
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'Unsafe archive member'):
                rebuild.members(path, hashlib.sha256(raw).hexdigest())

    def test_bundle_and_repository_changes_rejected(self):
        files = rebuild.members(ROOT / 'release/complete-1.0.12/source-custody.zip', rebuild.CUSTODY_SHA)
        name = 'sources/RiscRTE.bundle'
        with self.assertRaisesRegex(ValueError, 'source bundle changed'):
            rebuild.validate_mapping({**files, name: files[name] + b'changed'})
        import json
        mapping = json.loads(files['source-equivalence.json'])
        mapping['sources'][0]['repository'] = 'other/RiscRTE-T-Watch-S3'
        with self.assertRaisesRegex(ValueError, 'Unexpected source repositories'):
            rebuild.validate_mapping({**files, 'source-equivalence.json': json.dumps(mapping).encode()})

    def test_existing_reconstruction_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'output must be new'):
                rebuild.hydrate(Path(temporary), None, None)
            with self.assertRaisesRegex(ValueError, 'Refusing to replace output'):
                rebuild.extract({'file': b'value'}, Path(temporary))


if __name__ == '__main__':
    unittest.main()

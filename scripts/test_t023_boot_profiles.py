#!/usr/bin/env python3
"""Source-only composition tests. Synthetic ELFs do not claim target admission."""
import copy
import hashlib
import importlib.util
import shutil
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import t023_boot_profiles as core
import t023_provider_compaction as compaction

PRODUCT = 'twatch'
ROOT = Path(__file__).resolve().parents[1]
NATIVE_VERSION = '0.2.24'
BASELINE_NATIVE_VERSION = '0.2.23'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n')


def driver(store, name, capability, requires=(), instance=None):
    folder = store / name
    folder.mkdir(parents=True)
    write_json(folder / 'manifest.json', {'type': 'driver', 'id': name, 'version': '1.0.0',
               'file_name': 'driver.elf', 'requires': list(requires),
               'provides': [{'capability': capability, 'api': 1}]})
    (folder / 'driver.elf').write_bytes(b'source-test-only:' + name.encode())
    result = {'manifest': name + '/manifest.json'}
    if instance is not None:
        result['instance_id'] = instance
    return result


def requirement(capability):
    return {'capability': capability, 'api': 1}


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = self.root / 'baseline'
        self.baseline.mkdir()
        drivers = [driver(self.baseline, 'bus', 'i2c.bus'),
                   driver(self.baseline, 'native-support', 'test.native-support', [requirement('i2c.bus')]),
                   driver(self.baseline, 'native-selected', 'test.native', [requirement('test.native-support')]),
                   driver(self.baseline, 'plugin', 'test.plugin')]
        if PRODUCT == 'wave':
            drivers += [driver(self.baseline, 'sd-volume', 'storage.volume', [requirement('i2c.bus')], 12),
                        driver(self.baseline, 'usb-msc', 'usb.device.msc', [requirement('storage.volume')])]
        count = 36 if PRODUCT == 'wave' else 34
        while len(drivers) < count:
            name = 'driver-' + str(len(drivers))
            drivers.append(driver(self.baseline, name, 'test.' + name))
        apps = []
        for name in ['default', 'springboard', 'notes', 'legacy']:
            manifest = {'type': 'application', 'id': name, 'version': '1.0.0',
                        'file_name': name + '.elf', 'requires': [requirement('test.product-feature')],
                        'optional': [requirement('test.optional-feature')]}
            write_json(self.baseline / (name + '.json'), manifest)
            (self.baseline / (name + '.elf')).write_bytes(b'source-test-only:' + name.encode())
            apps.append({'manifest': name + '.json', 'grants': [
                {'capability': 'storage.app-data', 'api': 1, 'instance_id': 61}]})
        apps[2]['app_data_export'] = [{'name': 'notes', 'mode': 'read'}]
        self.boot = {'board': 'board.json', 'default_app': 'default.elf', 'drivers': drivers,
                     'app_capabilities': apps, 'provider_activation': 'demand-retained'}
        if PRODUCT == 'wave':
            self.boot['installation'] = {'volume_instance': 12, 'grants': []}
        write_json(self.baseline / 'boot.json', self.boot)
        write_json(self.baseline / 'board.json', {'schema': 'source-fixture'})
        write_json(self.baseline / 'cohort.json', {'product': core.PRODUCTS[PRODUCT], 'version': 'source-fixture', 'runtime_version': BASELINE_NATIVE_VERSION})
        # Exercise the complete >128-file inventory, including non-ELF files.
        for index in range(len(core.inventory(self.baseline)), 156):
            (self.baseline / ('data-' + str(index) + '.bin')).write_bytes(b'preserve-exactly')
        for app in ['default', 'springboard']:
            folder = self.root / app
            folder.mkdir()
            manifest = core.read_json(self.baseline / (app + '.json'))
            manifest['requires'] = [requirement('runtime.retained-wake')] if app == 'default' and PRODUCT == 'wave' else []
            manifest['optional'] = []
            write_json(folder / (app + '.json'), manifest)
            (folder / (app + '.elf')).write_bytes(b'new-source-test-only:' + app.encode())
        self.catalog = self.root / 'catalog'
        self.catalog.mkdir()
        write_json(self.catalog / 'manifest.json', {'type': 'driver', 'id': 'installed-apps',
                   'file_name': 'driver.elf', 'requires': [core.REQUEST, requirement('platform.package-volume')],
                   'provides': [requirement('software.installed-apps')]})
        (self.catalog / 'driver.elf').write_bytes(b'source-test-only:catalog')
        write_json(self.catalog / 'build.json', {'boot_profiles': True, 'native_feed': True,
                   'internal_packages': True, 'feed_product': core.PRODUCTS[PRODUCT],
                   'feed_url': 'https://example.invalid/source-fixture-only',
                   'elf_sha256': hashlib.sha256((self.catalog / 'driver.elf').read_bytes()).hexdigest()})
        self.internal = self.root / 'internal'
        self.internal.mkdir()
        write_json(self.internal / 'manifest.json', {'type': 'driver', 'id': 'pkg-internal',
                   'file_name': 'driver.elf', 'requires': [requirement('platform.package-volume')],
                   'provides': [requirement('storage.volume')]})
        (self.internal / 'driver.elf').write_bytes(b'source-test-only:internal')
        (self.root / 'firmware.bin').write_bytes(b'source-test-only:native\0RISC_RUNTIME_VERSION:' + NATIVE_VERSION.encode() + b'\0')
        write_json(self.root / 'native.json', ['native-selected/manifest.json'])

    def run_compose(self, enabled=True, success=True, runtime_version=NATIVE_VERSION, extra_args=()):
        output = self.root / ('bridge' if enabled else 'legacy-output')
        args = [sys.executable, str(ROOT / 'scripts/compose_provisioning.py'),
                '--baseline', str(self.baseline), '--home', str(self.root / 'default'),
                '--springboard', str(self.root / 'springboard'), '--catalog', str(self.catalog),
                '--internal', str(self.internal), '--output', str(output),
                '--firmware', str(self.root / 'firmware.bin'), '--version', 'test-version',
                '--source-revision', 'a' * 40]
        if enabled:
            if runtime_version is not None:
                args += ['--runtime-version', runtime_version]
            args += ['--boot-profiles', '--native-provider-manifests', str(self.root / 'native.json'),
                     '--composition-report', str(self.root / 'report.json')]
        args += list(extra_args)
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return output, result

    def test_complete_inventory_and_authority_preserved(self):
        output, _ = self.run_compose()
        after = core.read_json(output / 'boot.json')
        report = core.read_json(self.root / 'report.json')
        self.assertEqual(core.read_json(output / 'cohort.json')['runtime_version'], NATIVE_VERSION)
        self.assertEqual(report['runtime_version'], NATIVE_VERSION)
        self.assertEqual((report['baseline_file_count'], report['output_file_count']), (156, 160))
        self.assertEqual(report['added_files'], ['installed-apps/driver.elf', 'installed-apps/manifest.json',
                                               'pkg-internal/driver.elf', 'pkg-internal/manifest.json'])
        final_inventory = core.inventory(output)
        for name, digest in core.inventory(self.baseline).items():
            if name not in core.REPLACED:
                self.assertEqual(final_inventory[name], digest)
        for old, new in zip(self.boot['app_capabilities'], after['app_capabilities']):
            self.assertEqual(old['manifest'], new['manifest'])
            self.assertTrue(all(grant in new['grants'] for grant in old['grants']))
            self.assertEqual(old.get('app_data_export'), new.get('app_data_export'))
        for old, new in zip(self.boot['drivers'], after['drivers']):
            self.assertEqual(old, {k: v for k, v in new.items() if k not in ('image_source', 'bindings')})
        for app in ['default', 'springboard']:
            manifest = core.read_json(output / (app + '.json'))
            self.assertIn(requirement('test.product-feature'), manifest['requires'])
            self.assertIn(requirement('test.optional-feature'), manifest['optional'])
        if PRODUCT == 'wave':
            closure = report['internal_provider_closure']
            self.assertTrue({'sd-volume/manifest.json', 'pkg-internal/manifest.json', 'bus/manifest.json',
                             'native-selected/manifest.json', 'native-support/manifest.json'} <= set(closure))
            for entry in after['drivers'] + after['app_capabilities']:
                if entry['manifest'] in closure:
                    self.assertNotIn('image_source', entry)
                    continue
                manifest, image = core.image_file(output, entry)
                source = entry['image_source']
                self.assertEqual(source['volume_instance'], 12)
                self.assertTrue(source['internal_fallback'])
                self.assertIn('/' + manifest['id'] + '/image-' + hashlib.sha256(image.read_bytes()).hexdigest() + '.elf', source['path'])
            manifests = [core.image_file(output, entry)[0] for entry in after['drivers']]
            graph = core.dependencies(after, manifests)
            sd = next(i for i, entry in enumerate(after['drivers']) if entry['manifest'] == 'sd-volume/manifest.json')
            for i, entry in enumerate(after['drivers']):
                if 'image_source' in entry:
                    graph[i].add(sd)
            core.assert_acyclic(graph)
        else:
            self.assertEqual(report['mirrors'], {})
            self.assertEqual(report['mirror_count'], 0)
            self.assertFalse(any('image_source' in e for e in after['drivers'] + after['app_capabilities']))
            self.assertEqual(after['installation']['volume_instance'], 0)
            self.assertFalse(any(g['capability'] == 'storage.volume' for g in after['installation']['grants']))

    def test_legacy_mode_does_not_enable_mirrors(self):
        output, _ = self.run_compose(enabled=False)
        boot = core.read_json(output / 'boot.json')
        self.assertEqual(core.read_json(output / 'cohort.json')['runtime_version'], BASELINE_NATIVE_VERSION)
        self.assertFalse(any('image_source' in e for e in boot['drivers'] + boot['app_capabilities']))

    def test_legacy_mode_does_not_require_native_marker(self):
        (self.root / 'firmware.bin').write_bytes(b'source-test-only:legacy-unmarked')
        output, _ = self.run_compose(enabled=False)
        self.assertEqual(core.read_json(output / 'cohort.json')['runtime_version'], BASELINE_NATIVE_VERSION)

    def test_excess_complete_inventory_rejected(self):
        (self.baseline / 'one-too-many.txt').write_text('preserve')
        _, result = self.run_compose(success=False)
        self.assertIn('maximum 160', result.stderr)

    def test_wrong_catalog_options_rejected(self):
        receipt = core.read_json(self.catalog / 'build.json')
        receipt['boot_profiles'] = False
        write_json(self.catalog / 'build.json', receipt)
        _, result = self.run_compose(success=False)
        self.assertIn('--boot-profiles --native-feed', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())

    def test_catalog_receipt_hash_mismatch_rejected(self):
        (self.catalog / 'driver.elf').write_bytes(b'changed')
        _, result = self.run_compose(success=False)
        self.assertIn('build receipt', result.stderr)

    def test_missing_internal_elf_rejected(self):
        (self.baseline / 'notes.elf').unlink()
        _, result = self.run_compose(success=False)
        self.assertIn('Missing internal fallback', result.stderr)

    def test_unknown_native_provider_rejected(self):
        write_json(self.root / 'native.json', ['absent/manifest.json'])
        _, result = self.run_compose(success=False)
        self.assertIn('Native-selected provider absent', result.stderr)

    def test_explicit_native_selection_required(self):
        with self.assertRaisesRegex(ValueError, 'native-provider-manifests'):
            core.validate_inputs(self.catalog, PRODUCT, None)

    def test_existing_external_only_policy(self):
        self.boot['app_capabilities'][-1]['image_source'] = {'volume_instance': 12, 'path': 'Apps/legacy/legacy.elf'}
        (self.baseline / 'legacy.elf').unlink()
        write_json(self.baseline / 'boot.json', self.boot)
        output, result = self.run_compose(success=PRODUCT == 'wave')
        if PRODUCT == 'wave':
            after = core.read_json(output / 'boot.json')
            self.assertEqual(self.boot['app_capabilities'][-1], after['app_capabilities'][-1])
            self.assertEqual(core.read_json(self.root / 'report.json')['external_only_apps_preserved'], ['legacy.json'])
        else:
            self.assertIn('Missing internal fallback', result.stderr)

    def test_bootstrap_cycle_rejected(self):
        manifest = core.read_json(self.baseline / 'bus/manifest.json')
        manifest['requires'].append(requirement('test.native'))
        write_json(self.baseline / 'bus/manifest.json', manifest)
        _, result = self.run_compose(success=False)
        self.assertIn('cycle', result.stderr)

    def test_app_identity_change_rejected(self):
        manifest = core.read_json(self.root / 'springboard/springboard.json')
        manifest['id'] = 'different-app'
        write_json(self.root / 'springboard/springboard.json', manifest)
        _, result = self.run_compose(success=False)
        self.assertIn('existing app identity', result.stderr)

    def test_invalid_report_path_rejected_before_copy(self):
        # The inventory report is evidence, never an extra payload in bootfs.
        report = self.root / 'report.json'
        report.symlink_to(self.root / 'bridge/extra.json')
        _, result = self.run_compose(success=False)
        self.assertIn('outside the store', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())

    def test_bridge_requires_native_version(self):
        _, result = self.run_compose(runtime_version=None, success=False)
        self.assertIn('requires --runtime-version', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())

    def test_mismatched_native_version_rejected(self):
        _, result = self.run_compose(runtime_version=BASELINE_NATIVE_VERSION, success=False)
        self.assertIn('exact firmware native version marker', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())

    def test_missing_native_marker_rejected(self):
        (self.root / 'firmware.bin').write_bytes(b'source-test-only:no-marker')
        _, result = self.run_compose(success=False)
        self.assertIn('exact firmware native version marker', result.stderr)

    def test_conflicting_native_markers_rejected(self):
        path = self.root / 'firmware.bin'
        path.write_bytes(path.read_bytes() + b'RISC_RUNTIME_VERSION:9.9.9\0')
        _, result = self.run_compose(success=False)
        self.assertIn('exact firmware native version marker', result.stderr)

    def test_native_parser_prefix_literal_is_not_a_version(self):
        firmware = b'RISC_RUNTIME_VERSION:\0RISC_RUNTIME_VERSION:' + NATIVE_VERSION.encode() + b'\0'
        self.assertEqual(core.verify_runtime_version(NATIVE_VERSION, firmware), NATIVE_VERSION)
        for suffix in [b'RISC_RUNTIME_VERSION:9.9.9\0', b'RISC_RUNTIME_VERSION:9.9.9']:
            with self.assertRaisesRegex(ValueError, 'exact firmware native version marker'):
                core.verify_runtime_version(NATIVE_VERSION, firmware + suffix)
        with self.assertRaisesRegex(ValueError, 'exact firmware native version marker'):
            core.verify_runtime_version(NATIVE_VERSION, b'RISC_RUNTIME_VERSION:\0')

    def test_real_native_ci_markers_when_supplied(self):
        source = os.environ.get('T023_NATIVE_FIRMWARE')
        if source is None:
            self.skipTest('Set T023_NATIVE_FIRMWARE to exercise the exact product CI binary')
        firmware = Path(source).read_bytes()
        marker = b'RISC_RUNTIME_VERSION:' + NATIVE_VERSION.encode() + b'\0'
        self.assertIn(b'RISC_RUNTIME_VERSION:\0', firmware)
        self.assertIn(marker, firmware)
        self.assertEqual(core.verify_runtime_version(NATIVE_VERSION, firmware), NATIVE_VERSION)
        for candidate in [firmware + b'RISC_RUNTIME_VERSION:9.9.9\0',
                          firmware + b'RISC_RUNTIME_VERSION:9.9.9',
                          firmware.replace(marker, b'RISC_RUNTIME_VERSION:\0')]:
            with self.assertRaisesRegex(ValueError, 'exact firmware native version marker'):
                core.verify_runtime_version(NATIVE_VERSION, candidate)

    def test_invalid_native_versions_rejected(self):
        for version in ['0.3', 'v0.3.4', '0.03.4', '0.3.4-extra', '4294967296.0.0', '']:
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'canonical bounded'):
                core.verify_runtime_version(version, b'RISC_RUNTIME_VERSION:' + version.encode() + b'\0')

    def compaction_args(self, debug_dir=None):
        return ['--compact-new-providers', '--compiler', shutil.which('gcc') or '/missing/gcc',
                '--debug-sidecar-dir', str(debug_dir or self.root / 'debug-sidecars')]

    def real_provider_fixtures(self):
        if importlib.util.find_spec('elftools') is None or not shutil.which('gcc') or not shutil.which('objcopy'):
            self.skipTest('Real checked-compaction regression requires pyelftools, gcc and objcopy')
        source = self.root / 'source-test-only.c'
        source.write_text('static int state = 3; int fixture(int x) { return state + x; }\n')
        for folder in [self.catalog, self.internal]:
            subprocess.run([shutil.which('gcc'), '-std=c11', '-g', '-fPIC', '-shared',
                            '-Wl,--hash-style=sysv', str(source), '-o', str(folder / 'driver.elf')], check=True)
        receipt = core.read_json(self.catalog / 'build.json')
        receipt['elf_sha256'] = hashlib.sha256((self.catalog / 'driver.elf').read_bytes()).hexdigest()
        write_json(self.catalog / 'build.json', receipt)

    def test_checked_provider_compaction_before_mirror_hashing(self):
        self.real_provider_fixtures()
        originals = {name: (folder / 'driver.elf').read_bytes() for name, folder in
                     [('installed-apps', self.catalog), ('pkg-internal', self.internal)]}
        baseline_before = core.inventory(self.baseline)
        output, _ = self.run_compose(extra_args=self.compaction_args())
        report = core.read_json(self.root / 'report.json')
        self.assertEqual(set(report['provider_compaction']),
                         {'installed-apps/driver.elf', 'pkg-internal/driver.elf'})
        self.assertEqual(core.inventory(self.baseline), baseline_before)
        for name, original in originals.items():
            relative = name + '/driver.elf'
            proof = report['provider_compaction'][relative]
            final = (output / relative).read_bytes()
            self.assertEqual((self.root / 'debug-sidecars' / relative).read_bytes(), original)
            self.assertEqual(proof['before_sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(proof['after_sha256'], hashlib.sha256(final).hexdigest())
            self.assertLess(len(final), len(original))
            self.assertTrue(proof['retained_loader_sections_symbols_relocations_unchanged'])
            semantic = proof['semantic_equivalence']
            self.assertTrue(all(semantic['components_unchanged'].values()))
            self.assertEqual(semantic['before_sha256'], semantic['after_sha256'])
            self.assertEqual(set(semantic['retained_semantics']),
                             {'header', 'order', 'sections', 'symbols', 'symbol_sections'})
        self.assertEqual((self.catalog / 'driver.elf').read_bytes(), originals['installed-apps'])
        self.assertEqual((self.internal / 'driver.elf').read_bytes(), originals['pkg-internal'])
        if PRODUCT == 'wave':
            boot = core.read_json(output / 'boot.json')
            entry = next(e for e in boot['drivers'] if e['manifest'] == 'installed-apps/manifest.json')
            digest = report['provider_compaction']['installed-apps/driver.elf']['after_sha256']
            self.assertIn('image-' + digest + '.elf', entry['image_source']['path'])
            self.assertNotIn('image-' + hashlib.sha256(originals['installed-apps']).hexdigest() + '.elf', entry['image_source']['path'])

    def test_compaction_requires_explicit_compiler_and_sidecars(self):
        _, result = self.run_compose(extra_args=['--compact-new-providers'], success=False)
        self.assertIn('requires --compiler, --debug-sidecar-dir and --composition-report', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())

    def test_compaction_requires_written_report(self):
        with self.assertRaisesRegex(ValueError, 'requires --compiler'):
            compaction.prepare(PRODUCT, Path('/usr/bin/gcc'), self.root / 'debug', None,
                               self.root / 'bridge', [self.baseline])

    def test_default_provider_bytes_are_unchanged(self):
        output, _ = self.run_compose()
        self.assertEqual((output / 'installed-apps/driver.elf').read_bytes(),
                         (self.catalog / 'driver.elf').read_bytes())
        self.assertEqual((output / 'pkg-internal/driver.elf').read_bytes(),
                         (self.internal / 'driver.elf').read_bytes())
        self.assertNotIn('provider_compaction', core.read_json(self.root / 'report.json'))

    def test_compaction_options_without_flag_rejected(self):
        _, result = self.run_compose(extra_args=['--compiler', '/missing/gcc'], success=False)
        self.assertIn('require --compact-new-providers', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())

    def test_compaction_sidecars_inside_store_rejected(self):
        _, result = self.run_compose(extra_args=self.compaction_args(self.root / 'bridge/debug'), success=False)
        self.assertIn('outside and separate', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())

    def test_compaction_sidecars_in_input_rejected(self):
        _, result = self.run_compose(extra_args=self.compaction_args(self.catalog / 'debug'), success=False)
        self.assertIn('overlap an input tree', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())

    def test_compaction_nested_sidecar_symlink_rejected(self):
        debug = self.root / 'debug-sidecars'
        debug.mkdir()
        (debug / 'installed-apps').symlink_to(self.catalog, target_is_directory=True)
        _, result = self.run_compose(extra_args=self.compaction_args(), success=False)
        self.assertIn('escapes its output directory', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())

    def test_existing_compaction_sidecar_not_overwritten(self):
        sidecar = self.root / 'debug-sidecars/installed-apps/driver.elf'
        sidecar.parent.mkdir(parents=True)
        sidecar.write_bytes(b'existing-evidence')
        _, result = self.run_compose(extra_args=self.compaction_args(), success=False)
        self.assertIn('existing debug sidecar', result.stderr)
        self.assertEqual(sidecar.read_bytes(), b'existing-evidence')
        self.assertFalse((self.root / 'bridge').exists())

    def test_original_receipt_checked_before_compaction(self):
        (self.catalog / 'driver.elf').write_bytes(b'wrong-original')
        _, result = self.run_compose(extra_args=self.compaction_args(), success=False)
        self.assertIn('build receipt', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())
        self.assertFalse((self.root / 'debug-sidecars').exists())

    def test_compaction_report_cannot_replace_sidecar(self):
        args = self.compaction_args() + ['--composition-report', str(self.root / 'debug-sidecars/installed-apps/driver.elf')]
        _, result = self.run_compose(extra_args=args, success=False)
        self.assertIn('aliases a debug sidecar', result.stderr)
        self.assertFalse((self.root / 'bridge').exists())

    def test_compaction_never_replaces_a_baseline_provider(self):
        path = self.baseline / 'installed-apps/driver.elf'
        path.parent.mkdir()
        path.write_bytes(b'baseline-provider')
        _, result = self.run_compose(extra_args=self.compaction_args(), success=False)
        self.assertIn('limited to newly added ELFs', result.stderr)
        self.assertEqual(path.read_bytes(), b'baseline-provider')
        self.assertFalse((self.root / 'bridge').exists())

    def test_native_profile_opt_in_flag(self):
        text = (ROOT / 'native/t023-provisioning.ini').read_text()
        env = 'waveshare' if PRODUCT == 'wave' else 'watch'
        before, after = text.split('[env:' + env + '-t023-boot-profiles]')
        self.assertNotIn('-DRISC_NATIVE_PROVISION_REQUEST=1', before)
        self.assertIn('-DRISC_NATIVE_PROVISION_REQUEST=1', after)


if __name__ == '__main__':
    unittest.main()

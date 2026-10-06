"""Synthetic frozen-custody tests; these fixtures are never release inputs."""
import copy
import json
from pathlib import Path
import struct
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import publish_watch_product as pub
import watch_main_product as main
import watch_release_index as idx
import current_cohort
import current_flash_layout
from current_bootfs import build as pack_current


def elf():
    data = bytearray(64)
    data[:7] = b'\x7fELF\x01\x01\x01'
    data[16:20] = b'\x03\x00\x5e\x00'
    return bytes(data)


def spiffs(store):
    """Minimal valid 256/4096 SPIFFS fixture, tested with the real decoder."""
    raw = bytearray(b'\xff' * main.BOOTFS_SIZE)
    pages = iter(i for i in range(main.BOOTFS_SIZE // 256) if i % 16)
    def allocate(obj, span, flags):
        page = next(pages)
        struct.pack_into('<H', raw, (page // 16) * 4096 + (page % 16 - 1) * 2, obj)
        struct.pack_into('<HHB', raw, page * 256, obj, span, flags)
        return page
    for identity, (name, data) in enumerate(sorted(store.items()), 1):
        header = allocate(identity | 0x8000, 0, 0xf8)
        offset = header * 256
        struct.pack_into('<I', raw, offset + 8, len(data))
        raw[offset + 12] = 1
        filename = ('/' + name).encode() + b'\0'
        assert len(filename) <= 32 and len(data) <= 103 * 251
        raw[offset + 13:offset + 13 + len(filename)] = filename
        for span, start in enumerate(range(0, len(data), 251)):
            page = allocate(identity, span, 0xfc)
            chunk = data[start:start + 251]
            raw[page * 256 + 5:page * 256 + 5 + len(chunk)] = chunk
            struct.pack_into('<H', raw, offset + 49 + span * 2, page)
    return bytes(raw)


def fixture():
    watch, tree, runtime = 'a' * 40, 'b' * 40, 'c' * 40
    sources = {'watch': {'repository': idx.REPOSITORY, 'accepted_sha': watch, 'tree': tree},
               'runtime': {'repository': 'michaelrolphone-cmyk/RiscRTE', 'accepted_sha': runtime}}
    lanes = {key: {'utilities': {'repository': 'example/Utilities', 'commit': 'd' * 40}} for key in ('audio', 'points', 'update')}
    store = {'boot.json': b'{}', 'board.json': b'{}'}
    versions = {'runtime': '0.1.16', 'default': '0.8.0', 'clock': '0.8.0', 'new_app': '0.1.0'}
    for name, version in versions.items():
        if name == 'runtime':
            continue
        store[name + '.elf'] = elf()
        store[name + '.json'] = pub.encoded({'type': 'application', 'id': name, 'version': version,
                                           'architecture': 'xtensa-esp32s3', 'file_name': name + '.elf'})
    driver_source = {'id': 'twatch-test', 'type': 'driver', 'version': '0.1.0'}
    store['test/driver.elf'] = elf()
    store['test/manifest.json'] = pub.encoded(driver_source)
    for name in ('alarm-service', 'update-fw', 'update-apps'):
        store[name + '/driver.elf'] = elf()
        store[name + '/manifest.json'] = pub.encoded({'id': name, 'type': 'driver', 'version': '0.1.0'})
    while len(store) < 58:
        store[f'fixture-{len(store)}.data'] = b'fixture'
    image = spiffs(store)
    binary = bytearray(b'\xff' * main.FLASH_BYTES)
    components = []
    for name, offset, limit in main.PARTITIONS:
        data = image if name == 'bootfs.bin' else b'X' * (limit - offset if name in ('otadata.bin', 'bank_state.bin') else 256)
        binary[offset:offset + len(data)] = data
        components.append({'file': 'components/' + name, 'offset': hex(offset), 'size_bytes': len(data), 'sha256': pub.sha(data)})
    binary = bytes(binary)
    commons = {}
    for key in ('audio', 'points'):
        files = {'licenses/LICENSE': b'Synthetic fixture only',
                 'shared/' + ('audio-sources.json' if key == 'audio' else 'alarm-sources.json'):
                     pub.encoded({'sources': lanes[key]} if key == 'audio' else lanes[key])}
        if key == 'audio':
            files['shared/update-sources.json'] = pub.encoded(lanes['update'])
        commons[key] = pub.archive(files)
    bin_name = 'twatch-s3-main-0.8.0-aaaaaaaa.bin'
    bundle_name = 'twatch-s3-main-0.8.0-aaaaaaaa-install.zip'
    manifest = {'schema': 1, 'kind': 'latest-merged-main-full-flash', 'file': bin_name,
                'watch_source': watch, 'watch_tree': tree, 'watch_version': '0.8.0',
                'runtime_source': runtime, 'runtime_version': versions['runtime'], 'layout': main.LAYOUT,
                'store_abi': 1, 'bin_sha256': pub.sha(binary), 'size_bytes': main.FLASH_BYTES,
                'flash_offset': '0x0', 'overwrite_bytes': main.FLASH_BYTES, 'flash_capacity_bytes': main.FLASH_BYTES,
                'physical_verification': 'pending', 'components': components, 'bootfs_sha256': pub.sha(image),
                'audio_common_sha256': pub.sha(commons['audio']), 'points_common_sha256': pub.sha(commons['points']),
                'audio_tools': {'sources': lanes['audio']},
                'points_overlay': {'paired_clock': {'points_sources': lanes['points'],
                    'files': {n: {'size_bytes': len(store[n]), 'sha256': pub.sha(store[n])}
                              for n in ('default.elf', 'default.json', 'clock.elf', 'clock.json')}}},
                'store': [{'path': n, 'size_bytes': len(b), 'sha256': pub.sha(b)} for n, b in sorted(store.items())]}
    files = {bin_name: binary, 'manifest.json': pub.encoded(manifest), 'FLASHING.md': b'Synthetic fixture only\n'}
    files['SHA256SUMS'] = ''.join(f'{pub.sha(b)}  {n}\n' for n, b in sorted(files.items())).encode()
    bundle = pub.archive(files)
    artifacts = {'main': pub.archive({**files, bundle_name: bundle}),
                 **{key: pub.archive({'common.zip': raw}) for key, raw in commons.items()}}
    driver_files = {'driver.elf': elf(), 'source-manifest.json': pub.encoded(driver_source)}
    driver_manifest = {'id': 'twatch-test', 'version': '0.1.0', 'kind': 'driver', 'architecture': 'xtensa-esp32s3',
                       'entries': [{'name': n, 'size_bytes': len(b), 'sha256': pub.sha(b)} for n, b in driver_files.items()]}
    driver = pub.archive({**driver_files, '.package.json': pub.encoded(driver_manifest)})
    driver_name = 'driver-twatch-test-0.1.0-xtensa-esp32s3.rte.zip'
    catalog = {'schema': 1, 'packages': [{'id': 'twatch-test', 'version': '0.1.0', 'archive': driver_name,
                                        'size_bytes': len(driver), 'sha256': pub.sha(driver)}]}
    artifacts['drivers'] = pub.archive({'catalog.json': pub.encoded(catalog), driver_name: driver})
    product = {'schema': 2, 'product': 'Synthetic fixture only', 'repository': idx.REPOSITORY,
               'version': '1.0.1', 'tag': 'firmware-v1.0.1', 'accepted_build': '0.8.0',
               'acceptance': copy.deepcopy(main.ACCEPTANCE), 'accepted_on': '2026-10-05', 'sources': sources, 'deployment_sources': lanes,
               'accepted_bin_name': bin_name, 'accepted_bundle_name': bundle_name,
               'accepted_bin_sha256': pub.sha(binary), 'accepted_bundle_sha256': pub.sha(bundle),
               'bin_size': main.FLASH_BYTES, 'flash_capacity': main.FLASH_BYTES, 'flash_offset': '0x0',
               'store_file_count': len(store), 'component_versions': versions, 'driver_versions': {'twatch-test': '0.1.0'},
               'embedded_driver_versions': {n: '0.1.0' for n in ('test', 'alarm-service', 'update-fw', 'update-apps')},
               'artifacts': {name: {'repository': idx.REPOSITORY, 'run_id': 123, 'artifact_id': i + 1,
                                    'run_attempt': 1, 'head_sha': watch, 'name': {'main': 'twatch-flashable-bin-' + watch,
                                    'audio': 'twatch-update-integration-' + watch, 'points': 'twatch-points-integration-' + watch,
                                    'drivers': 'twatch-driver-packages'}[name],
                                    'sha256': pub.sha(raw), **({'bundle_member': 'common.zip'} if name in commons else {})}
                             for i, (name, raw) in enumerate(artifacts.items())}}
    return product, artifacts, store


class MainProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.artifacts, cls.store = fixture()

    def test_dynamic_inventory_and_exact_seven_firmware_assets(self):
        main.validate_config(self.p)
        releases, drivers, assets, index = main.payloads(self.p, 'e' * 40, self.artifacts, pub)
        self.assertEqual([r['id'] for r in index['apps']], ['clock', 'default', 'new_app'])
        self.assertEqual(len(drivers), 1)
        firmware, files, _, latest = releases[-1]
        self.assertTrue(latest)
        self.assertEqual(set(files) | {'SHA256SUMS'}, {firmware['asset'], self.p['accepted_bundle_name'],
            'FLASHING.md', 'product-provenance.json', 'release-index.json', 'release-record.json', 'SHA256SUMS'})
        self.assertIn('Physical verification is pending', files['FLASHING.md'].decode())
        self.assertIn('entire 16 MiB', files['FLASHING.md'].decode())
        self.assertNotIn('owner-accepted', files['product-provenance.json'].decode())
        self.assertEqual(files[firmware['asset']], main.image_custody(self.p, self.artifacts['main'], pub)[0])

    def test_abi2_release_binds_native_and_full_store_without_persistent_data(self):
        p, artifacts, store = copy.deepcopy(self.p), copy.deepcopy(self.artifacts), copy.deepcopy(self.store)
        p['version'] = '1.0.2'; p['tag'] = 'firmware-v1.0.2'
        p['component_versions']['runtime'] = '0.1.33'
        p['deployment'] = dict(target='esp32s3-16mb-appdata', layout=current_flash_layout.APP_DATA_LAYOUT,
                               store_abi=2, flash_bytes=main.FLASH_BYTES, partitions=current_flash_layout.APP_DATA_PARTS)
        native = b'fixture native' * 32
        identity = current_cohort.create('1.0.2', '0.1.33', p['sources']['watch']['accepted_sha'], native)
        store['cohort.json'] = current_cohort.encode(identity)
        image, _ = pack_current(store, current_cohort.STORE_SIZE)
        raw = bytearray(b'\xff' * main.FLASH_BYTES); components = []
        empty = b'E' * 0x80000  # Synthetic only; production has one pinned disk2.1 digest.
        for name, start, limit in main.APP_DATA_PARTITIONS:
            data = {'firmware.bin': native, 'bootfs.bin': image, 'appdata.bin': empty}.get(name)
            if data is None: data = b'X' * (limit - start if name in ('otadata.bin', 'bank_state.bin') else 256)
            raw[start:start + len(data)] = data
            components.append(dict(file='components/' + name, offset=hex(start), size_bytes=len(data), sha256=pub.sha(data)))
        raw = bytes(raw)
        old = main.zip_files(artifacts['main'], pub)
        manifest = json.loads(old['manifest.json'])
        manifest.update(kind='initial-app-data-full-flash', layout=current_flash_layout.APP_DATA_LAYOUT, store_abi=2,
                        runtime_version='0.1.33', cohort=identity, components=components, ordinary_ota_includes_appdata=False,
                        bootfs_sha256=pub.sha(image), bin_sha256=pub.sha(raw),
                        store=[dict(path=n, size_bytes=len(b), sha256=pub.sha(b)) for n,b in sorted(store.items())])
        files = {p['accepted_bin_name']: raw, 'manifest.json': pub.encoded(manifest), 'FLASHING.md': old['FLASHING.md']}
        files['SHA256SUMS'] = ''.join(f'{pub.sha(b)}  {n}\n' for n,b in sorted(files.items())).encode()
        bundle = pub.archive(files)
        artifacts['main'] = pub.archive({**files, p['accepted_bundle_name']: bundle})
        p.update(accepted_bin_sha256=pub.sha(raw), accepted_bundle_sha256=pub.sha(bundle), store_file_count=len(store))
        p['artifacts']['main']['sha256'] = pub.sha(artifacts['main'])
        main.validate_config(p)
        with patch.object(main, 'APP_DATA_SHA', pub.sha(empty)):
            releases, _, _, index = main.payloads(p, 'e' * 40, artifacts, pub)
        record, assets, _, _ = releases[-1]
        ota = record['ota']; self.assertEqual(index['firmware']['ota'], ota)
        self.assertEqual(native + image, assets[ota['asset']])
        self.assertEqual(len(native) + len(image), ota['size'])
        self.assertEqual(pub.sha(assets[ota['asset']]), ota['sha256'])
        self.assertEqual('paired-cohort', ota['kind'])
        self.assertIn('use built-in Firmware Update', assets['FLASHING.md'].decode())
        with self.assertRaisesRegex(ValueError, 'Initial app-data custody'):
            main.image_custody(p, artifacts['main'], pub)
        altered = copy.deepcopy(p); altered['version'] = '1.0.3'; altered['tag'] = 'firmware-v1.0.3'
        with patch.object(main, 'APP_DATA_SHA', pub.sha(empty)), self.assertRaisesRegex(ValueError, 'Cohort version differs'):
            main.image_custody(altered, artifacts['main'], pub)

    def test_all_component_versions_must_be_pinned(self):
        for action in ('remove', 'extra', 'wrong'):
            p = copy.deepcopy(self.p)
            if action == 'remove': del p['component_versions']['new_app']
            if action == 'extra': p['component_versions']['absent'] = '0.1.0'
            if action == 'wrong': p['component_versions']['new_app'] = '0.2.0'
            with self.subTest(action=action), self.assertRaises(ValueError):
                main.app_inventory(p, self.store)

    def test_next_cohort_reuses_unchanged_apps_without_republishing_assets(self):
        p = copy.deepcopy(self.p)
        first, _, _, previous = main.payloads(p, 'e' * 40, self.artifacts, pub)
        reused = copy.deepcopy(next(r for r in previous['apps'] if r['id'] == 'new_app'))
        reused['source_sha'] = 'f' * 40
        reused['minimum_runtime_version'] = '0.1.12'
        p['reused_app_records'] = {'new_app': reused}
        main.validate_config(p)
        releases, _, _, index = main.payloads(p, 'd' * 40, self.artifacts, pub)
        self.assertEqual(reused, next(r for r in index['apps'] if r['id'] == 'new_app'))
        self.assertNotIn(reused['tag'], [r[0]['tag'] for r in releases])
        self.assertEqual(len(first) - 1, len(releases))
        p['reused_app_records']['new_app']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Immutable app payload/manifest collision'):
            main.payloads(p, 'd' * 40, self.artifacts, pub)

    def test_invalid_elf_and_unmanifested_application(self):
        for key, raw in [('new_app.elf', b'bad'), ('unmanifested.elf', elf())]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                main.app_inventory(self.p, {**self.store, key: raw})

    def test_pending_or_overclaim_config_rejected(self):
        for key, value in [('accepted_bin_sha256', None), ('acceptance', {'kind': 'hardware-accepted'}),
                           ('bin_size', 8388608), ('store_file_count', 57)]:
            p = copy.deepcopy(self.p); p[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): main.validate_config(p)

    def test_known_limitations_are_bounded_and_in_flashing_provenance(self):
        p = copy.deepcopy(self.p)
        text = 'Observed Hybrid wake issue remains deferred; the separate recovery change is excluded.'
        p['known_limitations'] = [text]
        main.validate_config(p)
        self.assertIn(text, main.flashing_document(p).decode())
        releases, _, _, _ = main.payloads(p, 'e' * 40, self.artifacts, pub)
        provenance = json.loads(releases[-1][1]['product-provenance.json'])
        self.assertEqual(provenance['known_limitations'], [text])
        for invalid in (None, '', [''], ['  '], [1], ['x' * 501], ['x'] * 11, ['first\nsecond']):
            p['known_limitations'] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'Known limitations'):
                main.validate_config(p)

    def test_known_limitations_are_in_firmware_release_notes(self):
        p = copy.deepcopy(self.p); p['known_limitations'] = ['An observed issue is deferred.']
        absent = subprocess.CompletedProcess([], 1, b'', b'HTTP 404')
        release = {'tag': p['tag'], 'source_sha': 'e' * 40, 'latest': True, 'assets': {}}
        def capture(*args):
            self.assertIn('body=', ' '.join(args))
            body = next(value for value in args if value.startswith('body='))
            self.assertIn(p['known_limitations'][0], body)
            raise RuntimeError('Captured notes without a remote write')
        with patch.object(pub, 'read_config', return_value=p), patch.object(pub, 'release_by_tag', return_value=None), \
             patch.object(pub.subprocess, 'run', return_value=absent), patch.object(pub, 'gh', side_effect=capture):
            with self.assertRaisesRegex(RuntimeError, 'Captured notes'): pub.publish_one(release, Path('/unused'))

    def test_mixed_ci_run_attempt_rejected(self):
        p = copy.deepcopy(self.p); p['artifacts']['audio']['run_attempt'] = 2
        with self.assertRaisesRegex(ValueError, 'one accepted CI'): main.validate_config(p)

    def test_store_manifest_cannot_omit_member(self):
        p = copy.deepcopy(self.p); p['store_file_count'] += 1
        with self.assertRaisesRegex(ValueError, 'inventory'): main.image_custody(p, self.artifacts['main'], pub)

    def test_wrong_runtime_source_rejected(self):
        p = copy.deepcopy(self.p); p['sources']['runtime']['accepted_sha'] = 'f' * 40
        with self.assertRaisesRegex(ValueError, 'identity'): main.image_custody(p, self.artifacts['main'], pub)

    def test_source_generations_are_preserved_and_checked(self):
        p = copy.deepcopy(self.p); p['deployment_sources']['points']['utilities']['commit'] = 'f' * 40
        with self.assertRaisesRegex(ValueError, 'source generations'): main.payloads(p, 'e' * 40, self.artifacts, pub)

    def current_fixture(self):
        p = copy.deepcopy(self.p)
        configuration = {'schema': 1, 'profile': 'watch-current-apps-v1',
                         'sources': {key: {'repository': 'michaelrolphone-cmyk/' + repo, 'commit': ('c' if key == 'runtime' else 'd') * 40}
                                     for key, repo in {'system-apps': 'RiscRTE-System-Apps', 'utilities': 'RiscRTE-Utilities',
                                                       'runtime': 'RiscRTE', 'productivity': 'RiscRTE-Productivity'}.items()},
                         'app_versions': {n: v for n, v in p['component_versions'].items() if n != 'runtime'}, 'service_version': '0.1.0'}
        p['current_apps_configuration'] = configuration
        changed_files = {name: raw for name, raw in self.store.items()
                         if name.startswith(('new_app.', 'default.', 'clock.', 'alarm-service/', 'update-fw/', 'update-apps/'))}
        record = {'schema': 1, 'profile': 'watch-current-apps-v1', 'watch_source': 'a' * 40,
                  'configuration': configuration, 'boot': json.loads(self.store['boot.json']), 'target_validation': True,
                  'apps': {n: {'version': v, 'sha256': pub.sha(self.store[n + '.elf']), 'size_bytes': len(self.store[n + '.elf'])}
                           for n, v in configuration['app_versions'].items()},
                  'clock': {'watch_source': 'a' * 40, 'paired_boot_confirmation': True,
                            'sources': configuration['sources'],
                            'headers': {n: 'f' * 64 for n in ('PointsRecords.h', 'PointsSchedule.h')},
                            'source_sha256': {'apps/clock/clock.c': 'f' * 64},
                            'files': {n: {'size_bytes': len(self.store[n]), 'sha256': pub.sha(self.store[n])}
                                      for n in ('default.json', 'default.elf', 'clock.json', 'clock.elf')}},
                  'service': {'points_headers': {n: 'f' * 64 for n in ('PointsRecords.h', 'PointsSchedule.h')}},
                  'files': {name: {'size_bytes': len(raw), 'sha256': pub.sha(raw)} for name, raw in changed_files.items()}}
        files = {'current-apps-build.json': pub.encoded(record), 'source-profile.json': pub.encoded(configuration),
                 'licenses/LICENSE': b'Synthetic current-apps fixture only',
                 **{'files/' + name: raw for name, raw in changed_files.items()}}
        raw = pub.archive(files)
        outer = pub.archive({**files, 'current-apps.zip': raw})
        artifacts = {**self.artifacts, 'current-apps': outer}
        p['artifacts']['current-apps'] = {**p['artifacts']['main'], 'artifact_id': 5,
                                        'name': 'twatch-current-apps-' + 'a' * 40, 'sha256': pub.sha(outer)}
        _, _, manifest, _ = main.image_custody(self.p, artifacts['main'], pub)
        changed = set(changed_files) | {'boot.json'}
        metadata = lambda n: {'size_bytes': len(self.store[n]), 'sha256': pub.sha(self.store[n])}
        manifest['current_apps_overlay'] = {'build_record': record, 'build_record_sha256': pub.sha(files['current-apps-build.json']),
                                            'archive_sha256': pub.sha(raw),
                                            'files': {n: metadata(n) for n in changed},
                                            'preserved_files': {n: metadata(n) for n in set(self.store) - changed}}
        return p, manifest, artifacts

    def test_current_overlay_custody(self):
        p, manifest, artifacts = self.current_fixture()
        main.validate_config(p)
        evidence = main.current_apps_custody(p, manifest, self.store, artifacts, pub)
        self.assertIn('current-apps/licenses/LICENSE', evidence)
        self.assertIn('current-apps/current-apps-build.json', evidence)

    def test_current_overlay_full_release_payloads(self):
        p, manifest, artifacts = self.current_fixture()
        outer = main.zip_files(artifacts['main'], pub)
        frozen = main.zip_files(outer[p['accepted_bundle_name']], pub)
        frozen['manifest.json'] = pub.encoded(manifest)
        frozen['SHA256SUMS'] = ''.join(f'{pub.sha(b)}  {n}\n' for n, b in sorted(frozen.items()) if n != 'SHA256SUMS').encode()
        bundle = pub.archive(frozen)
        artifacts['main'] = pub.archive({**frozen, p['accepted_bundle_name']: bundle})
        p['accepted_bundle_sha256'] = pub.sha(bundle)
        p['artifacts']['main']['sha256'] = pub.sha(artifacts['main'])
        main.validate_config(p)
        releases, _, _, index = main.payloads(p, 'e' * 40, artifacts, pub)
        self.assertEqual(len(index['apps']), 3)
        self.assertEqual(releases[0][0]['current_apps_configuration'], p['current_apps_configuration'])
        with pub.checked_zip(releases[0][1]['LICENSES.zip']) as licenses:
            self.assertIn('current-apps/current-apps-build.json', licenses.namelist())
        provenance = json.loads(releases[-1][1]['product-provenance.json'])
        self.assertEqual(provenance['accepted_manifest']['current_apps_overlay']['build_record']['clock']['sources'],
                         p['current_apps_configuration']['sources'])

    def test_self_consistent_current_clock_false_proof_rejected(self):
        for case in ('source', 'paired', 'headers', 'paths'):
            p, manifest, artifacts = self.current_fixture()
            outer = main.zip_files(artifacts['current-apps'], pub)
            files = main.zip_files(outer['current-apps.zip'], pub)
            record = json.loads(files['current-apps-build.json'])
            if case == 'source': record['clock']['watch_source'] = 'f' * 40
            if case == 'paired': record['clock']['paired_boot_confirmation'] = False
            if case == 'headers': record['clock']['headers']['PointsRecords.h'] = 'e' * 64
            if case == 'paths': record['clock']['source_sha256'] = {'../outside': 'f' * 64}
            files['current-apps-build.json'] = pub.encoded(record)
            archive = pub.archive(files)
            artifacts['current-apps'] = pub.archive({**files, 'current-apps.zip': archive})
            p['artifacts']['current-apps']['sha256'] = pub.sha(artifacts['current-apps'])
            manifest['current_apps_overlay'].update(build_record=record,
                build_record_sha256=pub.sha(files['current-apps-build.json']), archive_sha256=pub.sha(archive))
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, 'Current Clock'):
                main.current_apps_custody(p, manifest, self.store, artifacts, pub)

    def test_current_overlay_fails_closed(self):
        for case in ('configuration', 'build_record', 'archive', 'partition', 'bytes', 'artifact', 'clock_source', 'clock_pair'):
            p, manifest, artifacts = self.current_fixture()
            store = dict(self.store)
            overlay = manifest['current_apps_overlay']
            if case == 'configuration': p['current_apps_configuration']['service_version'] = '9.0.0'
            if case == 'build_record': overlay['build_record_sha256'] = 'f' * 64
            if case == 'archive': overlay['archive_sha256'] = 'f' * 64
            if case == 'partition': del overlay['preserved_files']['board.json']
            if case == 'bytes': store['new_app.elf'] = b'changed'
            if case == 'artifact': del artifacts['current-apps']
            if case == 'clock_source': overlay['build_record']['clock']['watch_source'] = 'f' * 40
            if case == 'clock_pair': overlay['build_record']['clock']['paired_boot_confirmation'] = False
            with self.subTest(case=case), self.assertRaises(ValueError):
                main.current_apps_custody(p, manifest, store, artifacts, pub)

    def test_explicit_driver_reuse_preserves_original_record_and_current_installation(self):
        p = copy.deepcopy(self.p)
        original = main.driver_records(p, self.artifacts['drivers'], self.store, pub)[0][0]
        original.update(included_in_accepted_bin=False, source_sha='f' * 40, historical_note='Preserve exactly')
        p['reused_driver_records'] = {'twatch-test': original}
        main.validate_config(p)
        releases, drivers, _, index = main.payloads(p, 'e' * 40, self.artifacts, pub)
        self.assertEqual(drivers, [original])
        self.assertEqual(index['drivers'], [original])
        provenance = json.loads(releases[-1][1]['product-provenance.json'])
        self.assertEqual(provenance['installed_physical_drivers'][0]['id'], 'twatch-test')
        self.assertEqual(provenance['installed_physical_drivers'][0]['elf']['sha256'], pub.sha(self.store['test/driver.elf']))
        self.assertFalse(drivers[0]['included_in_accepted_bin'])

    def test_driver_reuse_cannot_hide_package_or_manifest_collision(self):
        for case in ('hash', 'manifest', 'version', 'asset'):
            p = copy.deepcopy(self.p)
            original = main.driver_records(p, self.artifacts['drivers'], self.store, pub)[0][0]
            if case == 'hash': original['sha256'] = 'f' * 64
            if case == 'manifest': original['manifest']['entries'][0]['sha256'] = 'f' * 64
            if case == 'version': original['version'] = '0.0.1'
            if case == 'asset': original['asset'] = 'different.zip'
            p['reused_driver_records'] = {'twatch-test': original}
            with self.subTest(case=case), self.assertRaises(ValueError):
                main.driver_records(p, self.artifacts['drivers'], self.store, pub)

    def test_driver_elf_collision_is_fatal(self):
        with self.assertRaisesRegex(ValueError, 'differs from frozen BIN'):
            main.driver_records(self.p, self.artifacts['drivers'], {**self.store, 'test/driver.elf': b'changed'}, pub)

    def test_artifact_hash_tamper_rejected(self):
        raw = dict(self.artifacts); raw['main'] += b'extra'
        with self.assertRaisesRegex(ValueError, 'artifact changed'): main.payloads(self.p, 'e' * 40, raw, pub)

    def test_install_checksum_inventory_tamper(self):
        with self.assertRaisesRegex(ValueError, 'checksum inventory'):
            main.verify_checksums({'a': b'x', 'SHA256SUMS': b''}, pub)

    def test_end_to_end_stage_verify_and_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); inputs = root / 'inputs'; inputs.mkdir()
            watch = root / 'watch'; (watch / 'apps').mkdir(parents=True)
            for lane, value in self.p['deployment_sources'].items():
                (watch / f'apps/{lane}-sources.json').write_bytes(pub.encoded({'sources': value} if lane == 'audio' else value))
            (watch / 'apps/update-runtime-requirements.json').write_bytes(pub.encoded({
                'source_sha': self.p['sources']['runtime']['accepted_sha'], 'firmware_version': self.p['component_versions']['runtime']}))
            for name, raw in self.artifacts.items(): (inputs / (name + '.zip')).write_bytes(raw)
            output = root / 'stage'
            def command(*args, cwd=None):
                if 'status' in args: return b''
                if 'HEAD^{tree}' in args: return self.p['sources']['watch']['tree'].encode()
                if cwd == watch: return self.p['sources']['watch']['accepted_sha'].encode()
                if cwd == root / 'runtime': return self.p['sources']['runtime']['accepted_sha'].encode()
                return b'e' * 40
            with patch.object(pub, 'command', side_effect=command), patch.object(pub, 'read_config', return_value=self.p), \
                 patch.object(pub, 'verify_watch_ancestry', return_value={}):
                pub.stage(inputs, watch, root / 'runtime', output)
                pub.verify_stage(output)
                for case in ('source', 'latest', 'drivers', 'index', 'bin', 'extra'):
                    altered = root / ('altered-' + case)
                    shutil.copytree(output, altered)
                    plan_path = altered / 'publication-plan.json'
                    plan = json.loads(plan_path.read_text())
                    if case == 'source': plan['releases'][0]['source_sha'] = 'f' * 40
                    if case == 'latest': plan['releases'][0]['latest'] = True
                    if case == 'drivers': plan['driver_records'] = []
                    if case == 'index': plan['index']['firmware']['sha256'] = 'f' * 64
                    if case == 'bin':
                        name = plan['index']['firmware']['asset']
                        path = altered / self.p['tag'] / name
                        raw = bytearray(path.read_bytes()); raw[500] ^= 1; path.write_bytes(raw)
                        plan['releases'][-1]['assets'][name] = {'size': len(raw), 'sha256': pub.sha(raw)}
                    if case == 'extra': (altered / self.p['tag'] / 'unreviewed.bin').write_bytes(b'extra')
                    plan_path.write_bytes(pub.encoded(plan))
                    with self.subTest(case=case), self.assertRaises(ValueError): pub.verify_stage(altered)
                    shutil.rmtree(altered)
                path = output / self.p['tag'] / 'FLASHING.md'
                path.write_bytes(path.read_bytes() + b'false claim')
                plan_path = output / 'publication-plan.json'
                plan = json.loads(plan_path.read_text())
                plan['releases'][-1]['assets']['FLASHING.md'] = {'size': path.stat().st_size, 'sha256': pub.sha(path.read_bytes())}
                plan_path.write_bytes(pub.encoded(plan))
                with self.assertRaisesRegex(ValueError, 'frozen bytes'): pub.verify_stage(output)


class MainCITests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(pub, 'verify_watch_ancestry', return_value={})
        guard.start(); self.addCleanup(guard.stop)

    @classmethod
    def setUpClass(cls):
        cls.p, cls.artifacts, cls.store = fixture()

    def test_ci_missing_job_rejected_before_artifact_download(self):
        run = {'id': 123, 'head_sha': 'a' * 40, 'run_attempt': 1, 'status': 'completed', 'conclusion': 'success',
               'path': '.github/workflows/drivers.yml', 'repository': {'full_name': idx.REPOSITORY}}
        jobs = [{'name': n, 'conclusion': 'success'} for n in main.CI_JOBS if n != 'latest-main-image']
        with patch.object(pub, 'api', return_value=run), patch.object(pub, 'gh', return_value=pub.encoded([{'jobs': jobs}])) as gh:
            with self.assertRaisesRegex(ValueError, 'job missing'): main.verify_ci(self.p, pub)
            self.assertEqual(gh.call_count, 1)

    def test_ci_exact_attempt_all_jobs_accepted(self):
        run = {'id': 123, 'head_sha': 'a' * 40, 'run_attempt': 1, 'status': 'completed', 'conclusion': 'success',
               'path': '.github/workflows/drivers.yml', 'repository': {'full_name': idx.REPOSITORY}}
        jobs = [{'name': n, 'conclusion': 'success'} for n in main.CI_JOBS]
        with patch.object(pub, 'api', return_value=run), patch.object(pub, 'gh', return_value=pub.encoded([{'jobs': jobs}])):
            main.verify_ci(self.p, pub)

    def test_publish_rejects_unreviewed_external_config(self):
        with patch.object(pub, 'CONFIG', Path('/tmp/local-review-only.json')), patch.object(pub, 'verify_stage') as verify:
            with self.assertRaisesRegex(ValueError, 'canonical committed'): pub.publish(Path('/unused'))
            verify.assert_not_called()

    def test_publish_rejects_dirty_release_code(self):
        with patch.object(pub, 'command', return_value=b' M scripts/publish_watch_product.py'), patch.object(pub, 'verify_stage') as verify:
            with self.assertRaisesRegex(ValueError, 'source checkout dirty'): pub.publish(Path('/unused'))
            verify.assert_not_called()

    def test_download_symlink_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); target = root / 'kept'; target.write_bytes(b'keep')
            path = root / 'main.zip'; path.symlink_to(target)
            with self.assertRaisesRegex(ValueError, 'symlinks'): pub.write_input(path, b'bad')
            self.assertEqual(target.read_bytes(), b'keep')
            (root / 'linked').symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlinks'): pub.write_input(root / 'linked' / 'new.zip', b'bad')
            self.assertFalse((root / 'new.zip').exists())

    def test_download_rejects_an_artifact_from_a_previous_attempt(self):
        run = {'run_started_at': '2026-10-05T01:00:00Z', 'updated_at': '2026-10-05T02:00:00Z'}
        item = self.p['artifacts']['main']
        metadata = {'id': item['artifact_id'], 'name': item['name'], 'expired': False,
                    'workflow_run': {'id': item['run_id'], 'head_sha': item['head_sha']},
                    'created_at': '2026-10-05T00:59:59Z'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(pub, 'read_config', return_value=self.p), \
             patch.object(main, 'verify_ci', return_value=run), patch.object(pub, 'api', return_value=metadata), \
             patch.object(pub, 'gh') as gh:
            with self.assertRaisesRegex(ValueError, 'accepted CI attempt'):
                pub.artifact_inputs(Path(tmp), download=True)
            gh.assert_not_called()

    def test_reused_record_must_equal_existing_index_before_remote_download(self):
        p = copy.deepcopy(self.p)
        original = main.driver_records(p, self.artifacts['drivers'], self.store, pub)[0][0]
        p['reused_driver_records'] = {'twatch-test': {**original, 'included_in_accepted_bin': False}}
        current = {**copy.deepcopy(idx.EMPTY_INDEX), 'drivers': [original]}
        with patch.object(pub, 'current_release_index', return_value=('a' * 40, current)), patch.object(pub, 'verify_driver_releases') as check:
            with self.assertRaisesRegex(ValueError, 'differs from current immutable index'):
                pub.publication_preflight({'product': p}, Path('/unused'))
            check.assert_not_called()

    def test_reused_package_public_download_and_source_custody(self):
        records, assets = main.driver_records(self.p, self.artifacts['drivers'], self.store, pub)
        r = records[0]; r['source_sha'] = 'f' * 40
        release = {'draft': False, 'target_commitish': 'f' * 40, 'assets': [{'name': r['asset'], 'id': 1}, {'name': 'release-record.json', 'id': 2}]}
        raw_record = {'id': r['id'], 'version': r['version'], 'sha256': r['sha256'], 'size_bytes': r['size'],
                      'kind': 'driver', 'architecture': r['architecture'], 'archive': r['asset'],
                      'tag': r['tag'], 'source_sha': 'f' * 40}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp); (output / 'driver-assets').mkdir()
            (output / 'driver-assets' / r['asset']).write_bytes(assets[r['asset']])
            for case in ('exact', 'payload', 'record', 'tag'):
                bad_record = {**raw_record, **({'source_sha': 'e' * 40} if case == 'record' else {})}
                def gh(*args):
                    return pub.encoded(bad_record) if args[1].endswith('/2') else (b'changed' if case == 'payload' else assets[r['asset']])
                with self.subTest(case=case), patch.object(pub, 'release_by_tag', return_value=release), \
                     patch.object(pub, 'gh', side_effect=gh), patch.object(pub, 'api', return_value={'sha': ('e' if case == 'tag' else 'f') * 40}):
                    if case == 'exact': pub.verify_driver_releases({'driver_records': [r]}, output)
                    else:
                        with self.assertRaises(ValueError): pub.verify_driver_releases({'driver_records': [r]}, output)

    def test_full_publication_plan_index_collision_precedes_writes(self):
        r = pub.record('firmware', '', '1.0.1', 'twatch-s3-launcher-1.0.1.bin', b'new')
        old = idx.update_index(copy.deepcopy(idx.EMPTY_INDEX), 'firmware', {**r, 'sha256': 'f' * 64})
        planned = idx.update_index(copy.deepcopy(idx.EMPTY_INDEX), 'firmware', r)
        with patch.object(pub, 'current_release_index', return_value=('a' * 40, old)), patch.object(pub, 'gh') as gh:
            with self.assertRaisesRegex(ValueError, 'Immutable'):
                pub.publication_preflight({'index': planned}, Path('/unused'))
            gh.assert_not_called()

    def test_later_orphaned_public_release_fails_before_writes(self):
        releases = [{'tag': tag, 'source_sha': 'e' * 40, 'assets': {}} for tag in ('new-app', 'orphan')]
        existing = {'target_commitish': 'e' * 40, 'draft': False, 'assets': []}
        absent = subprocess.CompletedProcess([], 1, b'', b'HTTP 404')
        with patch.object(pub, 'current_release_index', return_value=(None, idx.EMPTY_INDEX)), \
             patch.object(pub, 'merged_index'), patch.object(pub, 'verify_driver_releases'), \
             patch.object(pub, 'release_by_tag', side_effect=[None, existing]), \
             patch.object(pub.subprocess, 'run', return_value=absent), patch.object(pub, 'gh') as gh:
            with self.assertRaisesRegex(ValueError, 'Published release tag missing'):
                pub.publication_preflight({'index': {}, 'releases': releases, 'product': self.p, 'source_sha': 'e' * 40}, Path('/unused'))
            gh.assert_not_called()

    def test_later_release_collision_does_not_create_earlier_release(self):
        releases = [{'tag': tag, 'source_sha': 'e' * 40, 'assets': {}} for tag in ('new-app', 'collision')]
        existing = {'target_commitish': 'f' * 40, 'draft': False, 'assets': []}
        absent = subprocess.CompletedProcess([], 1, b'', b'HTTP 404')
        with patch.object(pub, 'current_release_index', return_value=(None, idx.EMPTY_INDEX)), \
             patch.object(pub, 'merged_index'), patch.object(pub, 'verify_driver_releases'), \
             patch.object(pub, 'release_by_tag', side_effect=[None, existing]), \
             patch.object(pub.subprocess, 'run', return_value=absent), patch.object(pub, 'gh') as gh:
            with self.assertRaisesRegex(ValueError, 'source collision'):
                pub.publication_preflight({'index': {}, 'releases': releases, 'product': self.p, 'source_sha': 'e' * 40}, Path('/unused'))
            gh.assert_not_called()


class IntegrationAncestryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, _, _ = fixture()
        cls.owners = {'schema': 1, 'profile': 'watch-current-apps-v1', 'sources': {
            name: {'repository': 'michaelrolphone-cmyk/' + repo, 'commit': chr(97 + i) * 40}
            for i, (name, repo) in enumerate({'system-apps': 'RiscRTE-System-Apps',
                'utilities': 'RiscRTE-Utilities', 'productivity': 'RiscRTE-Productivity', 'runtime': 'RiscRTE'}.items())}}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        def git(*args):
            return subprocess.check_output(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                                            *args], cwd=self.root, stderr=subprocess.DEVNULL).decode().strip()
        git('init', '--initial-branch=main'); git('commit', '--allow-empty', '-m', 'base')
        self.base = git('rev-parse', 'HEAD')
        git('checkout', '-b', 'unmerged-candidate'); git('commit', '--allow-empty', '-m', 'candidate')
        self.candidate = git('rev-parse', 'HEAD')
        git('checkout', 'main'); git('commit', '--allow-empty', '-m', 'release')
        self.release = git('rev-parse', 'HEAD')

    def test_real_watch_graph_rejects_unmerged_candidate(self):
        with patch.object(pub, 'ROOT', self.root):
            self.assertTrue(pub.verify_watch_ancestry(self.base, self.release)['verified'])
            self.assertTrue(pub.verify_watch_ancestry(self.release, self.release)['verified'])
            with self.assertRaisesRegex(ValueError, 'not a verified ancestor'):
                pub.verify_watch_ancestry(self.candidate, self.release)

    def test_stage_rejects_unmerged_before_output(self):
        p = copy.deepcopy(self.p); p['sources']['watch']['accepted_sha'] = self.candidate
        output = self.root / 'must-not-exist'
        with patch.object(pub, 'ROOT', self.root), patch.object(pub, 'artifact_inputs', return_value=p), \
             patch.object(pub, 'command', return_value=self.release.encode()):
            with self.assertRaisesRegex(ValueError, 'not a verified ancestor'):
                pub.stage(Path('/unused'), Path('/unused'), Path('/unused'), output)
        self.assertFalse(output.exists())

    def test_publish_rechecks_unmerged_before_any_remote_call(self):
        p = copy.deepcopy(self.p); p['sources']['watch']['accepted_sha'] = self.candidate
        config = self.root / 'release/product.json'; config.parent.mkdir(); config.write_bytes(pub.encoded(p))
        def command(*args):
            return b'' if 'status' in args else config.read_bytes()
        with patch.object(pub, 'ROOT', self.root), patch.object(pub, 'CONFIG', config), \
             patch.object(pub, 'command', side_effect=command), patch.object(pub, 'api') as api, \
             patch.object(pub, 'verify_stage', return_value={'product': p, 'source_sha': self.release}):
            with self.assertRaisesRegex(ValueError, 'not a verified ancestor'): pub.publish(Path('/unused'))
            api.assert_not_called()

    def live_api(self, case='ahead'):
        pins = {pin['repository']: pin['commit'] for pin in self.owners['sources'].values()}
        counts = {}
        def api(endpoint):
            self.assertTrue(endpoint.startswith('repos/'))
            repository = '/'.join(endpoint.split('/')[1:3])
            suffix = '/'.join(endpoint.split('/')[3:])
            if not suffix:
                counts[repository] = counts.get(repository, 0) + 1
                return {'full_name': repository, 'default_branch': 'other' if case == 'moved' and counts[repository] > 1 else 'release/stable'}
            if suffix.startswith('commits/'):
                self.assertEqual(suffix, 'commits/release%2Fstable')
                return {'sha': pins[repository] if case == 'identical' else 'f' * 40}
            source = pins[repository]
            self.assertEqual(suffix, 'compare/' + source + '...' + (source if case == 'identical' else 'f' * 40))
            if case == 'missing': raise ValueError('GitHub compare 404')
            return {'base_commit': {'sha': 'e' * 40 if case == 'wrong-base' else source},
                    'merge_base_commit': {'sha': 'e' * 40 if case in ('diverged', 'behind') else source},
                    'status': case if case in ('identical', 'diverged', 'behind') else 'ahead',
                    'behind_by': 1 if case in ('diverged', 'behind') else 0}
        return api

    def test_live_defaults_prove_all_four_current_sources(self):
        product = {'current_apps_configuration': self.owners}
        for case in ('ahead', 'identical'):
            with self.subTest(case=case), patch.object(pub, 'api', side_effect=self.live_api(case)):
                evidence = pub.verify_current_source_ancestry(product)
                self.assertEqual({e['owner'] for e in evidence}, set(self.owners['sources']))
                self.assertTrue(all(e['default_branch'] == 'release/stable' and e['merge_base'] == e['source_sha'] for e in evidence))

    def test_live_default_rejects_pr_only_missing_or_moving_sources(self):
        product = {'current_apps_configuration': self.owners}
        for case in ('diverged', 'behind', 'wrong-base', 'missing', 'moved'):
            with self.subTest(case=case), patch.object(pub, 'api', side_effect=self.live_api(case)), self.assertRaises(ValueError):
                pub.verify_current_source_ancestry(product)

    def test_preflight_current_source_failure_precedes_publication_actions(self):
        product = {'sources': {'watch': {'accepted_sha': self.base}}, 'current_apps_configuration': self.owners}
        with patch.object(pub, 'ROOT', self.root), patch.object(pub, 'current_release_index', return_value=(None, idx.EMPTY_INDEX)), \
             patch.object(pub, 'merged_index'), patch.object(pub, 'api', side_effect=self.live_api('diverged')), \
             patch.object(pub, 'verify_driver_releases') as drivers, patch.object(pub, 'release_by_tag') as releases:
            with self.assertRaisesRegex(ValueError, 'not merged'):
                pub.publication_preflight({'product': product, 'source_sha': self.release, 'index': {}}, Path('/unused'))
            drivers.assert_not_called(); releases.assert_not_called()


if __name__ == '__main__':
    unittest.main()

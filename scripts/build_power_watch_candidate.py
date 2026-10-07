#!/usr/bin/env python3
"""Build/verify an isolated power-repair candidate with freshly rebuilt native firmware."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

from build_wifi_common import zip_bytes
from check_power_installed_catalog import check as check_installed_catalog
from check_runtime_store_admission import admit_cohort
from current_apps_overlay import ROOT, encoded, metadata, require, verify as verify_apps
from current_bootfs import build as build_store
from current_cohort import parse
from read_only_spiffs import read_image
from power_watch_candidate import (PROFILE, STORE_BYTES, accepted, read_native,
                                checked_source, compose, document, sha, paired_payload, initial_image)
from test_power_watch_upgrade import prove, validate_proof, check_disk, FREE_RESERVE
from power_watch_origins import ORIGINS, read_origin, read_installed_native
from power_repair_profile import VERSION, RUNTIME_VERSION

MODES = ('paired', 'initial', 'both')
DATA_EFFECTS = {
    'paired': 'Native firmware plus bootfs only. Preserves NVS settings, Wi-Fi credentials, Bluetooth bonds, alarms, Points and app-data. Previous pair remains intact until normal health confirmation. Never flash this payload at offset zero.',
    'initial': 'Full 16MiB initial image at offset zero. Erases NVS settings, Wi-Fi credentials, Bluetooth bonds, alarms, Points, all app-data and both banks. Never use this initial image for a preserving update.',
}


def safe_archive(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        require(len(names) == len(set(names)), 'Duplicate RF archive member')
        require(sum(e.file_size for e in entries) <= 64 * 1024 * 1024, 'RF app archive is unbounded')
        for entry in entries:
            name = PurePosixPath(entry.filename)
            require(not entry.is_dir() and name.parts and not name.is_absolute() and '..' not in name.parts
                    and str(name) == entry.filename and '\\' not in entry.filename
                    and entry.orig_filename == entry.filename and '\x00' not in entry.filename
                    and not stat.S_ISLNK(entry.external_attr >> 16), 'Unsafe RF archive member')
        return {entry.filename: archive.read(entry) for entry in entries}


def materialize_apps(raw, root):
    members = safe_archive(raw)
    check_disk(root, sum(map(len, members.values())) + len(raw))
    for name, content in members.items():
        path = root / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(content)
    (root / 'current-apps.zip').write_bytes(raw)


def instructions(mode, model, ota, initial, source_kind='accepted-1.0.7'):
    lines = ['Watch ' + VERSION + ' cutoff power-repair candidate; motion model ' + model + '.',
             'Offline candidate only. No publication or device installation was performed.']
    if ota:
        lines += ['', 'PAIRED UPDATE: ' + ota['asset'], DATA_EFFECTS['paired'],
                  ('Only the exact accepted Watch 1.0.7 BMA423/selectable source is qualified by this proof.' if source_kind == 'accepted-1.0.7' else 'Only the exact delivered Watch 1.0.10 BMA423/selectable test candidate is qualified by this proof; no device installation or acceptance is inferred.'),
                  'The installed catalog proof checks parser grammar only.',
                  'This private paired file is not reachable through the installed updater catalog until separately approved publication.',
                  'No release or catalog publication is authorized or performed by this builder.',
                  'A future approved catalog route must use the paired-cohort updater, never a raw full-image flashing command.',
                  'The production host proof covers native API gates, data preservation, failure/reboot/retry and rollback.',
                  'Physical flash, TLS, native SPIFFS parsing, target execution and real default-app health remain unqualified.']
    if initial:
        lines += ['', 'INITIAL FLASH: ' + initial['asset'], DATA_EFFECTS['initial'],
                  'Flash offset: 0x0. This is a different operation from the paired update.']
    lines += ['', 'Native firmware uses the exact verified Runtime ' + RUNTIME_VERSION + ' input. This Watch packager does not recompile it. Review power-watch-build-proof.json,',
              'SHA256SUMS and the exact source profile before any separate installation decision.']
    return '\n'.join(lines) + '\n'


def license_archive(app_archive, root=ROOT):
    licenses = {name: raw for name, raw in safe_archive(app_archive).items() if name.startswith('licenses/')}
    base = Path(root) / 'release/complete-1.0.7/licenses'
    for path in base.rglob('*'):
        if path.is_file(): licenses['accepted-native/' + path.relative_to(base).as_posix()] = path.read_bytes()
    require(licenses, 'RF licenses missing')
    return zip_bytes(licenses)


def prepare(apps_dir, runtime, native_dir, output, *, mode='paired', installed_system_apps=None, installed_runtime=None, installed_native_dir=None, source_cohort='accepted-1.0.7', source_bundle=None, allow_open_selection=False, root=ROOT):
    require(mode in MODES, 'Unknown RF candidate mode')
    root, apps_dir, output = Path(root).resolve(), Path(apps_dir).resolve(), Path(output).resolve()
    require(not output.exists(), 'RF candidate output must be new')
    head = checked_source(root)
    files, apps = verify_apps(apps_dir, head, root, profile=PROFILE)
    require(apps['cutoff_selection']['status'] == 'frozen' or allow_open_selection,
            'Cutoff selection remains open; use explicit staging mode or wait for the frozen selection')
    origin, native = read_origin(source_cohort, source_bundle, root), read_native(native_dir, runtime, root)
    following, identity, policy = compose(origin, native, files, apps, head, root, initial_only=mode == 'initial')
    check_disk(Path(tempfile.gettempdir()))
    bootfs, packing = build_store(following)
    # Capacity uses the actual exact target store and independently decoded bytes.
    require(packing['empty_blocks'] >= 2 and packing['independent_round_trip_verified'], 'RF bootfs capacity proof missing')
    staged = {}
    ota = initial = transaction = None
    catalog = None
    if mode in ('paired', 'both'):
        require(installed_system_apps is not None, 'Preserving RF OTA requires the exact installed System catalog parser')
        payload, ota = paired_payload(identity, native['blobs']['firmware.bin'], bootfs, apps['motion_model'])
        catalog = check_installed_catalog(ota, installed_system_apps, expected_source=origin['apps']['configuration']['sources']['system-apps']['commit'])
        require(installed_runtime is not None and installed_native_dir is not None, 'Preserving update needs exact accepted Runtime inputs')
        installed_native = read_installed_native(origin, installed_native_dir, installed_runtime, root)
        transaction = prove(origin, native, following, payload, runtime, apps_dir=apps_dir,
                            installed_runtime=installed_runtime, installed_native=installed_native)
        validate_proof(transaction, origin, following, payload, native)
        staged[ota['asset']] = payload
        staged['power-watch-upgrade-proof.json'] = encoded(transaction)
        staged['installed-catalog-proof.json'] = encoded(catalog)
        admission = {'installed': transaction['installed_runtime_admission'], 'self': transaction['target_self_admission']}
    else:
        check_disk(Path(tempfile.gettempdir()))
        admission = {'installed': None, 'self': admit_cohort(runtime, native['blobs']['firmware.elf'], following, following)}
    if mode in ('initial', 'both'):
        name, full, parts = initial_image(native, bootfs, runtime, apps['motion_model'])
        staged[name] = full
        initial = {'asset': name, **metadata(full), 'flash_offset': '0x0', 'components': parts,
                   'erases_persistent_data': True}
    app_archive = (apps_dir / 'current-apps.zip').read_bytes()
    staged['power-apps.zip'] = app_archive
    staged['runtime-requirements.json'] = (root / 'apps/power-repair-runtime-requirements.json').read_bytes()
    staged['native-custody.json'] = encoded(native['custody'])
    staged['LICENSES.zip'] = license_archive(app_archive, root)
    staged['INSTALL.txt'] = instructions(mode, apps['motion_model'], ota, initial, source_cohort).encode()
    proof = {'schema': 1, 'kind': 'watch-power-candidate', 'mode': mode, 'watch_source': head,
             'configuration': apps['configuration'], 'cutoff_selection': apps['cutoff_selection'],
             'provisional_selection': apps['cutoff_selection']['status'] == 'open', 'motion_model': apps['motion_model'], 'radio_model': apps['radio_model'],
             'source_kind': origin['kind'], 'source_physical_acceptance_claimed': origin['physical_acceptance_claimed'],
             'source_cohort': origin['identity'], 'target_cohort': identity,
             'source_initial_image': metadata(origin['full']), 'source_app_evidence_sha256': origin['evidence_sha256'],
             'native_custody': native['custody'], 'native_rebuilt': False, 'native_reused_exact': True,
             'native_build_mode': 'verified-external-runtime-input',
             'native_changed_from_source': native['blobs']['firmware.bin'] != origin['full'][0x10000:0x10000 + origin['identity']['firmware_size']],
             'app_archive': metadata(app_archive), 'files': {name: metadata(raw) for name, raw in sorted(following.items())},
             'policy': policy, 'packing': packing, 'admission': admission, 'ota': ota, 'initial': initial,
             'installed_catalog': catalog,
             'data_effects': {key: DATA_EFFECTS[key] for key in ('paired', 'initial') if mode in (key, 'both')},
             'preserving_update_proven': transaction is not None, 'complete_target_artifact': True,
             'physical_verification': False, 'published': False,
             'artifacts': {name: metadata(raw) for name, raw in sorted(staged.items())}}
    staged['power-watch-build-proof.json'] = encoded(proof)
    staged['SHA256SUMS'] = ''.join(sha(raw) + '  ' + name + '\n' for name, raw in sorted(staged.items())).encode()
    checked_source(root, head);checked_source(runtime, native['record']['source_sha'])
    output.parent.mkdir(parents=True, exist_ok=True)
    require(shutil.disk_usage(output.parent).free >= FREE_RESERVE + sum(map(len, staged.values())),
            'RF candidate output would leave less than 100MiB free')
    # The preserving artifact appears only after all exact-byte proofs succeed.
    with tempfile.TemporaryDirectory(prefix='.rf-candidate-', dir=output.parent) as temp:
        directory = Path(temp) / 'ready';directory.mkdir()
        for name, raw in staged.items(): (directory / name).write_bytes(raw)
        require(not output.exists(), 'RF output appeared during validation')
        directory.rename(output)
    return proof


def verify_bundle(bundle, runtime, native_dir, root=ROOT, *, installed_system_apps=None, installed_runtime=None, installed_native_dir=None, source_bundle=None):
    bundle, root = Path(bundle).resolve(), Path(root).resolve()
    proof_raw = (bundle / 'power-watch-build-proof.json').read_bytes();proof = document(proof_raw)
    require(proof['schema'] == 1 and proof['kind'] == 'watch-power-candidate' and proof['mode'] in MODES,
            'Wrong RF candidate proof kind/mode')
    expected = set(proof['artifacts']) | {'power-watch-build-proof.json', 'SHA256SUMS'}
    require({p.name for p in bundle.iterdir()} == expected, 'RF candidate artifact inventory differs')
    members = {}
    for name in expected:
        require(PurePosixPath(name).name == name and name not in ('', '.', '..'), 'Unsafe RF candidate artifact path')
        path = bundle / name
        require(path.is_file() and not path.is_symlink(), 'Invalid RF candidate artifact')
        members[name] = path.read_bytes()
    require({name: metadata(members[name]) for name in proof['artifacts']} == proof['artifacts'],
            'RF candidate artifact digest/size differs')
    require(members['SHA256SUMS'] == ''.join(sha(raw) + '  ' + name + '\n' for name, raw in
            sorted(members.items()) if name != 'SHA256SUMS').encode(), 'RF candidate checksum inventory differs')
    head = checked_source(root, proof['watch_source'])
    origin, native = read_origin(proof['source_kind'], source_bundle, root), read_native(native_dir, runtime, root)
    require(proof['source_physical_acceptance_claimed'] is origin['physical_acceptance_claimed'], 'Source acceptance claim differs')
    require(proof['native_build_mode'] == 'verified-external-runtime-input' and
            proof['native_changed_from_source'] is (native['blobs']['firmware.bin'] != origin['full'][0x10000:0x10000 + origin['identity']['firmware_size']]), 'Native transition claim differs')
    require(proof['native_custody'] == native['custody'] and proof['native_rebuilt'] is False and proof['native_reused_exact'] is True
            and proof['source_cohort'] == origin['identity'] and proof['source_initial_image'] == metadata(origin['full'])
            and proof['source_app_evidence_sha256'] == origin['evidence_sha256'], 'RF accepted source/native proof differs')
    require(members['native-custody.json'] == encoded(native['custody'])
            and members['runtime-requirements.json'] == (root / 'apps/power-repair-runtime-requirements.json').read_bytes(),
            'RF source descriptors differ')
    with tempfile.TemporaryDirectory(prefix='rf-bundle-apps-') as temp:
        app_root = Path(temp)
        materialize_apps(members['power-apps.zip'], app_root)
        files, apps = verify_apps(app_root, head, root, profile=PROFILE)
        following, identity, policy = compose(origin, native, files, apps, head, root, initial_only=proof['mode'] == 'initial')
    check_disk(Path(tempfile.gettempdir()))
    bootfs, packing = build_store(following)
    require(proof['cutoff_selection'] == apps['cutoff_selection'] and
            proof['provisional_selection'] is (apps['cutoff_selection']['status'] == 'open'), 'Cutoff freeze claim differs')
    require(proof['configuration'] == apps['configuration'] and proof['app_archive'] == metadata(members['power-apps.zip'])
            and proof['motion_model'] == apps['motion_model'] and proof['radio_model'] == apps['radio_model']
            and proof['target_cohort'] == identity and proof['policy'] == policy and proof['packing'] == packing
            and proof['files'] == {name: metadata(raw) for name, raw in sorted(following.items())},
            'RF reconstructed target/source/packing proof differs')
    paired = proof['mode'] in ('paired', 'both')
    initial = proof['mode'] in ('initial', 'both')
    artifacts = {'power-apps.zip', 'runtime-requirements.json', 'native-custody.json', 'LICENSES.zip', 'INSTALL.txt'}
    if paired: artifacts |= {'power-watch-upgrade-proof.json', 'installed-catalog-proof.json', proof['ota']['asset']}
    if initial: artifacts.add(proof['initial']['asset'])
    require(set(proof['artifacts']) == artifacts, 'Unexpected RF candidate artifact for its mode')
    require(members['LICENSES.zip'] == license_archive(members['power-apps.zip'], root), 'RF license custody differs')
    require(proof['preserving_update_proven'] is paired and proof['complete_target_artifact'] is True
            and proof['physical_verification'] is False and proof['published'] is False,
            'RF proof scope/data effects overstated')
    require(proof['data_effects'] == {key: DATA_EFFECTS[key] for key in ('paired', 'initial')
                                    if proof['mode'] in (key, 'both')}, 'RF installation data effects differ')
    if paired:
        require(installed_system_apps is not None, 'Preserving RF OTA verification requires installed System source')
        payload, ota = paired_payload(identity, native['blobs']['firmware.bin'], bootfs, apps['motion_model'])
        require(proof['ota'] == ota and members[ota['asset']] == payload, 'RF paired OTA bytes/identity differ')
        catalog = check_installed_catalog(ota, installed_system_apps, expected_source=origin['apps']['configuration']['sources']['system-apps']['commit'])
        require(proof['installed_catalog'] == catalog and document(members['installed-catalog-proof.json']) == catalog,
                'RF installed catalog parser proof differs')
        transaction = document(members['power-watch-upgrade-proof.json'])
        require(installed_runtime is not None and installed_native_dir is not None, 'Preserving proof requires installed native inputs')
        installed_native = read_installed_native(origin, installed_native_dir, installed_runtime, root)
        validate_proof(transaction, origin, following, payload, native)
        require(transaction['installed_native_elf'] == metadata(installed_native['blobs']['firmware.elf']), 'Installed native proof differs')
        require(transaction['app_archive'] == proof['app_archive'], 'RF transaction app artifact differs')
        require(proof['admission'] == {'installed': transaction['installed_runtime_admission'],
                                       'self': transaction['target_self_admission']}, 'RF graph proof differs')
    else:
        require(proof['ota'] is None and proof['admission']['installed'] is None
                and proof['installed_catalog'] is None
                and 'power-watch-upgrade-proof.json' not in members, 'Initial-only artifact claims preserving update')
    if initial:
        name, full, parts = initial_image(native, bootfs, runtime, apps['motion_model'])
        require(proof['initial'] == {'asset': name, **metadata(full), 'flash_offset': '0x0',
                                    'components': parts, 'erases_persistent_data': True}
                and members[name] == full, 'RF initial image bytes/data effects differ')
    else:
        require(proof['initial'] is None, 'Paired-only bundle contains an initial image')
    require(members['INSTALL.txt'] == instructions(proof['mode'], apps['motion_model'], proof['ota'], proof['initial'], proof['source_kind']).encode(),
            'RF install instructions differ')
    # Re-run exact target graph/ELF self-admission when verifying a sealed bundle.
    check_disk(Path(tempfile.gettempdir()))
    result = admit_cohort(runtime, native['blobs']['firmware.elf'], following, following)
    recorded = dict(proof['admission']['self'])
    recorded.setdefault('native_elf_sha256', sha(native['blobs']['firmware.elf']))
    recorded.setdefault('target_instructions_executed', False)
    require(result == recorded, 'RF repeated strict target admission differs')
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build')
    build.add_argument('--apps-dir', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--mode', choices=MODES, default='paired')
    build.add_argument('--source-cohort', choices=ORIGINS, default='accepted-1.0.7')
    build.add_argument('--allow-open-selection', action='store_true', help='Explicit provisional staging only; never freezes cutoff inputs')
    verify = sub.add_parser('verify')
    verify.add_argument('--bundle', type=Path, required=True)
    for command in (build, verify):
        command.add_argument('--runtime', type=Path, required=True)
        command.add_argument('--native-dir', type=Path, required=True)
        command.add_argument('--installed-system-apps', type=Path)
        command.add_argument('--installed-runtime', type=Path)
        command.add_argument('--installed-native-dir', type=Path)
        command.add_argument('--source-bundle', type=Path)
    args = parser.parse_args()
    result = (prepare(args.apps_dir, args.runtime, args.native_dir, args.output, mode=args.mode,
                      installed_system_apps=args.installed_system_apps, installed_runtime=args.installed_runtime, installed_native_dir=args.installed_native_dir, source_cohort=args.source_cohort, source_bundle=args.source_bundle, allow_open_selection=args.allow_open_selection)
              if args.command == 'build' else verify_bundle(args.bundle, args.runtime, args.native_dir,
                                                            installed_system_apps=args.installed_system_apps, installed_runtime=args.installed_runtime, installed_native_dir=args.installed_native_dir, source_bundle=args.source_bundle))
    print(json.dumps({'mode': result['mode'], 'source': result['watch_source'], 'version': result['target_cohort']['version'],
                      'preserving_update_proven': result['preserving_update_proven'], 'published': False}, sort_keys=True))


if __name__ == '__main__':
    main()

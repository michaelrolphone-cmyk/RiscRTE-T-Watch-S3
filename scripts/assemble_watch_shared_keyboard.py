#!/usr/bin/env python3
"""Compose Watch 1.1.17 with a real shared masked Wi-Fi keyboard consumer."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = '628f72b09786880edeafa7c161aedd7114c2d7bc'
BASE_SHA = '63a89adf489ff568bb4236c0f4378f5b707554ec1f9394bd45ed58c71e52a7ef'
RUNTIME = '267aab6d9382ce4921a1536fab1620749b2f5301'
RUNTIME_TREE = '62fe2dfc53169317f91bbc8fadadd9e0bda7e62c'
SYSTEM = '9c0ad2faa4b3aa73daf1c92cc343e0f83c2a5af3'
SYSTEM_TREE = 'd63b624b1dd397afd38cdb4db0b4cf94c53ba409'
SDK = '1c1ed8661ea30d47e7e9707c41d492ce3a2b4d70'
NATIVE_ELF_SHA = '7025c5158323a0b26a62c3608684a3eecdbfd74e42049ba760f57822315307f0'
FIRMWARE_SHA = 'f9cc819421775cfb9e55a8c7b2c1f2174c9a61b1a85560446cf4f680d14a7726'
SCENE_SHA = '361e9d3d4ea879653afdea116f799565c0ce95430db0453d7d019c97745f1a35'
TEXT_SHA = 'f7d3f99ebf20c52d8f35ff8edd6260c9c0371e624486e814ed727061d50a4fef'
VERSION = '1.1.17'
WIFI_VERSION = '1.1.28'
IMAGE = 'WATCH-1.1.17-FULL-INITIAL-ERASES-DATA.bin'
BOOTFS = (0x2f0000, 0x800000)
BANK = (0xff2000, 0xff4000)
PRESERVED = ((0, BOOTFS[0]), (BOOTFS[1], BANK[0]), (BANK[1], 0x1000000))
CHANGED = {'boot.json', 'cohort.json', 'wifi_settings.elf', 'wifi_settings.json',
           'ui-scene/driver.elf', 'ui-scene/manifest.json'}
ADDED = {'text-input/driver.elf', 'text-input/manifest.json'}
TEXT_REQUIREMENT = {'capability': 'ui.text-input', 'api': 1}
TEXT_GRANT = dict(TEXT_REQUIREMENT, instance_id=0)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_sources(record, root=None):
    hashes = record.get('source_sha256', {})
    require(bool(hashes), 'Build lacks compiled source hashes')
    for name, digest in hashes.items():
        if ':' in name and name.split(':', 1)[0] in record.get('source_roots', {}):
            label, relative = name.split(':', 1)
            path = Path(record['source_roots'][label]) / relative
        else:
            path = Path(name)
        if not path.is_absolute():
            require(root is not None, 'Relative source lacks a root')
            path = Path(root) / path
        require(path.is_file() and sha(path.read_bytes()) == digest,
                'Compiled source changed: ' + str(path))
    return len(hashes)


def changed_store(old, revision, scene_elf, text_elf, text_manifest, wifi_elf, wifi_manifest):
    cohort = json.loads(old['cohort.json'])
    require(cohort['version'] == '1.1.16' and cohort['source_revision'] == BASE,
            'Wrong predecessor cohort')
    require(not ADDED.intersection(old), 'Text provider already present')
    before_wifi = json.loads(old['wifi_settings.json'])
    after_wifi = json.loads(wifi_manifest)
    require(before_wifi['version'] == '1.1.20', 'Wrong predecessor Wi-Fi')
    expected_wifi = copy.deepcopy(before_wifi)
    expected_wifi['version'] = WIFI_VERSION
    require(TEXT_REQUIREMENT not in expected_wifi['requires'], 'Existing shared Wi-Fi requirement')
    expected_wifi['requires'].append(TEXT_REQUIREMENT)
    require(after_wifi == expected_wifi, 'Wi-Fi manifest changed beyond version and text-input requirement')
    scene = json.loads(old['ui-scene/manifest.json'])
    require(scene['id'] == 'scene-host' and scene['version'] == '0.3.2', 'Wrong predecessor scene')
    require(scene['requires'] == [
        {'api': 1, 'capability': 'display.output'}, {'api': 1, 'capability': 'input.touch.raw'},
        {'api': 1, 'capability': 'platform.clock'}, {'api': 1, 'capability': 'ui.presentation-profile'}],
        'Wrong Watch touch-only scene dependencies')
    scene['version'] = '0.4.3'
    text = json.loads(text_manifest)
    require(text == {'architecture': 'xtensa-esp32s3', 'driver_abi': 2, 'file_name': 'driver.elf',
                     'id': 'text-input-host', 'provides': [TEXT_REQUIREMENT],
                     'requires': [{'api': 1, 'capability': 'ui.scene'}], 'type': 'driver', 'version': '0.1.4'},
            'Unexpected text provider or USB dependency')
    boot = json.loads(old['boot.json'])
    require(len(boot['app_capabilities']) == 25 and len(boot['drivers']) == 30, 'Wrong complete boot graph')
    require(boot['provider_activation'] == 'demand-retained', 'Wrong provider activation policy')
    wifi_rows = [row for row in boot['app_capabilities'] if row['manifest'] == 'wifi_settings.json']
    require(len(wifi_rows) == 1 and TEXT_GRANT not in wifi_rows[0]['grants'], 'Wrong Wi-Fi policy')
    wifi_rows[0]['grants'].append(TEXT_GRANT)
    boot['drivers'].append({'manifest': 'text-input/manifest.json'})
    cohort.update(version=VERSION, source_revision=revision)
    result = dict(old)
    result.update({'cohort.json': encoded(cohort), 'boot.json': encoded(boot),
                   'ui-scene/manifest.json': encoded(scene), 'ui-scene/driver.elf': scene_elf,
                   'text-input/manifest.json': encoded(text), 'text-input/driver.elf': text_elf,
                   'wifi_settings.json': encoded(after_wifi), 'wifi_settings.elf': wifi_elf})
    return result


def verify_preservation(previous, full, old, new):
    require(len(full) == len(previous) == 0x1000000, 'Incorrect flash size')
    for begin, end in PRESERVED:
        require(full[begin:end] == previous[begin:end], 'Non-store flash changed')
    require(set(new) - set(old) == ADDED and not set(old) - set(new), 'Unexpected store members')
    require({name for name in old if old[name] != new[name]} == CHANGED, 'Unapproved store change')
    require(json.loads(new['file_browser.json'])['version'] == '1.5.31', 'Mounted Files version changed')
    require(json.loads(new['default.json'])['version'] == '0.11.5', 'Clock/wake predecessor changed')
    return {'preserved_store_files': len(old) - len(CHANGED), 'changed_store_files': sorted(CHANGED),
            'added_store_files': sorted(ADDED), 'native_firmware_byte_preserved': True,
            'unrelated_app_provider_bytes_preserved': True, 'files_1_5_31_byte_preserved': True,
            'unchanged_flash_ranges': [list(pair) for pair in PRESERVED],
            'existing_grants_preserved': True, 'added_app_grants': {'wifi_settings.json': [TEXT_GRANT]},
            'scene_dependency_selection': 'existing Watch touch-only; no navigation or USB provider added'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-image', 'runtime', 'native', 'system', 'sdk-runtime', 'keyboard-build', 'wifi-build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--compose-only', action='store_true')
    args = parser.parse_args()
    require(not git(ROOT, 'status', '--porcelain'), 'Dirty product source')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    for root, commit, tree in ((args.runtime, RUNTIME, RUNTIME_TREE), (args.system, SYSTEM, SYSTEM_TREE),
                               (args.sdk_runtime, SDK, None)):
        require(git(root, 'rev-parse', 'HEAD') == commit and
                not git(root, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty source: ' + str(root))
        if tree:
            require(git(root, 'rev-parse', 'HEAD^{tree}') == tree, 'Wrong source tree')
    sys.path[:0] = [str(ROOT / 'scripts'), str(args.runtime / 'scripts'), str(args.system / 'scripts')]
    from current_bootfs import build, read_image
    from watch_boot_order_spiffs import build as ordered_build, ordered_paths
    from paired_bank_images import initial_bank_state, parse_record
    from check_runtime_store_admission import admit_cohort
    from compact_current_elf import compact
    sdk_spec = importlib.util.spec_from_file_location('keyboard_source_sdk', args.system / 'scripts/scene_sdk.py')
    sdk_module = importlib.util.module_from_spec(sdk_spec)
    sdk_spec.loader.exec_module(sdk_module)
    stage_sdk = sdk_module.stage_sdk
    previous = args.baseline_image.read_bytes()
    require(sha(previous) == BASE_SHA and len(previous) == 0x1000000, 'Not exact frozen Watch 1.1.16')
    old = read_image(previous[slice(*BOOTFS)], 0x510000)
    require(len(old) == 111, 'Wrong predecessor file count')
    firmware = (args.native / 'firmware.bin').read_bytes()
    native_elf = (args.native / 'firmware.elf').read_bytes()
    require(sha(firmware) == FIRMWARE_SHA and sha(native_elf) == NATIVE_ELF_SHA and
            previous[0x10000:0x10000 + len(firmware)] == firmware, 'Wrong native pair')
    packages = [('scene', args.keyboard_build / 'presentation/scene-host', SCENE_SHA, 'scene-host', '0.4.3'),
                ('text', args.keyboard_build / 'text-input-host', TEXT_SHA, 'text-input-host', '0.1.4')]
    records, modules, compactions = {}, {}, {}
    source_count = 0
    compiler = os.environ.get('NATIVE_APP_CC')
    require(bool(compiler), 'Set pinned NATIVE_APP_CC')
    with tempfile.TemporaryDirectory(prefix='watch-keyboard-inputs-') as temporary:
        temporary = Path(temporary)
        include = stage_sdk(args.sdk_runtime, args.system, temporary)
        scene_headers = {path.name: sha(path.read_bytes()) for path in include.glob('*.h')}
        shutil.copy(args.system / 'sdk/app/RiscTextEntryV1.h', include)
        for name in ('RiscUsbHidV1.h', 'RiscUsbControllerV1.h', 'RiscUsbProviderV1.h'):
            source = args.system / 'Services/text_input' / name
            require(not (include / name).exists() or (include / name).read_bytes() == source.read_bytes(),
                    'Conflicting USB contract')
            shutil.copy(source, include)
        text_headers = {path.name: sha(path.read_bytes()) for path in include.glob('*.h')}
        for key, folder, digest, identity, version in packages:
            raw = (folder / 'driver.elf').read_bytes()
            record = json.loads((folder / 'build.json').read_bytes())
            require(sha(raw) == digest == record['sha256'] and len(raw) == record['size_bytes'] and
                    record['id'] == identity and record['version'] == version and
                    record['defines'] == (['-DSCENE_HOST_TELEMETRY=0', '-DSCENE_HOST_WATCH_240=1'] if key == 'scene' else []),
                    'Wrong keyboard build receipt')
            require(record['sdk_sha256'] == (scene_headers if key == 'scene' else text_headers), 'SDK input mismatch')
            source_count += check_sources(record)
            records[key] = record
            elf_path = temporary / (key + '.elf')
            elf_path.write_bytes(raw)
            compactions[key] = compact(elf_path, compiler, debug_path=temporary / (key + '.full.elf'))
            modules[key] = elf_path.read_bytes()
        wifi_raw = (args.wifi_build / 'wifi_settings.elf').read_bytes()
        wifi_manifest = (args.wifi_build / 'wifi_settings.json').read_bytes()
        wifi_record = json.loads((args.wifi_build / 'wifi_settings-build-record.json').read_bytes())
        require(wifi_record['sha256'] == sha(wifi_raw) and wifi_record['bytes'] == len(wifi_raw) and
                wifi_record['version'] == WIFI_VERSION and wifi_record['manifest_sha256'] == sha(wifi_manifest),
                'Wrong Wi-Fi build receipt')
        require(wifi_record['sources']['system-apps'] == SYSTEM and wifi_record['sources']['runtime'] == RUNTIME and
                wifi_record['sources']['utilities'] == 'fc0bdbbbc600ce891e60c44d091fce0586ade7d8' and
                wifi_record['sources']['watch'] == '089868395268b696c05651c33816345bfe0425df',
                'Wi-Fi source pins differ from the qualified profile')
        require(wifi_record['build_recipe_sha256'] == sha((ROOT / 'scripts/build_watch_keyboard_wifi.py').read_bytes()),
                'Wi-Fi build recipe differs from product source')
        require(b'ui.text-input\0' in wifi_raw and '-DPORTABLE_TEXT_INPUT_CLIENT' in wifi_record['defines'],
                'Wi-Fi ELF has no shared text client')
        require(wifi_record['baseline_grants_preserved'] and wifi_record['baseline_feature_flags_preserved'] and
                wifi_record['full_contexts_catalog_preserved'] and not wifi_record['native_changed'] and
                not wifi_record['sd_persistence_changed'], 'Wi-Fi feature or source scope differs')
        source_count += check_sources(wifi_record, args.system)
        required = next(row['grants'] for row in json.loads(old['boot.json'])['app_capabilities']
                        if row['manifest'] == 'wifi_settings.json') + [TEXT_GRANT]
        key = lambda value: (value['capability'], value['api'], value['instance_id'], value.get('file', ''))
        require(sorted(wifi_record['required_grants'], key=key) == sorted(required, key=key), 'Wi-Fi authority changed')
        wifi_path = temporary / 'wifi_settings.elf'
        wifi_path.write_bytes(wifi_raw)
        compactions['wifi'] = compact(wifi_path, compiler, debug_path=temporary / 'wifi_settings.full.elf')
        modules['wifi'] = wifi_path.read_bytes()
    new = changed_store(old, revision, modules['scene'], modules['text'],
                        (args.keyboard_build / 'text-input-host/manifest.json').read_bytes(), modules['wifi'], wifi_manifest)
    require(json.loads((args.keyboard_build / 'presentation/scene-host/manifest.json').read_bytes()) ==
            json.loads(new['ui-scene/manifest.json']), 'Watch scene manifest differs from selected build profile')
    image, packing = ordered_build(new, build)
    require([name for name in ordered_paths(new) if name not in ADDED] == ordered_paths(old),
            'Existing boot access order changed')
    record_bundle = {'packing': packing, 'scene-build': records['scene'], 'text-build': records['text'],
                     'wifi-build': wifi_record, 'compaction': compactions}
    if not args.verify_only:
        require(not args.output.exists(), 'Use a new output directory')
        full = bytearray(previous)
        full[slice(*BOOTFS)] = image
        full[slice(*BANK)] = initial_bank_state(firmware, image, True)
        (args.output / 'receipts').mkdir(parents=True)
        (args.output / 'components').mkdir()
        for name, raw in new.items():
            path = args.output / 'store' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (args.output / IMAGE).write_bytes(full)
        (args.output / 'components/bootfs.bin').write_bytes(image)
        (args.output / 'components/bank_state.bin').write_bytes(full[slice(*BANK)])
        for name, record in record_bundle.items():
            (args.output / 'receipts' / (name + '.json')).write_bytes(encoded(record))
    for name, record in record_bundle.items():
        require(json.loads((args.output / 'receipts' / (name + '.json')).read_bytes()) == record,
                'Written input receipt differs: ' + name)
    full = (args.output / IMAGE).read_bytes()
    proof = verify_preservation(previous, full, old, new)
    require(full[slice(*BOOTFS)] == image and read_image(image, 0x510000) == new, 'Final bootfs decode differs')
    require((args.output / 'components/bootfs.bin').read_bytes() == image and
            (args.output / 'components/bank_state.bin').read_bytes() == full[slice(*BANK)], 'Components differ')
    actual = {path.relative_to(args.output / 'store').as_posix(): path.read_bytes()
              for path in (args.output / 'store').rglob('*') if path.is_file()}
    require(actual == new, 'Written store differs')
    state = full[slice(*BANK)]
    record = parse_record(state[:96], True)
    require(record[2] == 0 and record[3] == len(firmware) and record[6] == hashlib.sha256(firmware).digest() and
            record[7] == hashlib.sha256(image).digest() and state[96:] == b'\xff' * (8192 - 96), 'Incorrect bank state')
    proof.update(product_source=revision, product_tree=git(ROOT, 'rev-parse', 'HEAD^{tree}'), product_version=VERSION,
                 baseline_product=BASE, baseline_full_image_sha256=BASE_SHA, system_source=SYSTEM, sdk_source=SDK,
                 runtime_source=RUNTIME, wifi_source_pins=wifi_record['sources'], full_image_sha256=sha(full), full_image_bytes=len(full),
                 compiled_source_hashes_verified=source_count, existing_boot_access_order_preserved=True,
                 scene_version='0.4.3', scene_profile='watch-compact; 240x240 RGB565; optional OBD telemetry excluded', text_version='0.1.4', wifi_version=WIFI_VERSION,
                 compact_elf_sha256={key: sha(raw) for key, raw in modules.items()},
                 hardware_verified=False, full_initial_erases_data=True)
    if args.compose_only:
        proof['full_admission_pending'] = True
        name = 'composition.json'
    else:
        admission = admit_cohort(args.runtime, native_elf, old, new, app_policy_rows=24,
                                 native_profile=args.native / 'crown-wake-profile.ini')
        require(admission['prepared'] and admission['cohort_validated'] and admission['elf_count'] == 55 and
                admission['hardware_calls'] == admission['storage_calls'] == 0, 'Full production admission failed')
        proof.update(admission, sanitizers='ASan+UBSan; LeakSanitizer disabled under ptrace'
                     if os.getenv('SANITIZE') == '1' else 'none')
        name = 'final-image-admission-sanitizer.json' if os.getenv('SANITIZE') == '1' else 'final-image-admission.json'
    (args.output / 'receipts' / name).write_bytes(encoded(proof))
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()

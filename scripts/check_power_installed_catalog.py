#!/usr/bin/env python3
"""Check actual power-repair OTA metadata with the exact accepted installed catalog parser.

Only its outer firmware framing is synthetic. No release catalog, full-image
hash qualification, publication, download, or device operation is produced.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_SOURCE = 'f146d82d4c2bc4d4b6ac97f7be83b04035ad7d60'
REPOSITORY = 'michaelrolphone-cmyk/RiscRTE-T-Watch-S3'
VERSION = '1.0.11'
from power_repair_profile import RUNTIME_VERSION
SOURCE_FILES = ('Services/update/Catalog.h', 'Services/update/JsonCursor.h',
                'lib/PortableApps/include/SoftwareUpdateV1.h',
                'lib/PortableApps/include/RiscBankStoreV1.h',
                'lib/NativeApps/include/T5PackageVersion.h')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_state(system_apps, expected_source=SYSTEM_SOURCE):
    head = subprocess.check_output(['git', '-C', str(system_apps), 'rev-parse', 'HEAD'], text=True).strip()
    require(head == expected_source, 'RF catalog check requires the exact accepted System source')
    require(not subprocess.check_output(['git', '-C', str(system_apps), 'status', '--porcelain',
                                         '--untracked-files=no'], text=True).strip(),
            'Installed System source is dirty')
    return {name: sha((system_apps / name).read_bytes()) for name in SOURCE_FILES}


def framing(ota):
    # These outer values satisfy the catalog grammar only. In particular, the
    # all-zero full-image hash does not identify any generated or verified image.
    asset = 'twatch-s3-launcher-' + VERSION + '.bin'
    tag = 'firmware-v' + VERSION
    return {'schema': 1, 'firmware': {
        'kind': 'firmware', 'version': VERSION, 'tag': tag, 'asset': asset,
        'url': 'https://github.com/' + REPOSITORY + '/releases/download/' + tag + '/' + asset,
        'size': 0x1000000, 'sha256': '0' * 64, 'ota': ota}}


def cases(ota):
    yield 'canonical', copy.deepcopy(ota), True
    for label in ('renamed-asset-and-url', 'renamed-asset', 'renamed-url',
                  'mismatched-version', 'wrong-source-repo', 'malformed-payload-sha',
                  'malformed-firmware-sha', 'malformed-store-sha'):
        changed = copy.deepcopy(ota)
        if label.startswith('renamed-'):
            alternate = 'twatch-s3-1.0.11-NATIVE-BOOTFS-OTA-PRESERVES-DATA-bma423.bin'
            if label in ('renamed-asset-and-url', 'renamed-asset'):
                changed['asset'] = alternate
            if label in ('renamed-asset-and-url', 'renamed-url'):
                changed['url'] = changed['url'].rsplit('/', 1)[0] + '/' + alternate
        elif label == 'mismatched-version':
            changed['version'] = '1.0.7'
        elif label == 'wrong-source-repo':
            changed['source_repo'] = 'other/watch'
        else:
            key = {'malformed-payload-sha': 'sha256', 'malformed-firmware-sha': 'firmware_sha256',
                   'malformed-store-sha': 'store_sha256'}[label]
            changed[key] = 'z' + changed[key][1:]
        yield label, changed, False


def check(ota, system_apps, *, expected_source=SYSTEM_SOURCE):
    """Return source-bound parser evidence for the supplied exact OTA descriptor."""
    system_apps = Path(system_apps).resolve()
    require(isinstance(ota, dict) and ota.get('kind') == 'paired-cohort'
            and ota.get('version') == VERSION and ota.get('runtime_version') == RUNTIME_VERSION
            and ota.get('layout') == 'riscrte-paired-appdata-v2' and ota.get('store_abi') == 2,
            'RF catalog check requires a the selected Watch1.0.11/Runtime paired descriptor')
    supplied = encoded(ota)
    source_files = source_state(system_apps, expected_source)
    fixture = ROOT / 'tests/rf_watch_upgrade/catalog_admission.cpp'
    fixture_sha = sha(fixture.read_bytes())
    results = []
    with tempfile.TemporaryDirectory(prefix='rf-installed-catalog-') as temporary:
        root = Path(temporary);executable = root / 'parser';input_path = root / 'framing-fixture.json'
        dependencies = root / 'parser.d'
        subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation',
                        '-MMD', '-MF', str(dependencies),
                        *['-I' + str(system_apps / path) for path in
                          ('Services/update', 'lib/PortableApps/include', 'lib/NativeApps/include')],
                        str(fixture), '-o', str(executable)], check=True, timeout=60, capture_output=True, text=True)
        compiled = dependencies.read_text().replace('\\\n', ' ').split(':', 1)[1]
        require({Path(path).resolve() for path in shlex.split(compiled)} ==
                {fixture.resolve(), *(system_apps / name for name in SOURCE_FILES)},
                'Installed catalog compiler used unexpected or shadowed source headers')
        for label, descriptor, expected in cases(ota):
            input_path.write_bytes(encoded(framing(descriptor)))
            process = subprocess.run([str(executable), str(input_path)], check=True, timeout=15,
                                     capture_output=True, text=True)
            result = json.loads(process.stdout)
            require(result.get('accepted') is expected and result.get('row_count') == int(expected),
                    'Installed RF catalog parser outcome differs: ' + label)
            if expected:
                require(result['paired_cohort'] is True and result['store_abi'] == ota['store_abi']
                        and result['firmware_size'] == ota['firmware_size']
                        and result['store_size'] == ota['store_size'] and result['payload_size'] == ota['size'],
                        'Installed RF parser did not retain the supplied paired payload sizes')
            results.append({'scenario': label, 'ota_sha256': sha(encoded(descriptor)),
                            'parser_assertions_passed': True, **result})
    require(source_state(system_apps, expected_source) == source_files and sha(fixture.read_bytes()) == fixture_sha,
            'RF catalog parser source changed during verification')
    require(encoded(ota) == supplied, 'RF catalog check modified the supplied OTA descriptor')
    return {'schema': 1, 'installed_system_source': expected_source, 'source_file_sha256': source_files,
            'fixture_sha256': fixture_sha, 'accepted_ota_sha256': sha(supplied),
            'ota_digest_encoding': 'sorted compact JSON with trailing newline',
            'framing_fixture_only': True, 'full_initial_image_verified': False,
            'publishable_catalog_emitted': False, 'cases': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-apps', required=True, type=Path)
    parser.add_argument('--ota', required=True, type=Path, help='JSON file containing the actual OTA descriptor')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output is not None:
        require(not args.output.exists(), 'RF catalog proof output must be new')
    proof = check(json.loads(args.ota.read_bytes()), args.system_apps)
    raw = json.dumps(proof, sort_keys=True, indent=2) + '\n'
    if args.output is None:
        print(raw, end='')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw)


if __name__ == '__main__':
    main()

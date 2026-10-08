#!/usr/bin/env python3
"""Fresh-native custody and exact RF-preserving Watch power candidate policy."""
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

from current_apps_overlay import APPS, ROOT, config, configure_board, encoded, metadata, require
from current_cohort import create, encode, package, parse, verify as verify_identity
from current_flash_layout import assemble
from read_only_spiffs import read_image
from rf_watch_candidate import (accepted, authority, checked_source as checked_tracked_source, document, module, sha,
                                STORE_BYTES, FIRMWARE_BYTES, FIRMWARE_OFFSETS, STORE_OFFSETS, SOURCE_VERSION)
from rf_spectrum_profile import PRIVATE_GRANTS, upgrade_boot
from power_repair_profile import PROFILE, VERSION, RUNTIME_VERSION, POWER_DRIVERS, runtime_requirements


def checked_source(root, expected=None):
    head = checked_tracked_source(root, expected)
    require(not subprocess.check_output(['git', '-C', str(root), 'ls-files', '--others', '--exclude-standard'], text=True).strip(),
            'Untracked power candidate source inputs: ' + str(root))
    return head


def read_native(native_dir, runtime, root=ROOT, *, requirements_override=None):
    """Require clean pinned source, new compiled markers and fresh native proofs."""
    native_dir, runtime, root = Path(native_dir), Path(runtime), Path(root)
    requirements = runtime_requirements(root) if requirements_override is None else requirements_override
    expected_version = requirements['firmware_version']
    source = requirements['source_sha'];checked_source(runtime, source)
    raw = (native_dir / 'candidate.json').read_bytes();record = document(raw)
    require(record['schema'] == 1 and record['source_sha'] == source and record['firmware_version'] == expected_version,
            'Power native candidate source/version differs')
    expected_assets = {'firmware.bin', 'firmware.elf', 'bootloader.bin', 'partitions.bin', 'platformio.ini',
                       'partitions-paired-appdata.csv', 'requirements-ci.txt', 'radio-iq-proof.json',
                       'appdata.bin', 'appdata-image.json'}
    require(set(record['assets']) == expected_assets and {p.name for p in native_dir.iterdir()} ==
            expected_assets | {'candidate.json', 'SHA256SUMS'}, 'Power native asset inventory differs')
    blobs = {}
    for name, item in record['assets'].items():
        require(PurePosixPath(name).name == name, 'Unsafe native member')
        path = native_dir / name
        require(path.is_file() and not path.is_symlink(), 'Invalid native file: ' + name)
        blobs[name] = path.read_bytes()
        require(item == {'bytes': len(blobs[name]), 'sha256': sha(blobs[name])}, 'Power native bytes differ: ' + name)
    require((native_dir / 'SHA256SUMS').read_text() == ''.join(sha(p.read_bytes()) + '  ' + p.name + '\n'
            for p in sorted(native_dir.iterdir()) if p.name != 'SHA256SUMS'), 'Power native checksum inventory differs')
    validator = r'''
import json,sys
from pathlib import Path
runtime,native=map(Path,sys.argv[1:]);sys.path.insert(0,str(runtime/'scripts'))
from paired_candidate import partitions,APP_DATA_EXPECTED,native_proof
from paired_bank_images import BOOTLOADER_SHA256
from release_assets import esp_image,elf
from radio_iq_proof import prove
from app_data_image import verify_initial
import hashlib
record=json.loads((native/'candidate.json').read_text())
blobs={n:(native/n).read_bytes() for n in ('firmware.bin','firmware.elf','bootloader.bin','partitions.bin')}
for n in ('firmware.bin','bootloader.bin'):
    esp_image(blobs[n])
    if blobs[n][3]>>4!=4: raise ValueError('Native 16MiB flag differs')
if hashlib.sha256(blobs['bootloader.bin']).hexdigest()!=BOOTLOADER_SHA256: raise ValueError('Unreviewed bootloader')
elf(blobs['firmware.elf'])
if json.loads(json.dumps(partitions(blobs['partitions.bin'],APP_DATA_EXPECTED)))!=record['partitions']:
    raise ValueError('Native partition proof differs')
for marker in ('RTE_SOURCE='+record['source_sha'],'RISC_RUNTIME_VERSION:'+record['firmware_version'],'RISC_PAIRED_STORE_ABI:2',record['target']):
    if not all(marker.encode()+b'\0' in blobs[n] for n in ('firmware.bin','firmware.elf')):
        raise ValueError('Compiled native identity differs: '+marker)
if b'RISC_PAIRED_STORE_ABI:1\0' in blobs['firmware.bin']: raise ValueError('Native ABI1 marker')
proof=native_proof(blobs['firmware.elf']);proof['radio_iq']=prove(blobs['firmware.elf'])
proof=json.loads(json.dumps(proof))
if proof!=record['native_proof']: raise ValueError('Native post-link proof differs')
if proof['radio_iq']!=json.loads((native/'radio-iq-proof.json').read_text()): raise ValueError('IQ proof file differs')
if verify_initial(native)!=record['initial_appdata']: raise ValueError('Initial appdata custody differs')
for n in ('platformio.ini','partitions-paired-appdata.csv','requirements-ci.txt'):
    if (runtime/n).read_bytes()!=(native/n).read_bytes(): raise ValueError('Native source bytes differ: '+n)
'''
    subprocess.run([sys.executable, '-c', validator, str(runtime.resolve()), str(native_dir.resolve())], check=True)
    for key in ('target', 'layout', 'store_abi', 'flash_bytes'):
        require(requirements['deployment'][key] == record[key], 'Power native deployment mismatch: ' + key)
    require(len(blobs['firmware.bin']) <= FIRMWARE_BYTES, 'Power native exceeds slot')
    require(requirements['deployment']['partitions'] == {
        name: {'offset': values[2], 'size': values[3]} for name, values in record['partitions'].items() if name != 'nvs'},
        'Power native partition requirements differ')
    require(record['partitions']['nvs'] == [1, 2, 0x9000, 0x6000], 'Power native NVS geometry changed')
    custody = {'schema': 1, 'source_sha': source, 'firmware_version': expected_version,
               'target': record['target'], 'candidate_sha256': sha(raw), 'native_rebuilt': False, 'native_reused_exact': True,
               'assets': {name: metadata(b) for name, b in sorted(blobs.items())}}
    return {'record': record, 'blobs': blobs, 'custody': custody, 'requirements': requirements}


def check_policy(previous, following, configuration, *, initial_only=False):
    require(set(previous) == set(following), 'Power candidate changed full-store inventory')
    if not initial_only: require(previous['board.json'] == following['board.json'], 'Preserving update changed accepted board')
    source_version = parse(previous['cohort.json'])['version']
    require(source_version in ('1.0.7', '1.0.10'), 'Unqualified power source version')
    old_boot, new_boot = document(previous['boot.json']), document(following['boot.json'])
    require(new_boot == (upgrade_boot(old_boot) if source_version == '1.0.7' else old_boot), 'Power candidate changed accepted plus RF boot authority')
    for name in APPS:
        old, new = document(previous[name + '.json']), document(following[name + '.json'])
        expected = authority(old)
        if name == 'waterfall' and source_version == '1.0.7': expected['requires'] |= {(g['capability'], g['api']) for g in PRIVATE_GRANTS}
        require(authority(new) == expected and new['version'] == configuration['app_versions'][name],
                'Power candidate changed app authority/version: ' + name)
    for row in old_boot['drivers']:
        name = row['manifest']
        require(authority(document(previous[name])) == authority(document(following[name])),
                'Power candidate changed provider authority: ' + name)
    for folder, version in POWER_DRIVERS.items():
        require(document(following[folder + '/manifest.json'])['version'] == version,
                'Power candidate lost repaired driver: ' + folder)
        old_version = document(previous[folder + '/manifest.json'])['version']
        if old_version == version:
            require(previous[folder + '/driver.elf'] == following[folder + '/driver.elf'], 'Changed power driver needs a version increment: ' + folder)
        else:
            require(previous[folder + '/driver.elf'] != following[folder + '/driver.elf'], 'Power driver was not rebuilt: ' + folder)
    return {'accepted_boot_sha256': sha(previous['boot.json']), 'candidate_boot_sha256': sha(following['boot.json']),
            'prior_app_count': len(APPS), 'provider_bindings_preserved': True,
            'all_prior_persistent_owners_preserved': True, 'new_private_grants': PRIVATE_GRANTS if source_version == '1.0.7' else [],
            'shared_migration_added': False, 'board_bytes_preserved': following['board.json'] == previous['board.json'],
            'power_driver_versions': POWER_DRIVERS}


def compose(origin, native, files, apps, head, root=ROOT, *, initial_only=False):
    configuration = config(root, profile=PROFILE)
    require(apps['configuration'] == configuration and apps['watch_source'] == head, 'Power artifact source/profile differs')
    for key in ('baseline_boot', 'baseline_board', 'baseline_sha256', 'catalog'):
        require(apps[key] == origin['apps'][key], 'Power candidate changed accepted baseline: ' + key)
    board = configure_board(apps['baseline_board'], root, motion_model=apps['motion_model'], radio_model=apps['radio_model'])
    require(apps['board'] == board and document(files['board.json']) == board, 'Power board proof differs')
    if not initial_only: require(apps['motion_model'] == 'bma423' and apps['radio_model'] == 'selectable',
                                 'Preserving power update has only an accepted BMA423/selectable origin')
    if origin['identity']['version'] == '1.0.7':
        require(native['blobs']['firmware.bin'] != origin['full'][0x10000:0x10000 + len(native['blobs']['firmware.bin'])],
                'Accepted 1.0.7 requires the verified replacement Runtime')
    else:
        old_runtime = tuple(map(int, origin['identity']['runtime_version'].split('.')))
        target_runtime = tuple(map(int, native['record']['firmware_version'].split('.')))
        require(target_runtime >= old_runtime, 'Cutoff may not downgrade the delivered Runtime')
        if target_runtime == old_runtime:
            require(native['blobs']['firmware.bin'] == origin['full'][0x10000:0x10000 + len(native['blobs']['firmware.bin'])],
                    'Changed Runtime bytes require a version increment')
    following = {**origin['store'], **files, 'boot.json': encoded(apps['boot'])}
    identity = create(VERSION, RUNTIME_VERSION, head, native['blobs']['firmware.bin'])
    following['cohort.json'] = encode(identity)
    policy = check_policy(origin['store'], following, configuration, initial_only=initial_only)
    return following, identity, policy


def paired_payload(identity, firmware, bootfs, motion_model):
    require(motion_model == 'bma423', 'Power paired payload requires accepted BMA423 origin')
    verify_identity(identity, firmware, version=VERSION, runtime_version=RUNTIME_VERSION)
    return package(identity, firmware, bootfs)


def initial_image(native, bootfs, runtime, motion_model):
    require(motion_model in ('bma423', 'bma456h'), 'Unknown initial power motion model')
    store = read_image(bootfs, STORE_BYTES)
    verify_identity(parse(store['cohort.json']), native['blobs']['firmware.bin'], version=VERSION, runtime_version=RUNTIME_VERSION)
    bank = module('power_initial_bank_images', Path(runtime) / 'scripts/paired_bank_images.py')
    components = {n: native['blobs'][n] for n in ('bootloader.bin', 'partitions.bin', 'firmware.bin', 'appdata.bin')}
    components.update({'bootfs.bin': bootfs, 'otadata.bin': bank.initial_otadata(),
                       'bank_state.bin': bank.initial_bank_state(native['blobs']['firmware.bin'], bootfs, app_data=True)})
    image, parts = assemble(components, native['requirements']['deployment'], True)
    require(read_image(image[0x2f0000:0x800000], STORE_BYTES) == store, 'Initial power store round trip differs')
    return 'twatch-s3-' + VERSION + '-FULL-INITIAL-ERASES-DATA-' + motion_model + '.bin', image, parts

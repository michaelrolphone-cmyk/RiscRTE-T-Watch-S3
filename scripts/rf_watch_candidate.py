#!/usr/bin/env python3
"""Exact accepted native/store custody and isolated Watch RF packaging policy."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

from current_apps_overlay import APPS, ROOT, config, configure_board, encoded, metadata, require
from current_cohort import create, encode, package, parse, verify as verify_identity
from current_flash_layout import assemble
from publish_complete_watch import CUSTODY_HASHES, IMAGE_SHA, verify_accepted
from read_only_spiffs import read_image
from rf_spectrum_profile import PRIVATE_GRANTS, PROFILE, RUNTIME_SOURCE, VERSION, runtime_requirements, upgrade_boot

RUNTIME_VERSION = '0.1.41'
STORE_BYTES = 0x510000
SOURCE_VERSION = '1.0.7'
FIRMWARE_OFFSETS = (0x10000, 0x800000)
STORE_OFFSETS = (0x2f0000, 0xae0000)
FIRMWARE_BYTES = 0x260000


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def document(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def checked_source(root, expected=None):
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    require(expected is None or head == expected, 'Wrong source revision: ' + str(root))
    require(not subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain',
                                         '--untracked-files=no'], text=True).strip(),
            'Dirty source: ' + str(root))
    return head


def accepted(root=ROOT):
    root = Path(root)
    inputs = root / 'release/complete-1.0.7'
    full = gzip.decompress((inputs / 'accepted.bin.gz').read_bytes())
    evidence = (inputs / 'accepted-app-evidence.zip').read_bytes()
    custody = {name: (root / 'docs/consolidated-test-1.0.7-sdr-cursor' / name).read_bytes()
               for name in CUSTODY_HASHES}
    store, _, acceptance, build, _, _ = verify_accepted(full, evidence, custody)
    require(document((inputs / 'acceptance.json').read_bytes()) == acceptance,
            'Accepted release/source custody records disagree')
    return {'full': full, 'store': store, 'identity': parse(store['cohort.json']),
            'acceptance': acceptance, 'apps': build,
            'evidence_sha256': sha(evidence)}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def read_native(native_dir, runtime, root=ROOT):
    """Verify fixed accepted bytes and re-run their source's post-link proofs."""
    native_dir, runtime, root = Path(native_dir), Path(runtime), Path(root)
    checked_source(runtime, RUNTIME_SOURCE)
    custody = document((root / 'apps/rf-spectrum-native-custody.json').read_bytes())
    require(custody['schema'] == 1 and custody['source_sha'] == RUNTIME_SOURCE
            and custody['firmware_version'] == RUNTIME_VERSION
            and custody['target'] == 'esp32s3-16mb-appdata-iq', 'Wrong accepted native custody identity')
    raw = (native_dir / 'candidate.json').read_bytes()
    require(sha(raw) == custody['candidate_sha256'], 'Accepted native candidate record differs')
    record = document(raw)
    require(record['source_sha'] == RUNTIME_SOURCE and record['firmware_version'] == RUNTIME_VERSION,
            'Accepted native source/version differs')
    expected = set(custody['assets']) | {'candidate.json', 'SHA256SUMS'}
    require({p.name for p in native_dir.iterdir()} == expected, 'Accepted native asset inventory differs')
    blobs = {}
    for name, item in custody['assets'].items():
        require(PurePosixPath(name).name == name and name not in ('', '.', '..'), 'Unsafe native member')
        path = native_dir / name
        require(path.is_file() and not path.is_symlink(), 'Invalid native file: ' + name)
        blobs[name] = path.read_bytes()
        require(metadata(blobs[name]) == item and record['assets'][name] ==
                {'bytes': item['size_bytes'], 'sha256': item['sha256']}, 'Accepted native bytes differ: ' + name)
    checksums = ''.join(sha(p.read_bytes()) + '  ' + p.name + '\n'
                        for p in sorted(native_dir.iterdir()) if p.name != 'SHA256SUMS')
    require((native_dir / 'SHA256SUMS').read_text() == checksums, 'Accepted native checksums differ')
    validator = r'''
import hashlib,json,sys
from pathlib import Path
runtime,native=map(Path,sys.argv[1:])
sys.path.insert(0,str(runtime/'scripts'))
from paired_candidate import partitions,APP_DATA_EXPECTED,native_proof
from release_assets import esp_image,elf
from radio_iq_proof import prove
from app_data_image import verify_initial
record=json.loads((native/'candidate.json').read_text())
blobs={n:(native/n).read_bytes() for n in ('firmware.bin','firmware.elf','bootloader.bin','partitions.bin')}
for n in ('firmware.bin','bootloader.bin'):
    esp_image(blobs[n])
    if blobs[n][3]>>4!=4: raise ValueError('Native 16MiB flag differs')
elf(blobs['firmware.elf'])
if json.loads(json.dumps(partitions(blobs['partitions.bin'],APP_DATA_EXPECTED)))!=record['partitions']:
    raise ValueError('Native partition proof differs')
for marker in ('RTE_SOURCE='+record['source_sha'],'RISC_RUNTIME_VERSION:'+record['firmware_version'],'RISC_PAIRED_STORE_ABI:2'):
    if not all(marker.encode()+b'\0' in blobs[n] for n in ('firmware.bin','firmware.elf')):
        raise ValueError('Compiled native identity differs')
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
    requirements = runtime_requirements(root)
    for key in ('target', 'layout', 'store_abi', 'flash_bytes'):
        require(requirements['deployment'][key] == record[key], 'Native deployment mismatch: ' + key)
    require(requirements['deployment']['partitions'] == {
        name: {'offset': values[2], 'size': values[3]} for name, values in record['partitions'].items() if name != 'nvs'},
        'Native partition requirements differ')
    return {'record': record, 'blobs': blobs, 'custody': custody, 'requirements': requirements}


def bind_native_to_accepted(origin, native, runtime):
    image = origin['full']
    for component in origin['acceptance']['components']:
        name = PurePosixPath(component['file']).name
        if name not in native['blobs']:
            continue
        raw = native['blobs'][name]
        start = int(component['offset'], 16)
        require(raw == image[start:start + component['size_bytes']], 'Native input differs from accepted image: ' + name)
    verify_identity(origin['identity'], native['blobs']['firmware.bin'], version=SOURCE_VERSION,
                    runtime_version=RUNTIME_VERSION, source_revision=origin['acceptance']['watch_source'])
    bank = module('rf_accepted_bank_images', Path(runtime) / 'scripts/paired_bank_images.py')
    require(image[0xff2000:0xff4000] == bank.initial_bank_state(
        native['blobs']['firmware.bin'], image[0x2f0000:0x800000], app_data=True),
        'Accepted bank journal differs from native/store pair')


def authority(manifest):
    result = {key: value for key, value in manifest.items()
              if key not in ('version', 'description', 'display_name', 'status', 'physical_verification')}
    if 'requires' in result:
        rows = result['requires']
        require(all(set(r) == {'capability', 'api'} for r in rows), 'Unexpected manifest requirement fields')
        result['requires'] = {(r['capability'], r['api']) for r in rows}
        require(len(result['requires']) == len(rows), 'Duplicate manifest requirements')
    return result


def check_policy(previous, following, configuration, *, initial_only=False):
    require(set(following) == set(previous), 'RF store inventory changed')
    if not initial_only:
        require(following['board.json'] == previous['board.json'], 'Preserving RF OTA requires accepted bma423 board bytes')
    old_boot, new_boot = document(previous['boot.json']), document(following['boot.json'])
    require(new_boot == upgrade_boot(old_boot), 'RF boot authority differs from accepted plus private namespaces')
    for name in APPS:
        old = document(previous[name + '.json'])
        new = document(following[name + '.json'])
        expected = authority(old)
        if name == 'waterfall':
            expected['requires'] |= {(g['capability'], g['api']) for g in PRIVATE_GRANTS}
        require(authority(new) == expected, 'RF app identity/authority changed: ' + name)
        require(new['version'] == configuration['app_versions'][name], 'RF deployment version differs: ' + name)
    for row in old_boot['drivers']:
        name = row['manifest']
        require(authority(document(previous[name])) == authority(document(following[name])),
                'RF provider identity/authority changed: ' + name)
    return {'accepted_boot_sha256': sha(previous['boot.json']), 'candidate_boot_sha256': sha(following['boot.json']),
            'prior_app_count': len(APPS), 'provider_bindings_preserved': True,
            'all_prior_persistent_owners_preserved': True, 'new_private_grants': PRIVATE_GRANTS,
            'shared_migration_added': False, 'board_bytes_preserved': following['board.json'] == previous['board.json']}


def compose(origin, native, files, apps, head, root=ROOT, *, initial_only=False):
    configuration = config(root, profile=PROFILE)
    require(apps['configuration'] == configuration and apps['watch_source'] == head,
            'RF app artifact source/profile differs')
    for key in ('baseline_boot', 'baseline_board', 'baseline_sha256', 'catalog'):
        require(apps[key] == origin['apps'][key], 'RF app artifact changed accepted baseline: ' + key)
    board = configure_board(apps['baseline_board'], root, motion_model=apps['motion_model'], radio_model=apps['radio_model'])
    require(apps['board'] == board and document(files['board.json']) == board, 'RF configured board proof differs')
    if not initial_only:
        require(apps['motion_model'] == 'bma423' and apps['radio_model'] == 'selectable',
                'Preserving RF OTA has only an accepted bma423/selectable origin')
    following = {**origin['store'], **files, 'boot.json': encoded(apps['boot'])}
    identity = create(VERSION, RUNTIME_VERSION, head, native['blobs']['firmware.bin'])
    following['cohort.json'] = encode(identity)
    policy = check_policy(origin['store'], following, configuration, initial_only=initial_only)
    return following, identity, policy


def paired_payload(identity, firmware, bootfs, motion_model):
    require(motion_model == 'bma423', 'RF paired payload requires accepted bma423 origin')
    verify_identity(identity, firmware, version=VERSION, runtime_version=RUNTIME_VERSION)
    # The accepted installed catalog parser requires this canonical asset/URL.
    # Installation instructions carry the explicit data-preservation label.
    return package(identity, firmware, bootfs)


def initial_image(native, bootfs, runtime, motion_model):
    require(motion_model in ('bma423', 'bma456h'), 'Unknown initial RF motion model')
    store = read_image(bootfs, STORE_BYTES)
    verify_identity(parse(store['cohort.json']), native['blobs']['firmware.bin'],
                    version=VERSION, runtime_version=RUNTIME_VERSION)
    bank = module('rf_initial_bank_images', Path(runtime) / 'scripts/paired_bank_images.py')
    components = {name: native['blobs'][name] for name in ('bootloader.bin', 'partitions.bin', 'firmware.bin', 'appdata.bin')}
    components.update({'bootfs.bin': bootfs, 'otadata.bin': bank.initial_otadata(),
                       'bank_state.bin': bank.initial_bank_state(native['blobs']['firmware.bin'], bootfs, app_data=True)})
    image, parts = assemble(components, native['requirements']['deployment'], True)
    require(read_image(image[0x2f0000:0x800000], STORE_BYTES) == store,
            'Initial RF store round trip differs')
    return 'twatch-s3-1.0.8-FULL-INITIAL-ERASES-DATA-' + motion_model + '.bin', image, parts

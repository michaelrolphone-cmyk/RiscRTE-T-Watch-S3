#!/usr/bin/env python3
"""Compose the qualified shared Watch components on exact 1.1.21-r1 custody.

This staging command emits no firmware or bank record. Final composition must
bind the ABI3 native image, cohort and paired-bank records before delivery.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import types

from stage_watch_shared_recovery import load_home, stage_pair, compact_metadata, document
from read_only_spiffs import read_image
from compact_current_elf import compact, evidence

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA = '4e43fc376021779a2d7a5cada96aee255735d5db1eb0e896c5aacf65bb3889bc'
BASELINE_SELECTION_SHA = '862cb81d8f3d8bfe810274f3f803f30346970818e8c0e114f53771fd5527a503'
# SHA-256 of encode(inventory): all 119 qualified output paths, sizes and hashes.
# This binds metadata as well as payloads, without importing a mutable receipt.
TARGET_INVENTORY_SHA = '59b9a88268bf13696fdb9a1ac00f7da4aaaf770c84af1bb4631523cd1a608cfd'
PHYSICAL_BLOCKS = 1360  # Explicit ABI3 0x550000-byte store / 4096.
MINIMUM_FREE_BLOCKS = 2
AUTHORITY_CAPACITY = 32
GENERIC_CAPABILITIES = ('power.sleep', 'input.power-key', 'display.power')
REPLACED = {'default.elf', 'settings.elf', 'springboard.elf', 'contexts.elf', 'ui-scene/driver.elf'}
ADAPTERS = {
    'power_sleep': ('power-sleep', 2496, '2930cf26f1d7f234b9f77eb24f418a03a084ca4fb3f5b75012e6a1b02f8ac09f'),
    'power_key': ('powerkey', 2400, 'c554afa6be5ffea40ec540bf3f7a6cd7ff55a908ae2f278b026b8117196d0e15'),
    'display_power': ('display-power', 2440, 'dbebe25d7e3817048daa63a07b5658e1059353de6ea0f78338ff389d4e648028'),
}
ADAPTER_MANIFESTS = {
    'power_sleep': (236, '03b51f515bb72efb701976aa81de78f69bd590761d3671f41877cebfa5105e30'),
    'power_key': (238, 'e7278f18a506c29e94936358fac18cf2b3710ad008aed09a96eb8290257bc6b2'),
    'display_power': (241, '6d9fe86bdd8da3a6c20d798a06e875a1c392fce7c32ed176d69d436961032fcb'),
}
UI = {
    'settings': (225256, '4ee26705175a325f62af18e6dc98edc9e28aa51b9bf239bc946d8908cbce1385', 139760, '0866d709f94e29e1f3979e41d7822b7878b2e9860e0115ef826df09a81451634'),
    'springboard': (228136, 'f33ff27719ffd1faa1fb5f671579ada881aac29c9bd4c4673779798064470b17', 146812, '68b7a818a9c3ade67c7ec6c0621d3e30bed22e4ec8e1615615779172d5983f49'),
}

def require(value, message):
    if not value:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()

def checked(path, size, digest):
    raw = Path(path).read_bytes()
    require(len(raw) == size and sha(raw) == digest, 'Artifact custody mismatch: ' + str(path))
    return raw

def git_blob(repo, revision, path):
    return subprocess.check_output(['git', '-C', str(repo), 'show', revision + ':' + path],
                                   env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'})

def exact_baseline(path):
    raw = checked(path, 0x1000000, BASELINE_SHA)
    old = read_image(raw[0x2f0000:0x800000], 0x510000)
    selected = (ROOT / 'docs/watch-recovery/selection.json').read_bytes()
    require(sha(selected) == BASELINE_SELECTION_SHA, 'Recovery selection changed')
    selection = document(selected)
    require(len(old) == 113 and sum(n.endswith('.elf') for n in old) == 55, 'Incomplete recovered store')
    require(set(old) == set(selection['files']), 'Recovered store membership differs')
    for name, item in selection['files'].items():
        require(name in old and len(old[name]) == item['bytes'] and sha(old[name]) == item['sha256'],
                'Recovered file mismatch: ' + name)
    return old


def load_adapter(root, role):
    directory, size, digest = ADAPTERS[role]
    elf = checked(root / role / 'driver.elf', size, digest)
    raw = checked(root / role / 'manifest.json', *ADAPTER_MANIFESTS[role])
    manifest = document(raw)
    require(manifest['architecture'] == 'xtensa-esp32s3' and manifest['driver_abi'] == 2 and
            manifest['version'] == '0.1.0' and manifest['file_name'] == 'driver.elf',
            'Generic provider metadata differs')
    # Canonicalize only after raw custody succeeds; preserve qualified output hashes.
    return {directory + '/driver.elf': elf, directory + '/manifest.json': encode(manifest)}


def inventory(store):
    return {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(store.items())}


def capacity(store):
    """Count pinned SPIFFS allocations without emitting an image or bank record.

    Each object has a header index page with 103 references, then index pages
    with 124 references. Data pages hold 251 bytes; blocks hold 15 usable pages.
    Empty objects still allocate their header index page.
    """
    pages = 0
    for raw in store.values():
        require(isinstance(raw, bytes), 'Store members must be exact bytes')
        data_pages = (len(raw) + 250) // 251
        pages += data_pages + 1 + (max(0, data_pages - 103) + 123) // 124
    occupied = (pages + 14) // 15
    free = PHYSICAL_BLOCKS - occupied
    require(free >= MINIMUM_FREE_BLOCKS, 'Expanded store lacks free-block reserve')
    return pages, occupied, free


def verify_store(old, store):
    """Fail closed on the complete selected composition before any output write."""
    additions = {directory + '/' + name for directory, _, _ in ADAPTERS.values()
                 for name in ('driver.elf', 'manifest.json')}
    require(set(store) == set(old) | additions, 'Complete store membership differs')
    require(len(store) == 119 and sum(n.endswith('.elf') for n in store) == 58,
            'Complete store membership differs')
    require(store['cohort.json'] == old['cohort.json'], 'Unsealed cohort changed')
    for name in old:
        if name.endswith('.elf') and name not in REPLACED:
            require(store[name] == old[name], 'Retained app/provider changed: ' + name)

    before, boot = document(old['boot.json']), document(store['boot.json'])
    original_apps = [r['manifest'] for r in before['app_capabilities']]
    manifests = [r['manifest'] for r in boot['app_capabilities']]
    require(len(manifests) == len(set(manifests)) == 25 and manifests == original_apps,
            'Retained application membership differs')
    expected = copy.deepcopy(before)
    expected['drivers'] += [{'manifest': directory + '/manifest.json'}
                            for directory, _, _ in ADAPTERS.values()]
    require(len(boot['drivers']) == 34 and boot['drivers'] == expected['drivers'],
            'Retained provider membership or policy differs')
    expected_rows = {r['manifest']: r for r in expected['app_capabilities']}
    expected_rows['clock.json']['grants'] = []
    for name in ('default.json', 'settings.json', 'springboard.json'):
        expected_rows[name]['grants'] += [{'capability': cap, 'api': 1, 'instance_id': 0}
                                          for cap in GENERIC_CAPABILITIES]
    for name in ('settings.json', 'springboard.json', 'contexts.json'):
        expected_rows[name]['grants'].append({'capability': 'app.catalog', 'api': 1, 'instance_id': 0})

    ids, elfs = set(), set()
    for row in boot['app_capabilities']:
        name = row['manifest']
        manifest = document(store[name])
        requests = manifest['requires'] + manifest.get('optional', [])
        require(len(requests) <= AUTHORITY_CAPACITY and len(row['grants']) <= AUTHORITY_CAPACITY,
                'Native authority row capacity exceeded: ' + name)
        requested = [(r['capability'], r['api']) for r in requests]
        grants = [(g['capability'], g['api'], g['instance_id']) for g in row['grants']]
        require(len(requested) == len(set(requested)) and len(grants) == len(set(grants)),
                'Duplicate application authority: ' + name)
        require(manifest['type'] == 'application' and manifest['id'] not in ids and
                manifest['file_name'] in store and manifest['file_name'] not in elfs,
                'Application identity or payload differs: ' + name)
        ids.add(manifest['id'])
        elfs.add(manifest['file_name'])
    require(boot == expected, 'Unrelated boot authority or metadata changed')
    contexts = document(store['contexts.json'])
    require(contexts['optional'] == [{'capability': 'app.catalog', 'api': 1}] and
            not any(r['capability'] == 'app.catalog' for r in contexts['requires']),
            'Contexts catalog must remain optional')
    result = capacity(store)
    require(sha(encode(inventory(store))) == TARGET_INVENTORY_SHA,
            'Qualified component or metadata inventory differs')
    return result


def compose(args):
    old = exact_baseline(args.baseline_bin)
    stager, apps, home_record = load_home(args.shared_watch, args.home_build)
    store, _, home_compactions = stage_pair(old, apps, stager, compact_unsigned=True)
    boot = document(store['boot.json'])
    for role, (directory, size, digest) in ADAPTERS.items():
        adapter = load_adapter(args.generic_components, role)
        require(not set(adapter) & set(store), 'Generic provider already exists')
        store.update(adapter)
        boot['drivers'].append({'manifest': directory + '/manifest.json'})
    rows = {row['manifest']: row for row in boot['app_capabilities']}
    compaction = {}
    with tempfile.TemporaryDirectory(prefix='shared-watch-ui-') as td:
        for app, (raw_size, raw_sha, compact_size, compact_sha) in UI.items():
            original = checked(args.ui_build / (app + '.elf'), raw_size, raw_sha)
            temporary = Path(td) / (app + '.elf')
            temporary.write_bytes(original)
            compaction[app] = compact(temporary, args.compiler)
            candidate = checked(temporary, compact_size, compact_sha)
            require(evidence(original) == evidence(candidate), 'UI loader semantics changed')
            store[app + '.elf'] = candidate
            manifest = document(store[app + '.json'])
            for cap in GENERIC_CAPABILITIES:
                req = {'capability': cap, 'api': 1}
                grant = {**req, 'instance_id': 0}
                require(req not in manifest['requires'] and grant not in rows[app + '.json']['grants'], 'Duplicate generic authority')
                manifest['requires'].append(req)
                rows[app + '.json']['grants'].append(grant)
            store[app + '.json'] = encode(manifest)
    store['boot.json'] = encode(boot)

    helper_path = args.shared_watch / 'scripts/stage_app_catalog_metadata.py'
    helper_source = helper_path.read_bytes()
    require(helper_source == git_blob(args.shared_watch, '362537417c4f37bbb240879d5ba756686511fec1',
                                     'scripts/stage_app_catalog_metadata.py'), 'Metadata helper differs')
    helper = types.ModuleType('qualified_catalog_metadata')
    exec(compile(helper_source, str(helper_path), 'exec'), helper.__dict__)
    fixture_path = 'test/native_apps/fixtures/watch_springboard_catalog_23.c'
    fixture = git_blob(args.system_ui, '72f435fcee376ec62d17ece6180753385ea547d9', fixture_path).decode()
    labels = re.findall(r'\.display_name="([^"]+)",\.file_name="([^"]+)",\.icon="([^"]+)"', fixture)
    require(len(labels) == len({elf for _, elf, _ in labels}) == 23, 'Incomplete retained launcher presentation')
    by_elf = {document(store[r['manifest']])['file_name']: r['manifest'] for r in boot['app_capabilities']}
    require(len(by_elf) == 25 and {elf for _, elf, _ in labels} == set(by_elf) - {'default.elf', 'springboard.elf'},
            'Retained launcher membership differs')
    entries = [{'manifest': by_elf[elf], 'id': document(store[by_elf[elf]])['id'],
                'display_name': name, 'icon': icon} for name, elf, icon in labels]
    entries += [{'manifest': name, 'id': document(store[name])['id'], 'launcher_visible': False}
                for name in ('default.json', 'springboard.json')]
    store, metadata_record = helper.stage(store, {'schema': 1, 'entries': entries,
                                                'consumers': ['settings.json', 'springboard.json']},
                                          requirement_capacity=AUTHORITY_CAPACITY, grant_capacity=AUTHORITY_CAPACITY)
    # Standalone Contexts declares catalog optionally; never convert it to a
    # mandatory capability or duplicate optional and required declarations.
    store['contexts.elf'] = checked(args.contexts_build / 'contexts.elf', 88020,
        '8db9d4be5801635bdb58e3f5ddaa41bcbdb744243a0e875a4a8252496cd24402')
    manifest = document(store['contexts.json'])
    require(manifest['version'] == '0.4.4' and 'optional' not in manifest, 'Unexpected Contexts predecessor')
    manifest['version'] = '0.4.5'
    manifest['optional'] = [{'capability': 'app.catalog', 'api': 1}]
    store['contexts.json'] = encode(manifest)
    boot = document(store['boot.json'])
    context_policy = next(r for r in boot['app_capabilities'] if r['manifest'] == 'contexts.json')
    context_policy['grants'].append({'capability': 'app.catalog', 'api': 1, 'instance_id': 0})
    store['boot.json'] = encode(boot)
    store['ui-scene/driver.elf'] = checked(args.scene_component, 310220,
        '017039a424e0482cf35c062a5b883af621bda0457e8bb9ff321fe63640e54fa1')
    require(sha(store['text-input/driver.elf']) == 'c3cbb95ceee72fe4374b2ba4382d13bf6907b2956496218a80819bb6f85aad35',
            'Repaired text provider changed')
    require(document(store['ui-scene/manifest.json'])['version'] == '0.4.6', 'Wrong scene API metadata')
    store, compacted_metadata = compact_metadata(store)
    pages, occupied, free = verify_store(old, store)
    record = {'schema': 1, 'status': 'unsealed component staging only', 'version': '1.1.22',
              'baseline_sha256': BASELINE_SHA, 'files': len(store), 'elfs': 58, 'apps': 25, 'providers': 34,
              'all_existing_files_preserved': True, 'unchanged_recovered_elfs': 50,
              'replaced_elfs': sorted(REPLACED), 'ui_compaction': compaction,
              'catalog_provisioning': metadata_record, 'metadata_compactions': sorted(set(home_compactions + compacted_metadata)),
              'live_pages': pages, 'occupied_blocks': occupied, 'free_blocks': free,
              'native_cohort_admitted': False, 'flashable': False,
              'factory_warning': 'Full factory BIN erases current settings; appdata capacity remains 512 KiB.',
              'inventory': inventory(store)}
    return store, record

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-bin', 'shared-watch', 'home-build', 'ui-build', 'generic-components',
                 'contexts-build', 'scene-component', 'system-ui', 'compiler', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    require(not args.output.exists(), 'Choose a fresh staging output')
    store, record = compose(args)
    args.output.mkdir(parents=True)
    for name, raw in store.items():
        target = args.output / 'UNSEALED-STORE' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (args.output / 'staging.json').write_bytes(encode(record))
    print(json.dumps({k: record[k] for k in ('files', 'elfs', 'apps', 'providers', 'occupied_blocks', 'free_blocks', 'flashable')}))

if __name__ == '__main__':
    main()

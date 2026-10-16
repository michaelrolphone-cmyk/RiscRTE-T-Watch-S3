#!/usr/bin/env python3
"""Verify and stage a shared Home overlay on recovered Watch 1.1.21-r1.

This command NEVER builds or emits firmware, a filesystem image or a bank record.
Its overlay remains deliberately unsealed pending complete provider/native and
capacity admission. Exact native, appdata and unrelated payloads stay untouched.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import types

from current_bootfs import CONFIG, GENERATOR, GENERATOR_SHA, IMAGE_SIZE
from read_only_spiffs import read_image
from verify_watch_recovery import audit, SELECTION as RECOVERY
from watch_factory_appdata import require, sha

ROOT = Path(__file__).resolve().parents[1]
SELECTION = json.loads((ROOT / 'docs/shared-home-recovery/selection.json').read_bytes())
HOME_PATHS = {'boot.json', 'default.elf', 'default.json', 'clock.elf', 'clock.json'}
SIGNED_KEYS = {'signature', 'signatures', 'signed', 'signed_payload', 'signed_metadata',
               'certificate', 'certificates', 'jws', 'jwt', 'hmac', 'mac'}


def document(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'Duplicate JSON key: ' + key)
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Invalid JSON constant: ' + v)))


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def signed(value):
    if isinstance(value, dict):
        return bool(SIGNED_KEYS.intersection(k.lower() for k in value)) or any(signed(v) for v in value.values())
    return isinstance(value, list) and any(signed(v) for v in value)


def compact_metadata(store):
    """Explicit optional whitespace-only change; never rewrites cohort/signatures."""
    out, changed = dict(store), []
    for name, raw in store.items():
        if not name.endswith('.json') or name == 'cohort.json':
            continue
        value = document(raw)
        if signed(value):
            continue
        compact = encoded(value)
        require(document(compact) == value, 'Metadata semantics changed: ' + name)
        if len(compact) < len(raw):
            out[name] = compact
            changed.append(name)
    return out, sorted(changed)


def source_blob(repository, commit, path):
    return subprocess.check_output(['git', '-C', str(repository), 'show', commit + ':' + path])


def verify_record(record):
    home = SELECTION['home']
    require(record['build_variant'] == 'shared-no-board-defines', 'Board-specific Home build')
    for dependency in ['system', 'utilities']:
        expected = home[dependency + '_source']
        require(record['dependency_lock'][dependency]['commit'] == expected and
                record['verified_dependencies'][dependency]['commit'] == expected,
                'Wrong shared Home dependency: ' + dependency)
    for role in ['default', 'clock']:
        item = record['artifacts'][role]
        require(all(item[k] == home[role][k] for k in ['bytes', 'sha256', 'defines']),
                'Shared Home pair, fonts or feature flags differ: ' + role)
        require(item['compaction']['retained_loader_sections_symbols_relocations_unchanged'],
                'Loader sections were changed')
    require(record['artifacts']['clock']['role'] == 'return-to-default' and
            record['artifacts']['clock']['imports'] == [], 'Return module gained services')


def load_home(repository, build):
    """Use exact committed shared stager, even if a later branch is checked out."""
    selected = SELECTION['home']
    raw = (build / 'build.json').read_bytes()
    require(sha(raw) == selected['build_receipt_sha256'], 'Wrong exact shared build receipt')
    record = document(raw)
    verify_record(record)
    for name, digest in record['home_files_sha256'].items():
        require(sha(source_blob(repository, selected['source'], name)) == digest,
                'Shared source receipt mismatch: ' + name)
    for role in ['default', 'clock']:
        require((build / (role + '.json')).read_bytes() == source_blob(
            repository, selected['source'], 'apps/clock/' + role + '.json'), 'Shared manifest changed')
    stager_source = source_blob(repository, selected['source'], 'scripts/stage_product.py')
    require(sha(stager_source) == selected['stager_sha256'], 'Wrong shared stager')
    module = types.ModuleType('pinned_watch_stage_product')
    exec(compile(stager_source, '<pinned-shared-stage-product>', 'exec'), module.__dict__)
    apps, loaded_record = module.app_bundle(build)
    require(record == loaded_record, 'Shared build changed while reading')
    for role in ['default', 'clock']:
        require(len(apps[role + '.elf']) == selected[role]['bytes'] and
                sha(apps[role + '.elf']) == selected[role]['sha256'], 'Exact shared pair differs')
    return module, apps, record


def verify_preservation(old, new, compacted=()):
    require(set(old) == set(new), 'Store files added or removed without provider selection')
    require(set(compacted) <= set(old), 'Unknown compacted metadata')
    for name in old:
        if name in HOME_PATHS:
            continue
        if name in compacted:
            require(name.endswith('.json') and name != 'cohort.json' and
                    not signed(document(old[name])) and document(old[name]) == document(new[name]),
                    'Unauthorized metadata change: ' + name)
        else:
            require(old[name] == new[name], 'Unrelated bytes changed: ' + name)
    before, after = document(old['boot.json']), document(new['boot.json'])
    expected = copy.deepcopy(before)
    rows = {r['manifest']: r for r in expected['app_capabilities']}
    for grant in SELECTION['generic_services']:
        require(grant not in rows['default.json']['grants'], 'Generic grant already selected')
        rows['default.json']['grants'].append(grant)
    rows['clock.json']['grants'] = []
    require(after == expected, 'Unrelated authority or provider selection changed')
    for role in ['default', 'clock']:
        prior, current = document(old[role + '.json']), document(new[role + '.json'])
        require({k: v for k, v in prior.items() if k not in ['version', 'requires']} ==
                {k: v for k, v in current.items() if k not in ['version', 'requires']},
                'Application identity or other metadata changed')
    require(old['clock.elf'] == new['clock.elf'], 'Existing return ELF changed')


def stage_pair(old, apps, stager, compact_unsigned=False):
    # Stage missing generic grants explicitly. The output is only an unsealed
    # source checkpoint: no fake provider implementation or permissive fallback.
    for role in ['default', 'clock']:
        selected = SELECTION['home'][role]
        require(len(apps[role + '.elf']) == selected['bytes'] and
                sha(apps[role + '.elf']) == selected['sha256'], 'Exact shared pair differs')
        require(document(apps[role + '.json'])['version'] == '0.15.0', 'Wrong shared manifest version')
    proposed = dict(old)
    boot = document(old['boot.json'])
    home = next(r for r in boot['app_capabilities'] if r['manifest'] == 'default.json')
    for grant in SELECTION['generic_services']:
        require(grant not in home['grants'], 'Unexpected predecessor generic grant')
        home['grants'].append(dict(grant))
    proposed['boot.json'] = encoded(boot)
    board = document(old[boot['board']])
    out, staging = stager.stage(proposed, apps, {}, {
        'schema': 1, 'name': 'twatch-recovered-unsealed-home',
        'board_id': board['board_id'], 'services': []}, provider_capacity=32)
    # Avoid pretty-print inflation from the shared generic stager; semantics are
    # checked against its output before any optional unrelated JSON compaction.
    for name in ['boot.json', 'default.json', 'clock.json']:
        parsed = document(out[name])
        out[name] = encoded(parsed)
        require(document(out[name]) == parsed, 'Selected metadata semantics differ')
    compacted = []
    if compact_unsigned:
        out, compacted = compact_metadata(out)
    verify_preservation(old, out, compacted)
    required = {(r['capability'], r['api']) for r in document(apps['default.json'])['requires']}
    declared = {(r['capability'], r['api']) for r in document(out['default.json'])['requires']}
    require(required <= declared, 'Shared Home requests were not declared')
    return out, staging, compacted


def capacity(store):
    """Count exact pinned-generator allocations; never create a filesystem image.

    A bounded analytical scratch geometry allows counting overflow. The result
    is ALWAYS judged against the unchanged physical geometry and reserve. This
    function cannot authorize or generate a larger partition.
    """
    require(sha(GENERATOR.read_bytes()) == GENERATOR_SHA, 'SPIFFS generator changed')
    spec = importlib.util.spec_from_file_location('count_spiffs', GENERATOR)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    physical_blocks = IMAGE_SIZE // CONFIG['block_size']
    fs = generator.SpiffsFS(IMAGE_SIZE + 64 * CONFIG['block_size'], generator.SpiffsBuildConfig(**CONFIG))
    with tempfile.TemporaryDirectory(prefix='watch-shared-count-') as temporary:
        path = Path(temporary) / 'member'
        for name, raw in sorted(store.items()):
            path.write_bytes(raw)
            fs.create_file('/' + name, str(path))
    occupied = len(fs.blocks)
    free = physical_blocks - occupied
    return dict(physical_bytes=IMAGE_SIZE, physical_blocks=physical_blocks,
                occupied_blocks=occupied, free_blocks=free,
                required_free_blocks=SELECTION['minimum_free_spiffs_blocks'],
                missing_blocks=max(0, SELECTION['minimum_free_spiffs_blocks'] - free),
                admitted=free >= SELECTION['minimum_free_spiffs_blocks'],
                payload_bytes=sum(map(len, store.values())), image_generated=False)


def closure_gaps(store):
    boot = document(store['boot.json'])
    provided = set()
    for row in boot['drivers']:
        for item in document(store[row['manifest']])['provides']:
            provided.add((item['capability'], item['api'], row.get('instance_id', 0)))
    return [g for g in SELECTION['generic_services']
            if (g['capability'], g['api'], g['instance_id']) not in provided]


def provision_guards(before, after):
    """Future assemblers must retain native and factory appdata until separately qualified."""
    require(len(before) == len(after) == RECOVERY['full_image_bytes'], 'Wrong full image length')
    for start, end, label in [(0, 0x270000, 'boot/native/partitions'),
                               (0x270000, 0x2f0000, 'factory appdata'),
                               (0x800000, 0xff2000, 'inactive banks'),
                               (0xff4000, 0x1000000, 'tail')]:
        require(before[start:end] == after[start:end], 'Preserved flash range changed: ' + label)
    require(sha(after[0x270000:0x2f0000]) == RECOVERY['appdata_sha256'], 'Formatted appdata changed')


def run(baseline, shared_source, shared_apps, output, compact_unsigned=False):
    require(not output.exists(), 'Use a new output directory')
    baseline_selection = ROOT / 'docs/watch-recovery/selection.json'
    require(sha(baseline_selection.read_bytes()) == SELECTION['baseline_selection_sha256'],
            'Recovery selection changed')
    raw = baseline.read_bytes()
    recovery = audit(raw)
    provision_guards(raw, raw)
    old = read_image(raw[0x2f0000:0x800000], IMAGE_SIZE)
    stager, apps, record = load_home(shared_source, shared_apps)
    staged, _, compacted = stage_pair(old, apps, stager, compact_unsigned)
    planning = capacity(staged)
    gaps = closure_gaps(staged)
    changed = sorted(n for n in old if old[n] != staged[n])
    blockers = ['No selected generic native successor/profile build and complete admission',
                'No complete selected provider closure and retained-RGB565 sleep behavior qualification',
                'No normal/sanitized complete native/store admission or physical qualification']
    if not planning['admitted']:
        blockers.insert(0, 'SPIFFS capacity: need %d additional free blocks before provider additions' % planning['missing_blocks'])
    report = dict(schema='riscrte.twatch-shared-home-source-staging', source_only=True,
                  flashable=False, firmware_built=False, image_generated=False,
                  product_source=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                  selection_sha256=sha((ROOT / 'docs/shared-home-recovery/selection.json').read_bytes()),
                  recovery=recovery, home_source=SELECTION['home']['source'],
                  home_sha256=sha(staged['default.elf']), return_sha256=sha(staged['clock.elf']),
                  home_feature_flags=record['artifacts']['default']['defines'],
                  native_retained=SELECTION['native'], factory_appdata_preserved=True,
                  cohort_and_bank_unsealed=True, cohort_bytes_unchanged=old['cohort.json'] == staged['cohort.json'],
                  changed_paths=changed, compacted_unsigned_json=compacted,
                  unchanged_elfs=sum(n.endswith('.elf') and old[n] == staged[n] for n in old),
                  unchanged_paths=len(old)-len(changed), store_files=len(staged),
                  provider_instances=len(document(staged['boot.json'])['drivers']),
                  missing_generic_services=gaps, capacity=planning, blockers=blockers,
                  source_pins=SELECTION, no_device_operation=True)
    output.mkdir(parents=True)
    overlay = output / 'UNSEALED-OVERLAY'
    overlay.mkdir()
    for name in changed:
        target = overlay / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(staged[name])
    report['overlay_inventory'] = {n: dict(bytes=len(staged[n]), sha256=sha(staged[n])) for n in changed}
    (output / 'staging.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    (output / 'NOT-FLASHABLE.txt').write_text('Source/component staging only. Do not provision this unsealed overlay.\n' + '\n'.join(blockers) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['baseline-image', 'shared-source', 'shared-apps', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--compact-unsigned-json', action='store_true',
                        help='Explicit semantic-preserving metadata compaction; cohort/signatures excluded')
    args = parser.parse_args()
    report = run(args.baseline_image, args.shared_source, args.shared_apps, args.output,
                 args.compact_unsigned_json)
    print(json.dumps({k: report[k] for k in ['flashable', 'capacity', 'blockers', 'changed_paths']}, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Default-only composition over the exact shipped alarm/native baseline.

This staging command is not native qualification and cannot publish firmware.
Final qualification requires a fresh controlled native Runtime build, complete
production-loader admission and cross-product extraction. Historical recipes
are imported for utilities only and their contracts are never broadened.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import re
import sys

import serial_files_product as serial_files

from package_alarm_sleep import encoded, record, require, sha, clean_source

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/shared-default'
CHANGED = ['boot.json', 'cohort.json', 'default.elf', 'default.json']
ALARM_SHA = '189ce61b0e4a2b08cbd83ff90564a4c79a6c5e9a3d74b4ad4dcc2a61b4b51604'


def pins():
    p = json.loads((DOCS / 'source-pins.json').read_bytes())
    require(p['schema'] == 1 and p['product'] in ('twatch', 'waveshare'), 'Invalid product contract')
    require(type(p['finalized']) is bool and type(p['publication_enabled']) is bool, 'Invalid publication gates')
    require(p['changed_store_files'] == CHANGED and p['alarm_sha256'] == ALARM_SHA, 'Unexpected change scope')
    require(p['release_tag'] == 'test-shared-default-' + p['version'], 'Wrong release tag')
    require(p['release_branch'] == 'release/shared-default-' + p['version'], 'Wrong release branch')
    require(sha((DOCS / 'released-alarm-baseline.json').read_bytes()) == p['baseline_contract_sha256'], 'Released baseline contract changed')
    for path, expected in p['historical_contracts'].items():
        require(sha((ROOT / path).read_bytes()) == expected, 'Historical contract modified: ' + path)
    for role in ('watch', 'system', 'utilities', 'sdk', 'image_helper'):
        require(re.fullmatch('[0-9a-f]{40}', p[role + '_revision']), 'Immutable source pin required: ' + role)
    if p['finalized'] or p['publication_enabled']:
        require(p['finalized'] and re.fullmatch('[0-9a-f]{40}', p.get('runtime_revision') or ''), 'Final Runtime pin required')
    require(p['serial_files'] == serial_files.check_profile((ROOT / 'profiles/native-idf61.cmake').read_text(), p['product'],
        (ROOT / p['previous_release_profile']).read_text()), 'Serial product authority differs')
    for path, expected in p['native_input_sha256'].items():
        require(sha((ROOT / path).read_bytes()) == expected, 'Native product input differs: ' + path)
    return p


def baseline_contract(p):
    c = json.loads((DOCS / 'released-alarm-baseline.json').read_bytes())
    require(c['product'] == p['product'] and c['version'] == p['baseline_version'], 'Baseline identity differs')
    return c


def check_baseline(before, contract):
    require({n: record(b) for n, b in sorted(before.items())} == contract['files'], 'Released store inventory differs')
    require(sum(n.endswith('.elf') for n in before) == contract['elf_count'], 'Released ELF count differs')
    require(sha(before['alarm-service/driver.elf']) == ALARM_SHA, 'Released alarm fix is missing')
    cohort = json.loads(before['cohort.json'])
    require(cohort['version'] == contract['version'] and cohort['source_revision'] == contract['source_revision'], 'Released cohort differs')


def provision(boot, manifest, product):
    result = copy.deepcopy(boot)
    rows = [row for row in result['app_capabilities'] if row['manifest'] == 'default.json']
    require(len(rows) == 1, 'Exactly one default application policy required')
    row = rows[0]
    declared = {(r['capability'], r['api']) for r in manifest['requires'] + manifest.get('optional', [])}
    require(('storage.preferences', 1) in declared and ('storage.files', 1) in declared, 'Canonical generic storage declarations missing')
    require(not any(c in ('storage.volume', 'storage.key-value.atomic', 'storage.shared-data') for c, _ in declared), 'Canonical default selected a legacy backend')
    require(not any(g['capability'] in ('storage.preferences', 'storage.files') for g in row['grants']), 'Baseline already has new storage grants')
    require(any(g == {'capability': 'storage.key-value', 'api': 1, 'instance_id': 1} for g in row['grants']), 'Existing common settings namespace1 missing')
    volumes = [g for g in row['grants'] if g['capability'] == 'storage.volume']
    require(volumes == ([{'capability': 'storage.volume', 'api': 1, 'instance_id': 12}] if product == 'waveshare' else []), 'Unreviewed product file routing')
    # Keep every still-declared authority exactly; only default loses obsolete
    # legacy declarations. All unrelated application policies remain unchanged.
    row['grants'] = [g for g in row['grants'] if (g['capability'], g['api']) in declared]
    row['grants'].append({'capability': 'storage.preferences', 'api': 1, 'instance_id': 1})
    if product == 'waveshare':
        row['grants'].append({'capability': 'storage.files', 'api': 1, 'instance_id': 12,
                              'backend_capability': 'storage.volume', 'backend_instance': 12,
                              'backend_provider': 'sdmmc-fatfs', 'label': 'SD card'})
    return result


def expected_cohort(before, p, revision, firmware=None):
    require(re.fullmatch('[0-9a-f]{40}', revision), 'Immutable product revision required')
    cohort = dict(json.loads(before['cohort.json']), version=p['version'], source_revision=revision)
    if firmware is not None:
        versions = re.findall(rb'RISC_RUNTIME_VERSION:([^\x00]+)', firmware)
        require(len(versions) == 1, 'Missing/ambiguous Runtime version')
        cohort.update(runtime_version=versions[0].decode('ascii'), firmware_size=len(firmware), firmware_sha256=sha(firmware))
    return cohort


def verify_store(before, after, default, manifest, p, revision, firmware=None):
    require(set(before) == set(after), 'Store inventory changed')
    require(sorted(n for n in before if before[n] != after[n]) == CHANGED, 'Unexpected changed store files')
    require(record(default) == {'bytes': p['default_bytes'], 'sha256': p['default_sha256']}, 'Canonical default ELF differs')
    require(sha(manifest) == p['default_manifest_sha256'], 'Canonical default manifest differs')
    require(after['default.elf'] == default and after['default.json'] == manifest, 'Packaged default differs from canonical bytes')
    app = json.loads(manifest)
    require(app['id'] == json.loads(before['default.json'])['id'] == 'twatch-clock', 'Default application identity changed')
    require(app['file_name'] == 'default.elf', 'Default filename changed')
    require(json.loads(after['boot.json']) == provision(json.loads(before['boot.json']), app, p['product']), 'Unrelated boot authority changed')
    require(json.loads(after['cohort.json']) == expected_cohort(before, p, revision, firmware), 'Unrelated cohort authority changed')
    require(after['alarm-service/driver.elf'] == before['alarm-service/driver.elf'] and sha(after['alarm-service/driver.elf']) == ALARM_SHA, 'Alarm fix changed')
    return {'changed_store_files': CHANGED, 'unchanged_store_payloads': len(before) - len(CHANGED),
            'unchanged_elf_count': sum(n.endswith('.elf') for n in before) - 1,
            'default': record(default), 'default_manifest': record(manifest), 'alarm_sha256': ALARM_SHA}


def compose(before, default, manifest, p, revision, firmware=None):
    after = dict(before)
    after.update({'default.elf': default, 'default.json': manifest,
                  'boot.json': encoded(provision(json.loads(before['boot.json']), json.loads(manifest), p['product'])),
                  'cohort.json': encoded(expected_cohort(before, p, revision, firmware))})
    verify_store(before, after, default, manifest, p, revision, firmware)
    return after


def stage(args):
    p = pins()
    clean_source(ROOT, args.source_revision)
    clean_source(args.watch.resolve(), p['watch_revision'])
    require(not args.output.exists(), 'Output must be new')
    spec = importlib.util.spec_from_file_location('canonical_default_verifier', args.watch / 'scripts/verify_shared_default.py')
    verifier = importlib.util.module_from_spec(spec); spec.loader.exec_module(verifier)
    proof = verifier.verify(args.first, args.second)
    default, manifest, _ = verifier.check_build(args.first)
    clean_source(args.image_helper.resolve(), p['image_helper_revision'])
    sys.path.insert(0, str(args.image_helper / 'scripts'))
    from read_only_spiffs import read_image
    from current_bootfs import build
    sys.path.insert(0, str(args.runtime / 'scripts'))
    from prepare_preserving_update import layout, pair
    contract = baseline_contract(p)
    baseline = args.baseline.read_bytes()
    require(record(baseline) == {'bytes': contract['factory_bytes'], 'sha256': contract['factory_sha256']}, 'Exact released alarm factory required')
    _, _, packed = pair(baseline, 0, layout(baseline))
    require(sha(packed) == contract['store_sha256'], 'Released store bytes differ')
    before = read_image(packed, 0x550000)
    check_baseline(before, contract)
    after = compose(before, default, manifest, p, args.source_revision)
    packed, packing = build(after, size=0x550000)
    require(build(after, size=0x550000)[0] == packed, 'Store packing is not deterministic')
    extracted = read_image(packed, 0x550000)
    require(extracted == after, 'Packaged store extraction differs')
    preservation = verify_store(before, extracted, default, manifest, p, args.source_revision)
    args.output.mkdir(parents=True)
    (args.output / 'staged-store.bin').write_bytes(packed)
    (args.output / 'stage-proof.json').write_bytes(encoded(dict(schema=1, status='store-stage-only-not-firmware-qualified',
        product=p['product'], candidate_version=p['version'], source_revision=args.source_revision,
        native_qualified=False, hardware_tested=False, device_accessed=False, publication_enabled=False,
        canonical_builds=proof, preservation=preservation, packing=packing, store=record(packed))))
    print(p['product'] + ': canonical default extraction and complete unrelated payload preservation PASS; native qualification pending')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'watch', 'runtime', 'image-helper', 'first', 'second', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--source-revision', required=True)
    stage(parser.parse_args())

#!/usr/bin/env python3
"""Source-replay one public-ABI alarm service over a verified native release.

No resident firmware build, deployed image access, or hardware qualification.
The historical native migration recipes and their contracts remain unchanged.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

import transport_native_idf61_release as baseline_transport
from native_idf61_candidate import reject_private
from native_idf61_qualification import admit_product, preservation_model

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/alarm-sleep'
CHANGED = ['alarm-service/driver.elf', 'alarm-service/manifest.json', 'cohort.json']
PRODUCTS = {'waveshare': ('Waveshare', '0.1.50', '0.1.49'), 'twatch': ('TWatch', '1.1.41', '1.1.40')}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def record(data):
    return {'bytes': len(data), 'sha256': sha(data)}


def run(*command):
    return subprocess.check_output([str(x) for x in command], text=True,
                                   env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})


def clean_source(root, revision):
    require(re.fullmatch('[0-9a-f]{40}', revision), 'Immutable source pin required')
    require(run('git', '-C', root, 'rev-parse', 'HEAD').strip() == revision, 'Source revision differs: ' + str(root))
    require(not run('git', '-C', root, 'status', '--porcelain', '--untracked-files=no').strip(), 'Dirty source: ' + str(root))
    require(not run('git', '-C', root, 'ls-files', '--others', '--exclude-standard').strip(), 'Untracked source: ' + str(root))
    return {'revision': revision, 'tree': run('git', '-C', root, 'rev-parse', 'HEAD^{tree}').strip()}


def pins():
    p = baseline_transport.decode((DOCS / 'source-pins.json').read_bytes())
    require(p.get('schema') == 1 and p.get('finalized') is True and type(p.get('publication_enabled')) is bool, 'Final pins required')
    require(p['product'] in PRODUCTS, 'Unknown product')
    prefix, version, previous = PRODUCTS[p['product']]
    require(p['version'] == version and p['baseline_version'] == previous, 'Wrong increment')
    require(p['release_tag'] == 'test-alarm-sleep-' + version and p['release_branch'] == 'release/alarm-sleep-' + version, 'Wrong release identity')
    require(p['changed_store_files'] == CHANGED and p['alarm_version'] == '0.4.12', 'Unreviewed change scope')
    require(set(p['sources']) == {'runtime', 'system', 'watch', 'image_helper', 'sdk', 'utilities'}, 'Source closure differs')
    require(all(re.fullmatch('[0-9a-f]{40}', x) for x in p['sources'].values()), 'Full source revisions required')
    for key in ('baseline_source',):
        require(re.fullmatch('[0-9a-f]{40}', p[key]), 'Full baseline source required')
    for key in ('baseline_transport_sha256', 'alarm_sha256', 'alarm_manifest_sha256', 'builder_sha256', 'compiler_sha256', 'toolchain_archive_sha256'):
        require(re.fullmatch('[0-9a-f]{64}', p[key]), 'Missing digest: ' + key)
    return p


def compose(before, alarm, manifest_bytes, source_revision, p):
    require(record(alarm) == {'bytes': p['alarm_bytes'], 'sha256': p['alarm_sha256']}, 'Alarm replay bytes differ')
    require(sha(manifest_bytes) == p['alarm_manifest_sha256'], 'Alarm replay manifest differs')
    old_manifest = json.loads(before['alarm-service/manifest.json'])
    new_manifest = json.loads(manifest_bytes)
    require(old_manifest['version'] == p['baseline_alarm_version'], 'Unexpected predecessor alarm version')
    require(new_manifest == dict(old_manifest, version=p['alarm_version']), 'Alarm manifest authority or settings identity changed')
    original = json.loads(before['cohort.json'])
    require(original['version'] == p['baseline_version'], 'Wrong baseline cohort')
    after = dict(before)
    after['alarm-service/driver.elf'] = alarm
    # Retain the exact prior manifest authority and update its version only.
    after['alarm-service/manifest.json'] = manifest_bytes
    after['cohort.json'] = encoded(dict(original, version=p['version'], source_revision=source_revision))
    verify_store(before, after, p, source_revision)
    return after


def verify_store(before, after, p, source_revision):
    require(set(before) == set(after), 'Store inventory changed')
    changed = sorted(name for name in before if before[name] != after[name])
    require(changed == CHANGED, 'Unexpected changed store payloads: ' + str(changed))
    require(json.loads(after['alarm-service/manifest.json']) == dict(json.loads(before['alarm-service/manifest.json']), version='0.4.12'), 'Manifest identity changed')
    require(json.loads(after['cohort.json']) == dict(json.loads(before['cohort.json']), version=p['version'], source_revision=source_revision), 'Cohort authority changed')
    require(sha(after['alarm-service/driver.elf']) == p['alarm_sha256'], 'Wrong service ELF')
    require(sum(n.endswith('.elf') for n in after) == p['elf_count'], 'Incomplete ordinary ELF inventory')
    return changed


def replace_store(baseline, firmware, packed):
    from prepare_preserving_update import layout, pair
    from paired_bank_images import initial_bank_state
    require(len(baseline) == 0x1000000 and len(packed) == 0x550000, 'Wrong image geometry')
    candidate = bytearray(baseline)
    candidate[0x2f0000:0x840000] = packed
    state = initial_bank_state(firmware, packed, True, True)
    require(len(state) == 8192 and state[4096:] == baseline[0xff3000:0xff4000], 'Unexpected inactive bank-state content')
    candidate[0xff2000:0xff3000] = state[:4096]
    for start, end in ((0, 0x2f0000), (0x840000, 0xff2000), (0xff3000, 0x1000000)):
        require(candidate[start:end] == baseline[start:end], 'Native, bootloader, partitions, settings, or protected range changed')
    require(layout(candidate) == layout(baseline) and pair(candidate, 0, layout(candidate))[1:] == (firmware, packed), 'Paired bank binding differs')
    return bytes(candidate)


def make_archive(files):
    import io
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    return out.getvalue()


def verify_output(output, expected_sha, source_revision):
    sums_bytes = (output / 'SHA256SUMS').read_bytes()
    require(sha(sums_bytes) == expected_sha, 'Checksum custody differs')
    sums = baseline_transport.checksums(sums_bytes)
    require({p.name for p in output.iterdir()} == set(sums) | {'SHA256SUMS'}, 'Asset set differs')
    for name, digest in sums.items():
        p = output / name
        require(p.is_file() and not p.is_symlink() and sha(p.read_bytes()) == digest, 'Asset changed: ' + name)
    release = json.loads((output / 'release.json').read_bytes())
    require(release['source_revision'] == source_revision and release['native_rebuilt'] is False
            and release['hardware_tested'] is False and release['device_accessed'] is False, 'Release identity or limits differ')
    require(release['changed_store_files'] == CHANGED and release['alarm_version'] == '0.4.12', 'Release scope differs')
    for name, row in release['artifacts'].items():
        require(record((output / name).read_bytes()) == row, 'Release inventory differs')


def package(args):
    require(__debug__, 'Do not disable validation')
    p = pins()
    roots = {role: getattr(args, role).resolve() for role in p['sources']}
    roots['product'] = ROOT
    source_ids = {**p['sources'], 'product': args.source_revision}
    source_closure = {role: clean_source(root, source_ids[role]) for role, root in roots.items()}
    require(not args.output.exists(), 'Output must be new')
    baseline_contract_bytes = (ROOT / 'docs/native-idf61/release-transport.json').read_bytes()
    require(sha(baseline_contract_bytes) == p['baseline_transport_sha256'], 'Historical native transport modified')
    contract = baseline_transport.decode(baseline_contract_bytes)
    require(contract['version'] == p['baseline_version'] and contract['product'] == p['product'], 'Wrong official native baseline')
    require(p['sources']['runtime'] == contract['runtime_revision'], 'Resident Runtime source differs')
    baseline_transport.final_contract(contract)
    members, _ = baseline_transport.verify_runtime_envelope(contract, args.runtime_manifest.read_bytes(), args.evidence)
    with zipfile.ZipFile(args.evidence) as z:
        blobs, original_qualification = baseline_transport.validate_candidate(z, members, contract)
        lock = original_qualification['input_lock']
        native_elf = z.read('build/' + lock['native_files']['firmware_elf']['path'])
    baseline = args.baseline.read_bytes()
    require(baseline == blobs['factory-candidate-erases-data-0x0.bin'], 'Official baseline factory differs from qualified evidence')
    firmware = blobs['firmware.bin']
    sys.path[:0] = [str(roots['runtime'] / 'scripts'), str(roots['image_helper'] / 'scripts')]
    from prepare_preserving_update import layout, pair
    from read_only_spiffs import read_image
    from current_bootfs import build
    require(pair(baseline, 0, layout(baseline))[1:] == (firmware, blobs['store.bin']), 'Baseline native/store pair differs')
    before = read_image(blobs['store.bin'], 0x550000)
    builder = roots['utilities'] / 'scripts/build_alarm_sleep_retry.py'
    require(sha(builder.read_bytes()) == p['builder_sha256'] and sha(args.compiler.resolve().read_bytes()) == p['compiler_sha256'], 'Builder or compiler differs')
    with tempfile.TemporaryDirectory(prefix='alarm-sleep-') as temp:
        temp = Path(temp)
        replay_files = {}
        targets = []
        for number in (1, 2):
            out = temp / ('replay-' + str(number))
            log = run(sys.executable, builder, '--runtime', roots['runtime'], '--system-apps', roots['system'], '--watch', roots['watch'], '--cc', args.compiler.absolute(), '--output', out)
            targets.append(((out / 'driver.elf').read_bytes(), (out / 'manifest.json').read_bytes()))
            receipt = json.loads((out / 'build-receipt.json').read_bytes())
            require(receipt['sources'] == {key: source_ids[key] for key in ('runtime', 'system', 'watch', 'utilities')}, 'Builder source closure differs')
            require(receipt['elf_sha256'] == p['alarm_sha256'] and receipt['elf_bytes'] == p['alarm_bytes'], 'Builder target differs')
            require(receipt['sdk_private_imports'] is False and receipt['libc_layout_sensitive_imports'] is False, 'Public ABI boundary missing')
            replay_files['replay-' + str(number) + '.json'] = encoded(receipt)
            replay_files['replay-' + str(number) + '.log'] = log.encode()
        require(targets[0] == targets[1], 'Source replay is not reproducible')
        alarm, manifest = targets[0]
        tests = run(sys.executable, roots['utilities'] / 'scripts/test_alarm_color_sleep.py', '--runtime', roots['runtime'], '--system-apps', roots['system'], '--watch', roots['watch'], '--output', temp / 'tests')
        replay_files['source-tests.log'] = tests.encode()
    after = compose(before, alarm, manifest, args.source_revision, p)
    imports = reject_private(after, roots['runtime'])
    packed, packing = build(after, size=0x550000)
    require(build(after, size=0x550000)[0] == packed and read_image(packed, 0x550000) == after, 'Store replay/round-trip differs')
    candidate = replace_store(baseline, firmware, packed)
    native_proof = original_qualification['native']
    admission = admit_product(roots, native_elf, before, after, native_proof, sanitized=False)
    admission_sanitized = admit_product(roots, native_elf, before, after, native_proof, sanitized=True)
    require(admission['elf_count'] == admission_sanitized['elf_count'] == p['elf_count'], 'Incomplete production loader admission')
    preservation = preservation_model(baseline, candidate, sha(baseline))
    require({role: clean_source(root, source_ids[role]) for role, root in roots.items()} == source_closure, 'Sources changed during qualification')
    report = dict(schema=1, status='software-qualified-hardware-pending', product=p['product'], version=p['version'],
                  source_revision=args.source_revision, source_closure=source_closure, baseline_source_revision=p['baseline_source'],
                  baseline_factory_sha256=sha(baseline), baseline_evidence_sha256=sha(args.evidence.read_bytes()),
                  original_native_qualification_sha256=contract['qualification_sha256'], native_rebuilt=False,
                  native_firmware_sha256=sha(firmware), native_elf_sha256=sha(native_elf),
                  unchanged_native_components={name: record(blobs[name]) for name in ('firmware.bin', 'bootloader.bin', 'partitions.bin')},
                  alarm_version=p['alarm_version'], alarm_sha256=p['alarm_sha256'], changed_store_files=CHANGED,
                  unchanged_elf_count=p['elf_count'] - 1, total_elf_count=p['elf_count'],
                  all_other_store_payloads_unchanged=True, settings_identities_unchanged=True,
                  store_before={name: record(data) for name, data in sorted(before.items())},
                  store_after={name: record(data) for name, data in sorted(after.items())},
                  public_imports=imports, packing=packing, admission=admission, admission_sanitized=admission_sanitized,
                  preservation_software_model=preservation, replay_count=2, target_loader_passed=True,
                  hardware_tested=False, device_accessed=False, factory_erases_data=True,
                  preserving_update_kit_emitted=False, preserving_sdk_migration_eligible=False)
    prefix, version, _ = PRODUCTS[p['product']]
    stem = prefix + '-' + version + '-Alarm-Sleep'
    files = {stem + '-factory-erases-data-0x0.bin': candidate,
             stem + '-firmware.bin': firmware, stem + '-bootloader.bin': blobs['bootloader.bin'],
             stem + '-partitions.bin': blobs['partitions.bin'], stem + '-store.bin': packed,
             'qualification.json': encoded(report), 'source-pins.json': (DOCS / 'source-pins.json').read_bytes(),
             'baseline-transport-contract.json': baseline_contract_bytes,
             'baseline-runtime-release-manifest.json': args.runtime_manifest.read_bytes(),
             'RELEASE-NOTES.txt': (DOCS / 'RELEASE-NOTES.txt').read_bytes()}
    replay_files.update({'driver.elf': alarm, 'manifest.json': manifest, 'qualification.json': encoded(report),
                         'source-pins.json': files['source-pins.json'],
                         'workflow.yml': (ROOT / '.github/workflows/alarm-sleep-release.yml').read_bytes()})
    files[stem + '-Evidence.zip'] = make_archive(replay_files)
    release = dict(schema=1, product=p['product'], version=p['version'], source_revision=args.source_revision,
                   baseline_version=p['baseline_version'], baseline_source_revision=p['baseline_source'],
                   utilities_revision=p['sources']['utilities'], alarm_version='0.4.12', alarm_sha256=p['alarm_sha256'],
                   native_rebuilt=False, native_firmware_sha256=sha(firmware), changed_store_files=CHANGED,
                   hardware_tested=False, device_accessed=False, factory_erases_data=True,
                   preserving_update_kit_emitted=False, artifacts={name: record(data) for name, data in sorted(files.items())})
    files['release.json'] = encoded(release)
    files['SHA256SUMS'] = ''.join(sha(data) + '  ' + name + '\n' for name, data in sorted(files.items())).encode()
    args.output.mkdir(parents=True)
    for name, data in files.items():
        (args.output / name).write_bytes(data)
    verify_output(args.output, sha(files['SHA256SUMS']), args.source_revision)
    print(prefix + ' ' + version + ': two identical shared service replays, strict store diff, complete loader admission, native identity, and preserving software model PASS; hardware pending.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'evidence', 'runtime-manifest', 'runtime', 'system', 'watch', 'image-helper', 'sdk', 'utilities', 'compiler', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    package(parser.parse_args())


if __name__ == '__main__':
    main()

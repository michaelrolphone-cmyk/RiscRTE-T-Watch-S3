#!/usr/bin/env python3
"""Seal the selected qualified Watch union as a full initial 0x0 test image.

All native firmware and app/provider bytes are retained exactly. Only the
cohort's product version and source revision are changed. No upload or flash.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from assemble_watch_points_union import require, sha, encoded, git, BOOTFS, BANK
from assemble_watch_spectrum_policy import streamed_digest, strict_json
from current_bootfs import build, read_image
from watch_boot_order_spiffs import build as ordered_build
from check_runtime_store_admission import admit_cohort, store_digest

ROOT = Path(__file__).resolve().parents[1]
SELECTION = strict_json((ROOT / 'docs/evening-watch-1119/selection.json').read_bytes())
VERSION = SELECTION['version']
IMAGE_SIZE = 0x1000000


def checked_bytes(path, digest, label):
    raw = Path(path).read_bytes()
    require(sha(raw) == digest, label + ' SHA-256 mismatch')
    return raw


def validate_store(files, selection=SELECTION):
    baseline = selection['baseline']
    require(len(files) == baseline['store_files'], 'Incomplete store inventory')
    require(sum(name.endswith('.elf') for name in files) == baseline['elf_count'], 'Incomplete ELF inventory')
    require(store_digest(files) == baseline['candidate_store_sha256'], 'Baseline store differs')
    cohort = strict_json(files['cohort.json'])
    require(cohort['version'] == '1.1.18' and cohort['source_revision'] == baseline['compiled_recipe_commit'], 'Wrong baseline cohort')
    require(strict_json(files['waterfall.json'])['version'] == selection['preservation']['rf_version'], 'Unselected RF version')
    require(selection['preservation']['watch_has_sd'] is False, 'Watch has no SD')
    return cohort


def seal_store(files, revision, selection=SELECTION):
    cohort = validate_store(files, selection)
    require(len(revision) == 40 and set(revision) <= set('0123456789abcdef'), 'Invalid source revision')
    cohort.update(version=selection['version'], source_revision=revision)
    sealed = dict(files, **{'cohort.json': encoded(cohort)})
    require(set(sealed) == set(files), 'Store inventory changed')
    require({name for name in files if files[name] != sealed[name]} == {'cohort.json'}, 'Component changed while sealing')
    return sealed


def check_full_image(path, previous, firmware, bootfs, bank):
    require(Path(path).stat().st_size == IMAGE_SIZE, 'Incorrect full image size')
    with Path(path).open('rb') as output, Path(previous).open('rb') as source:
        for start, end in [(0, BOOTFS[0]), (BOOTFS[1], BANK[0]), (BANK[1], IMAGE_SIZE)]:
            output.seek(start); source.seek(start)
            remaining = end - start
            while remaining:
                size = min(65536, remaining)
                require(output.read(size) == source.read(size), 'Preserved image range changed')
                remaining -= size
        for start, raw in [(0x10000, firmware), (BOOTFS[0], bootfs), (BANK[0], bank)]:
            output.seek(start)
            require(output.read(len(raw)) == raw, 'Full image component differs')


def write_full_image(path, previous, bootfs, bank):
    # Sequential writes preserve the exact erased 0xff regions. Zero runs are
    # sparse holes; they still read back as the original bytes.
    with Path(previous).open('rb') as source, Path(path).open('xb') as output:
        while chunk := source.read(65536):
            if chunk == b'\0' * len(chunk):
                output.seek(len(chunk), 1)
            else:
                output.write(chunk)
        output.truncate(IMAGE_SIZE)
        for offset, raw in [(BOOTFS[0], bootfs), (BANK[0], bank)]:
            output.seek(offset); output.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['baseline', 'baseline-handoff', 'native-candidate', 'runtime', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--materialize', action='store_true')
    args = parser.parse_args()
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty product source')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    selected = SELECTION['baseline']; native_selection = SELECTION['native']
    checked_bytes(args.baseline_handoff, selected['handoff_sha256'], 'Selected handoff')
    receipt = checked_bytes(args.baseline / 'receipts/final-normal.json', selected['normal_receipt_sha256'], 'Normal baseline receipt')
    require((args.baseline / 'receipts/final-sanitized.json').read_bytes() == receipt, 'Normal/sanitized baseline disagreement')
    prior = strict_json(receipt)
    require(prior['product_source'] == selected['compiled_recipe_commit'] and prior['product_tree'] == selected['product_tree'], 'Wrong baseline recipe identity')
    require(prior['prepared'] and prior['cohort_validated'] and not prior['hardware_calls'] and not prior['storage_calls'], 'Unqualified baseline')
    require(prior['candidate_store_sha256'] == selected['candidate_store_sha256'], 'Baseline receipt custody mismatch')
    require(prior['free_spiffs_blocks'] >= SELECTION['preservation']['minimum_free_spiffs_blocks'], 'Baseline reserve below floor')
    baseline_bootfs = checked_bytes(args.baseline / 'components/bootfs.bin', selected['bootfs_sha256'], 'Baseline bootfs')
    baseline_bank = checked_bytes(args.baseline / 'components/bank_state.bin', selected['bank_state_sha256'], 'Baseline bank')
    old = read_image(baseline_bootfs, 0x510000)
    sealed = seal_store(old, revision)
    native = checked_bytes(args.native_candidate / 'components/firmware.elf', native_selection['native_elf_sha256'], 'Native ELF')
    firmware = checked_bytes(args.native_candidate / 'components/firmware.bin', native_selection['firmware_sha256'], 'Native BIN')
    previous = args.native_candidate / 'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin'
    require(streamed_digest(previous) == native_selection['ancestor_full_image_sha256'], 'Wrong native ancestor image')
    require(streamed_digest(previous, {BOOTFS[0]: baseline_bootfs, BANK[0]: baseline_bank}) == selected['full_image_sha256'], 'Baseline full reconstruction mismatch')
    require(git(args.runtime, 'rev-parse', 'HEAD') == native_selection['runtime_commit'] and not git(args.runtime, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty Runtime')
    profile = args.runtime / 'watch-file-source-profile.ini'
    require(profile.read_bytes() == (ROOT / 'docs/file-source/watch-file-source-profile.ini').read_bytes(), 'Wrong native profile')
    bootfs, packing = ordered_build(sealed, build)
    require(packing['empty_blocks'] >= SELECTION['preservation']['minimum_free_spiffs_blocks'], 'SPIFFS reserve below floor')
    require(read_image(bootfs, 0x510000) == sealed, 'Packed store roundtrip mismatch')
    sys.path.insert(0, str(args.runtime / 'scripts'))
    from paired_bank_images import initial_bank_state, parse_record
    bank = initial_bank_state(firmware, bootfs, True)
    rec = parse_record(bank[:96], True)
    require(rec[3] == len(firmware) and rec[6] == hashlib.sha256(firmware).digest() and rec[7] == hashlib.sha256(bootfs).digest(), 'Paired bank digest mismatch')
    full_sha = streamed_digest(previous, {BOOTFS[0]: bootfs, BANK[0]: bank})
    if not args.verify_only:
        require(not args.output.exists(), 'Use new output directory')
        (args.output / 'components').mkdir(parents=True)
        (args.output / 'receipts').mkdir()
        (args.output / 'components/bootfs.bin').write_bytes(bootfs)
        (args.output / 'components/bank_state.bin').write_bytes(bank)
        (args.output / 'receipts/packing.json').write_bytes(encoded(packing))
        inventory = {name: dict(bytes=len(raw), sha256=sha(raw)) for name, raw in sorted(sealed.items())}
        (args.output / 'receipts/store-inventory.json').write_bytes(encoded(inventory))
        (args.output / 'receipts/cohort.json').write_bytes(sealed['cohort.json'])
    require((args.output / 'components/bootfs.bin').read_bytes() == bootfs and (args.output / 'components/bank_state.bin').read_bytes() == bank, 'Written packed artifacts differ')
    image = args.output / ('WATCH-' + VERSION + '-FULL-INITIAL-ERASES-DATA.bin')
    if args.materialize and not image.exists():
        write_full_image(image, previous, bootfs, bank)
    if image.exists():
        check_full_image(image, previous, firmware, bootfs, bank)
        require(streamed_digest(image) == full_sha, 'Materialized full image differs')
    admission = admit_cohort(args.runtime, native, old, sealed, app_policy_rows=24, native_profile=profile)
    require(admission['elf_count'] == selected['elf_count'], 'Incomplete full-cohort admission')
    require(git(ROOT, 'rev-parse', 'HEAD') == revision and not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Source changed during verification')
    proof = dict(product='Watch', version=VERSION, product_source=revision,
        product_tree=git(ROOT, 'rev-parse', 'HEAD^{tree}'), baseline_source=selected['compiled_recipe_commit'],
        baseline_handoff_sha256=selected['handoff_sha256'], runtime_source=native_selection['runtime_commit'],
        baseline_store_sha256=selected['candidate_store_sha256'], changed_store_paths=['cohort.json'],
        preserved_store_paths=len(old)-1, native_unchanged=True, boot_json_byte_identical=True,
        all_app_and_provider_bytes_unchanged=True, all_fonts_and_features_preserved=True, grant_delta=[],
        store_files=len(sealed), free_spiffs_blocks=packing['empty_blocks'], required_free_spiffs_blocks=2,
        full_image_bytes=IMAGE_SIZE, full_image_sha256=full_sha, flash_offset='0x0',
        full_initial_erases_data=True, full_image_materialized=image.exists(),
        delivered=False, flashed=False, hardware_verified=False,
        delivery_hold_until_utc=SELECTION['delivery']['hold_until_utc'], **admission)
    name = 'final-sanitized.json' if os.environ.get('SANITIZE') == '1' else 'final-normal.json'
    (args.output / 'receipts' / name).write_bytes(encoded(proof))
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()

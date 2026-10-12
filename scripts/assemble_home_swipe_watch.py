#!/usr/bin/env python3
"""Overlay Home 0.11.6 onto exact Watch 1.1.19 and qualify Watch 1.1.20.

Only default.elf, default.json and cohort.json may differ. No publication or flash.
"""
import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path

from assemble_watch_points_union import require, sha, encoded, git, read_store, BOOTFS, BANK
from assemble_watch_spectrum_policy import streamed_digest, strict_json
from assemble_evening_watch import check_full_image, write_full_image, verify_sidecars
from current_bootfs import build, read_image
from watch_boot_order_spiffs import build as ordered_build
from check_runtime_store_admission import admit_cohort, store_digest

ROOT = Path(__file__).resolve().parents[1]
SELECTION = strict_json((ROOT / 'docs/home-swipe/selection.json').read_bytes())
VERSION = '1.1.20'
CHANGED = {'default.elf', 'default.json', 'cohort.json'}
HOME_CHANGED = {'watch:apps/clock/crown.c', 'watch:apps/clock/launcher_touch.h', 'watch:apps/clock/nova/nova.h'}


def checked(path, digest, label):
    raw = Path(path).read_bytes()
    require(sha(raw) == digest, label + ' SHA-256 mismatch')
    return raw


def baseline(path):
    selected = SELECTION['baseline']
    raw = checked(path / 'receipts/final-normal.json', selected['receipt_sha256'], 'Baseline qualification')
    require((path / 'receipts/final-sanitized.json').read_bytes() == raw, 'Baseline normal/sanitized disagreement')
    prior = strict_json(raw)
    require(prior['product_source'] == selected['source'] and prior['product_tree'] == selected['tree'] and
            prior['version'] == '1.1.19' and prior['prepared'] and prior['cohort_validated'] and
            prior['hardware_calls'] == prior['storage_calls'] == 0, 'Wrong baseline qualification')
    bootfs = checked(path / 'components/bootfs.bin', selected['bootfs_sha256'], 'Baseline bootfs')
    bank = checked(path / 'components/bank_state.bin', selected['bank_state_sha256'], 'Baseline bank')
    old = read_image(bootfs, 0x510000)
    require(len(old) == 113 and sum(name.endswith('.elf') for name in old) == 55, 'Incomplete baseline inventory')
    require(store_digest(old) == selected['store_sha256'] == prior['candidate_store_sha256'], 'Baseline store custody mismatch')
    require(len(old['default.elf']) == selected['home_bytes'] and sha(old['default.elf']) == selected['home_elf_sha256'], 'Wrong baseline Home')
    previous = path / 'WATCH-1.1.19-FULL-INITIAL-ERASES-DATA.bin'
    require(streamed_digest(previous) == selected['full_image_sha256'] == prior['full_image_sha256'], 'Wrong exact full-image baseline')
    return old, prior, bootfs, bank, previous


def component(path, baseline_clock, revision):
    selected = SELECTION['baseline']
    before = strict_json(checked(baseline_clock / 'build.json', selected['home_build_receipt_sha256'], 'Retained Home build receipt'))
    record = strict_json((path / 'build.json').read_bytes())
    require(record['product_source'] == revision and record['product_tree'] == git(ROOT, 'rev-parse', 'HEAD^{tree}'), 'Home target source differs')
    require(record['recipe_sha256'] == sha((ROOT / 'scripts/build_home_swipe.py').read_bytes()), 'Home target recipe differs')
    require(record['baseline_receipt_sha256'] == selected['home_build_receipt_sha256'] and
            record['baseline_elf_sha256'] == selected['home_elf_sha256'], 'Wrong Home predecessor custody')
    require(set(record['changed_dependency_keys']) == HOME_CHANGED, 'Unexpected Home source delta')
    require(len(record['dependencies']) == 98 and set(record['dependencies']) == set(before['dependencies']), 'Incomplete Home source receipt')
    for key, value in record['dependencies'].items():
        require(value['predecessor_sha256'] == before['dependencies'][key]['sha256'], 'Home baseline input differs: ' + key)
        require((value['sha256'] != value['predecessor_sha256']) == (key in HOME_CHANGED), 'Home changed-input receipt differs: ' + key)
        owner, relative = key.split(':', 1)
        if owner == 'watch':
            require(sha((ROOT / relative).read_bytes()) == value['sha256'], 'Home compiled source changed: ' + key)
    flags = [item for item in before['fast_clock']['command'] if item.startswith('-D')]
    require(record['feature_flags'] == flags and record['compiler'] == before['compiler'] and record['fonts_unchanged'], 'Home fonts, flags or compiler changed')
    files = {name: (path / name).read_bytes() for name in ('default.elf', 'default.json')}
    require(sha(files['default.elf']) == record['sha256'] and len(files['default.elf']) == record['bytes'], 'Home target custody differs')
    require(sha(files['default.json']) == record['manifest']['sha256'] and record['manifest']['version'] == '0.11.6', 'Home manifest custody differs')
    from elftools.elf.elffile import ELFFile
    elf = ELFFile(io.BytesIO(files['default.elf']))
    require(elf.elfclass == 32 and elf.little_endian and elf['e_machine'] == 'EM_XTENSA' and elf['e_type'] == 'ET_DYN', 'Invalid Home target layout')
    symbols = list(elf.get_section_by_name('.dynsym').iter_symbols())
    imports = sorted(symbol.name for symbol in symbols if symbol.name and symbol['st_shndx'] == 'SHN_UNDEF')
    exports = sorted(symbol.name for symbol in symbols if symbol.name and symbol['st_shndx'] != 'SHN_UNDEF' and symbol['st_info']['bind'] in ('STB_GLOBAL', 'STB_WEAK'))
    require(imports == record['imports'] == before['fast_clock']['imports'] and exports == record['exports'] == ['app_main'], 'Home imports or exports changed')
    require(record['compaction']['retained_loader_sections_symbols_relocations_unchanged'] and
            record['compaction']['profile'] == 'loader-metadata-v3', 'Home compaction custody missing')
    return files, record


def payload(old, files, revision):
    require(set(files) == {'default.elf', 'default.json'}, 'Unexpected Home component member')
    expected = strict_json(old['default.json'])
    require(expected['version'] == '0.11.5', 'Wrong Home manifest predecessor')
    expected['version'] = '0.11.6'
    require(strict_json(files['default.json']) == expected, 'Home manifest authority or features changed')
    require(old['default.json'].count(b'"version":"0.11.5"') == 1, 'Unexpected baseline Home formatting')
    manifest = old['default.json'].replace(b'"version":"0.11.5"', b'"version":"0.11.6"')
    require(strict_json(manifest) == expected, 'Home manifest version substitution failed')
    cohort = strict_json(old['cohort.json'])
    require(cohort['version'] == '1.1.19' and cohort['source_revision'] == SELECTION['baseline']['source'], 'Wrong cohort predecessor')
    cohort.update(version=VERSION, source_revision=revision)
    new = dict(old, **{'default.elf': files['default.elf'], 'default.json': manifest, 'cohort.json': encoded(cohort)})
    verify_preservation(old, new)
    return new


def verify_preservation(old, new):
    require(set(old) == set(new), 'Store inventory changed')
    require({name for name in old if old[name] != new[name]} == CHANGED, 'Unexpected store delta')
    require(new['boot.json'] == old['boot.json'], 'Boot authority or formatting changed')
    require(sum(name.endswith('.elf') and name != 'default.elf' and old[name] == new[name] for name in old) == 54, 'Other ELF bytes changed')
    require(all(old[name] == new[name] for name in old if name not in CHANGED), 'Unrelated path bytes changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'baseline-clock', 'native-candidate', 'home-build', 'runtime', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--materialize', action='store_true')
    args = parser.parse_args()
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Commit product source before qualification')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    old, prior, old_bootfs, old_bank, previous = baseline(args.baseline)
    files, record = component(args.home_build, args.baseline_clock, revision)
    new = payload(old, files, revision)
    native = checked(args.native_candidate / 'components/firmware.elf', SELECTION['native']['elf_sha256'], 'Native ELF')
    firmware = checked(args.native_candidate / 'components/firmware.bin', SELECTION['native']['firmware_sha256'], 'Native firmware')
    check_full_image(previous, previous, firmware, old_bootfs, old_bank)
    require(git(args.runtime, 'rev-parse', 'HEAD') == SELECTION['native']['runtime_source'] and
            not git(args.runtime, 'status', '--porcelain', '--untracked-files=no'), 'Wrong or dirty Runtime')
    profile = args.runtime / 'watch-file-source-profile.ini'
    require(profile.read_bytes() == (ROOT / 'docs/file-source/watch-file-source-profile.ini').read_bytes(), 'Native profile differs')
    bootfs, packing = ordered_build(new, build)
    require(packing['empty_blocks'] >= 2 and packing['file_count'] == 113, 'SPIFFS reserve or inventory violated')
    require(read_image(bootfs, 0x510000) == new, 'Packed store roundtrip differs')
    sys.path.insert(0, str(args.runtime / 'scripts'))
    from paired_bank_images import initial_bank_state, parse_record
    bank = initial_bank_state(firmware, bootfs, True)
    rec = parse_record(bank[:96], True)
    require(rec[3] == len(firmware) and rec[6] == hashlib.sha256(firmware).digest() and
            rec[7] == hashlib.sha256(bootfs).digest(), 'Paired bank digest differs')
    full_sha = streamed_digest(previous, {BOOTFS[0]: bootfs, BANK[0]: bank})
    inventory = {name: dict(bytes=len(raw), sha256=sha(raw)) for name, raw in sorted(new.items())}
    if not args.verify_only:
        require(not args.output.exists(), 'Use a new output directory')
        (args.output / 'components').mkdir(parents=True)
        (args.output / 'receipts').mkdir()
        (args.output / 'overlay').mkdir()
        for name in CHANGED:
            (args.output / 'overlay' / name).write_bytes(new[name])
        for name, raw in [('bootfs.bin', bootfs), ('bank_state.bin', bank)]:
            (args.output / 'components' / name).write_bytes(raw)
        for name, obj in [('packing', packing), ('store-inventory', inventory), ('home-build', record), ('baseline', prior)]:
            (args.output / 'receipts' / (name + '.json')).write_bytes(encoded(obj))
        (args.output / 'receipts/cohort.json').write_bytes(new['cohort.json'])
    require(read_store(args.output / 'overlay') == {name: new[name] for name in CHANGED}, 'Written overlay differs')
    require((args.output / 'components/bootfs.bin').read_bytes() == bootfs and
            (args.output / 'components/bank_state.bin').read_bytes() == bank, 'Written packed artifacts differ')
    verify_sidecars(args.output, packing, inventory, new['cohort.json'])
    for name, obj in [('home-build', record), ('baseline', prior)]:
        require((args.output / 'receipts' / (name + '.json')).read_bytes() == encoded(obj), 'Written input receipt differs')
    image = args.output / ('WATCH-' + VERSION + '-FULL-INITIAL-ERASES-DATA.bin')
    if args.materialize and not image.exists():
        write_full_image(image, previous, bootfs, bank)
    if image.exists():
        check_full_image(image, previous, firmware, bootfs, bank)
        require(streamed_digest(image) == full_sha, 'Full-image hash differs')
    admission = admit_cohort(args.runtime, native, old, new, app_policy_rows=24, native_profile=profile)
    require(admission['elf_count'] == 55, 'Incomplete full-cohort admission')
    require(git(ROOT, 'rev-parse', 'HEAD') == revision and not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Source changed during qualification')
    proof = dict(product='Watch', version=VERSION, home_version='0.11.6', product_source=revision,
        product_tree=git(ROOT, 'rev-parse', 'HEAD^{tree}'), baseline_source=SELECTION['baseline']['source'],
        baseline_full_image_sha256=SELECTION['baseline']['full_image_sha256'],
        home_sha256=sha(new['default.elf']), home_bytes=len(new['default.elf']),
        home_source_delta=sorted(HOME_CHANGED), home_feature_flags_unchanged=True, home_fonts_source_unchanged=True,
        changed_store_paths=sorted(CHANGED), preserved_store_paths=110, preserved_other_elf_count=54,
        native_unchanged=True, boot_json_byte_identical=True, grant_delta=[],
        other_app_provider_font_bytes_unchanged=True, free_spiffs_blocks=packing['empty_blocks'],
        required_free_spiffs_blocks=2, store_files=113, full_image_bytes=0x1000000,
        full_image_sha256=full_sha, flash_offset='0x0', full_initial_erases_data=True,
        full_image_materialized=image.exists(), delivered=False, flashed=False, hardware_verified=False,
        **admission)
    name = 'final-sanitized.json' if os.environ.get('SANITIZE') == '1' else 'final-normal.json'
    (args.output / 'receipts' / name).write_bytes(encoded(proof))
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Add the qualified Points component to the complete Files/Scanner/RTC cohort.

No flashing or delivery. The generated full initial image erases user data if flashed.
"""
import argparse, copy, hashlib, json, os, subprocess, sys
from pathlib import Path
from current_bootfs import build, read_image
from watch_boot_order_spiffs import build as ordered_build
from check_runtime_store_admission import admit_cohort, store_digest

ROOT = Path(__file__).resolve().parents[1]
FILES_SOURCE = 'e788a761b092ed2bc54a7b7798875308939ff265'
POINTS_SOURCE = '329f1a87a888dfe45a8a9eb694020df3b3a81c3f'
POINTS_SHA = '4ee1c06b8eb191980afdd0522c5f1f2b1c05c1eeb38c8fa18e9c10cb382205b5'
RUNTIME_SOURCE = '64c8e52e46fd91e8fdafd636db04eed88f0c51a9'
TEXT_GRANT = {'capability': 'ui.text-input', 'api': 1, 'instance_id': 0}
CHANGED = {'points_in_time.elf', 'points_in_time.json', 'boot.json', 'cohort.json'}
BOOTFS = (0x2f0000, 0x800000)
BANK = (0xff2000, 0xff4000)

def require(value, message):
    if not value: raise ValueError(message)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def encoded(obj): return (json.dumps(obj, indent=2, sort_keys=True) + '\n').encode()
def git(root, *args): return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
def read_store(root): return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}

def points_union(previous, component, revision):
    require(set(component) == {'points_in_time.elf', 'points_in_time.json'}, 'Unexpected Points component member')
    expected = json.loads(previous['points_in_time.json'])
    require(expected['version'] == '0.6.12', 'Wrong Points predecessor')
    expected['version'] = '0.6.13'
    expected['requires'].append({'capability': 'ui.text-input', 'api': 1})
    require(json.loads(component['points_in_time.json']) == expected, 'Points manifest exceeds additive delta')
    boot = json.loads(previous['boot.json'])
    rows = [r for r in boot['app_capabilities'] if r['manifest'] == 'points_in_time.json']
    require(len(rows) == 1 and TEXT_GRANT not in rows[0]['grants'], 'Wrong Points authority predecessor')
    rows[0]['grants'].append(copy.deepcopy(TEXT_GRANT))
    cohort = json.loads(previous['cohort.json'])
    require(cohort['version'] == '1.1.18' and cohort['source_revision'] == FILES_SOURCE, 'Wrong Files union predecessor')
    cohort['source_revision'] = revision
    result = dict(previous, **component)
    result['boot.json'] = encoded(boot); result['cohort.json'] = encoded(cohort)
    require(set(result) == set(previous), 'Store members changed')
    require({n for n in result if result[n] != previous[n]} == CHANGED, 'Unexpected store delta')
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['candidate', 'baseline', 'points-build', 'runtime', 'output']:
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--verify-only', action='store_true'); a = p.parse_args()
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty product source')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    previous = read_store(a.candidate / 'store'); active = read_store(a.baseline)
    prior = json.loads((a.candidate / 'receipts/final-normal.json').read_text())
    require(store_digest(previous) == prior['candidate_store_sha256'], 'Candidate receipt differs')
    require(store_digest(active) == prior['active_store_sha256'], 'Delivered baseline receipt differs')
    require(len(previous) == len(active) == 113, 'Incomplete store')
    record = json.loads((a.points_build / 'points_in_time-build-record.json').read_text())
    component = {n: (a.points_build / n).read_bytes() for n in ['points_in_time.elf', 'points_in_time.json']}
    require(record['sources']['product-recipe'] == POINTS_SOURCE, 'Unqualified Points recipe')
    require(record['sources']['system-apps'] == '9550949bab67e820aa19984ef7bc20322756feb3', 'Unqualified System source')
    require(record['sources']['productivity'] == '519dba53fbfd498da0443f516445450e864c7bc3', 'Unqualified Points source')
    require(record['sha256'] == POINTS_SHA == sha(component['points_in_time.elf']), 'Points ELF receipt differs')
    require(record['bytes'] == len(component['points_in_time.elf']) == 155064, 'Points size differs')
    require(record['manifest_sha256'] == sha(component['points_in_time.json']), 'Points manifest receipt differs')
    result = points_union(previous, component, revision)
    bootfs, packing = ordered_build(result, build)
    require(packing['empty_blocks'] >= 2, 'Watch store reserve violated')
    require(read_image(bootfs, 0x510000) == result, 'Boot store round trip differs')
    require(git(a.runtime, 'rev-parse', 'HEAD') == RUNTIME_SOURCE, 'Wrong native Runtime source')
    profile = a.runtime / 'watch-file-source-profile.ini'
    require(profile.read_bytes() == (ROOT / 'docs/file-source/watch-file-source-profile.ini').read_bytes(), 'Wrong native profile')
    native = (a.candidate / 'components/firmware.elf').read_bytes()
    require(sha(native) == prior['native_elf_sha256'], 'Native ELF differs')
    firmware = (a.candidate / 'components/firmware.bin').read_bytes()
    source_image = (a.candidate / 'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin').read_bytes()
    require(sha(source_image) == prior['full_image_sha256'], 'Candidate image differs')
    require(source_image[0x10000:0x10000 + len(firmware)] == firmware, 'Native bytes differ')
    sys.path.insert(0, str(a.runtime / 'scripts'))
    from paired_bank_images import initial_bank_state, parse_record
    bank = initial_bank_state(firmware, bootfs, True)
    full = bytearray(source_image); full[slice(*BOOTFS)] = bootfs; full[slice(*BANK)] = bank
    require(len(full) == 0x1000000, 'Wrong full image size')
    for lo, hi in [(0, BOOTFS[0]), (BOOTFS[1], BANK[0]), (BANK[1], len(full))]:
        require(full[lo:hi] == source_image[lo:hi], 'Unrelated partition bytes changed')
    rec = parse_record(bank[:96], True)
    require(rec[3] == len(firmware) and rec[6] == hashlib.sha256(firmware).digest() and rec[7] == hashlib.sha256(bootfs).digest(), 'Bank digest differs')
    if not a.verify_only:
        require(not a.output.exists(), 'Use new output directory')
        (a.output / 'receipts').mkdir(parents=True); (a.output / 'components').mkdir()
        for name, raw in result.items():
            dest = a.output / 'store' / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
        for name, raw in [('bootfs.bin', bootfs), ('bank_state.bin', bank), ('firmware.bin', firmware), ('firmware.elf', native)]:
            (a.output / 'components' / name).write_bytes(raw)
        (a.output / 'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin').write_bytes(full)
        (a.output / 'receipts/packing.json').write_bytes(encoded(packing))
    require(read_store(a.output / 'store') == result, 'Written store differs')
    require((a.output / 'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin').read_bytes() == full, 'Written image differs')
    admission = admit_cohort(a.runtime, native, active, result, app_policy_rows=24, native_profile=profile)
    require(admission['elf_count'] == 55, 'Incomplete ELF admission')
    proof = dict(product='Watch', version='1.1.18', product_source=revision,
                 product_tree=git(ROOT, 'rev-parse', 'HEAD^{tree}'), points_recipe=POINTS_SOURCE,
                 source_candidate=FILES_SOURCE, changed_vs_files_candidate=sorted(CHANGED),
                 preserved_vs_files_candidate=len(previous) - len(CHANGED), free_spiffs_blocks=packing['empty_blocks'],
                 existing_app_provider_and_grant_preservation=True, full_image_sha256=sha(full),
                 full_image_bytes=len(full), full_initial_erases_data=True, hardware_verified=False, **admission)
    name = 'final-sanitized.json' if os.environ.get('SANITIZE') == '1' else 'final-normal.json'
    (a.output / 'receipts' / name).write_bytes(encoded(proof)); print(json.dumps(proof, indent=2))

if __name__ == '__main__': main()

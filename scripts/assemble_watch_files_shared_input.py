#!/usr/bin/env python3
"""Compose shared Files entry over the complete qualified Watch cohort.

The output is a held full-initial image. It erases user data if flashed.
"""
import argparse, copy, hashlib, json, os, sys
from pathlib import Path
from current_bootfs import build, read_image
from watch_boot_order_spiffs import build as ordered_build
from check_runtime_store_admission import admit_cohort, store_digest
from assemble_watch_points_union import require, sha, encoded, git, read_store, BOOTFS, BANK

ROOT = Path(__file__).resolve().parents[1]
BASE = 'ec667cd39babea571405d501f9f0ac3b5d32191c'
SYSTEM = 'e3fd26c2257cef91c8f6a7b98065b52f1db7a54d'
SYSTEM_TREE = '05ca25fa292f9420a32743b1468f7efee6d2fc78'
RUNTIME = '64c8e52e46fd91e8fdafd636db04eed88f0c51a9'
GRANT = dict(capability='ui.text-input', api=1, instance_id=0)
CHANGED = {'file_browser.elf', 'file_browser.json', 'ui-scene/driver.elf',
           'ui-scene/manifest.json', 'text-input/driver.elf',
           'text-input/manifest.json', 'boot.json', 'cohort.json'}

def component(files, hosts):
    f = json.loads((files / 'file_browser-build-record.json').read_bytes())
    h = json.loads((hosts / 'hosts-build-record.json').read_bytes())
    require(f['sources']['system'] == SYSTEM and f['version'] == '1.5.34', 'Wrong Files source')
    require(f['sources']['runtime'] == RUNTIME and f['baseline_grants_preserved'], 'Wrong Files profile')
    data = {n: (files / n).read_bytes() for n in ['file_browser.elf', 'file_browser.json']}
    require(sha(data['file_browser.elf']) == f['sha256'] and len(data['file_browser.elf']) == f['bytes'], 'Files custody differs')
    for key, dest, version in [('scene', 'ui-scene', '0.4.4'), ('text', 'text-input', '0.1.5')]:
        r = h[key]
        require(r['system_commit'] == SYSTEM and r['system_tree'] == SYSTEM_TREE and not r['working_tree_dirty'], 'Host source differs')
        require(r['version'] == version, 'Host version differs')
        for name in ['driver.elf', 'manifest.json']:
            data[dest + '/' + name] = (hosts / key / name).read_bytes()
        require(sha(data[dest + '/driver.elf']) == r['sha256'] and len(data[dest + '/driver.elf']) == r['size_bytes'], 'Host custody differs')
    require(h['scene']['defines'] == ['-DSCENE_HOST_TELEMETRY=0', '-DSCENE_HOST_WATCH_240=1'], 'Compact Watch profile lost')
    return data, f, h

def payload(old, components, revision):
    new = dict(old, **components)
    expected = json.loads(old['file_browser.json'])
    require(expected['version'] == '1.5.33', 'Wrong Files predecessor')
    expected['version'] = '1.5.34'; expected['requires'].append(dict(capability='ui.text-input', api=1))
    require(json.loads(new['file_browser.json']) == expected, 'Files authority exceeds additive grant')
    for name, version in [('ui-scene/manifest.json', '0.4.4'), ('text-input/manifest.json', '0.1.5')]:
        require(json.loads(new[name]) == dict(json.loads(old[name]), version=version), 'Host authority changed')
    boot = json.loads(old['boot.json']); original = copy.deepcopy(boot)
    rows = [r for r in boot['app_capabilities'] if r['manifest'] == 'file_browser.json']
    require(len(rows) == 1 and GRANT not in rows[0]['grants'], 'Unexpected Files authority')
    rows[0]['grants'].append(copy.deepcopy(GRANT))
    new['boot.json'] = encoded(boot)
    rows[0]['grants'].pop(); require(boot == original, 'Unrelated boot change')
    cohort = json.loads(old['cohort.json'])
    require(cohort['version'] == '1.1.18' and cohort['source_revision'] == BASE, 'Wrong baseline')
    cohort['source_revision'] = revision; new['cohort.json'] = encoded(cohort)
    require(set(new) == set(old) and {n for n in new if new[n] != old[n]} == CHANGED, 'Unexpected store delta')
    return new

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ['candidate', 'files-build', 'hosts-build', 'runtime', 'output']:
        p.add_argument('--' + n, type=Path, required=True)
    p.add_argument('--verify-only', action='store_true'); a = p.parse_args()
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty product source')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    old = read_store(a.candidate / 'store')
    prior = json.loads((a.candidate / 'receipts/final-normal.json').read_bytes())
    require(prior['product_source'] == BASE and store_digest(old) == prior['candidate_store_sha256'] and len(old) == 113, 'Wrong baseline custody')
    data, files, hosts = component(a.files_build, a.hosts_build)
    new = payload(old, data, revision)
    bootfs, packing = ordered_build(new, build)
    require(packing['empty_blocks'] >= 2, 'Watch reserve violated')
    require(read_image(bootfs, 0x510000) == new, 'Packed store roundtrip differs')
    require(git(a.runtime, 'rev-parse', 'HEAD') == RUNTIME, 'Wrong Runtime source')
    profile = a.runtime / 'watch-file-source-profile.ini'
    require(profile.read_bytes() == (ROOT / 'docs/file-source/watch-file-source-profile.ini').read_bytes(), 'Wrong native profile')
    native = (a.candidate / 'components/firmware.elf').read_bytes()
    require(sha(native) == prior['native_elf_sha256'], 'Wrong native ELF')
    firmware = (a.candidate / 'components/firmware.bin').read_bytes()
    previous = (a.candidate / 'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin').read_bytes()
    require(sha(previous) == prior['full_image_sha256'] and previous[0x10000:0x10000 + len(firmware)] == firmware, 'Wrong baseline image')
    sys.path.insert(0, str(a.runtime / 'scripts'))
    from paired_bank_images import initial_bank_state, parse_record
    bank = initial_bank_state(firmware, bootfs, True)
    full = bytearray(previous); full[slice(*BOOTFS)] = bootfs; full[slice(*BANK)] = bank
    for lo, hi in [(0, BOOTFS[0]), (BOOTFS[1], BANK[0]), (BANK[1], len(full))]:
        require(full[lo:hi] == previous[lo:hi], 'Unrelated partition changed')
    rec = parse_record(bank[:96], True)
    require(rec[3] == len(firmware) and rec[6] == hashlib.sha256(firmware).digest() and rec[7] == hashlib.sha256(bootfs).digest(), 'Bank digest differs')
    if not a.verify_only:
        require(not a.output.exists(), 'Use new output directory')
        for name, raw in new.items():
            dest = a.output / 'store' / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
        (a.output / 'components').mkdir(); (a.output / 'receipts').mkdir()
        for name, raw in [('bootfs.bin', bootfs), ('bank_state.bin', bank), ('firmware.bin', firmware), ('firmware.elf', native)]:
            (a.output / 'components' / name).write_bytes(raw)
        (a.output / 'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin').write_bytes(full)
        for name, obj in [('packing', packing), ('files-build', files), ('hosts-build', hosts)]:
            (a.output / 'receipts' / (name + '.json')).write_bytes(encoded(obj))
    require(read_store(a.output / 'store') == new and (a.output / 'WATCH-1.1.18-FULL-INITIAL-ERASES-DATA.bin').read_bytes() == full, 'Written output differs')
    admission = admit_cohort(a.runtime, native, old, new, app_policy_rows=24, native_profile=profile)
    require(admission['elf_count'] == 55, 'Incomplete admission')
    proof = dict(product='Watch', version='1.1.18', product_source=revision,
        product_tree=git(ROOT, 'rev-parse', 'HEAD^{tree}'), system_source=SYSTEM, system_tree=SYSTEM_TREE,
        source_candidate=BASE, changed_store_paths=sorted(CHANGED), preserved_store_paths=len(old)-len(CHANGED),
        free_spiffs_blocks=packing['empty_blocks'], existing_apps_and_providers_preserved=True,
        grant_delta=[dict(manifest='file_browser.json', grant=GRANT)], native_unchanged=True,
        full_image_bytes=len(full), full_image_sha256=sha(full), full_initial_erases_data=True,
        hardware_verified=False, delivered=False, delivery_hold_until_utc='2026-10-12T23:30:00Z', **admission)
    name = 'final-sanitized.json' if os.environ.get('SANITIZE') == '1' else 'final-normal.json'
    (a.output / 'receipts' / name).write_bytes(encoded(proof)); print(json.dumps(proof, indent=2))

if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Compose shared LoRa entry over the complete qualified Watch cohort.

Output is a held eight-file overlay plus verified boot-store/bank artifacts.
The complete full-initial image is reconstructed only in memory for hash and
partition-custody checks; a later integrator owns actual firmware delivery.
"""
import argparse, copy, hashlib, json, os, sys
from pathlib import Path
from current_bootfs import build, read_image
from watch_boot_order_spiffs import build as ordered_build
from check_runtime_store_admission import admit_cohort, store_digest
from assemble_watch_points_union import require, sha, encoded, git, read_store, BOOTFS, BANK

ROOT = Path(__file__).resolve().parents[1]
BASE = 'd3687db3ea6e6e5c8a36e5d01c5dfd2ba69ed453'
RUNTIME = '64c8e52e46fd91e8fdafd636db04eed88f0c51a9'
GRANT = dict(capability='ui.text-input', api=1, instance_id=0)
CHANGED = {'lora_messages.elf', 'lora_messages.json', 'ui-scene/driver.elf',
           'ui-scene/manifest.json', 'text-input/driver.elf',
           'text-input/manifest.json', 'boot.json', 'cohort.json'}

def component(files, hosts, system, system_tree):
    f = json.loads((files / 'lora_messages-build-record.json').read_bytes())
    h = json.loads((hosts / 'hosts-build-record.json').read_bytes())
    require(f['sources']['system-apps'] == system and f['version'] == '0.1.14', 'Wrong LoRa source')
    require(f['sources']['runtime'] == RUNTIME and f['baseline_grants_preserved'], 'Wrong LoRa profile')
    data = {n: (files / n).read_bytes() for n in ['lora_messages.elf', 'lora_messages.json']}
    require(sha(data['lora_messages.elf']) == f['sha256'] and len(data['lora_messages.elf']) == f['bytes'], 'LoRa custody differs')
    for key, dest, version in [('scene', 'ui-scene', '0.4.5'), ('text', 'text-input', '0.1.6')]:
        r = h[key]
        require(r['system_commit'] == system and r['system_tree'] == system_tree and not r['working_tree_dirty'], 'Host source differs')
        require(r['version'] == version, 'Host version differs')
        for name in ['driver.elf', 'manifest.json']:
            data[dest + '/' + name] = (hosts / key / name).read_bytes()
        require(sha(data[dest + '/driver.elf']) == r['sha256'] and len(data[dest + '/driver.elf']) == r['size_bytes'], 'Host custody differs')
    require(h['scene']['defines'] == ['-DSCENE_HOST_TELEMETRY=0', '-DSCENE_HOST_WATCH_240=1'], 'Compact Watch profile lost')
    return data, f, h

def payload(old, components, revision):
    new = dict(old, **components)
    expected = json.loads(old['lora_messages.json'])
    require(expected['version'] == '0.1.13', 'Wrong LoRa predecessor')
    expected['version'] = '0.1.14'; expected['requires'].append(dict(capability='ui.text-input', api=1))
    require(json.loads(new['lora_messages.json']) == expected, 'LoRa authority exceeds additive grant')
    for name, version in [('ui-scene/manifest.json', '0.4.5'), ('text-input/manifest.json', '0.1.6')]:
        require(json.loads(new[name]) == dict(json.loads(old[name]), version=version), 'Host authority changed')
    boot = json.loads(old['boot.json']); original = copy.deepcopy(boot)
    rows = [r for r in boot['app_capabilities'] if r['manifest'] == 'lora_messages.json']
    require(len(rows) == 1 and GRANT not in rows[0]['grants'], 'Unexpected LoRa authority')
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
    for n in ['candidate', 'lora-build', 'hosts-build', 'runtime', 'system', 'output']:
        p.add_argument('--' + n, type=Path, required=True)
    p.add_argument('--verify-only', action='store_true'); a = p.parse_args()
    require(not git(ROOT, 'status', '--porcelain', '--untracked-files=no'), 'Dirty product source')
    revision = git(ROOT, 'rev-parse', 'HEAD')
    old = read_store(a.candidate / 'store')
    prior = json.loads((a.candidate / 'receipts/final-normal.json').read_bytes())
    require(prior['product_source'] == BASE and store_digest(old) == prior['candidate_store_sha256'] and len(old) == 113, 'Wrong baseline custody')
    system=git(a.system, 'rev-parse', 'HEAD'); system_tree=git(a.system, 'rev-parse', 'HEAD^{tree}')
    require(not git(a.system, 'status', '--porcelain', '--untracked-files=no'), 'Dirty System source')
    data, files, hosts = component(a.lora_build, a.hosts_build, system, system_tree)
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
        (a.output / 'components').mkdir(parents=True); (a.output / 'receipts').mkdir()
        for name in sorted(CHANGED):
            dest = a.output / 'overlay' / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(new[name])
        (a.output / 'components/bootfs.bin').write_bytes(bootfs)
        (a.output / 'components/bank_state.bin').write_bytes(bank)
        for name, obj in [('packing', packing), ('lora-build', files), ('hosts-build', hosts)]:
            (a.output / 'receipts' / (name + '.json')).write_bytes(encoded(obj))
    written=read_store(a.output / 'overlay')
    require(written == {name:new[name] for name in CHANGED}, 'Written overlay differs')
    require((a.output / 'components/bootfs.bin').read_bytes()==bootfs, 'Written bootfs differs')
    admission = admit_cohort(a.runtime, native, old, new, app_policy_rows=24, native_profile=profile)
    require(admission['elf_count'] == 55, 'Incomplete admission')
    proof = dict(product='Watch', version='1.1.18', product_source=revision,
        product_tree=git(ROOT, 'rev-parse', 'HEAD^{tree}'), system_source=system, system_tree=system_tree,
        source_candidate=BASE, changed_store_paths=sorted(CHANGED), preserved_store_paths=len(old)-len(CHANGED),
        free_spiffs_blocks=packing['empty_blocks'], existing_apps_and_providers_preserved=True,
        grant_delta=[dict(manifest='lora_messages.json', grant=GRANT)], native_unchanged=True,
        full_image_bytes=len(full), full_image_sha256=sha(full), full_initial_erases_data=True, full_image_materialized=False,
        hardware_verified=False, delivered=False, delivery_hold_until_utc='2026-10-12T23:30:00Z', **admission)
    name = 'final-sanitized.json' if os.environ.get('SANITIZE') == '1' else 'final-normal.json'
    (a.output / 'receipts' / name).write_bytes(encoded(proof)); print(json.dumps(proof, indent=2))

if __name__ == '__main__': main()

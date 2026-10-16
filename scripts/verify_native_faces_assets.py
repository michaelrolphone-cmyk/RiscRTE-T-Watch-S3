#!/usr/bin/env python3
"""Independently inspect every release asset and the complete firmware store."""
import argparse, json, sys, zipfile
from pathlib import Path
from watch_native_faces import PINS, ROOT, encoded, files, git, need, require_final, sha, verify_baseline, verify_metadata
from package_native_faces import PREFIX


def manifest(data):
    result = {}
    for line in data.decode().splitlines():
        digest, name = line.split('  ', 1)
        need(name not in result and '..' not in Path(name).parts and not Path(name).is_absolute(), 'Unsafe/duplicate checksum name')
        result[name] = digest
    return result


def zip_files(path):
    with zipfile.ZipFile(path) as archive:
        need(archive.testzip() is None and len(archive.namelist()) == len(set(archive.namelist())), 'Corrupt/ambiguous ZIP')
        data = {n: archive.read(n) for n in archive.namelist()}
    hashes = manifest(data.pop('SHA256SUMS.txt'))
    need(set(hashes) == set(data) and all(sha(data[n]) == h for n, h in hashes.items()), 'ZIP checksums differ')
    return data


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('assets', 'baseline', 'runtime'): p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--source-revision', required=True); a = p.parse_args(); require_final()
    data = files(a.assets); expected = manifest(data['SHA256SUMS'])
    names = {'release.json', 'RELEASE-NOTES.txt', 'UPDATE-INSTRUCTIONS.txt', PREFIX+'-factory-erases-data-0x0.bin',
             PREFIX+'-Evidence.zip', PREFIX+'-Preserving-Update-From-1.1.37.zip'}
    need(set(expected) == names and set(data) == names | {'SHA256SUMS'}, 'Asset inventory differs')
    need(all(sha(data[n]) == h for n, h in expected.items()), 'Asset checksum differs')
    release = json.loads(data['release.json'])
    need(release['source_revision'] == a.source_revision and release['version'] == PINS['version'], 'Product source differs')
    for name in ('runtime', 'shared', 'system', 'utilities'): need(release[name+'_revision'] == PINS[name+'_revision'], 'Dependency revision differs')
    baseline = a.baseline.read_bytes(); factory = data[PREFIX+'-factory-erases-data-0x0.bin']
    need(sha(baseline) == PINS['baseline_sha256'] == release['baseline_sha256'], 'Baseline differs')
    need(len(factory) == len(baseline) == 0x1000000 and sha(factory) == release['factory_sha256'], 'Factory differs')
    from read_only_spiffs import read_image
    before = read_image(baseline[0x2f0000:0x840000], 0x550000); after = read_image(factory[0x2f0000:0x840000], 0x550000)
    verify_baseline(before)
    evidence = zip_files(a.assets/(PREFIX+'-Evidence.zip'))
    need(evidence['release.json'] == data['release.json'] and json.loads(evidence['source-pins.json']) == PINS, 'Evidence source binding differs')
    firmware = evidence['firmware.bin']; elf = evidence['firmware.elf']
    need(sha(firmware) == release['firmware_sha256'] and sha(elf) == release['native_elf_sha256'], 'Native digests differ')
    need(firmware == baseline[0x10000:0x10000+len(firmware)] == factory[0x10000:0x10000+len(firmware)], 'Native bytes changed')
    changed = verify_metadata(before, after, firmware, a.source_revision)
    need(evidence['default.elf'] == after['default.elf'] and evidence['default.json'] == after['default.json'], 'Packaged Home differs')
    need(manifest(evidence['store-SHA256SUMS.txt']) == {n: sha(v) for n, v in after.items()}, 'Complete store hashes differ')
    need(sha(factory[0x2f0000:0x840000]) == release['store_sha256'], 'Store digest differs')
    sys.path.insert(0, str(a.runtime.resolve()/'scripts'))
    from paired_bank_images import initial_bank_state
    state = initial_bank_state(firmware, factory[0x2f0000:0x840000], True, True)
    need(factory[0xff2000:0xff2000+len(state)] == state, 'Bank state differs')
    for start, end in ((0, 0x2f0000), (0x840000, 0xff2000), (0xff2000+len(state), 0x1000000)):
        need(factory[start:end] == baseline[start:end], 'Protected factory region differs')
    for name in ('admission.json', 'admission-sanitized.json'):
        report = json.loads(evidence[name])
        need(report['prepared'] and report['cohort_validated'] and report['elf_count'] == 59 and report['hardware_calls'] == report['storage_calls'] == 0, 'Admission proof differs')
    proof = json.loads(evidence['preservation.json'])
    need(len(proof['cases']) == 272 and proof['candidate_store_sha256'] == release['store_sha256'] and proof['candidate_native_sha256'] == sha(firmware), 'Preservation proof differs')
    kit = zip_files(a.assets/(PREFIX+'-Preserving-Update-From-1.1.37.zip'))
    need(kit['baseline-1.1.37.bin'] == baseline and kit['candidate-1.1.38.bin'] == factory, 'Preserving kit payloads differ')
    for name in ('prepare_preserving_update.py', 'paired_bank_images.py', 'spiffs_image.py'):
        need(kit[name] == git(a.runtime, 'show', PINS['runtime_revision']+':scripts/'+name), 'Preserving helper source differs')
    print(json.dumps(dict(version=PINS['version'], source_revision=a.source_revision, all_assets_verified=len(data),
                         factory_sha256=sha(factory), home_sha256=sha(after['default.elf']), changed_store_files=changed,
                         unchanged_store_files=118, admitted_elfs=59, preserving_update_cases=272,
                         native_bytes_preserved=True, device_accessed=False, hardware_tested=False), indent=2))


if __name__ == '__main__': main()

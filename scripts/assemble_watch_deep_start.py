#!/usr/bin/env python3
"""Assemble and admit Watch 1.1.13 from exact delivered 1.1.12.

Changes only the source-qualified native runtime and default Clock application.
No device access, upload or flashing. These checks run during image manufacture,
never in the device wake path. --verify-only admits an existing assembly.
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECIPE = ROOT / 'docs/watch-1.1.13-deep-start/source-recipe.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def clean(path):
    assert not git(path, 'status', '--porcelain', '--untracked-files=no'), 'Dirty selected source'
    return git(path, 'rev-parse', 'HEAD')


def record(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


p = argparse.ArgumentParser(description=__doc__)
for name in ('runtime', 'system', 'native', 'clock', 'baseline-image', 'output'):
    p.add_argument('--' + name, type=pathlib.Path, required=True)
p.add_argument('--verify-only', action='store_true')
a = p.parse_args()
sys.path.insert(0, str(ROOT / 'scripts'))
from read_only_spiffs import read_image
from check_runtime_store_admission import admit_cohort

r = json.loads(RECIPE.read_text())
product = clean(ROOT)
assert clean(a.runtime) == r['native']['runtime_commit']
assert git(a.runtime, 'rev-parse', 'HEAD^{tree}') == r['native']['runtime_tree']
assert clean(a.system) == r['system_assembly_source']
for name, expected in r['clock']['source_files'].items():
    assert sha((ROOT / name).read_bytes()) == expected, name
base = a.baseline_image.read_bytes()
assert len(base) == 0x1000000 and sha(base) == r['predecessor']['full_image_sha256']
active = read_image(base[0x2f0000:0x800000], 0x510000)
assert len(active) == 111 and json.loads(active['cohort.json'])['version'] == '1.1.12'
boot = json.loads(active['boot.json'])
assert len(boot['app_capabilities']) == 25 and len(boot['drivers']) == 30
assert json.loads(active['file_browser.json'])['version'] == '1.5.30'
assert not any('image_source' in row for row in boot['app_capabilities'])
for folder, expected_files in ((a.native, r['native']['files']), (a.clock, r['clock']['files'])):
    for name, expected in expected_files.items():
        raw = (folder / name).read_bytes()
        assert len(raw) == expected['bytes'] and sha(raw) == expected['sha256'], name
clock_build = json.loads((a.clock / 'build.json').read_text())
assert clock_build['delivered_reproduction']['sha256'] == r['clock']['original_reproduction_sha256']
assert sha(active['default.elf']) == r['clock']['predecessor_default_sha256']
assert clock_build['changed_dependency_keys'] == r['clock']['changed_dependency_keys']
assert clock_build['fast_clock']['sha256'] == sha((a.clock / 'default.elf').read_bytes())
assert clock_build['manifest']['sha256'] == sha((a.clock / 'default.json').read_bytes())
assert clock_build['clock_return_wrapper_changed'] is False
before_manifest = json.loads(active['default.json'])
after_manifest = json.loads((a.clock / 'default.json').read_bytes())
assert after_manifest == dict(before_manifest, version=r['clock']['version']), 'Clock grants or contract changed'
for name, offset in [('bootloader.bin', 0), ('partitions.bin', 0x8000)]:
    raw = (a.native / name).read_bytes()
    assert base[offset:offset+len(raw)] == raw, 'Boot component changed'
if not a.verify_only:
    assert not a.output.exists(), 'Choose a new assembly output'
    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        store = work / 'store'
        store.mkdir()
        for name, raw in active.items():
            if name in ('default.elf', 'default.json'):
                raw = (a.clock / name).read_bytes()
            f = store / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(raw)
        initial = work / 'appdata.bin'
        initial.write_bytes(base[0x270000:0x2f0000])
        subprocess.run([sys.executable, str(a.system / 'scripts/assemble_shared_files_bundle.py'),
            '--runtime', str(a.runtime.resolve()), '--tools', str(ROOT), '--native', str(a.native.resolve()),
            '--store', str(store), '--initial-image', str(initial), '--output', str(a.output.resolve()),
            '--product-metadata', str(ROOT / 'docs/shared-files/product.json'), '--target', 'watch',
            '--product-source', product], check=True)
full_path = a.output / 'WATCH-1.1.13-Shared-Files-FULL-INITIAL-ERASES-DATA.bin'
full = full_path.read_bytes()
assert len(full) == 0x1000000
candidate = read_image(full[0x2f0000:0x800000], 0x510000)
assert set(candidate) == set(active)
changed = sorted(n for n in active if active[n] != candidate[n])
assert changed == ['cohort.json', 'default.elf', 'default.json'], changed
cohort = json.loads(candidate['cohort.json'])
expected = dict(json.loads(active['cohort.json']), version='1.1.13', source_revision=product,
                runtime_version=r['native']['runtime_version'],
                firmware_sha256=sha((a.native / 'firmware.bin').read_bytes()),
                firmware_size=(a.native / 'firmware.bin').stat().st_size)
assert cohort == expected
for name in ('default.elf', 'default.json'):
    assert candidate[name] == (a.clock / name).read_bytes()
allowed = [(0x10000, 0x270000), (0x2f0000, 0x800000), (0xff2000, 0xff4000)]
cursor = 0
for begin, end in allowed:
    assert full[cursor:begin] == base[cursor:begin], 'Unrelated flash range changed'
    cursor = end
assert full[cursor:] == base[cursor:]
proof = admit_cohort(a.runtime, (a.native / 'firmware.elf').read_bytes(), active, candidate,
                     app_policy_rows=24, native_profile=a.native / 'crown-wake-profile.ini')
assert proof['prepared'] and proof['cohort_validated'] and proof['elf_count'] == 54
assert proof['hardware_calls'] == proof['storage_calls'] == 0
proof.update(full_image_sha256=sha(full), product_source=product,
             native_source=r['native']['runtime_commit'], clock_source=r['clock']['product_commit'],
             predecessor=r['predecessor'], unchanged_store_files=108, changed_store_files=changed,
             all_other_app_provider_bytes_preserved=True, clock_grants_preserved=True,
             unchanged_flash_outside_native_bootfs_bankstate=True,
             sanitizers='ASan+UBSan; leak detection disabled under ptrace' if os.getenv('SANITIZE') == '1' else 'none',
             hardware_verified=False, initial_flash_erases_internal_data=True)
name = 'final-image-admission-sanitizer.json' if os.getenv('SANITIZE') == '1' else 'final-image-admission.json'
record(a.output / 'receipts' / name, proof)
record(a.output / 'receipts/source-recipe.json', r)
record(a.output / 'receipts/clock-build.json', clock_build)
print(json.dumps(proof, indent=2))

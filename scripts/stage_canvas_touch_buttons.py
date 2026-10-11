#!/usr/bin/env python3
"""Stage a narrow successor from verified Watch 1.1.0 store bytes.

Only touch and Buttons ELF/manifest pairs change. This deliberately does not
emit firmware: full source-bound admission and power qualification are separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from read_only_spiffs import read_image

BASELINE_SHA256 = 'c4827bc7f2157cc14fd041b9c617f5f716264f8c1ee28d7415b5175782d0263a'
BASELINE_BYTES = 16777216

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):
    return json.loads(p.read_text())

p = argparse.ArgumentParser(description=__doc__)
for name in ('baseline', 'baseline-bin', 'baseline-receipt', 'touch', 'buttons', 'output'):
    p.add_argument('--' + name, type=Path, required=True)
a = p.parse_args()
base = a.baseline.resolve()
raw = a.baseline_bin.read_bytes()
assert len(raw) == BASELINE_BYTES, 'Authoritative full BIN size differs'
assert hashlib.sha256(raw).hexdigest() == BASELINE_SHA256, 'Authoritative Watch 1.1.0 full BIN hash differs'
decoded = read_image(raw[0x2f0000:0x800000], 0x510000)
assert len(decoded) == 105, 'Authoritative store file count differs'
# The receipt must come from independently verified delivery custody, not a
# generated inventory used as a substitute for missing baseline bytes.
custody = read(a.baseline_receipt)
assert custody['version'] == '1.1.0'
inventory = {str(f.relative_to(base)): digest(f) for f in base.rglob('*') if f.is_file()}
assert inventory == {n: hashlib.sha256(b).hexdigest() for n, b in decoded.items()}, 'Extracted store differs from independently decoded full BIN'
assert inventory == {n: r['sha256'] for n, r in custody['store_files'].items()}
boot = read(base / 'boot.json')
assert len(boot['app_capabilities']) == 25 and len(boot['drivers']) == 27
assert len([n for n in inventory if n.endswith('.elf')]) == 51
for name in ('default', 'clock'):
    assert read(base / (name + '.json'))['version'] == '0.11.2'
for name in ('model_viewer', 'lists', 'contexts'):
    assert name + '.elf' in inventory
assert read(base / 'ble_buttons.json')['version'] == '0.1.14'
touch_rows = [r['manifest'] for r in boot['drivers'] if read(base / r['manifest'])['id'] == 'twatch-touch']
assert len(touch_rows) == 1
touch_manifest = Path(touch_rows[0])
old_touch = read(base / touch_manifest)
assert old_touch['version'] == '0.2.1'
new_touch = read(a.touch / 'manifest.json')
assert new_touch['version'] == '0.2.2'
assert {k:v for k,v in new_touch.items() if k != 'version'} == {k:v for k,v in old_touch.items() if k != 'version'}
assert digest(a.touch / 'driver.elf') == read(a.touch / 'qualification.json')['sha256']
buttons = read(a.buttons / 'build.json')
assert buttons['version'] == '0.1.22'
assert digest(a.buttons / 'ble_buttons.elf') == buttons['sha256']
assert not a.output.exists()
shutil.copytree(base, a.output)
for name in ('driver.elf', 'manifest.json'):
    shutil.copyfile(a.touch / name, a.output / touch_manifest.parent / name)
shutil.copyfile(a.buttons / 'ble_buttons.elf', a.output / 'ble_buttons.elf')
m = read(base / 'ble_buttons.json')
m['version'] = '0.1.22'
(a.output / 'ble_buttons.json').write_text(json.dumps(m, indent=2) + '\n')
after = {str(f.relative_to(a.output)): digest(f) for f in a.output.rglob('*') if f.is_file()}
changed = {n for n in inventory if inventory[n] != after[n]}
expected = {str(touch_manifest), str(touch_manifest.parent / 'driver.elf'), 'ble_buttons.json', 'ble_buttons.elf'}
assert set(after) == set(inventory) and changed == expected
receipt = {'schema': 1, 'baseline_version': '1.1.0', 'baseline_receipt_sha256': digest(a.baseline_receipt),
           'baseline_bin_sha256': BASELINE_SHA256, 'baseline_bin_bytes': BASELINE_BYTES,
           'independently_decoded_store_files': len(decoded),
           'baseline_files': inventory, 'stage_files': after, 'changed_paths': sorted(changed),
           'app_count': 25, 'provider_count': 27, 'elf_count': 51,
           'buttons_build': buttons, 'touch_build': read(a.touch / 'qualification.json'),
           'whole_cohort_qualified': False, 'hardware_tested': False}
a.output.with_name(a.output.name + '-stage.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('Staged four changed paths; all other store bytes preserved. Full-image qualification still required.')

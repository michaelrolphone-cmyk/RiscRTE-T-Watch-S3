#!/usr/bin/env python3
"""Exact-source native Home successor; immutable native and non-Home payloads."""
import argparse, copy, json, re, subprocess, sys
from pathlib import Path
from shared_native_ui import clean, encoded, files, git, need, sha, verify_wake, write

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/native-faces'
PINS = json.loads((DOCS / 'source-pins.json').read_text())


def require_final():
    need(PINS['finalized'] is True, 'Final Home source closure pending')
    need((PINS['version'], PINS['baseline_version'], PINS['home_version']) == ('1.1.38', '1.1.37', '0.16.0'), 'Wrong successor versions')
    for key in ('runtime_revision', 'baseline_source', 'shared_revision', 'system_revision', 'utilities_revision'):
        need(re.fullmatch('[0-9a-f]{40}', PINS[key] or ''), 'Immutable revision required: ' + key)
    need(re.fullmatch('[0-9a-f]{64}', PINS['home_sha256'] or ''), 'Exact Home digest required')
    need(re.fullmatch('[0-9a-f]{64}', PINS['compiler_sha256'] or ''), 'Exact compiler digest required')
    need(PINS['changed_store_files'] == ['cohort.json', 'default.elf', 'default.json'], 'Unexpected replacement scope')
    need(PINS['provisioning_version_reserved'] == '1.1.34', 'Provisioning reservation changed')


def verify_baseline(store):
    need({n: sha(v) for n, v in store.items()} == PINS['baseline_files'], 'Exact official 1.1.37 store required')
    need(len(store) == 121 and sum(n.endswith('.elf') for n in store) == 59, 'Incomplete baseline')
    cohort = json.loads(store['cohort.json'])
    need(cohort['version'] == PINS['baseline_version'] and cohort['source_revision'] == PINS['baseline_source'], 'Wrong baseline cohort')
    need(json.loads(store['default.json'])['version'] == '0.15.4', 'Wrong Home predecessor')
    return verify_wake(store)


def home_manifest(before):
    manifest = json.loads(before)
    manifest['version'] = PINS['home_version']
    return manifest


def verify_metadata(before, after, firmware, revision):
    need(set(before) == set(after), 'Store inventory changed')
    changed = sorted(n for n in before if before[n] != after[n])
    need(changed == PINS['changed_store_files'], 'Unexpected store changes: ' + str(changed))
    need(json.loads(after['default.json']) == home_manifest(before['default.json']), 'Home authority changed')
    need(sha(after['default.elf']) == PINS['home_sha256'] and len(after['default.elf']) == PINS['home_bytes'], 'Home candidate differs')
    cohort = json.loads(before['cohort.json'])
    need(cohort['firmware_sha256'] == sha(firmware) and cohort['firmware_size'] == len(firmware), 'Native firmware changed')
    cohort.update(version=PINS['version'], source_revision=revision)
    need(after['cohort.json'] == encoded(cohort), 'Cohort changed beyond product version/source')
    for name in before:
        if name not in changed:
            need(after[name] == before[name], 'Preserved file differs: ' + name)
    verify_wake(after)
    return changed


def native_stage(runtime):
    clean(runtime, PINS['runtime_revision'])
    for name in ('watch-expanded-profile.ini', 'watch-native-ui.ini'):
        data = (ROOT / 'native/shared-ui-profile' / name).read_bytes()
        target = runtime / name
        need(not target.exists() or target.read_bytes() == data, 'Conflicting native profile: ' + name)
        target.write_bytes(data)


def compose(baseline_store, home, firmware, revision, output):
    require_final(); clean(ROOT, revision)
    need(not output.exists(), 'Output must be new')
    before = files(baseline_store); wake = verify_baseline(before); store = copy.deepcopy(before)
    binary = (home / 'default.elf').read_bytes()
    need(binary[:7] == b'\x7fELF\x01\x01\x01', 'Invalid target ELF')
    built = json.loads((home / 'default.json').read_text())
    deployed = home_manifest(before['default.json'])
    need(all(built[k] == deployed[k] for k in ('id', 'version', 'architecture', 'entry', 'file_name', 'type')), 'Built Home identity differs')
    need(all(row in deployed['requires'] for row in built['requires']), 'Built Home requires undeclared authority')
    store['default.elf'] = binary; store['default.json'] = encoded(home_manifest(before['default.json']))
    cohort = json.loads(before['cohort.json']); cohort.update(version=PINS['version'], source_revision=revision)
    store['cohort.json'] = encoded(cohort)
    changed = verify_metadata(before, store, firmware, revision)
    from current_bootfs import build
    from read_only_spiffs import read_image
    image, packing = build(store, size=0x550000)
    need(read_image(image, 0x550000) == store, 'Store packing differs')
    write(output / 'store', store); (output / 'store.bin').write_bytes(image)
    report = dict(version=PINS['version'], baseline=PINS['baseline_version'], changed_store_files=changed,
                  unchanged_files=len(store)-len(changed), elf_count=59, store_sha256=sha(image),
                  native_sha256=sha(firmware), home_sha256=sha(binary), home_policy=wake, packing=packing,
                  native_bytes_preserved=True, hardware_tested=False, device_accessed=False)
    (output / 'composition.json').write_bytes(encoded(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args(); native_stage(args.runtime.resolve())

#!/usr/bin/env python3
"""Strict official-1.1.35 successor composition; no device or publication I/O."""
import argparse, copy, json, re, subprocess
from pathlib import Path
from shared_native_ui import clean, encoded, files, git, need, sha, verify_wake, write

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/shared-app-repair'
PINS = json.loads((DOCS / 'source-pins.json').read_text())


def require_final():
    need(PINS['finalized'] is True, 'Final repaired-app closure pending')
    need(PINS['version'] == '1.1.36' and PINS['baseline_version'] == '1.1.35', 'Wrong successor versions')
    need(PINS['provisioning_version_reserved'] == '1.1.34', 'Provisioning reservation changed')
    for key in ('runtime_revision', 'apps_system_revision', 'preserved_springboard_system_revision', 'baseline_source', 'replay_source_revision'):
        need(isinstance(PINS[key],str) and re.fullmatch('[0-9a-f]{40}', PINS[key]), 'Immutable source required: ' + key)
    need(sha((DOCS / 'app-manifest.json').read_bytes()) == PINS['app_manifest_sha256'], 'Final app manifest differs')
    manifest = json.loads((DOCS / 'app-manifest.json').read_text())
    need(manifest['complete'] is True and manifest['product'] == 'twatch' and manifest['all_transitive_inputs_verified'] is True, 'Incomplete source closure')
    need(manifest['system_source'] == PINS['apps_system_revision'] and manifest['runtime_repair'] == PINS['runtime_revision'], 'App/native source closure differs')
    need(set(manifest['apps']) == set(PINS['expected_repaired_apps']), 'Unexpected repaired app set')
    for name, row in manifest['apps'].items():
        need(row['deployed_sha256'] == PINS['baseline_files'][name+'.elf'], 'App predecessor differs: '+name)


def verify_baseline(store):
    need({n: sha(v) for n, v in store.items()} == PINS['baseline_files'], 'Exact official 1.1.35 store required')
    need(len(store) == 121 and sum(n.endswith('.elf') for n in store) == 59, 'Incomplete official baseline')
    cohort = json.loads(store['cohort.json'])
    need(cohort['version'] == '1.1.35' and cohort['source_revision'] == PINS['baseline_source'], 'Wrong official cohort')
    need(sha(store['springboard.elf']) == PINS['preserved_springboard_sha256'], 'Official Springboard differs')
    return verify_wake(store)


def next_manifest(before):
    value = json.loads(before)
    version = value['version'].split('.')
    need(len(version) == 3 and all(x.isdigit() for x in version), 'Unsupported app version')
    version[-1] = str(int(version[-1]) + 1)
    value['version'] = '.'.join(version)
    return value


def verify_metadata(before, after, firmware, revision):
    need(set(after) == set(before), 'Store inventory changed')
    changed = sorted(n for n in before if before[n] != after[n])
    need(changed == PINS['changed_store_files'], 'Unexpected changed store files')
    for name in PINS['expected_repaired_apps']:
        need(json.loads(after[name + '.json']) == next_manifest(before[name + '.json']), 'App manifest authority changed: ' + name)
    cohort = json.loads(before['cohort.json'])
    cohort.update(version=PINS['version'], source_revision=revision, runtime_version=PINS['runtime_version'],
                  firmware_sha256=sha(firmware), firmware_size=len(firmware))
    need(after['cohort.json'] == encoded(cohort), 'Cohort changed beyond successor source/firmware fields')
    for name in ('springboard.elf', 'springboard.json', 'default.elf', 'default.json', 'boot.json'):
        need(after[name] == before[name], 'Preserved UI/Home policy changed: ' + name)
    return changed


def native_stage(runtime):
    clean(runtime, PINS['runtime_revision'])
    subprocess.run(['git', '-C', str(runtime), 'merge-base', '--is-ancestor', PINS['baseline_runtime'], PINS['runtime_revision']], check=True)
    expected = git(runtime, 'show', PINS['profile_origin_runtime'] + ':watch-expanded-profile.ini')
    need((ROOT / 'native/shared-ui-profile/watch-expanded-profile.ini').read_bytes() == expected, 'Released native profile differs')
    for name in ('watch-expanded-profile.ini', 'watch-native-ui.ini'):
        value = (ROOT / 'native/shared-ui-profile' / name).read_bytes()
        target = runtime / name
        need(not target.exists() or target.read_bytes() == value, 'Conflicting profile: ' + name)
        target.write_bytes(value)


def compose(a):
    require_final(); clean(ROOT, a.source_revision)
    need(re.fullmatch('[0-9a-f]{40}', a.source_revision), 'Full product revision required')
    need(not a.output.exists(), 'Output must be new')
    before = files(a.baseline_store); wake = verify_baseline(before); store = copy.deepcopy(before)
    manifest = json.loads((DOCS / 'app-manifest.json').read_text())
    need(manifest['complete'] is True and manifest['product'] == 'twatch', 'Incomplete or wrong app closure')
    need(set(manifest['apps']) == set(PINS['expected_repaired_apps']), 'Wrong app closure members')
    for name, row in manifest['apps'].items():
        old = before[name + '.elf']; elf = (a.apps / (name + '.elf')).read_bytes()
        need(row['deployed_sha256'] == sha(old), 'App baseline mismatch: ' + name)
        need(sha(elf) == row['sha256'] and len(elf) == row['bytes'], 'App candidate differs: ' + name)
        need(elf[:7] == b'\x7fELF\x01\x01\x01', 'Invalid ELF: ' + name)
        store[name + '.elf'] = elf
        store[name + '.json'] = encoded(next_manifest(before[name + '.json']))
    firmware = a.firmware.read_bytes()
    need(24 < len(firmware) <= 0x260000, 'Native firmware size differs')
    need(set(re.findall(rb'RTE_SOURCE=([^\x00\s]+)', firmware)) == {PINS['runtime_revision'].encode()}, 'Native source marker differs')
    cohort = json.loads(before['cohort.json'])
    cohort.update(version=PINS['version'], source_revision=a.source_revision, runtime_version=PINS['runtime_version'],
                  firmware_sha256=sha(firmware), firmware_size=len(firmware))
    store['cohort.json'] = encoded(cohort)
    changed = verify_metadata(before, store, firmware, a.source_revision)
    from current_bootfs import build
    from read_only_spiffs import read_image
    image, packing = build(store, size=0x550000)
    need(read_image(image, 0x550000) == store, 'Store packing differs')
    write(a.output / 'store', store); (a.output / 'store.bin').write_bytes(image)
    report = dict(version=PINS['version'], baseline=PINS['baseline_version'], changed_store_files=changed,
                  unchanged_files=len(store)-len(changed), elf_count=59, store_sha256=sha(image), native_sha256=sha(firmware),
                  app_manifest_sha256=PINS['app_manifest_sha256'], preserved_springboard_sha256=sha(store['springboard.elf']),
                  home_policy=wake, packing=packing, hardware_tested=False, assets_published=False)
    (a.output / 'composition.json').write_bytes(encoded(report))
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('native-stage'); p.add_argument('--runtime', type=Path, required=True)
    p = commands.add_parser('compose')
    for name in ('baseline-store', 'apps', 'firmware', 'output'): p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--source-revision', required=True)
    a = parser.parse_args()
    if a.command == 'native-stage': native_stage(a.runtime.resolve())
    else: compose(a)


if __name__ == '__main__': main()

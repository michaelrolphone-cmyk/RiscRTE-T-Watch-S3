#!/usr/bin/env python3
"""Exact-source .38 to .39 launch-brightness composition; preserve native and Home."""
import copy, json, re
from pathlib import Path
from shared_native_ui import clean, encoded, files, git, need, sha, verify_wake, write

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/launch-brightness'
PINS = json.loads((DOCS / 'source-pins.json').read_text())
HANDOFF = json.loads((DOCS / 'integration-handoff.json').read_text())


def require_final():
    need(PINS['finalized'] is True, 'Exact .38 baseline closure pending')
    need((PINS['version'], PINS['baseline_version'], PINS['home_version']) == ('1.1.39', '1.1.38', '0.16.0'), 'Wrong successor versions')
    need(PINS['provisioning_version_reserved'] == '1.1.34', 'Provisioning reservation changed')
    for key in ('runtime_revision', 'baseline_source', 'producer_revision', 'adapter_revision', 'home_shared_revision', 'qualification_utilities_revision', 'bridges_revision', 'native_evidence_origin_source'):
        need(re.fullmatch('[0-9a-f]{40}', PINS[key] or ''), 'Immutable revision required: '+key)
    for key in ('baseline_sha256', 'compiler_sha256', 'home_sha256', 'handoff_sha256'):
        need(re.fullmatch('[0-9a-f]{64}', PINS[key] or ''), 'Exact digest required: '+key)
    need(sha((DOCS/'integration-handoff.json').read_bytes()) == PINS['handoff_sha256'], 'Producer handoff differs')
    need(HANDOFF['product'] == 'twatch' and HANDOFF['version'] == PINS['version'] and HANDOFF['baseline_version'] == PINS['baseline_version'], 'Wrong handoff identity')
    need(HANDOFF['producer_commit'] == PINS['producer_revision'] and HANDOFF['adapter_source'] == PINS['adapter_revision'] and HANDOFF['runtime_revision'] == PINS['runtime_revision'], 'Producer source closure differs')
    need(all(HANDOFF[k] is False for k in ('native_changed', 'home_changed', 'springboard_changed')), 'Unexpected replacement scope')
    need(sorted(HANDOFF['apps']) == PINS['expected_replaced_apps'] and len(HANDOFF['apps']) == 18, 'Incomplete 18-app closure')
    expected = sorted(['cohort.json']+[n+ext for n in HANDOFF['apps'] for ext in ('.elf', '.json')])
    need(PINS['changed_store_files'] == HANDOFF['changed_store_files'] == expected, 'Unexpected replacement scope')
    for name, row in HANDOFF['apps'].items():
        need(row['old_sha256'] == PINS['baseline_files'][name+'.elf'] and row['manifest_changes'] == ['version'], 'App predecessor or authority differs: '+name)


def verify_baseline(store):
    need({n:sha(v) for n,v in store.items()} == PINS['baseline_files'], 'Exact pinned 1.1.38 store required')
    need(len(store) == 121 and sum(n.endswith('.elf') for n in store) == 59, 'Incomplete baseline')
    cohort = json.loads(store['cohort.json'])
    need(cohort['version'] == PINS['baseline_version'] and cohort['source_revision'] == PINS['baseline_source'], 'Wrong baseline cohort')
    need(sha(store['default.elf']) == PINS['home_sha256'] and len(store['default.elf']) == PINS['home_bytes'], 'Native Home differs')
    need(json.loads(store['default.json'])['version'] == PINS['home_version'], 'Native Home version differs')
    need(sha(store['springboard.elf']) == PINS['preserved_springboard_sha256'], 'Springboard differs')
    for name,row in HANDOFF['apps'].items():
        need(sha(store[name+'.elf']) == row['old_sha256'] and len(store[name+'.elf']) == row['old_bytes'], 'Baseline app differs: '+name)
        need(json.loads(store[name+'.json'])['version'] == row['old_version'], 'Baseline app version differs: '+name)
    return verify_wake(store)


def app_manifest(name, before):
    manifest = json.loads(before)
    need(manifest['version'] == HANDOFF['apps'][name]['old_version'], 'Wrong predecessor: '+name)
    version = manifest['version'].split('.')
    need(len(version) == 3 and all(x.isdigit() for x in version), 'Unsupported app version')
    version[-1] = str(int(version[-1])+1)
    need('.'.join(version) == HANDOFF['apps'][name]['version'], 'Unexpected app version increment')
    manifest['version'] = HANDOFF['apps'][name]['version']
    return manifest


def verify_metadata(before, after, firmware, revision):
    need(re.fullmatch('[0-9a-f]{40}', revision), 'Exact product revision required')
    need(set(before) == set(after), 'Store inventory changed')
    changed = sorted(n for n in before if before[n] != after[n])
    need(changed == PINS['changed_store_files'], 'Unexpected store changes: '+str(changed))
    for name,row in HANDOFF['apps'].items():
        need(after[name+'.json'] == encoded(app_manifest(name, before[name+'.json'])), 'App authority or encoding changed: '+name)
        need(sha(after[name+'.elf']) == row['sha256'] and len(after[name+'.elf']) == row['bytes'], 'App payload differs: '+name)
    cohort = json.loads(before['cohort.json'])
    need(cohort['firmware_sha256'] == sha(firmware) and cohort['firmware_size'] == len(firmware), 'Native firmware changed')
    cohort.update(version=PINS['version'], source_revision=revision)
    need(after['cohort.json'] == encoded(cohort), 'Cohort changed beyond version/source')
    for name in before:
        if name not in changed: need(after[name] == before[name], 'Preserved file differs: '+name)
    verify_wake(after)
    return changed


def native_stage(runtime):
    clean(runtime, PINS['runtime_revision'])
    for name in ('watch-expanded-profile.ini', 'watch-native-ui.ini'):
        data = (ROOT/'native/shared-ui-profile'/name).read_bytes(); target = runtime/name
        need(not target.exists() or target.read_bytes() == data, 'Conflicting native profile: '+name)
        target.write_bytes(data)


def compose(baseline_store, apps, firmware, revision, output):
    require_final(); clean(ROOT, revision); need(not output.exists(), 'Output must be new')
    before = files(baseline_store); wake = verify_baseline(before); store = copy.deepcopy(before)
    for name,row in HANDOFF['apps'].items():
        binary = (apps/(name+'.elf')).read_bytes()
        need(binary[:7] == b'\x7fELF\x01\x01\x01', 'Invalid ELF: '+name)
        store[name+'.elf'] = binary; store[name+'.json'] = encoded(app_manifest(name, before[name+'.json']))
    cohort = json.loads(before['cohort.json']); cohort.update(version=PINS['version'], source_revision=revision)
    store['cohort.json'] = encoded(cohort); changed = verify_metadata(before, store, firmware, revision)
    from current_bootfs import build
    from read_only_spiffs import read_image
    image, packing = build(store, size=0x550000)
    need(read_image(image, 0x550000) == store, 'Store packing differs')
    write(output/'store', store); (output/'store.bin').write_bytes(image)
    report = dict(version=PINS['version'], baseline=PINS['baseline_version'], changed_store_files=changed,
                  unchanged_files=len(store)-len(changed), elf_count=59, store_sha256=sha(image),
                  native_sha256=sha(firmware), home_sha256=sha(store['default.elf']), home_policy=wake,
                  packing=packing, native_bytes_preserved=True, home_bytes_preserved=True,
                  hardware_tested=False, device_accessed=False)
    (output/'composition.json').write_bytes(encoded(report)); return report

#!/usr/bin/env python3
"""Read-only qualification of the immutable, retained T-Watch 1.1.46 product.

Downloads public inputs, never writes a device, release, catalog or source recipe.
Artifact and structural acceptance is explicitly not behavior or hardware proof.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

PRODUCT = 'ab9ff33975680c5bb8d9a2e7ed346d0300732a4e'
RUNTIME = '48229bd1593a2e24e95bf4537b495ee615990fd3'
BASE = 'https://github.com/michaelrolphone-cmyk/RiscRTE-T-Watch-S3/releases/download/test-provisioning-1.1.46/'
ASSETS = {
    'TWatch-1.1.46-Provisioning-factory-erases-data-0x0.bin': (16777216, 'e132a6276cd444cd41482ecfcc2043296b2acf02ef882acc83ba1af4c76edff6'),
    'firmware.bin': (1624560, 'cd8f7f51d9c604e4f3b12b5f54dcc83817b812baa973b5862321a94e951f0034'),
    'store.bin': (5570560, 'e50d26000dc0366be61abbf480cd39ee98323ea5ef489536baf0cf7c4097b126'),
    'TWatch-1.1.46-Provisioning-Evidence.zip': (21862871, '07eecd7b47ce3368f89025981df048408ba84a981285415e9f56fd66902d18e3'),
    'qualification.json': (1414901, '2933128fa25f11e73774d3f3ba68baa4a1124670967490780cfb14fcf48371b4'),
    'source-lock.json': (10148, 'a678bc8445ec5b0b0d573986dc47a81ffbc78599c8bd2be9c7ea62f31a78dec6'),
    'ci-provenance.zip': (6832, '8e7b6a641d0008ec989d05465a49aad17a34509978e666eb2f03301f904a3734'),
    'TESTING.txt': (2313, '68964214c3d7c0834b788162fde2cffc4f49433b3388dece8e00f718a4833de4'),
}
SETTINGS = (142164, 'fa1c87a1e971d1d64a5d65d8e655d898bbd227a42364f639517ff53ea2966e3e')
HOME = (554744, 'f376d722b07c52184cf4cd27df306054920cdf742ccb8bdd4d476a08e35aef54')

def need(value, message):
    if not value:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def exact(raw, expected, label):
    need((len(raw), sha(raw)) == tuple(expected), label + ' bytes/hash differ')

def source(root, revision):
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    need(head == revision, 'Source revision differs')
    need(not subprocess.check_output(['git', '-C', str(root), 'diff', 'HEAD', '--name-only']).strip(), 'Source has tracked changes')

def assets(directory):
    directory.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, identity in ASSETS.items():
        path = directory / name
        if not path.exists():
            request = urllib.request.Request(BASE + name, headers={'User-Agent': 'RiscRTE-retained-power-qualification'})
            with urllib.request.urlopen(request, timeout=180) as response:
                raw = response.read(identity[0] + 1)
            exact(raw, identity, name)
            path.write_bytes(raw)
        raw = path.read_bytes()
        exact(raw, identity, name)
        result[name] = raw
    return result

def binding(store):
    exact(store['settings.elf'], SETTINGS, 'Retained Settings')
    exact(store['default.elf'], HOME, 'Home')
    need(len(store) == 125 and sum(n.endswith('.elf') for n in store) == 61, 'Complete store inventory differs')
    settings = json.loads(store['settings.json'])
    need(settings['version'] == '1.3.25', 'Settings manifest version differs')
    boot = json.loads(store['boot.json'])
    need(boot['default_app'] == 'default.elf', 'Home route differs')
    for app in ('settings.json', 'default.json'):
        rows = [r for r in boot['app_capabilities'] if r['manifest'] == app]
        need(len(rows) == 1, 'Ambiguous app policy')
        for cap, instance in [('storage.key-value', 1), ('power.sleep', 0), ('display.power', 0), ('input.power-key', 0)]:
            grant = {'capability': cap, 'api': 1, 'instance_id': instance}
            need(rows[0]['grants'].count(grant) == 1, app + ' missing/duplicate ' + cap)
    for path, cap in [('power-sleep/manifest.json', 'power.sleep'), ('display-power/manifest.json', 'display.power')]:
        manifest = json.loads(store[path])
        need(manifest['provides'] == [{'api': 1, 'capability': cap}], 'Provider capability differs')
        rows = [r for r in boot['drivers'] if r['manifest'] == path]
        need(rows == [{'manifest': path}], 'Provider selection differs')
    return boot

def qualify(product, raw):
    source(product, PRODUCT)
    sys.path.insert(0, str(product / 'scripts'))
    from read_only_spiffs import read_image
    from build_provisioning_native import linked_provisioning_layout
    factory = raw['TWatch-1.1.46-Provisioning-factory-erases-data-0x0.bin']
    for name, offset in [('firmware.bin', 0x10000), ('store.bin', 0x2f0000)]:
        need(factory[offset:offset + len(raw[name])] == raw[name], 'Factory pair differs: ' + name)
    store = read_image(raw['store.bin'], 0x550000)
    boot = binding(store)
    proof = json.loads(raw['qualification.json'])
    lock = json.loads(raw['source-lock.json'])
    need(proof['source_revision'] == PRODUCT and lock['sources']['product']['revision'] == PRODUCT, 'Released producer differs')
    need(lock['sources']['runtime']['revision'] == RUNTIME, 'Released Runtime differs')
    with zipfile.ZipFile(io.BytesIO(raw['TWatch-1.1.46-Provisioning-Evidence.zip'])) as archive:
        need(archive.read('qualification.json') == raw['qualification.json'], 'Archived qualification differs')
        for key, item in lock['native_files'].items():
            content = archive.read('build-evidence/locked-native/' + item['path'])
            exact(content, (item['bytes'], item['sha256']), 'Native input ' + key)
        native = archive.read('build-evidence/locked-native/riscrte_native.elf')
        layout = linked_provisioning_layout(native)
    from elftools.elf.elffile import ELFFile
    symbols = {s.name for s in ELFFile(io.BytesIO(native)).get_section_by_name('.symtab').iter_symbols()}
    callbacks = ['_ZN8RiscBoot7Runtime12sleepPrepareEPy', '_ZN8RiscBoot7Runtime11sleepResumeEy',
                 '_ZN7RiscCpu4Port14gpioLightSleepEPvybP26risc_light_sleep_result_v1',
                 '_ZN7RiscCpu4Port13gpioDeepSleepEPvyb', '_ZN7RiscCpu4Port16gpioDeepSleepForEPvybm',
                 '_ZN7RiscCpu4Port17gpioLightSleepForEPvybmP26risc_light_sleep_result_v1',
                 '_ZN7RiscCpu4Port17gpioLightSleepSetEPvybmP26risc_light_sleep_result_v1',
                 '_ZN7RiscCpu4Port16gpioDeepSleepSetEPvybm',
                 '_ZN7RiscCpu11NativeSleep8timerArmEm', '_ZN7RiscCpu11NativeSleep5enterEv']
    need(set(callbacks) <= symbols, 'Native sleep implementation missing')
    app_sections = {}
    for name in ('settings.elf', 'default.elf'):
        elf = ELFFile(io.BytesIO(store[name]))
        app_sections[name] = {section.name: section['sh_size'] for section in elf.iter_sections() if section['sh_flags'] & 2}
    commands = json.loads((product / 'docs/t054/settings-command.json').read_bytes())
    flags = [x for x in commands if x.startswith('-D')]
    need(all(x in flags for x in ('-DPORTABLE_LOW_BATTERY', '-DPORTABLE_SLEEP_SETTINGS',
                                 '-DPORTABLE_TAP_SETTINGS', '-DPORTABLE_TOUCH_ROTATION=0')), 'Retained Settings flags differ')
    need(not any('ATOMIC' in x for x in flags), 'Retained Settings unexpectedly atomic')
    producer_pins = json.loads((product / 'docs/t054/source-pins.json').read_bytes())
    need(next(x['commit'] for x in producer_pins if x['checkout'] == 'System-rgb-t054') ==
         '9dcb2bbef44853e533d980a658a814d2c787a4fa', 'Historical Settings producer differs')
    need(layout == proof['provisioning']['linked_layout'], 'Native linked layout differs')
    for label in ('admission', 'admission_sanitized'):
        admission = proof[label]
        need(admission['prepared'] and admission['cohort_validated'] and admission['elf_count'] == 61, 'Incomplete admission')
        need(admission['native_elf_sha256'] == sha(native), 'Admission native identity differs')
        need(admission['active_platform_count'] == admission['candidate_platform_count'] == 20, 'Platform selection differs')
        need(not admission['hardware_calls'] and not admission['storage_calls'] and not admission['target_instructions_executed'], 'Evidence scope differs')
        need(admission['preserving_transition']['expected_rejection'], 'Preserving transition incorrectly accepted')
    baseline = proof['baseline_contract']['files']
    changed = set(proof['preservation']['changed_store_files'])
    added = set(proof['preservation']['added_store_files'])
    need(set(store) == set(baseline) | added, 'Retained inventory differs')
    for name, item in baseline.items():
        if name not in changed:
            exact(store[name], (item['bytes'], item['sha256']), 'Retained ' + name)
    for text in (b'sleep_mode\0', b'sleep_idle\0', b'sleep_deep\0', b'Light then Deep\0'):
        need(text in store['settings.elf'], 'Retained Settings control text missing')
    with zipfile.ZipFile(io.BytesIO(raw['ci-provenance.zip'])) as archive:
        ci = json.loads(archive.read('ci-run.json'))
    need(ci['GITHUB_SHA'] == PRODUCT and ci['GITHUB_RUN_ID'] == '39026555734', 'CI producer differs')
    need(proof['factory_erases_data'] and not proof['preserving_update_kit_emitted'], 'Installation scope differs')
    need('No preserving update kit is supplied.' in raw['TESTING.txt'].decode(), 'Installation disclosure missing')
    return {'schema': 1, 'status': 'artifact-and-structural-checks-passed-behavior-boundary-open',
            'product_revision': PRODUCT, 'runtime_revision': RUNTIME, 'producer_run': 39026555734,
            'release_url': BASE.replace('/download/', '/tag/').rstrip('/'),
            'assets': {n: {'bytes': len(b), 'sha256': sha(b)} for n, b in raw.items()},
            'settings': {'manifest_version': '1.3.25', 'bytes': SETTINGS[0], 'sha256': SETTINGS[1]},
            'home': {'bytes': HOME[0], 'sha256': HOME[1]}, 'store_files': len(store),
            'retained_files_verified': len(baseline) - len(changed), 'linked_layout': layout,
            'native_elf_sha256': sha(native), 'linked_native_sleep_symbols': callbacks,
            'app_alloc_sections_not_live_heap': app_sections,
            'historical_settings_recipe_flags': flags, 'namespace_1_granted_to_settings_and_home': True,
            'factory_erases_data': True, 'preserving_update_kit': False,
            'factory_firmware_store_pair_verified': True,
            'target_instructions_executed': False, 'hardware_tested': False, 'live_memory_fit_tested': False,
            'open_boundaries': ['Historical recipe is not a bit-for-bit fa1c Settings reproduction receipt; persisted-record compatibility boundary is tested separately',
                                'Physical sleep/wake/display/input/current and live memory fit']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = qualify(args.product.resolve(), assets(args.assets))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True, indent=2))

if __name__ == '__main__':
    main()

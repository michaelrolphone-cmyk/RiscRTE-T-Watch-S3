#!/usr/bin/env python3
"""Build the explicit Watch18 cleanup/source-route overlay on frozen Watch17."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

from current_apps_overlay import ROOT, SYSTEM_APPS, UTILITY_APPS, CLOCK_APPS, encoded, metadata, require
from contexts_profile import APPS, catalog, version
from build_contexts_cohort import clean, definitions, source_manifest, write_catalog, collect_licenses
from build_current_apps import application_inputs
from compact_current_elf import compact
from current_bootfs import build as pack_store
from current_cohort import encode, parse
from build_wifi_common import zip_bytes
from read_only_spiffs import read_image
import watch_native_binding as binding
from lifecycle_source_custody import (SourceCustody, QualifiedCompiler, catalog_inputs,
        application_command, provider_command, PROVIDER_FLAGS, verify_dependencies)

PROFILE = 'watch-lifecycle-routes-v1'
CONFIG = ROOT / 'apps/lifecycle-routes-sources.json'
REBUILT = tuple(n for n in APPS if n not in CLOCK_APPS)
PROVIDER_FILES = {'update-fw/driver.elf', 'update-fw/manifest.json'}
CHANGED = {n + s for n in REBUILT for s in ('.elf', '.json')} | PROVIDER_FILES | {'cohort.json'}


def configuration():
    c = json.loads(CONFIG.read_bytes())
    prior = json.loads((ROOT / 'apps/contexts-sources.json').read_bytes())
    require(c['schema'] == 1 and c['profile'] == PROFILE and c['product_version'] == '1.0.18', 'Wrong follow-on profile')
    require(set(c['app_versions']) == set(APPS), 'App inventory differs')
    for name in APPS:
        require((version(c['app_versions'][name]) > version(prior['app_versions'][name])) if name in REBUILT else
                c['app_versions'][name] == prior['app_versions'][name], 'Deployment version scope differs: ' + name)
    for key in ('source_app_versions', 'drivers', 'contexts_service', 'runtime_version', 'app_count', 'catalog_count',
                'prior_provider_artifacts', 'provider_selections', 'max_app_grants'):
        require(c[key] == prior[key], 'Unrelated profile field differs: ' + key)
    require(set(c['sources']) == set(prior['sources']), 'Source repository scope differs')
    for key, source in c['sources'].items():
        if key == 'system-apps':
            require(source['repository'] == prior['sources'][key]['repository'] and
                    source['commit'] == '3c9e6dbe54d4d744ef31511e7994890c900b808b', 'Unqualified System union')
        else:
            require(source == prior['sources'][key], 'Unrelated dependency changed: ' + key)
    require(c['features'] == {**prior['features'], 'background_cleanup_before_owned_cleanup': True,
            'source_aware_firmware_routes': True}, 'Feature scope differs')
    require(c['firmware_update'] == {'version': '0.1.5', 'source_routes': True, 'catalog_deployed': False}, 'Updater selection differs')
    require(c['baseline'] == {'binding_source': 'b6abe35ed3049174e53c89c8adb85edd3860da34',
            'version': '1.0.17', 'native_source': 'b587df55298e0bb8e676b3d59ca13679c0267bf7',
            'bootfs_sha256': 'f7b43befc8e0b24347ef3bafc48c5f2c729f99c0b4f2f4956700b5cbec81e851'}, 'Frozen baseline differs')
    return c


def baseline(directory, runtime, native):
    c = configuration()
    receipt, files, image, licenses = binding.verify(directory, runtime, native, c['baseline']['binding_source'])
    require(metadata(image)['sha256'] == c['baseline']['bootfs_sha256'], 'Baseline image differs')
    require(receipt['runtime']['source'] == c['baseline']['native_source'] and receipt['cohort']['version'] == '1.0.17',
            'Baseline native/version differs')
    return receipt, files, licenses


def check_scope(before, after, c, head):
    require(set(after) == set(before) and len(after) == 95, 'Complete store inventory differs')
    require({n for n in before if before[n] != after[n]} == CHANGED, 'Overlay changed-member scope differs')
    identity = parse(before['cohort.json'])
    require(parse(after['cohort.json']) == {**identity, 'version': c['product_version'], 'source_revision': head},
            'Native/layout/source cohort changed unexpectedly')
    for name in REBUILT:
        expected = {**json.loads(before[name + '.json']), 'version': c['app_versions'][name]}
        require(json.loads(after[name + '.json']) == expected, 'App authority changed: ' + name)
    old = json.loads(before['update-fw/manifest.json'])
    require(json.loads(after['update-fw/manifest.json']) == {**old, 'version': '0.1.5'}, 'Updater authority changed')
    boot = json.loads(after['boot.json'])
    require('cohort_migration' not in boot and len(boot['app_capabilities']) == 23 and len(boot['drivers']) == 24,
            'Policy inventory/migration changed')
    require(max(len(r['grants']) for r in boot['app_capabilities']) == 15, 'App grant bound changed')
    return {'app_count': 23, 'rebuilt_apps': sorted(REBUILT), 'preserved_apps': sorted(CLOCK_APPS),
            'changed_store_members': sorted(CHANGED), 'preserved_provider_artifacts': 22,
            'changed_provider_artifacts': ['software-update-firmware'], 'provider_selections': 24,
            'boot_board_and_all_grants_byte_identical': True, 'native_byte_identical': True}


def source_custody(c, head, out, roots):
    pins = {n: source['commit'] for n, source in c['sources'].items()}
    pins.update(drivers=c['drivers']['commit'], watch=head)
    require(set(roots) == set(pins) and roots['watch'] == str(ROOT), 'Source custody root inventory differs')
    guard = SourceCustody(roots, pins, catalog_inputs(out, catalog()))
    return guard, {'schema': 1, 'source_roots': roots, 'source_pins': pins,
                   'dependency_scan': 'actual-target-command', 'precompiled_inputs': 'rejected'}


def build_provider(system, out, cc, compiler):
    destination = out / 'update-provider-build'
    before = compiler.custody.check(provider_command(cc, system, out, PROVIDER_FLAGS))
    subprocess.run([sys.executable, str(system / 'scripts/build_portable_updates.py'), '--services-only',
                    '--source-routes', '--rtc-utc-offset-seconds', '28800', '--output-dir', str(destination)],
                   check=True, env={**os.environ, 'NATIVE_APP_CC': cc})
    folder = destination / 'software-update-firmware'
    proof = json.loads((folder / 'build-record.json').read_bytes())
    require(proof['repository_commit'] == configuration()['sources']['system-apps']['commit'] and
            proof['working_tree_dirty'] is False and proof['version'] == '0.1.5' and
            '-DUPDATE_SOURCE_ROUTES=1' in proof['build_defines'], 'Provider build selection differs')
    deps = compiler.custody.check(provider_command(cc, system, out, proof['build_defines']))
    require(deps == before, 'Provider compiler dependency closure changed during compilation')
    elf = folder / 'driver.elf'
    require(metadata(elf.read_bytes()) == {k: proof[k] for k in ('sha256', 'size_bytes')}, 'Provider bytes differ')
    compaction = compact(elf, cc, debug_path=out / 'debug/update-fw.elf')
    subprocess.run([str(compiler.validator), str(elf)], check=True)
    return elf.read_bytes(), (folder / 'manifest.json').read_bytes(), {
            **metadata(elf.read_bytes()), 'original_build': proof, 'compaction': compaction, 'target_dependencies': deps}


def verify(directory, baseline_dir, runtime, native, expected_source, *, cc=None):
    directory = Path(directory)
    c = configuration()
    original, before, licenses = baseline(baseline_dir, runtime, native)
    record = json.loads((directory / 'build.json').read_bytes())
    cc = cc or os.environ.get('TWATCH_CC')
    require(cc, 'Independently selected TWATCH_CC required for compiler input verification')
    compiler_version = subprocess.check_output([cc, '--version'], text=True).splitlines()[0]
    require('8.4.0' in compiler_version and record['compiler'] == compiler_version, 'Verification compiler differs')
    custody, custody_record = source_custody(c, expected_source, directory, record['input_custody']['source_roots'])
    require(record['input_custody'] == custody_record, 'Compiler source custody selection differs')
    repos = {n: Path(custody_record['source_roots'][n]) for n in c['sources']}
    require(record['schema'] == 1 and record['profile'] == PROFILE and record['watch_source'] == expected_source and
            record['configuration'] == c and record['configuration_file'] == metadata(CONFIG.read_bytes()), 'Build identity differs')
    require(record['baseline_binding'] == metadata((Path(baseline_dir) / 'binding.json').read_bytes()) and
            record['runtime'] == original['runtime'], 'Native/baseline proof differs')
    files = binding.files_at(directory / 'store')
    require(record['files'] == binding.inventory(files), 'Store receipt differs')
    require(record['scope'] == check_scope(before, files, c, expected_source), 'Scope proof differs')
    require(set(record['apps']) == set(REBUILT) and set(record['providers']) == {'software-update-firmware'},
            'Rebuilt component proofs differ')
    for name, proof in record['apps'].items():
        owner = 'system-apps' if name in SYSTEM_APPS else 'utilities' if name in (*UTILITY_APPS, 'contexts') else 'productivity'
        source = repos[owner] / 'Apps' / ('timecard_portable.c' if name == 'timecard' else name + '.c')
        sources, includes, _ = application_inputs(name, source, repos, ROOT, directory, 'runtime-features')
        includes += [repos['utilities'] / 'lib/Contexts/include']
        verify_dependencies(custody, application_command(cc, directory, name, sources,
                definitions(name, c['app_versions'][name]), includes), proof['target_dependencies'])
        require(metadata(files[name + '.elf']) == {k: proof[k] for k in ('sha256', 'size_bytes')}, 'App proof differs: ' + name)
        require(proof['defines'] == definitions(name, c['app_versions'][name]) and proof['version'] == c['app_versions'][name],
                'App build selection differs: ' + name)
        require(proof['host_fixture_excluded'] and proof['target_dependencies'] and
                proof['compaction']['before_sha256'] == metadata((directory / 'debug' / (name + '.elf')).read_bytes())['sha256'] and
                proof['compaction']['after_sha256'] == proof['sha256'], 'App compaction/input custody differs: ' + name)
    provider = record['providers']['software-update-firmware']
    verify_dependencies(custody, provider_command(cc, repos['system-apps'], directory,
            provider['original_build']['build_defines']), provider['target_dependencies'])
    require(metadata(files['update-fw/driver.elf']) == {k: provider[k] for k in ('sha256', 'size_bytes')} and
            provider['compaction']['before_sha256'] == metadata((directory / 'debug/update-fw.elf').read_bytes())['sha256'] and
            provider['compaction']['after_sha256'] == provider['sha256'], 'Provider compaction custody differs')
    require(provider['target_dependencies'] and provider['original_build']['version'] == '0.1.5' and
            '-DUPDATE_SOURCE_ROUTES=1' in provider['original_build']['build_defines'] and
            provider['original_build']['repository_commit'] == c['sources']['system-apps']['commit'], 'Provider source selection differs')
    image = (directory / 'bootfs.bin').read_bytes()
    rebuilt, packing = pack_store(files)
    require(image == rebuilt and read_image(image, 0x510000) == files and record['packing'] == packing and
            record['bootfs'] == metadata(image) and packing['empty_blocks'] >= 4, 'Store packing/capacity differs')
    require((directory / 'store.zip').read_bytes() == zip_bytes(files), 'Store archive differs')
    require((directory / 'LICENSES.zip').read_bytes() == licenses and record['licenses'] == metadata(licenses), 'Notices differ')
    require(record['physical_qualification'] is False and record['catalog_deployed'] is False,
            'Build overstates qualification/deployment')
    return record


def build(args):
    c = configuration()
    head = clean(ROOT)
    repos = {n: Path(getattr(args, n.replace('-', '_'))).resolve() for n in c['sources']}
    for n, repo in repos.items(): clean(repo, c['sources'][n]['commit'])
    drivers = Path(args.drivers).resolve(); clean(drivers, c['drivers']['commit'])
    native_runtime = Path(args.native_runtime).resolve()
    original, before, licenses = baseline(args.baseline, native_runtime, args.native_candidate)
    out = Path(args.output).resolve(); require(not out.exists(), 'Output must be new')
    out.mkdir(parents=True)
    write_catalog(out, catalog())
    cc = os.environ.get('TWATCH_CC'); require(cc, 'Pinned TWATCH_CC required')
    compiler_version = subprocess.check_output([cc, '--version'], text=True).splitlines()[0]
    require('8.4.0' in compiler_version, 'GCC8.4.0 required')
    custody, custody_record = source_custody(c, head, out,
            {n: str(path) for n, path in {**repos, 'drivers': drivers, 'watch': ROOT}.items()})
    compiler = QualifiedCompiler(cc, ROOT, out, repos, drivers, custody)
    after = dict(before)
    after['cohort.json'] = encode({**parse(before['cohort.json']), 'version': c['product_version'], 'source_revision': head})
    record = {'schema': 1, 'profile': PROFILE, 'watch_source': head, 'configuration': c,
              'configuration_file': metadata(CONFIG.read_bytes()), 'baseline_binding': metadata((Path(args.baseline) / 'binding.json').read_bytes()),
              'runtime': original['runtime'], 'compiler': compiler_version, 'input_custody': custody_record, 'apps': {}, 'providers': {},
              'physical_qualification': False, 'catalog_deployed': False}
    for name in REBUILT:
        owner = 'system-apps' if name in SYSTEM_APPS else 'utilities' if name in (*UTILITY_APPS, 'contexts') else 'productivity'
        repo = repos[owner]
        source = repo / 'Apps' / ('timecard_portable.c' if name == 'timecard' else name + '.c')
        sidecar = json.loads(source_manifest(repo, name).read_bytes())
        require(sidecar['version'] == c['source_app_versions'][name], 'Source version differs: ' + name)
        sources, includes, allowed = application_inputs(name, source, repos, ROOT, out, 'runtime-features')
        includes += [repos['utilities'] / 'lib/Contexts/include']
        raw, proof = compiler.build(name, sources, definitions(name, c['app_versions'][name]), includes,
                                   {'app_main', 'app_module_init', 'app_module_fini'}, allowed | {'memchr', 'strncmp'})
        after[name + '.elf'] = raw
        after[name + '.json'] = encoded({**json.loads(before[name + '.json']), 'version': c['app_versions'][name]})
        record['apps'][name] = {**proof, 'repository': owner, 'repository_sha': c['sources'][owner]['commit'],
                               'source_version': sidecar['version'], 'version': c['app_versions'][name]}
    raw, manifest, proof = build_provider(repos['system-apps'], out, cc, compiler)
    after['update-fw/driver.elf'] = raw; after['update-fw/manifest.json'] = manifest
    record['providers']['software-update-firmware'] = proof
    record['scope'] = check_scope(before, after, c, head)
    image, packing = pack_store(after)
    require(packing['empty_blocks'] >= 4, 'Provisioning reserve is insufficient')
    collect_licenses(ROOT, repos, out / 'licenses')
    notices = {**binding.files_at(out / 'licenses'), **binding.native_licenses(native_runtime)}
    require(zip_bytes(notices) == licenses, 'New source notices require explicit review')
    record.update(files=binding.inventory(after), packing=packing, bootfs=metadata(image), licenses=metadata(licenses))
    for name, raw in after.items():
        dest = out / 'store' / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
    for name, raw in {'bootfs.bin': image, 'store.zip': zip_bytes(after), 'LICENSES.zip': licenses,
                      'build.json': encoded(record)}.items(): (out / name).write_bytes(raw)
    for n, repo in repos.items(): clean(repo, c['sources'][n]['commit'])
    clean(drivers, c['drivers']['commit']); clean(ROOT, head)
    verify(out, args.baseline, native_runtime, args.native_candidate, head, cc=cc)
    print('Watch18: 23 apps, 21 rebuilt; source-routes0.1.5; policy/native unchanged; capacity verified')
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('system-apps', 'utilities', 'productivity', 'runtime', 'drivers', 'baseline', 'native-runtime', 'native-candidate', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    build(p.parse_args())


if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Qualify and assemble only an explicitly erasing Watch 1.0.13 initial image."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from build_contexts_cohort import clean, verify_build, SECTION_FLAGS, LINK_FLAGS
from build_wifi_common import zip_bytes
from check_runtime_store_admission import admit_cohort, store_digest
from contexts_profile import baseline_contract, baseline_inputs, configuration, VERSION, RUNTIME_VERSION
from current_apps_overlay import ROOT, encoded, metadata, require
from current_cohort import parse, verify as verify_identity
from current_flash_layout import assemble
from read_only_spiffs import read_image
from rf_watch_candidate import module
from runtime_features_watch_candidate import read_native
import runtime_features_store as runtime_test

ENABLED_CASES = ('enabled-handoff', 'enabled-sleep', 'enabled-sleep-refused',
                 'enabled-sleep-retained', 'enabled-close-retained', 'enabled-capture-retained')
DISABLED_CASES = runtime_test.SCENARIOS
IMAGE_NAME = 'twatch-s3-1.0.13-FULL-INITIAL-ERASES-DATA-bma423.bin'
DATA_EFFECTS = ('Full 16 MiB initial image at offset 0x0. Erases NVS settings, Wi-Fi credentials, '
                'Bluetooth bonds, alarms, Points, all app-data and both banks. '
                'Never use this image for a preserving update.')


def files_at(directory):
    directory = Path(directory)
    return {p.relative_to(directory).as_posix(): p.read_bytes()
            for p in directory.rglob('*') if p.is_file()}


def inventory(files):
    return {name: metadata(raw) for name, raw in sorted(files.items())}


def qualification_hashes(paths, enabled):
    old = runtime_test.HERE
    runtime_test.HERE = paths['watch'] / ('tests/contexts_store' if enabled else 'tests/runtime_features_store')
    try:
        result = runtime_test._source_hashes(paths['runtime'], paths['system'], paths['utilities'])
    finally:
        runtime_test.HERE = old
    result.update(runtime_test.external_source_hashes(paths['drivers']))
    roots = [paths['utilities']/'Apps', paths['utilities']/'lib', paths['utilities']/'Services/contexts',
             paths['watch']/'tests/contexts_store', paths['watch']/'scripts']
    for root in roots:
        for path in root.rglob('*'):
            if path.is_file() and path.suffix in ('.c', '.cpp', '.h', '.inc', '.json', '.py', '.sh'):
                result[str(path)] = runtime_test.sha(path)
    path = paths['watch']/'apps/contexts-sources.json'
    result[str(path)] = runtime_test.sha(path)
    return result


def validate_runtime_report(record, files, config, head, states, hashes, runner_sha, fixture_sha):
    require(record['schema'] == 2, 'Schema 2 Runtime proof required')
    enabled, sanitizer = record['monitoring_enabled'], record['sanitizer']
    require(type(enabled) is bool and sanitizer in ({'address': False, 'undefined': False},
                                                  {'address': True, 'undefined': True}), 'Incomplete Runtime proof mode')
    require(record['candidate_cohort'] == parse(files['cohort.json']) and record['watch_source'] == head and
            record['candidate_cohort']['source_revision'] == head, 'Runtime proof candidate identity differs')
    require(record['candidate_store_sha256'] == store_digest(files) and record['candidate_files'] == inventory(files),
            'Runtime proof candidate bytes differ')
    require(record['source_pins'] == config['sources'] and record['drivers_pin'] == config['drivers'] and
            record['source_states'] == states, 'Runtime proof source identity differs')
    require(record['source_hashes'] == hashes and record['runner_sha256'] == runner_sha and
            record['fixture_sha256'] == fixture_sha, 'Runtime proof source/fixture bytes differ')
    require(record['section_gc'] == {'compile_flags': SECTION_FLAGS, 'link_flags': LINK_FLAGS}, 'Runtime section policy differs')
    require(record['provider_artifacts'] == 23 and record['provider_selections'] == 24 and
            record['production_json_substitutions'] == 0 and record['target_instructions_executed'] is False and
            record['hardware_qualified'] is False, 'Runtime proof scope differs')
    scenarios = record['scenarios']
    expected = ENABLED_CASES if enabled else DISABLED_CASES
    require(len(scenarios) == len(expected) and {r['scenario'] for r in scenarios} == set(expected), 'Runtime scenarios incomplete')
    prefix = 'CONTEXTS_ENABLED_RESULT ' if enabled else 'UPDATE_CLOCK_RESULT '
    for result in scenarios:
        markers = [line[len(prefix):] for line in result['output'].splitlines() if line.startswith(prefix)]
        require(len(markers) == 1 and json.loads(markers[0]) == {k:v for k,v in result.items() if k != 'output'},
                'Runtime scenario output differs')
        name = result['scenario']
        retained = name in ('retained', 'native-context-seed', 'native-context-draw',
                            'enabled-sleep-retained', 'enabled-close-retained', 'enabled-capture-retained')
        require(result['retained'] is retained and result['modules_loaded'] > 0 and
                ((result['modules_loaded'] > result['modules_unloaded']) if retained else
                 (result['modules_loaded'] == result['modules_unloaded'])), 'Runtime cleanup result differs')
        if enabled:
            require(result['apps'] == 5 and result['audio_model_reads'] == result['radio_model_reads'] == 9 and
                    min(result['mic_opens'], result['mic_reads'], result['mic_closes']) > 0 and
                    result['unknown_input'] is True and
                    result['sleep_calls'] == int(name in ('enabled-sleep', 'enabled-sleep-refused', 'enabled-sleep-retained')),
                    'Enabled owner-export/capture/sleep result differs')
        else:
            require(result['raw_update_calls'] == result['radio_calls'] == 0 and
                    result['ready'] is (name == 'healthy') and
                    result['confirm_calls'] == int(name in ('healthy', 'confirm-refused')), 'Disabled startup result differs')
    return enabled, sanitizer['address']


def runtime_reports(report_paths, files, config, head, paths):
    require(len(report_paths) == 4, 'All four enabled/disabled normal/sanitized Runtime reports required')
    states = {name: runtime_test.source_state(path) for name, path in paths.items()}
    runner_sha = runtime_test.sha(paths['watch']/'scripts/test_contexts_runtime.py')
    reports = {}
    for path in report_paths:
        raw = Path(path).read_bytes();record = json.loads(raw)
        enabled = record.get('monitoring_enabled')
        require(type(enabled) is bool, 'Missing monitoring mode')
        fixture = paths['watch']/('tests/contexts_store' if enabled else 'tests/runtime_features_store')/'host.cpp'
        key = validate_runtime_report(record, files, config, head, states, qualification_hashes(paths, enabled),
                                      runner_sha, runtime_test.sha(fixture))
        require(key not in reports, 'Duplicate Runtime proof mode')
        reports[key] = raw
    require(set(reports) == {(e,s) for e in (False,True) for s in (False,True)}, 'Runtime proof matrix incomplete')
    return {('enabled' if e else 'disabled') + ('-sanitized' if s else '-normal') + '.json': raw
            for (e,s),raw in reports.items()}


def validate_target_sources(build, root, build_dir, repositories):
    owners = {**repositories, 'watch':root, 'generated':build_dir}
    for proof in [*build['apps'].values(), *build['providers'].values()]:
        require(proof['host_fixture_excluded'] is True and proof['target_dependencies'], 'Missing target source closure')
        for key, expected in proof['target_dependencies'].items():
            owner, relative = key.split(':', 1)
            require(owner in owners and not Path(relative).is_absolute() and '..' not in Path(relative).parts,
                    'Unknown target source owner/path')
            require(metadata((owners[owner]/relative).read_bytes()) == expected, 'Target source bytes changed: ' + key)


def build_snapshot(directory, build, files):
    """Capture only checked bytes; later mutable file reads cannot change the image."""
    blobs = {name:(directory/name).read_bytes() for name in
             ('contexts-build.json','contexts-source-profile.json','contexts-bootfs.bin','contexts-store.zip','contexts-apps.zip')}
    require(json.loads(blobs['contexts-build.json']) == build and
            json.loads(blobs['contexts-source-profile.json']) == build['configuration'], 'Build evidence changed')
    require(read_image(blobs['contexts-bootfs.bin'],0x510000) == files and
            metadata(blobs['contexts-bootfs.bin'])['sha256'] == build['packing']['sha256'], 'Qualified bootfs bytes differ')
    require(blobs['contexts-store.zip'] == zip_bytes(files), 'Qualified store archive differs')
    members = {'files/'+name:raw for name,raw in files.items()}
    for folder in ('debug','licenses'):
        members.update({folder+'/'+name:raw for name,raw in files_at(directory/folder).items()})
    for name in ('contexts-build.json','contexts-source-profile.json'):members[name] = blobs[name]
    require(blobs['contexts-apps.zip'] == zip_bytes(members), 'Qualified apps/evidence archive differs')
    provider = build['providers'].get('contexts-service')
    require(set(build['providers']) == {'contexts-service'} and provider and
            metadata(files['contexts/driver.elf']) == {k:provider[k] for k in ('sha256','size_bytes')} and
            provider['exports'] == ['t5_driver_get'] and provider['compaction'] is None and
            provider['defines'] == [] and set(provider['imports']) <= {'memcpy','memset','memcmp','memchr','strcmp','strlen'} and
            provider['section_gc'] == {'compile_flags':SECTION_FLAGS,'link_flags':LINK_FLAGS,'export_roots':['t5_driver_get']},
            'New provider target proof differs')
    blobs['LICENSES.zip'] = zip_bytes({name[len('licenses/'):]:raw for name,raw in members.items() if name.startswith('licenses/')})
    return blobs


@contextlib.contextmanager
def admission_environment(sanitized):
    previous = {k:os.environ.get(k) for k in ('SANITIZE','ASAN_OPTIONS')}
    os.environ['SANITIZE'] = str(int(sanitized));os.environ['ASAN_OPTIONS'] = 'detect_leaks=0'
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value


def initial_image(native, bootfs, runtime, identity, qualified_files):
    require(parse(qualified_files['cohort.json']) == identity, 'Qualified image cohort differs')
    verify_identity(identity, native['blobs']['firmware.bin'], version=VERSION, runtime_version=RUNTIME_VERSION)
    require(read_image(bootfs,0x510000) == qualified_files, 'Initial image differs from qualified store')
    bank = module('contexts_initial_bank', Path(runtime)/'scripts/paired_bank_images.py')
    components = {n:native['blobs'][n] for n in ('bootloader.bin','partitions.bin','firmware.bin','appdata.bin')}
    components.update({'bootfs.bin':bootfs, 'otadata.bin':bank.initial_otadata(),
                       'bank_state.bin':bank.initial_bank_state(native['blobs']['firmware.bin'],bootfs,app_data=True)})
    image, parts = assemble(components, native['requirements']['deployment'], True)
    require(read_image(image[0x2f0000:0x800000],0x510000) == qualified_files, 'Initial store round trip differs')
    return image, parts


def prepare(build_dir, accepted_dir, runtime, native_dir, system, utilities, productivity, drivers, reports, output, root=ROOT):
    root,build_dir,accepted_dir,output = map(lambda p:Path(p).resolve(), (root,build_dir,accepted_dir,output))
    require(not output.exists(), 'Initial output must be new')
    repos = {k:Path(v).resolve() for k,v in {'runtime':runtime,'system-apps':system,'utilities':utilities,
                                          'productivity':productivity,'drivers':drivers}.items()}
    head,config = clean(root),configuration(root)
    for name in ('runtime','system-apps','utilities','productivity'):clean(repos[name],config['sources'][name]['commit'])
    clean(repos['drivers'],config['drivers']['commit'])
    baseline = accepted_dir/'accepted-store.zip'
    previous = baseline_inputs(baseline,root)
    build = verify_build(build_dir,baseline,root)
    files = files_at(build_dir/'files');identity = parse(files['cohort.json'])
    snapshots = build_snapshot(build_dir,build,files)
    validate_target_sources(build,root,build_dir,repos)
    paths = {'watch':root,'runtime':repos['runtime'],'system':repos['system-apps'],'utilities':repos['utilities'],'drivers':repos['drivers']}
    qualified = runtime_reports(reports,files,config,head,paths)
    provenance_raw = (accepted_dir/'product-provenance.json').read_bytes()
    require(metadata(provenance_raw) == baseline_contract(root)['artifacts']['product-provenance.json'], 'Accepted provenance differs')
    provenance = json.loads(provenance_raw)
    native = read_native(native_dir,repos['runtime'],root)
    require(native['custody'] == provenance['accepted_build']['native_custody'], 'Original native custody differs')
    native_inputs = files_at(native_dir)
    require(set(native_inputs) == set(native['blobs']) | {'candidate.json','SHA256SUMS'} and
            {name:native_inputs[name] for name in native['blobs']} == native['blobs'] and
            metadata(native_inputs['candidate.json'])['sha256'] == native['custody']['candidate_sha256'], 'Native input changed')
    require(native_inputs['SHA256SUMS'] == ''.join(metadata(raw)['sha256']+'  '+name+'\n' for name,raw in sorted(native_inputs.items())
            if name != 'SHA256SUMS').encode(), 'Native input checksum inventory changed')
    verify_identity(identity,native['blobs']['firmware.bin'],version=VERSION,runtime_version=RUNTIME_VERSION,source_revision=head)
    admission = {}
    for sanitized in (False,True):
        with admission_environment(sanitized):
            admission['sanitized' if sanitized else 'normal'] = {
                'installed_to_candidate':admit_cohort(repos['runtime'],native['blobs']['firmware.elf'],previous,files),
                'candidate_self':admit_cohort(repos['runtime'],native['blobs']['firmware.elf'],files,files)}
    # Recheck sources and exact report bytes before the first full image is assembled.
    require(qualified == runtime_reports(reports,files,config,head,paths), 'Runtime reports changed during qualification')
    validate_target_sources(build,root,build_dir,repos);clean(root,head)
    require(build == verify_build(build_dir,baseline,root) and files == files_at(build_dir/'files') and
            snapshots == build_snapshot(build_dir,build,files), 'Target build changed during qualification')
    image,parts = initial_image(native,snapshots['contexts-bootfs.bin'],repos['runtime'],identity,files)
    staged = {IMAGE_NAME:image, 'contexts-build.json':snapshots['contexts-build.json'],
              'contexts-store.zip':snapshots['contexts-store.zip'],
              'contexts-apps.zip':snapshots['contexts-apps.zip'],
              'runtime-proofs.zip':zip_bytes(qualified), 'native-custody.json':encoded(native['custody']),
              'native-inputs.zip':zip_bytes(native_inputs),
              'accepted-baseline.json':encoded(baseline_contract(root)),
              'accepted-product-provenance.json':provenance_raw,
              'runtime-requirements.json':(root/'apps/runtime-features-runtime-requirements.json').read_bytes(),
              'INSTALL.txt':('Watch 1.0.13 Contexts development candidate.\n' + DATA_EFFECTS +
                  '\nNo publication or device installation was performed.\n'
                  'Runtime 0.1.55 and the 22 prior provider artifacts are reused byte-for-byte.\n'
                  'Host execution/admission passed; physical Watch qualification remains pending.\n').encode()}
    staged['LICENSES.zip'] = snapshots['LICENSES.zip']
    proof = {'schema':1,'kind':'watch-contexts-initial-candidate','mode':'initial','watch_source':head,
             'configuration':config,'source_cohort':parse(previous['cohort.json']),'target_cohort':identity,
             'accepted_store':metadata(baseline.read_bytes()),'candidate_store_sha256':store_digest(files),
             'files':inventory(files),'native_custody':native['custody'],'native_rebuilt':False,'native_changed':False,
             'initial':{'asset':IMAGE_NAME,**metadata(image),'flash_offset':'0x0','components':parts,'erases_persistent_data':True},
             'runtime_proofs':inventory(qualified),'admission':admission,'packing':build['packing'],
             'preserving_update_proven':False,'physical_verification':False,'published':False,'data_effects':DATA_EFFECTS,
             'artifacts':inventory(staged)}
    staged['contexts-initial-proof.json'] = encoded(proof)
    staged['SHA256SUMS'] = ''.join(metadata(raw)['sha256']+'  '+name+'\n' for name,raw in sorted(staged.items())).encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    require(shutil.disk_usage(output.parent).free >= 100*1024*1024+sum(map(len,staged.values())), 'Insufficient initial bundle disk reserve')
    with tempfile.TemporaryDirectory(prefix='.contexts-initial-',dir=output.parent) as temporary:
        directory = Path(temporary)/'candidate';directory.mkdir()
        for name,raw in staged.items():(directory/name).write_bytes(raw)
        require(not output.exists(), 'Initial output appeared during qualification')
        directory.rename(output)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build','accepted','runtime','native','system','utilities','productivity','drivers','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--runtime-report',required=True,action='append',type=Path)
    args = parser.parse_args()
    result = prepare(args.build,args.accepted,args.runtime,args.native,args.system,args.utilities,
                     args.productivity,args.drivers,args.runtime_report,args.output)
    print('Qualified initial development image:',result['initial']['sha256'])

if __name__ == '__main__':main()

"""Bind canonical owner model imports and terminal retention to a target store."""
import hashlib
import json
from pathlib import Path

from build_contexts_cohort import SECTION_FLAGS, LINK_FLAGS, optimization_policy
from current_apps_overlay import require
import runtime_features_store as runtime_test

MODEL_CASES = ('models-import', 'models-audio-stat-retained', 'models-audio-read-retained',
               'models-radio-stat-retained', 'models-radio-read-retained')
FIXTURE_INPUTS = {'audio_namespace':2, 'radio_namespace':3, 'bank_generations':[3,5],
                  'labels_per_source':2, 'positive_per_source':6, 'negative_per_source':4,
                  'checkpoint_source':'canonical trainers and promotion checks; test-only training'}


def source_hashes(paths, fixture_root):
    fixture_root = Path(fixture_root)
    old = runtime_test.HERE
    runtime_test.HERE = fixture_root/'tests/contexts_models_store'
    try:
        result = runtime_test._source_hashes(paths['runtime'], paths['system'], paths['utilities'])
    finally:
        runtime_test.HERE = old
    result.update(runtime_test.external_source_hashes(paths['drivers']))
    utilities, watch = paths['utilities'], paths['watch']
    roots = [utilities/'Apps', utilities/'lib', utilities/'Services/contexts',
             watch/'tests/contexts_store', watch/'scripts', fixture_root/'tests']
    for path in (fixture_root/'scripts/test_contexts_model_runtime.py',
                 utilities/'tests/spectrum_neural_fixture.h', watch/'apps/contexts-sources.json'):
        result[str(path)] = runtime_test.sha(path)
    for root in roots:
        for path in root.rglob('*'):
            if path.is_file() and path.suffix in ('.c','.cpp','.h','.inc','.json','.py','.sh'):
                result[str(path)] = runtime_test.sha(path)
    return result


def validate(record, files, config, head, states, hashes, runner_sha, fixture_sha):
    require(record['schema'] == 1 and record['kind'] == 'contexts-owner-model-runtime-proof' and
            record['monitoring_enabled'] is True, 'Model Runtime proof kind differs')
    sanitizer = record['sanitizer']
    sanitized = sanitizer['address']
    require(type(sanitized) is bool and sanitizer['undefined'] is sanitized and
            set(sanitizer) == {'address','undefined','asan_options'}, 'Incomplete model sanitizer mode')
    require(record['candidate_cohort'] == json.loads(files['cohort.json']) and record['watch_source'] == head and
            record['candidate_cohort']['source_revision'] == head, 'Model Runtime candidate identity differs')
    inventory = {n:{'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)}
                 for n,raw in sorted(files.items())}
    require(record['candidate_store_sha256'] == runtime_test.store_digest(files) and
            record['candidate_files'] == inventory, 'Model Runtime candidate bytes differ')
    require(record['source_pins'] == config['sources'] and record['drivers_pin'] == config['drivers'] and
            record['source_states'] == states and record['test_fixture_source'] == head and
            record['test_fixture_clean'] is True, 'Model Runtime source identity differs')
    require(record['source_hashes'] == hashes and record['runner_sha256'] == runner_sha and
            record['fixture_sha256'] == fixture_sha, 'Model Runtime source/fixture bytes differ')
    require(record['section_gc'] == {'compile_flags':SECTION_FLAGS,'link_flags':LINK_FLAGS} and
            record['optimization'] == optimization_policy(), 'Model Runtime compiler policy differs')
    require(record['provider_artifacts'] == 23 and record['provider_selections'] == 24 and
            record['production_json_substitutions'] == 0 and record['target_instructions_executed'] is False and
            record['hardware_qualified'] is False and record['fixture_inputs'] == FIXTURE_INPUTS,
            'Model Runtime proof scope differs')
    scenarios = record['scenarios']
    require(len(scenarios) == len(MODEL_CASES) and {r['scenario'] for r in scenarios} == set(MODEL_CASES),
            'Model Runtime scenarios incomplete')
    for result in scenarios:
        prefix = 'CONTEXTS_MODELS_RESULT '
        markers = [line[len(prefix):] for line in result['output'].splitlines() if line.startswith(prefix)]
        require(len(markers) == 1 and json.loads(markers[0]) == {k:v for k,v in result.items() if k != 'output'},
                'Model Runtime scenario output differs')
        name = result['scenario']
        retained = name != 'models-import'
        namespace = 2 if name.startswith('models-audio-') else (3 if retained else 0)
        read_boundary = name.endswith('read-retained')
        stats = [1,0] if namespace == 2 else ([3,1] if namespace == 3 else [3,3])
        reads = [int(read_boundary),0] if namespace == 2 else ([3,int(read_boundary)] if namespace == 3 else [3,3])
        ready = [False,False] if namespace == 2 else ([True,False] if namespace == 3 else [True,True])
        require(result['retained'] is retained and result['retained_namespace'] == namespace and
                result['post_retained_io'] == 0 and result['appdata_stats'] == stats and
                result['appdata_reads'] == reads and result['apps'] == (2 if namespace == 2 else (4 if namespace == 3 else 5)),
                'Model Runtime owner/storage fence differs')
        require(result['modules_loaded'] > 0 and
                ((result['modules_loaded'] > result['modules_unloaded']) if retained else
                 result['modules_loaded'] == result['modules_unloaded']), 'Model Runtime cleanup differs')
        for field, value in (('temporal_generations',1),('temporal_states',2),('neural_states',2),
                             ('positive_examples',6),('negative_examples',4)):
            require(result[field] == [value if r else 0 for r in ready], 'Model Runtime readiness differs: '+field)
        require(len(result['readiness_checks']) == 2 and
                all((count > 0) if expected else (count == 0)
                    for count,expected in zip(result['readiness_checks'],ready)), 'Model Runtime readiness was not observed')
    return sanitized


def reports(report_paths, files, config, head, paths):
    require(report_paths is not None and len(report_paths) == 2,
            'Both normal and sanitized model Runtime reports required')
    states = {name:runtime_test.source_state(path) for name,path in paths.items()}
    states['test_fixture'] = states['watch']
    root = paths['watch']
    hashes = source_hashes(paths,root)
    runner_sha = runtime_test.sha(root/'scripts/test_contexts_model_runtime.py')
    fixture_sha = runtime_test.sha(root/'tests/contexts_models_store/host.cpp')
    result = {}
    for path in report_paths:
        raw = Path(path).read_bytes()
        key = validate(json.loads(raw),files,config,head,states,hashes,runner_sha,fixture_sha)
        require(key not in result, 'Duplicate model Runtime mode')
        result[key] = raw
    require(set(result) == {False,True}, 'Model Runtime matrix incomplete')
    return {'models-'+('sanitized' if key else 'normal')+'.json':raw for key,raw in result.items()}

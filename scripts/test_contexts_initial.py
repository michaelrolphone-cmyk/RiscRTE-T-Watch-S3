#!/usr/bin/env python3
"""Fail-closed binding tests for the initial-only Contexts packager."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_contexts_initial import (ENABLED_CASES, DISABLED_CASES, inventory, runtime_reports,
                                    validate_runtime_report, build_snapshot, initial_image, prepare)
from build_contexts_cohort import SECTION_FLAGS, LINK_FLAGS, optimization_policy
from contexts_profile import baseline_contract, configuration
from current_cohort import encode
from check_runtime_store_admission import store_digest
from current_apps_overlay import metadata, encoded
from build_wifi_common import zip_bytes

class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.head = 'a'*40
        self.config = configuration()
        self.identity = {**baseline_contract()['accepted_cohort'],'version':'1.0.17','source_revision':self.head}
        self.files = {'cohort.json':encode(self.identity),'default.elf':b'fixture target bytes'}
        self.states = {name:{'commit':self.head,'tree':'b'*40,'tracked_changes':''}
                       for name in ('watch','runtime','system','utilities','drivers')}
        self.hashes = {'fixture':'c'*64}

    def record(self, enabled=False, sanitized=False):
        results = []
        for name in ENABLED_CASES if enabled else DISABLED_CASES:
            retained = name in ('retained','native-context-seed','native-context-draw',
                                'enabled-close-retained','enabled-sleep-retained','enabled-capture-retained')
            result = {'scenario':name,'retained':retained,'modules_loaded':30,'modules_unloaded':5 if retained else 30}
            if enabled:
                result.update(apps=5,audio_model_reads=9,radio_model_reads=9,mic_opens=1,mic_reads=5,
                              mic_closes=1,unknown_input=True,
                              sleep_calls=int(name in ('enabled-sleep','enabled-sleep-refused','enabled-sleep-retained')))
            else:
                result.update(raw_update_calls=0,radio_calls=0,ready=name=='healthy',
                              confirm_calls=int(name in ('healthy','confirm-refused')))
            prefix = 'CONTEXTS_ENABLED_RESULT ' if enabled else 'UPDATE_CLOCK_RESULT '
            result['output'] = prefix + json.dumps(result)
            results.append(result)
        return {'schema':2,'monitoring_enabled':enabled,'sanitizer':{'address':sanitized,'undefined':sanitized},
                'candidate_cohort':self.identity,'watch_source':self.head,'candidate_store_sha256':store_digest(self.files),
                'candidate_files':inventory(self.files),'source_pins':self.config['sources'],'drivers_pin':self.config['drivers'],
                'source_states':self.states,'source_hashes':self.hashes,'runner_sha256':'d'*64,'fixture_sha256':'d'*64,
                'section_gc':{'compile_flags':SECTION_FLAGS,'link_flags':LINK_FLAGS},'optimization':optimization_policy(),'provider_artifacts':23,
                'provider_selections':24,'production_json_substitutions':0,'target_instructions_executed':False,
                'hardware_qualified':False,'scenarios':results}

    def validate(self, record):
        return validate_runtime_report(record,self.files,self.config,self.head,self.states,self.hashes,'d'*64,'d'*64)

    def reject(self, mutate, enabled=False):
        record = copy.deepcopy(self.record(enabled));mutate(record)
        with self.assertRaises(ValueError):self.validate(record)

    def test_all_modes(self):
        for e in (False,True):
            for s in (False,True):self.assertEqual(self.validate(self.record(e,s)),(e,s))

    def test_obsolete_schema(self):self.reject(lambda r:r.update(schema=1))
    def test_other_candidate_digest(self):self.reject(lambda r:r.update(candidate_store_sha256='0'*64))
    def test_other_candidate_files(self):self.reject(lambda r:r['candidate_files'].pop('default.elf'))
    def test_other_source(self):self.reject(lambda r:r.update(watch_source='0'*40))
    def test_missing_source_hash(self):self.reject(lambda r:r.update(source_hashes={}))
    def test_changed_source_pin(self):self.reject(lambda r:r['source_pins']['utilities'].update(commit='0'*40))
    def test_changed_source_state(self):self.reject(lambda r:r['source_states']['watch'].update(tracked_changes=' M source'))
    def test_partial_sanitizer(self):self.reject(lambda r:r['sanitizer'].update(address=True))
    def test_missing_case(self):self.reject(lambda r:r['scenarios'].pop())
    def test_duplicate_case(self):self.reject(lambda r:r['scenarios'].__setitem__(1,r['scenarios'][0]))
    def test_missing_enabled_capture_fence(self):self.reject(lambda r:r['scenarios'].pop(),True)
    def test_changed_output(self):self.reject(lambda r:r['scenarios'][0].update(output='no result'))
    def test_removed_section_policy(self):self.reject(lambda r:r['section_gc'].update(link_flags=[]))
    def test_json_substitution(self):self.reject(lambda r:r.update(production_json_substitutions=1))
    def test_hardware_claim(self):self.reject(lambda r:r.update(hardware_qualified=True))
    def test_provider_graph_shortened(self):self.reject(lambda r:r.update(provider_selections=23))
    def test_wrong_model_owner_reads(self):
        def mutate(r):
            value=r['scenarios'][0];value['audio_model_reads']=0
            value['output']='CONTEXTS_ENABLED_RESULT '+json.dumps({k:v for k,v in value.items() if k!='output'})
        self.reject(mutate,True)

    def test_matrix_requires_unique_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths={name:Path(temporary)/name for name in self.states}
            reports=[]
            for i,(e,s) in enumerate(((False,False),(False,True),(True,False),(True,True))):
                path=Path(temporary)/str(i);path.write_text(json.dumps(self.record(e,s)));reports.append(path)
            with patch('build_contexts_initial.qualification_hashes',return_value=self.hashes), \
                 patch('build_contexts_initial.runtime_test.sha',return_value='d'*64), \
                 patch('build_contexts_initial.runtime_test.source_state',side_effect=lambda p:self.states[p.name]):
                self.assertEqual(len(runtime_reports(reports,self.files,self.config,self.head,paths)),4)
                with self.assertRaises(ValueError):runtime_reports(reports[:3],self.files,self.config,self.head,paths)
                with self.assertRaises(ValueError):runtime_reports(reports[:3]+[reports[0]],self.files,self.config,self.head,paths)

    def snapshot_fixture(self, directory):
        files = {**self.files,'contexts/driver.elf':b'fixture provider bytes'}
        provider = {**metadata(files['contexts/driver.elf']),'exports':['t5_driver_get'],'compaction':{'retained_loader_sections_symbols_relocations_unchanged':True,'before_sha256':metadata(b'provider debug')['sha256'],'after_sha256':metadata(files['contexts/driver.elf'])['sha256']},
                    'defines':[],'imports':['memcpy'],
                    'section_gc':{'compile_flags':SECTION_FLAGS,'link_flags':LINK_FLAGS,'export_roots':['t5_driver_get']}}
        build = {'configuration':self.config,'packing':metadata(b'fixture bootfs'),'providers':{'contexts-service':provider}}
        members = {'files/'+name:raw for name,raw in files.items()}
        members.update({'contexts-build.json':encoded(build),'contexts-source-profile.json':encoded(self.config),
                        'debug/default.elf':b'fixture debug','debug/contexts-service.elf':b'provider debug','licenses/LICENSE':b'fixture license'})
        for name,raw in members.items():
            path=directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        for name,raw in {'contexts-store.zip':zip_bytes(files),'contexts-apps.zip':zip_bytes(members),
                         'contexts-bootfs.bin':b'fixture bootfs'}.items():(directory/name).write_bytes(raw)
        return build,files

    def test_snapshot_rejects_changed_archives_and_bootfs(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);build,files=self.snapshot_fixture(directory)
            with patch('build_contexts_initial.read_image',return_value=files):
                self.assertIn('LICENSES.zip',build_snapshot(directory,build,files))
                for name in ('contexts-apps.zip','contexts-store.zip','contexts-bootfs.bin'):
                    path=directory/name;before=path.read_bytes();path.write_bytes(b'changed')
                    with self.assertRaises(ValueError):build_snapshot(directory,build,files)
                    path.write_bytes(before)

    def test_snapshot_requires_new_provider_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);build,files=self.snapshot_fixture(directory)
            for mutation in ('missing','hash','flags','compaction'):
                bad=copy.deepcopy(build)
                if mutation=='missing':bad['providers']={}
                elif mutation=='hash':bad['providers']['contexts-service']['sha256']='0'*64
                elif mutation=='flags':bad['providers']['contexts-service']['section_gc']['link_flags']=[]
                else:bad['providers']['contexts-service']['compaction']['before_sha256']='0'*64
                (directory/'contexts-build.json').write_bytes(encoded(bad))
                members={name:path.read_bytes() for path in directory.rglob('*') if path.is_file()
                         for name in [path.relative_to(directory).as_posix()]
                         if name.startswith(('files/','debug/','licenses/')) or name in ('contexts-build.json','contexts-source-profile.json')}
                (directory/'contexts-apps.zip').write_bytes(zip_bytes(members))
                with patch('build_contexts_initial.read_image',return_value=files):
                    with self.assertRaises(ValueError):build_snapshot(directory,bad,files)

    def test_image_rejects_other_qualified_cohort_before_assembly(self):
        other={**self.identity,'source_revision':'0'*40}
        with patch('build_contexts_initial.assemble') as assembly:
            with self.assertRaises(ValueError):initial_image({},b'bootfs',Path('.'),other,self.files)
            assembly.assert_not_called()

    def test_failed_execution_proof_creates_no_output(self):
        for failing_gate in ('baseline','model'):
            with self.subTest(gate=failing_gate), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);output=root/'not-emitted'
                with patch('build_contexts_initial.clean',return_value=self.head), \
                     patch('build_contexts_initial.configuration',return_value=self.config), \
                     patch('build_contexts_initial.baseline_inputs',return_value=self.files), \
                     patch('build_contexts_initial.verify_build',return_value={}), \
                     patch('build_contexts_initial.files_at',return_value=self.files), \
                     patch('build_contexts_initial.build_snapshot',return_value={}), \
                     patch('build_contexts_initial.validate_target_sources'), \
                     patch('build_contexts_initial.runtime_reports',return_value={}) as baseline, \
                     patch('build_contexts_initial.model_runtime_reports',return_value={}) as models, \
                     patch('build_contexts_initial.initial_image') as assembly:
                    (baseline if failing_gate=='baseline' else models).side_effect=ValueError('proof rejected')
                    with self.assertRaisesRegex(ValueError,'proof rejected'):
                        prepare(root,root,root,root,root,root,root,root,[],output,root=root)
                    assembly.assert_not_called();self.assertFalse(output.exists())

if __name__=='__main__':unittest.main()

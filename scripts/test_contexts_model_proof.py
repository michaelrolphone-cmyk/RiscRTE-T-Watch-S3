#!/usr/bin/env python3
"""Prevent packaging without exact-store successful model import and retention proofs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contexts_model_proof import FIXTURE_INPUTS, MODEL_CASES, validate, reports
import test_contexts_initial


class ModelQualificationTests(unittest.TestCase):
    def setUp(self):
        self.base = test_contexts_initial.QualificationTests(); self.base.setUp()
        self.base.states['test_fixture'] = self.base.states['watch']

    def record(self, sanitized=False):
        record = self.base.record(enabled=True,sanitized=sanitized)
        record.update(schema=1,kind='contexts-owner-model-runtime-proof',
                      test_fixture_source=self.base.head,test_fixture_clean=True,
                      fixture_inputs=copy.deepcopy(FIXTURE_INPUTS))
        record['sanitizer']['asan_options'] = 'detect_leaks=0'
        scenarios = []
        for name, apps, stats, reads, ready, namespace in (
            (MODEL_CASES[0],5,[3,3],[3,3],[True,True],0),
            (MODEL_CASES[1],2,[1,0],[0,0],[False,False],2),
            (MODEL_CASES[2],2,[1,0],[1,0],[False,False],2),
            (MODEL_CASES[3],4,[3,1],[3,0],[True,False],3),
            (MODEL_CASES[4],4,[3,1],[3,1],[True,False],3)):
            value = {'scenario':name,'apps':apps,'appdata_stats':stats,'appdata_reads':reads,
                     'retained':bool(namespace),'retained_namespace':namespace,'post_retained_io':0,
                     'modules_loaded':30,'modules_unloaded':5 if namespace else 30,
                     'readiness_checks':[11 if r else 0 for r in ready]}
            for key,count in (('temporal_generations',1),('temporal_states',2),('neural_states',2),
                              ('positive_examples',6),('negative_examples',4)):
                value[key] = [count if r else 0 for r in ready]
            value['output'] = 'CONTEXTS_MODELS_RESULT '+json.dumps(value)
            scenarios.append(value)
        record['scenarios'] = scenarios
        return record

    def check(self, record):
        b = self.base
        return validate(record,b.files,b.config,b.head,b.states,b.hashes,'d'*64,'d'*64)

    def reject(self, mutation):
        record = self.record(); mutation(record)
        with self.assertRaises(ValueError): self.check(record)

    def reject_result(self, index, **changes):
        def mutation(record):
            result = record['scenarios'][index]; result.update(changes)
            result['output'] = 'CONTEXTS_MODELS_RESULT '+json.dumps({k:v for k,v in result.items() if k != 'output'})
        self.reject(mutation)

    def test_both_modes(self):
        for sanitized in (False,True):self.assertEqual(self.check(self.record(sanitized)),sanitized)

    def test_missing_positive_import(self):self.reject(lambda r:r['scenarios'].pop(0))
    def test_missing_read_retention(self):self.reject(lambda r:r['scenarios'].pop(4))
    def test_duplicate_boundary(self):self.reject(lambda r:r['scenarios'].__setitem__(4,r['scenarios'][3]))
    def test_wrong_candidate(self):self.reject(lambda r:r.update(candidate_store_sha256='0'*64))
    def test_separate_fixture_source(self):self.reject(lambda r:r.update(test_fixture_source='0'*40))
    def test_dirty_fixture(self):self.reject(lambda r:r.update(test_fixture_clean=False))
    def test_missing_fixture_hash(self):self.reject(lambda r:r.update(source_hashes={}))
    def test_partial_sanitizer(self):self.reject(lambda r:r['sanitizer'].update(address=True))
    def test_wrong_namespace(self):self.reject_result(2,retained_namespace=3)
    def test_io_after_retention(self):self.reject_result(4,post_retained_io=1)
    def test_retained_owner_unloaded(self):self.reject_result(3,modules_unloaded=30)
    def test_live_owner_not_cleaned_up(self):self.reject_result(0,modules_unloaded=29)
    def test_missing_actual_model_reads(self):self.reject_result(0,appdata_reads=[0,0])
    def test_model_never_observed(self):self.reject_result(0,readiness_checks=[0,0])
    def test_neural_not_ready(self):self.reject_result(0,neural_states=[2,1])
    def test_negative_examples_lost(self):self.reject_result(0,negative_examples=[0,0])
    def test_retained_future_source_observed(self):self.reject_result(2,readiness_checks=[0,1])
    def test_output_disagrees(self):self.reject(lambda r:r['scenarios'][0].update(output='{}'))

    def test_reports_require_complete_unique_modes(self):
        b = self.base
        with tempfile.TemporaryDirectory() as temporary:
            paths = {name:Path(temporary)/name for name in b.states if name != 'test_fixture'}
            supplied = []
            for mode in (False,True):
                path = Path(temporary)/str(mode);path.write_text(json.dumps(self.record(mode)));supplied.append(path)
            with patch('contexts_model_proof.source_hashes',return_value=b.hashes), \
                 patch('contexts_model_proof.runtime_test.sha',return_value='d'*64), \
                 patch('contexts_model_proof.runtime_test.source_state',side_effect=lambda p:b.states[p.name]):
                self.assertEqual(len(reports(supplied,b.files,b.config,b.head,paths)),2)
                for bad in (None,[],supplied[:1],[supplied[0],supplied[0]]):
                    with self.assertRaises(ValueError):reports(bad,b.files,b.config,b.head,paths)


if __name__ == '__main__':unittest.main()

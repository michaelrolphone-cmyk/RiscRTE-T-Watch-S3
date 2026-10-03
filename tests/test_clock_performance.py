"""Clock projection limits and schema provenance; no hardware or target fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
import jsonschema

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_clock_deployment import selected_board
from check_twatch_drivers import check_board

class ClockPerformance(unittest.TestCase):
    def test_all_projections_only_change_selected_display_bus(self):
        profiles=sorted((ROOT/'hardware').glob('*.json'))
        self.assertEqual(len(profiles),8)
        manifests=[json.loads(p.read_text()) for p in (ROOT/'drivers').glob('*/manifest.json')]
        for path in profiles:
            with self.subTest(profile=path.name):
                original=json.loads(path.read_text());before=copy.deepcopy(original)
                selected=selected_board(original)
                self.assertEqual(original,before)
                self.assertEqual(next(b for b in original['buses'] if b['instance_id']==103)['frequency_hz'],10000000)
                self.assertEqual(next(b for b in selected['buses'] if b['instance_id']==103)['frequency_hz'],40000000)
                for bus in selected['buses']:
                    old=next(b for b in original['buses'] if b['instance_id']==bus['instance_id'])
                    expected=copy.deepcopy(old)
                    if bus['instance_id']==103:expected['frequency_hz']=40000000
                    self.assertEqual(bus,expected)
                check_board(selected,manifests)
                radio=copy.deepcopy(original)
                next(b for b in radio['buses'] if b['instance_id']==104)['frequency_hz']=40000000
                with self.assertRaises(AssertionError):check_board(radio,manifests)

    def test_schemas_have_typed_frequency_limits(self):
        original=json.loads(next((ROOT/'hardware').glob('*.json')).read_text())
        original['devices']=[next(d for d in original['devices'] if d['config_type']=='display.spi')]
        for schema_name,i2c_limit in [('board-manifest-v1.schema.json',1000000),('twatch-board-v1.schema.json',400000)]:
            validator=jsonschema.Draft202012Validator(json.loads((ROOT/'docs'/schema_name).read_text()))
            for kind,limit in [('spi',40000000),('i2c',i2c_limit)]:
                for hz,valid in [(0,False),(1,True),(limit,True),(limit+1,False)]:
                    with self.subTest(schema=schema_name,kind=kind,hz=hz):
                        board=copy.deepcopy(original)
                        next(b for b in board['buses'] if b['kind']==kind)['frequency_hz']=hz
                        self.assertEqual(validator.is_valid(board),valid)

    def test_runtime_pair_is_explicit(self):
        runtime=json.loads((ROOT/'apps/clock/runtime-requirements.json').read_text())
        self.assertEqual(runtime['source_sha'],'fe9d3c877ac98e52670d458f45b59fda8011a4fd')
        self.assertEqual(runtime['firmware_version'],'0.1.5')
        self.assertEqual(runtime['required_behavior']['provider_poll_max_quantum_ms'],8)
        self.assertEqual(runtime['required_behavior']['scheduler_waits_per_yield'],1)
        self.assertFalse(runtime['abi_changed'])

    def test_schema_provenance_records_local_derivation(self):
        record=json.loads((ROOT/'docs/SCHEMA_PROVENANCE.json').read_text())
        for name,expected in record['derived_schemas'].items():
            self.assertEqual(hashlib.sha256((ROOT/'docs'/name).read_bytes()).hexdigest(),expected)
        source=record['local_clarifications']['spi40mhz-typed-bus-limits-v1']
        self.assertEqual(source['source_commit'],'9884d62113cd2f7aa77cd179c346b9017eb08301')
        self.assertEqual(source['source_blob_sha'],'3273ca23cc7016b4fd210eb0711ba891a823e7bb')
        self.assertEqual(record['upstream_schema_sha256'],'001ea82caae4277ce31a5d9f1064b97618193e84504f6b7f4f094c947c42f7cc')

if __name__=='__main__':unittest.main()

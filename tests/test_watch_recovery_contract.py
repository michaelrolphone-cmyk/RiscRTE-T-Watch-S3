import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from watch_recovery_contract import PRESERVED_APPS, inspect_baseline, validate_overlay

def encoded(value):
    return json.dumps(value).encode()

def stores():
    names = sorted(PRESERVED_APPS) + ['app' + str(i) for i in range(21)]
    boot = {'app_capabilities': [{'manifest': n + '.json', 'grants': []} for n in names],
            'drivers': [{'manifest': 'driver' + str(i)} for i in range(30)]}
    base = {'boot.json': encoded(boot), 'cohort.json': encoded({'product': 'twatch-s3', 'version': '1.1.5'}),
            'ui-scene/manifest.json': encoded({'id': 'scene', 'version': '0.3.1', 'requires': []}),
            'ui-scene/driver.elf': b'provider', 'board.json': b'board',
            'contexts/manifest.json': encoded({'id':'contexts-service','version':'0.3.0','requires':[]}),
            'contexts/driver.elf': b'context-service'}
    for n in names:
        base[n + '.elf'] = n.encode()
        base[n + '.json'] = encoded({'id': n, 'file_name': n + '.elf', 'version': '1.0.0', 'requires': []})
    candidate = copy.deepcopy(base)
    for n in names:
        if n not in PRESERVED_APPS:
            m = json.loads(candidate[n + '.json']); m['version'] = '1.0.1'
            candidate[n + '.json'] = encoded(m); candidate[n + '.elf'] += b'rebuilt'
    m = json.loads(candidate['ui-scene/manifest.json']); m['version'] = '0.3.2'
    candidate['ui-scene/manifest.json'] = encoded(m)
    m = json.loads(candidate['contexts/manifest.json']); m['version'] = '0.3.2'
    candidate['contexts/manifest.json'] = encoded(m)
    return base, candidate

class ContractTests(unittest.TestCase):
    def test_complete_overlay(self):
        base, new = stores(); self.assertEqual(validate_overlay(base, new)['apps'], 25)
    def test_refuses_loss_extra_preserved_and_authority_changes(self):
        for kind in ('lost', 'extra', 'clock', 'boot', 'board'):
            with self.subTest(kind=kind):
                base, new = stores()
                if kind == 'lost': new.pop('app0.elf')
                elif kind == 'extra': new['unexpected'] = b'new'
                else: new[{'clock':'clock.elf','boot':'boot.json','board':'board.json'}[kind]] += b'changed'
                with self.assertRaises(ValueError): validate_overlay(base, new)
    def test_refuses_changed_manifest_authority(self):
        base, new = stores(); m = json.loads(new['app0.json']); m['requires'] = [{'capability':'new'}]
        new['app0.json'] = encoded(m)
        with self.assertRaises(ValueError): validate_overlay(base, new)
    def test_refuses_version_regression(self):
        base, new = stores(); new['app0.json'] = base['app0.json']
        with self.assertRaises(ValueError): validate_overlay(base, new)
    def test_refuses_incomplete_baseline_and_unqualified_sd(self):
        for kind in ('apps', 'providers', 'settings', 'sd'):
            with self.subTest(kind=kind):
                base, _ = stores(); b = json.loads(base['boot.json'])
                if kind == 'apps': b['app_capabilities'].pop()
                elif kind == 'providers': b['drivers'].pop()
                elif kind == 'settings': b['installation'] = {'shared_settings': {}}
                else: b['app_capabilities'][0]['image_source'] = {'path':'app.elf'}
                base['boot.json'] = encoded(b)
                with self.assertRaises(ValueError): inspect_baseline(base)
    def test_refuses_unsafe_paths(self):
        base, _ = stores(); base['../outside'] = b'bad'
        with self.assertRaises(ValueError): inspect_baseline(base)
    def test_refuses_duplicate_app(self):
        base, _ = stores(); b = json.loads(base['boot.json']); b['app_capabilities'][0] = b['app_capabilities'][1]
        base['boot.json'] = encoded(b)
        with self.assertRaises(ValueError): inspect_baseline(base)

if __name__ == '__main__': unittest.main()

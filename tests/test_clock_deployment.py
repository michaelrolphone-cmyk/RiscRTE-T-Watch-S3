"""Checks the actual built deployment and rejects corrupt/overprivileged bundles."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_clock_deployment as builder
from verify_clock_deployment import verify
ROOT=Path(__file__).resolve().parents[1]

class Deployment(unittest.TestCase):
    def test_all_variants_minimal_and_verified(self):
        paths=list((ROOT/'dist/clock-deployments').glob('*.zip'))
        self.assertEqual(len(paths),8)
        for path in paths:
            with self.subTest(path=path.name):
                record=verify(path)
                self.assertEqual(len(record['drivers']),5)
                self.assertEqual(record['runtime_sdk']['RiscRuntimeV1.h']['commit'],
                                 'be6efce33a19d3a21ced4077a038fdcc7b9b94a3')

    def test_projection_does_not_mutate_source(self):
        path=next((ROOT/'hardware').glob('*.json'))
        profile=json.loads(path.read_text());before=json.dumps(profile)
        selected=builder.selected_board(profile)
        self.assertEqual(json.dumps(profile),before)
        self.assertEqual({b['instance_id'] for b in selected['buses']},{101,103})
        self.assertEqual(next(d for d in selected['devices'] if d['instance_id']==5)['config']['rotation'],2)
        self.assertEqual({d['instance_id'] for d in selected['devices']},{1,2,4,5,8})

    def test_corruption_and_extra_grant_rejected(self):
        original=next((ROOT/'dist/clock-deployments').glob('*.zip'))
        with zipfile.ZipFile(original) as z:
            files={name:z.read(name) for name in z.namelist()}
        for semantic in (False,True):
            with self.subTest(semantic=semantic),tempfile.TemporaryDirectory() as tmp:
                payload=dict(files)
                boot=json.loads(payload['store/boot.json'])
                boot['app_capabilities'][0]['grants'].append({'capability':'platform.gpio','api':1,'instance_id':1})
                payload['store/boot.json']=json.dumps(boot).encode()
                if semantic:
                    record=json.loads(payload['deployment-record.json'])
                    entry=next(e for e in record['entries'] if e['path']=='store/boot.json')
                    entry.update(size_bytes=len(payload['store/boot.json']),sha256=hashlib.sha256(payload['store/boot.json']).hexdigest())
                    payload['deployment-record.json']=json.dumps(record).encode()
                path=Path(tmp)/'bad.zip'
                with zipfile.ZipFile(path,'w') as z:
                    for name,data in payload.items():z.writestr(name,data)
                with self.assertRaises(ValueError):verify(path)

if __name__=='__main__':unittest.main()

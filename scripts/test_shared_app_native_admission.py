#!/usr/bin/env python3
"""Successor policy tests; actual compiled native admission remains hosted."""
import copy
import hashlib
import json
import unittest
import shared_app_native_admission as p

def digest(files):
    return hashlib.sha256(json.dumps({n:b.hex() for n,b in sorted(files.items())}).encode()).hexdigest()

class Successor(unittest.TestCase):
    def setUp(self):
        boot={'drivers':[{}]*36,'app_capabilities':[{'manifest':'default.json','grants':[{'capability':'storage.key-value','api':1,'instance_id':6}]}]+[{}]*25}
        self.before={f'app{i}.elf':b'old' for i in range(60)}
        self.before.update({'boot.json':json.dumps(boot).encode(),'default.elf':b'old-home','default.json':b'old-manifest','cohort.json':b'old-cohort'})
        self.after=dict(self.before,**{'default.elf':b'new-home','default.json':b'new-manifest','cohort.json':b'new-cohort'})
        self.calls=[];self.override={};self.fail_call=1
    def run_cohort(self,a,b,expected):
        self.calls.append((a,b,expected))
        row=dict(prepared=True,cohort_validated=True,elf_count=61,hardware_calls=0,storage_calls=0,
                 active_store_sha256=digest(a),candidate_store_sha256=digest(b),active_platform_count=20,candidate_platform_count=20)
        if len(self.calls)==self.fail_call:row.update(self.override)
        return row
    def run_policy(self,count=61):return p.successor_admission(self.run_cohort,self.before,self.after,count,digest)
    def test_actual_transition_and_self(self):
        before=copy.deepcopy(self.before);after=copy.deepcopy(self.after)
        r=self.run_policy()
        self.assertEqual(self.calls,[(self.before,self.after,True),(self.after,self.after,True)])
        self.assertEqual((self.before,self.after),(before,after))
        self.assertEqual(r['mode'],'unchanged-authority-successor');self.assertEqual(r['selected_platform_capacity'],32)
        self.assertTrue(r['boot_authority_byte_identical'])
        self.assertEqual(r['preserving_transition']['active_store_sha256'],digest(before))
    def test_added_grant(self):
        b=json.loads(self.after['boot.json']);b['app_capabilities'][0]['grants'].append({'capability':'other','api':1,'instance_id':1});self.after['boot.json']=json.dumps(b).encode()
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.calls)
    def test_removed_existing_namespace(self):
        b=json.loads(self.after['boot.json']);b['app_capabilities'][0]['grants']=[];self.after['boot.json']=json.dumps(b).encode()
        with self.assertRaises(ValueError):self.run_policy()
        self.assertFalse(self.calls)
    def test_semantically_equal_boot_not_byte_identical(self):
        self.after['boot.json']+=b'\n'
        with self.assertRaises(ValueError):self.run_policy()
    def test_missing_boot(self):
        del self.before['boot.json'];del self.after['boot.json']
        with self.assertRaises(ValueError):self.run_policy()
    def test_added_store_file(self):
        self.after['new']=b''
        with self.assertRaises(ValueError):self.run_policy()
    def test_removed_elf(self):
        self.after.pop('app0.elf')
        with self.assertRaises(ValueError):self.run_policy()
    def test_incomplete_count(self):
        with self.assertRaises(ValueError):self.run_policy(60)
    def test_boolean_count(self):
        with self.assertRaises(ValueError):self.run_policy(True)
    def test_failure_self_admission(self):
        self.fail_call=2;self.override={'cohort_validated':False}
        with self.assertRaises(ValueError):self.run_policy()
        self.assertEqual(len(self.calls),2)

def negative(field,value):
    def test(self):
        self.override={field:value}
        with self.assertRaises(ValueError):self.run_policy()
        self.assertEqual(len(self.calls),1)
    return test
for field,value in [('prepared',False),('cohort_validated',False),('elf_count',60),('hardware_calls',1),('storage_calls',1),('active_store_sha256','bad'),('candidate_store_sha256','bad'),('active_platform_count',19),('candidate_platform_count',21)]:
    setattr(Successor,'test_reject_'+field,negative(field,value))
if __name__=='__main__':unittest.main()

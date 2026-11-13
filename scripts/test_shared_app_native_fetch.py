#!/usr/bin/env python3
import copy
import hashlib
import unittest
from fetch_shared_app_native_baseline import NAMES, validate_release, verify_bytes
class FetchContract(unittest.TestCase):
 def setUp(self):
  self.c={'repo':'owner/repo','release_id':1,'release_tag':'tag','source_revision':'a'*40}
  self.r={'id':1,'draft':False,'tag_name':'tag','assets':[]};self.t={'object':{'type':'commit','sha':'a'*40}}
  for n,(key,name) in enumerate(NAMES.items(),2):
   self.c[key]={'id':n,'bytes':3,'sha256':hashlib.sha256(b'abc').hexdigest()}
   self.r['assets'].append({'id':n,'name':name,'size':3,'browser_download_url':'https://github.com/owner/repo/releases/download/tag/'+name})
 def reject(self,r=None,t=None):
  with self.assertRaises(ValueError):validate_release(self.c,r or self.r,t or self.t)
 def test_exact(self):self.assertEqual(len(validate_release(self.c,self.r,self.t)),3);verify_bytes(self.c['factory'],b'abc')
 def test_wrong_release(self):self.r['id']=2;self.reject()
 def test_draft(self):self.r['draft']=True;self.reject()
 def test_wrong_tag(self):self.t['object']['sha']='b'*40;self.reject()
 def test_annotated_tag(self):self.t['object']['type']='tag';self.reject()
 def test_duplicate(self):self.r['assets'].append(copy.deepcopy(self.r['assets'][0]));self.reject()
 def test_destination(self):self.r['assets'][0]['browser_download_url']='https://example.com/factory';self.reject()
 def test_asset_id(self):self.r['assets'][0]['id']=99;self.reject()
 def test_asset_size(self):self.r['assets'][0]['size']=4;self.reject()
 def test_bytes(self):
  with self.assertRaises(ValueError):verify_bytes(self.c['factory'],b'abd')
if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Offline wrapper regressions; --payload exercises the real frozen native/store.

Creates only temporary files and unreferenced local Git test objects. No network
requests, hardware access, branch updates, private owner credentials or flashes.
"""
import argparse
import copy
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
import zlib

import watch_image_provisioning as w

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime',type=Path,required=True)
parser.add_argument('--payload',type=Path)
args,rest=parser.parse_known_args()
sys.path.insert(0,str(args.runtime.resolve()/'scripts'))
import provision_profile as profile


class Bounds(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def binding_input(self):
        directory=self.root/'binding';store=directory/'store';store.mkdir(parents=True)
        for number in range(95):(store/(str(number)+'.json')).write_bytes(b'{}')
        for name in ('bootfs.bin','binding.json'):(directory/name).write_bytes(b'fixture')
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_STORED) as archive:archive.writestr('LICENSE',b'notice')
        (directory/'LICENSES.zip').write_bytes(output.getvalue())
        return directory

    def test_binding_snapshot_is_frozen_and_inventory_bounded(self):
        directory=self.binding_input();output=self.root/'snapshot'
        w.snapshot_product(directory,output,profile)
        (directory/'store/0.json').write_bytes(b'changed')
        self.assertEqual((output/'store/0.json').read_bytes(),b'{}')
        (directory/'extra').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'inventory'):w.snapshot_product(directory,self.root/'bad',profile)
        self.assertFalse((self.root/'bad').exists())

    def test_binding_license_expansion_refused_before_binder(self):
        directory=self.binding_input();output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('LICENSE',b'A'*(8*1024*1024))
        (directory/'LICENSES.zip').write_bytes(output.getvalue())
        with patch.object(w,'pinned_binding_source'),patch.object(w.binding,'verify') as binder,\
                self.assertRaisesRegex(ValueError,'License ZIP'):
            w.checked_product(directory,self.root,self.root,'fixture',None,profile)
        binder.assert_not_called();self.assertFalse((self.root/'bad').exists())

    def test_binding_store_links_counts_and_file_bounds(self):
        directory=self.binding_input();store=directory/'store'
        (store/'0.json').unlink();(store/'0.json').symlink_to(store/'1.json')
        with self.assertRaisesRegex(ValueError,'symlink'):w.snapshot_product(directory,self.root/'link',profile)
        (store/'0.json').unlink();(store/'0.json').write_bytes(b'{}');(store/'extra.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'file count'):w.snapshot_product(directory,self.root/'count',profile)
        (store/'extra.json').unlink()
        with (store/'0.json').open('wb') as stream:stream.truncate(1024*1024+1)
        with self.assertRaisesRegex(ValueError,'bounds'):w.snapshot_product(directory,self.root/'large',profile)

    def test_binding_path_count_and_aggregate_bounds(self):
        directory=self.binding_input();store=directory/'store'
        for number in range(162):(store/('empty'+str(number))).mkdir()
        with self.assertRaisesRegex(ValueError,'path count'):w.snapshot_product(directory,self.root/'paths',profile)
        for path in store.iterdir():
            if path.is_dir():path.rmdir()
        for number in range(6):
            with (store/(str(number)+'.json')).open('wb') as stream:stream.truncate(1024*1024)
        with self.assertRaisesRegex(ValueError,'bounds'):w.snapshot_product(directory,self.root/'total',profile)
        self.assertFalse((self.root/'total').exists())

    def test_directory_limits_and_symlink_refusal(self):
        for number in range(64):(self.root/str(number)).write_bytes(b'x')
        self.assertEqual(len(w.read_seed(self.root,profile)),64)
        (self.root/'extra').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'inventory bound'):w.read_seed(self.root,profile)
        (self.root/'extra').unlink();(self.root/'0').unlink();(self.root/'0').symlink_to(self.root/'1')
        with self.assertRaisesRegex(ValueError,'symlink'):w.read_seed(self.root,profile)

    def test_directory_aggregate_and_individual_bounds(self):
        # Sparse host files avoid storing a large test fixture in the repository.
        for name in ('a','b'):
            with (self.root/name).open('wb') as stream:stream.truncate(32*1024*1024)
        (self.root/'c').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'bounds'):w.read_seed(self.root,profile)
        for path in self.root.iterdir():path.unlink()
        with (self.root/'large').open('wb') as stream:stream.truncate(32*1024*1024+1)
        with self.assertRaisesRegex(ValueError,'bounds'):w.read_seed(self.root,profile)

    def test_zip_duplicate_traversal_symlink_and_count_refusals(self):
        cases=[['same','same'],['../outside'],['nested/file'],[str(n) for n in range(65)]]
        for names in cases:
            output=io.BytesIO()
            with warnings.catch_warnings(),zipfile.ZipFile(output,'w') as archive:
                warnings.simplefilter('ignore',UserWarning)
                for name in names:archive.writestr(name,b'x')
            with self.assertRaises(ValueError):w.unpack(output.getvalue(),profile)
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            entry=zipfile.ZipInfo('link');entry.external_attr=0o120777<<16
            archive.writestr(entry,b'target')
        with self.assertRaisesRegex(ValueError,'member refused'):w.unpack(output.getvalue(),profile)

    def test_archive_reproducible_and_sorted(self):
        files={'z.json':b'z','a.json':b'a'}
        self.assertEqual(w.archive_bytes(files),w.archive_bytes(dict(reversed(list(files.items())))))
        self.assertEqual(w.unpack(w.archive_bytes(files),profile),files)

    def test_zip_expansion_is_bounded_even_with_false_header_size(self):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('test.json',b'A'*(2*1024*1024))
        raw=bytearray(output.getvalue());central=raw.index(b'PK\x01\x02')
        for offset in (14,central+16):struct.pack_into('<I',raw,offset,zlib.crc32(b'A'))
        for offset in (22,central+24):struct.pack_into('<I',raw,offset,1)
        original=zipfile._get_decompressor;allocations=[]
        class Measured:
            def __init__(self,inner):self.inner=inner
            def __getattr__(self,name):return getattr(self.inner,name)
            def decompress(self,*arguments):
                result=self.inner.decompress(*arguments);allocations.append(len(result));return result
        with patch.object(zipfile,'_get_decompressor',side_effect=lambda method:Measured(original(method))):
            self.assertEqual(w.unpack(bytes(raw),profile),{'test.json':b'A'})
        self.assertTrue(allocations);self.assertLessEqual(max(allocations),65536)

    def test_completion_is_last_and_failed_write_removes_output(self):
        output=self.root/'output';original=w.write_files;observations=[]
        def observed(directory,files):
            observations.append((set(files),(directory/'COMPLETE').exists()))
            original(directory,files)
        with patch.object(w,'write_files',side_effect=observed):
            w.publish_files(output,{'COMPLETE':b'done','payload':b'content'},profile)
        self.assertEqual(observations,[({'payload'},False),({'COMPLETE'},False)])
        def interrupted(directory,files):
            original(directory,files)
            self.assertFalse((directory/'COMPLETE').exists())
            raise KeyboardInterrupt()
        failed=self.root/'interrupted'
        with patch.object(w,'write_files',side_effect=interrupted),self.assertRaises(KeyboardInterrupt):
            w.publish_files(failed,{'COMPLETE':b'done','payload':b'content'},profile)
        self.assertFalse(failed.exists())

    def test_recipe_commit_and_helper_custody(self):
        repository=self.root/'repository';repository.mkdir()
        def git(*arguments):
            return subprocess.check_output(['git','-c','user.name=Codex','-c','user.email=codex@openai.com',
                                            *arguments],cwd=repository,stderr=subprocess.DEVNULL).decode().strip()
        git('init');(repository/'scripts').mkdir();helper=repository/'scripts/helper.py';helper.write_text('original\n')
        git('add','.');git('commit','-m','Original recipe');source=git('rev-parse','HEAD');tree=git('rev-parse','HEAD^{tree}')
        with patch.object(w,'ROOT',repository):
            w.pinned_packaging_source(source)
            with self.assertRaisesRegex(ValueError,'must be a commit'):w.pinned_packaging_source(tree)
            helper.write_text('changed\n')
            with self.assertRaisesRegex(ValueError,'dirty'):w.pinned_packaging_source(source)
            git('add','.');git('commit','-m','Changed helper')
            with self.assertRaisesRegex(ValueError,'Packaging source differs'):w.pinned_packaging_source(source)


@unittest.skipUnless(args.payload,'Supply --payload for genuine native/store checks')
class Product(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt,cls.files,cls.frozen=w.verify_payload(args.runtime,args.payload)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def payload(self,mutations=None):
        payload=self.root/'payload';payload.mkdir()
        w.write_files(payload,{**self.frozen,**(mutations or {})})
        return payload

    def git(self,arguments,raw=None,env=None):
        return subprocess.check_output(['git',*arguments],input=raw,cwd=w.ROOT,env=env).decode().strip()

    def commit(self,mutations=None):
        environment={**os.environ,'GIT_INDEX_FILE':str(self.root/'index')}
        self.git(['read-tree','HEAD'],env=environment)
        for name,raw in sorted({**self.frozen,**(mutations or {})}.items()):
            blob=self.git(['hash-object','-w','--stdin'],raw)
            self.git(['update-index','--add','--cacheinfo','100644,'+blob+','+w.PAYLOAD_PATH+'/'+name],env=environment)
        tree=self.git(['write-tree'],env=environment)
        commit=self.git(['-c','user.name=Codex','-c','user.email=codex@openai.com',
                         'commit-tree',tree,'-p','HEAD','-m','Unreferenced offline provisioning test'])
        return commit,tree

    def test_real_full_store_and_native_admitted(self):
        self.assertEqual(len(self.files),95)
        self.assertEqual(self.receipt['elf_count'],46)
        self.assertEqual(self.receipt['runtime_version'],'0.1.73')
        self.assertIn('board.json',self.files);self.assertIn('default.elf',self.files)
        self.assertFalse(self.receipt['admission']['hardware_calls'])
        self.assertFalse(self.receipt['admission']['storage_calls'])

    def test_incomplete_and_extra_payload_refused(self):
        payload=self.payload({'COMPLETE':b'incomplete'})
        with self.assertRaisesRegex(ValueError,'Incomplete'):w.verify_payload(args.runtime,payload)
        (payload/'COMPLETE').write_bytes(self.frozen['COMPLETE']);(payload/'extra').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'inventory'):w.verify_payload(args.runtime,payload)

    def test_rehashed_license_tamper_refused(self):
        altered=bytearray(self.frozen['LICENSES.zip']);altered[len(altered)//2]^=1
        receipt=copy.deepcopy(self.receipt);receipt['licenses_zip']=w.meta(altered)
        bound=json.loads(self.frozen['binding.json']);bound['licenses']={'size_bytes':len(altered),'sha256':w.meta(altered)['sha256']}
        payload=self.payload({'LICENSES.zip':bytes(altered),'payload.json':w.encoded(receipt),'binding.json':w.encoded(bound)})
        with self.assertRaises((ValueError,zipfile.BadZipFile)):w.verify_payload(args.runtime,payload)

    def test_rehashed_image_tamper_refused(self):
        altered=bytearray(self.frozen['image.bin']);needle=self.files['default.elf'][:32]
        offset=altered.find(needle);self.assertGreaterEqual(offset,0);altered[offset+16]^=1
        receipt=copy.deepcopy(self.receipt);receipt['image']=w.meta(altered)
        payload=self.payload({'image.bin':bytes(altered),'payload.json':w.encoded(receipt)})
        with self.assertRaises(ValueError):w.verify_payload(args.runtime,payload)

    def test_seed_duplicate_and_native_digest_tamper_refused(self):
        seed=w.unpack(self.frozen['seed.zip'],profile)
        changed=bytearray(seed['firmware.bin']);changed[-1]^=1;seed['firmware.bin']=bytes(changed)
        archive=w.archive_bytes(seed);receipt=copy.deepcopy(self.receipt);receipt['seed_zip']=w.meta(archive)
        payload=self.payload({'seed.zip':archive,'payload.json':w.encoded(receipt)})
        with self.assertRaisesRegex(ValueError,'seed digest'):w.verify_payload(args.runtime,payload)

    def test_exact_commit_pin_tree_refusal_and_url_validation(self):
        commit,tree=self.commit();output=self.root/'deployment'
        result=w.bind(args.runtime,args.payload,commit,output)
        self.assertEqual(result['payload_revision'],commit)
        self.assertEqual(len(json.loads((output/'inventory.json').read_bytes())['files']),95)
        with self.assertRaisesRegex(ValueError,'must be a commit'):
            w.bind(args.runtime,args.payload,tree,self.root/'tree-deployment')
        self.assertFalse((self.root/'tree-deployment').exists())
        record=json.loads((output/'deployment.json').read_bytes())
        for item in record['downloads'].values():item['url']=item['url'].replace('https://','http://')
        (output/'deployment.json').write_bytes(w.encoded(record))
        # All malformed URLs are rejected before an opener can request one.
        with self.assertRaisesRegex(ValueError,'image differs|download identity'):
            w.verify_endpoints(args.runtime,output)

    def test_committed_byte_mismatch_and_existing_output_refused(self):
        commit,_=self.commit({'COMPLETE':b'altered'})
        with self.assertRaisesRegex(ValueError,'Committed payload bytes'):
            w.bind(args.runtime,args.payload,commit,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())
        output=self.root/'existing';output.mkdir();(output/'owner').write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError,'output already exists'):
            w.bind(args.runtime,args.payload,commit,output)
        self.assertEqual((output/'owner').read_bytes(),b'keep')


if __name__=='__main__':unittest.main(argv=[sys.argv[0],*rest])

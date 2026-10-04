"""Real-artifact custody negatives; mandatory target-rebuild rejection in CI."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import audio_deployment as audio
import build_audio_flash_bundle as flash
from build_audio_apps import verify_target_bytes
from build_wifi_store import build as pack
from build_wifi_flash_bundle import verify_receipt


def refreshed(files):
    files=dict(files);r=json.loads(files.pop('deployment-record.json'));r['entries']=audio.entries(files);files['deployment-record.json']=audio.encoded(r);return files


class AudioCustody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archives=sorted((ROOT/'dist/audio-deployments').glob('*.zip'))
        if len(cls.archives)!=9:raise RuntimeError('Build eight audio profiles and common before testing')
        cls.path=next(p for p in cls.archives if p.name.endswith(audio.PROFILE+'.zip'));cls.files=audio.read_zip(cls.path);cls.record=json.loads(cls.files['deployment-record.json'])
    def rejects(self,change,message=''):
        f=copy.deepcopy(self.files);change(f)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'tampered.zip';p.write_bytes(audio.zip_bytes(refreshed(f)))
            with self.assertRaisesRegex((ValueError,AssertionError,KeyError),message):audio.verify(p)
    def test_nine_profiles_preserve_baseline(self):
        for p in self.archives:
            r=audio.verify(p,expected_head=self.record['source_sha']);self.assertEqual(r['changed_baseline_store'],sorted(audio.BASELINE_CHANGES));self.assertEqual(r['added_store'],['frequency_generator.elf','frequency_generator.json']);self.assertEqual(r['baseline']['store_files'],44)
        self.assertEqual(len({audio.verify(p)['profile'] for p in self.archives}),9)
    def test_preserved_bytes_cannot_be_rehashed(self):
        for p in ('store/default.elf','store/clock.elf','store/wifi_settings.elf','store/alarm-service/driver.elf','store/speaker/driver.elf','store/board.json'):
            with self.subTest(path=p):self.rejects(lambda f,p=p:f.__setitem__(p,f[p]+b'changed'),'overlay')
    def test_no_app_loss_or_extra_file(self):
        self.rejects(lambda f:f.pop('store/points_in_time.elf'),'overlay');self.rejects(lambda f:f.__setitem__('store/unreviewed',b'bad'),'overlay')
    def test_policy_cannot_expand_or_strip(self):
        for index in (0,-1):
            def change(f,index=index):
                b=json.loads(f['store/boot.json']);b['app_capabilities'][index]['grants'].pop();f['store/boot.json']=audio.encoded(b)
            self.rejects(change,'overlay')
        def change(f):
            b=json.loads(f['store/boot.json']);b['app_capabilities'][-1]['grants'].append(dict(capability='storage.key-value',api=1,instance_id=6));f['store/boot.json']=audio.encoded(b)
        self.rejects(change,'overlay')
    def test_baseline_cannot_hide_rehashed_change(self):
        def change(f):
            old=audio.read_zip(io.BytesIO(f['baseline.zip']));old['store/default.elf']+=b'bad';f['baseline.zip']=audio.zip_bytes(refreshed(old))
        self.rejects(change)
    def test_catalog_cannot_drop_or_reorder(self):
        def change(f):
            c=json.loads(f['catalog.json']);c[0],c[1]=c[1],c[0];f['catalog.json']=audio.encoded(c)
        self.rejects(change,'catalog')
    def test_exact_manifest_and_owner(self):
        def change(f):
            m=json.loads(f['store/frequency_generator.json']);m['requires'].pop();f['store/frequency_generator.json']=audio.encoded(m)
        self.rejects(change,'manifest')
        def owner(f):
            r=json.loads(f['audio-build.json']);r['apps']['frequency_generator']['repository_sha']='0'*40;f['audio-build.json']=audio.encoded(r)
        self.rejects(owner,'owning source')
    def test_runtime_pair_cannot_be_rehashed(self):
        def change(f):
            r=json.loads(f['runtime-requirements.json']);r['source_sha']='0'*40;f['runtime-requirements.json']=audio.encoded(r)
        self.rejects(change,'overlay')
    def test_source_pin_and_head(self):
        def change(f):
            r=json.loads(f['audio-build.json']);r['sources']['runtime']['commit']='0'*40;f['audio-build.json']=audio.encoded(r)
        self.rejects(change,'pins')
        with self.assertRaisesRegex(ValueError,'source head'):audio.verify(self.path,expected_head='0'*40)
    def test_target_shape_and_hash(self):
        self.rejects(lambda f:f.__setitem__('store/frequency_generator.elf',b'not ELF'),'target Xtensa')
        self.rejects(lambda f:f.__setitem__('store/frequency_generator.elf',f['store/frequency_generator.elf']+b'bad'),'Stale target')
    @unittest.skipUnless(os.environ.get('TWATCH_MKSPIFFS'),'Set pinned SPIFFS tool')
    def test_actual_spiffs_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            r=pack(self.path,Path(os.environ['TWATCH_MKSPIFFS']),Path(d),verify_archive=audio.verify);self.assertEqual(r['files'],46);self.assertTrue(r['round_trip_verified'])
    @unittest.skipUnless(all(os.environ.get(n) for n in ('AUDIO_SYSTEM_APPS','AUDIO_UTILITIES','AUDIO_BASELINE_SYSTEM_APPS')),'Set exact source paths for mandatory CI rebuild negative')
    def test_rehashed_valid_elf_rejected_by_source_rebuild(self):
        f=copy.deepcopy(self.files);data=f['store/frequency_generator.elf']+b'rehashed tamper';f['store/frequency_generator.elf']=data
        r=json.loads(f['audio-build.json']);r['apps']['frequency_generator'].update(size_bytes=len(data),sha256=audio.sha(data));f['audio-build.json']=audio.encoded(r)
        compiled={n+ext:f['store/'+n+ext] for n in ('springboard',*audio.APPS) for ext in ('.elf','.json')};compiled.update({n:f[n] for n in ('audio-build.json','catalog.json')})
        with tempfile.TemporaryDirectory() as d:
            archive=Path(d)/'baseline.zip';archive.write_bytes(f['baseline.zip'])
            with self.assertRaisesRegex(ValueError,'Independent target source rebuild differs'):
                verify_target_bytes(compiled,archive,*[Path(os.environ[n]).resolve() for n in ('AUDIO_SYSTEM_APPS','AUDIO_UTILITIES','AUDIO_BASELINE_SYSTEM_APPS')])
    def test_six_job_gate(self):
        raw=b'hosted artifact';h='1'*40;t='2'*40;r=dict(repository='michaelrolphone-cmyk/RiscRTE-T-Watch-S3',head=h,tree=t,conclusion='success',expired=False,artifact_name='twatch-audio-integration-'+h,artifact_sha256=audio.sha(raw),run_id=1,artifact_id=2,jobs=[dict(name=n,conclusion='success') for n in sorted(flash.JOBS)])
        verify_receipt(r,raw,h,t,required_jobs=flash.JOBS,artifact_prefix='twatch-audio-integration-')
        for missing in flash.JOBS:
            changed={**r,'jobs':[j for j in r['jobs'] if j['name']!=missing]}
            with self.subTest(missing=missing),self.assertRaises(ValueError):verify_receipt(changed,raw,h,t,required_jobs=flash.JOBS,artifact_prefix='twatch-audio-integration-')
        for failed in flash.JOBS:
            changed=copy.deepcopy(r);next(j for j in changed['jobs'] if j['name']==failed)['conclusion']='failure'
            with self.subTest(failed=failed),self.assertRaises(ValueError):verify_receipt(changed,raw,h,t,required_jobs=flash.JOBS,artifact_prefix='twatch-audio-integration-')
if __name__=='__main__':unittest.main()

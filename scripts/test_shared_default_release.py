#!/usr/bin/env python3
"""Release transport contracts and negative mutations; no hardware claims."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import shared_default_release as release
import publish_shared_default_release as publisher
import package_shared_default as package


class ReleaseContracts(unittest.TestCase):
    def fixture(self):
        p = package.pins(); c = package.baseline_contract(p); revision = '1' * 40
        sources = {r: {'revision': revision if r == 'product' else p[r+'_revision'], 'tree': '2'*40, 'submodules': []} for r in release.ROLES}
        lock = dict(schema=1, publication_enabled=False, candidate_version=p['version'], sources=sources)
        proof = dict(fresh_build=True, same_process_qualification=True, detached_receipt_is_attestation=False, compile_jobs=1, sources=sources)
        q = dict(schema=1, status='software-qualified-candidate-hardware-pending', product=p['product'], version=p['version'], source_revision=revision,
            publication_enabled=False, hardware_tested=False, device_accessed=False, factory_erases_data=True, preserving_update_kit_emitted=False,
            native_rebuilt=True, input_lock=lock, controlled_build=proof, artifacts={n: {'bytes': 1, 'sha256':'3'*64} for n in release.NATIVE},
            default=dict(independent_builds_identical=True,hardware_tested=False,default_sha256=p['default_sha256'],default_bytes=p['default_bytes'],manifest_sha256=p['default_manifest_sha256']),
            serial_files=p['serial_files'], baseline_contract=c, native=dict(arduino_core_linked=False,ordinary_app_payloads_rebuilt=False,unselected_usb_host_controller=False,elf_bin_identical=True),
            preservation_software_model=dict(passed=True,cases=496,nvs_and_appdata_preserved=True,bootloader_compatibility_tested=False,hardware_tested=False),
            preservation=dict(changed_store_files=package.CHANGED,unchanged_store_payloads=len(c['files'])-len(package.CHANGED),unchanged_elf_count=c['elf_count']-1,alarm_sha256=package.ALARM_SHA))
        for k,san in [('admission',False),('admission_sanitized',True)]:
            q[k]=dict(elf_count=c['elf_count'],sanitized=san,hardware_calls=0,storage_calls=0,target_instructions_executed=False)
        return q,p,revision

    def test_qualified_envelope(self):
        q,p,rev=self.fixture()
        self.assertEqual(release.check_qualification(q,p,rev),q['input_lock'])

    def test_every_contract_field_rejects_mutation(self):
        q,p,rev=self.fixture()
        mutations={('schema',):2,('status',):'store-stage-only-not-firmware-qualified',('product',):'other',('version',):'0.0.0',('source_revision',):'4'*40,
            ('publication_enabled',):True,('hardware_tested',):True,('device_accessed',):True,('factory_erases_data',):False,
            ('preserving_update_kit_emitted',):True,('native_rebuilt',):False,('input_lock','schema'):2,('input_lock','publication_enabled'):True,
            ('input_lock','candidate_version'):'0.0.0',('controlled_build','fresh_build'):False,('controlled_build','same_process_qualification'):False,
            ('controlled_build','detached_receipt_is_attestation'):True,('controlled_build','compile_jobs'):2,
            ('default','independent_builds_identical'):False,('default','hardware_tested'):True,('default','default_sha256'):'4'*64,
            ('serial_files','active_boot_bank_writable'):True,('serial_files','namespaces'):[],
            ('default','default_bytes'):1,('default','manifest_sha256'):'4'*64,('baseline_contract','factory_sha256'):'4'*64,
            ('native','arduino_core_linked'):True,('native','ordinary_app_payloads_rebuilt'):True,('native','unselected_usb_host_controller'):True,
            ('native','elf_bin_identical'):False,('preservation_software_model','passed'):False,('preservation_software_model','cases'):0,
            ('preservation_software_model','nvs_and_appdata_preserved'):False,('preservation_software_model','hardware_tested'):True,
            ('preservation_software_model','bootloader_compatibility_tested'):True,('preservation','changed_store_files'):[],
            ('preservation','unchanged_store_payloads'):0,('preservation','unchanged_elf_count'):0,('preservation','alarm_sha256'):'4'*64}
        for k in ('admission','admission_sanitized'):
            for field,v in [('elf_count',0),('sanitized',k!='admission_sanitized'),('hardware_calls',1),('storage_calls',1),('target_instructions_executed',True)]:mutations[(k,field)]=v
        for path,value in mutations.items():
            bad=copy.deepcopy(q); node=bad
            for key in path[:-1]:node=node[key]
            node[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(ValueError):release.check_qualification(bad,p,rev)
        for role in release.ROLES:
            for field,value in [('revision','4'*40),('tree','bad'),('submodules',['+dirty'])]:
                bad=copy.deepcopy(q);bad['input_lock']['sources'][role][field]=value
                with self.subTest(role=role,field=field),self.assertRaises(ValueError):release.check_qualification(bad,p,rev)
        for target in ('artifacts','input_lock'):
            bad=copy.deepcopy(q)
            if target=='artifacts':bad[target].pop('store.bin')
            else:bad[target]['sources'].pop('watch')
            with self.assertRaises(ValueError):release.check_qualification(bad,p,rev)

    def test_directory_custody(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); data=b'payload'; (root/'file.bin').write_bytes(data)
            sums=(package.sha(data)+'  file.bin\n').encode(); (root/'SHA256SUMS').write_bytes(sums)
            release.check_directory(root,package.sha(sums),{'file.bin','SHA256SUMS'})
            for change in ('digest','extra','missing','symlink'):
                with self.subTest(change=change):
                    if change=='digest':(root/'file.bin').write_bytes(b'changed')
                    if change=='extra':(root/'extra').write_bytes(b'x')
                    if change=='missing':(root/'file.bin').unlink()
                    if change=='symlink':(root/'file.bin').unlink();(root/'file.bin').symlink_to(root/'SHA256SUMS')
                    with self.assertRaises(ValueError):release.check_directory(root,package.sha(sums),{'file.bin','SHA256SUMS'})
                    for path in root.iterdir():
                        if path.name!='SHA256SUMS':path.unlink()
                    (root/'file.bin').write_bytes(data)
            with self.assertRaises(ValueError):release.check_directory(root,'0'*64)
            (root/'SHA256SUMS').write_bytes(sums+sums)
            with self.assertRaises(ValueError):release.check_directory(root)

    def output_fixture(self):
        q,p,rev=self.fixture();p=dict(p)
        default=b'synthetic-default';manifest=b'synthetic-manifest'
        p.update(default_bytes=len(default),default_sha256=package.sha(default),default_manifest_sha256=package.sha(manifest))
        q['default'].update(default_bytes=p['default_bytes'],default_sha256=p['default_sha256'],manifest_sha256=p['default_manifest_sha256'])
        native_blobs={k:('native-'+k).encode() for k in release.native.ARTIFACT_KEYS}
        q['input_lock']['native_files']={k:dict(path=k+'.bin',**package.record(b)) for k,b in native_blobs.items()}
        q['controlled_build']['artifacts']={k:package.record(b) for k,b in native_blobs.items()}
        target=json.loads((package.ROOT/'docs/native-idf61/released-baseline.json').read_bytes())['target']
        iq={'schema':1,'target_identity':target,'elf_sha256':package.sha(native_blobs['firmware_elf'])}
        q['native']['radio_iq']=iq
        blobs={'factory-candidate-erases-data-0x0.bin':b'synthetic-factory','store.bin':b'synthetic-store',
               'firmware.bin':native_blobs['firmware_bin'],'bootloader.bin':native_blobs['bootloader'],'partitions.bin':native_blobs['partitions']}
        q['artifacts']={n:package.record(b) for n,b in blobs.items()}
        blobs.update({'qualification.json':package.encoded(q),'source-lock.json':package.encoded(q['input_lock']),
                      'source-pins.json':(package.DOCS/'source-pins.json').read_bytes(),'default.elf':default,'default.json':manifest})
        evidence={n:blobs[n] for n in ['qualification.json','default.elf','default.json']}
        evidence.update({'build-evidence/build-closure.json':package.encoded(q['controlled_build']),'build-evidence/source-lock.json':blobs['source-lock.json']})
        evidence.update({'build/'+k+'.bin':b for k,b in native_blobs.items()})
        blobs['candidate-evidence.zip']=release.make_archive(evidence)
        _,renamed=release.release_names(p);files={renamed.get(n,n):b for n,b in blobs.items()}
        repo='michaelrolphone-cmyk/'+release.PRODUCTS[p['product']][0]
        ci={'GITHUB_REPOSITORY':repo,'GITHUB_SHA':rev,'GITHUB_WORKFLOW_SHA':rev,'GITHUB_REF':'refs/heads/work/serial-files-native',
            'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKFLOW_REF':repo+'/.github/workflows/shared-default-native.yml@refs/heads/work/serial-files-native'}
        c=package.baseline_contract(p);workflow=(package.ROOT/'.github/workflows/shared-default-native.yml').read_bytes()
        metadata={'ci-run.json':package.encoded(ci),'workflow.yml':workflow,'compiler-version.txt':b'esp-15.2.0_20251204',
            'iq-linked.json':package.encoded(iq),'baseline-tag.json':package.encoded({'ref':'refs/tags/'+c['release_tag'],'object':{'type':'commit','sha':c['source_revision']}}),
            'baseline-release.json':package.encoded({'tag_name':c['release_tag'],'draft':False,'assets':[{'name':c['factory_asset'],'browser_download_url':'https://github.com/'+repo+'/releases/download/'+c['release_tag']+'/'+c['factory_asset']}]})}
        files['ci-provenance.zip']=release.make_archive(metadata)
        files['TESTING.txt']=b'test instructions';files['RELEASE-NOTES.txt']=b'hardware pending'
        report=dict(schema=1,repository=repo,product=p['product'],version=p['version'],source_revision=rev,release_tag=p['release_tag'],publication_enabled=p['publication_enabled'],
            native_rebuilt=True,hardware_tested=False,device_accessed=False,factory_erases_data=True,preserving_update_kit_emitted=False,final_factory_default_extracted=True,
            changed_store_files=package.CHANGED,default_sha256=p['default_sha256'],default_manifest_sha256=p['default_manifest_sha256'],
            source_lock=q['input_lock'],qualification_sha256=package.sha(files['qualification.json']),
            ci={'repository':repo,'run_id':123,'run_attempt':1,'source_revision':rev,'firmware_elf_sha256':iq['elf_sha256'],'workflow_sha256':package.sha(workflow)})
        return files,report,p,rev

    def write_output(self,root,files,report):
        report=copy.deepcopy(report);report['artifacts']={n:package.record(b) for n,b in files.items()}
        out=dict(files);out['release.json']=package.encoded(report)
        sums=''.join(package.sha(b)+'  '+n+'\n' for n,b in sorted(out.items())).encode()
        out['SHA256SUMS']=sums
        for old in root.iterdir():old.unlink()
        for n,b in out.items():(root/n).write_bytes(b)
        return package.sha(sums)

    def test_complete_release_and_resigned_mutations(self):
        files,report,p,rev=self.output_fixture()
        with tempfile.TemporaryDirectory() as d,patch.object(package,'pins',return_value=p):
            root=Path(d);digest=self.write_output(root,files,report)
            release.verify_output(root,digest,rev)
            for name in files:
                bad=dict(files);del bad[name];digest=self.write_output(root,bad,report)
                with self.subTest(missing=name),self.assertRaises(ValueError):release.verify_output(root,digest,rev)
            for key,value in [('schema',2),('repository','WRONG-REPOSITORY'),('native_rebuilt',False),('hardware_tested',True),('final_factory_default_extracted',False)]:
                bad=dict(report);bad[key]=value;digest=self.write_output(root,files,bad)
                with self.subTest(field=key),self.assertRaises(ValueError):release.verify_output(root,digest,rev)
            for name in ('firmware.bin','source-lock.json','source-pins.json','default.elf','default.json','store.bin'):
                bad=dict(files);bad[name]=b'{}';digest=self.write_output(root,bad,report)
                with self.subTest(changed=name),self.assertRaises(ValueError):release.verify_output(root,digest,rev)
            bad=dict(files);bad['unexpected.bin']=b'payload';digest=self.write_output(root,bad,report)
            with self.assertRaises(ValueError):release.verify_output(root,digest,rev)
            q=json.loads(files['qualification.json']);del q['input_lock']['native_files']['firmware_map'];del q['controlled_build']['artifacts']['firmware_map']
            bad=dict(files);bad['qualification.json']=package.encoded(q);bad['source-lock.json']=package.encoded(q['input_lock'])
            digest=self.write_output(root,bad,report)
            with self.assertRaisesRegex(ValueError,'Incomplete native evidence inventory'):release.verify_output(root,digest,rev)
            import io,zipfile
            with zipfile.ZipFile(io.BytesIO(files['ci-provenance.zip'])) as z:metadata={n:z.read(n) for n in z.namelist()}
            for name in metadata:
                changed=dict(metadata);del changed[name]
                bad=dict(files);bad['ci-provenance.zip']=release.make_archive(changed);digest=self.write_output(root,bad,report)
                with self.subTest(missing_ci=name),self.assertRaises(ValueError):release.verify_output(root,digest,rev)
            ci=json.loads(metadata['ci-run.json']);ci['GITHUB_SHA']='f'*40
            changed=dict(metadata);changed['ci-run.json']=package.encoded(ci);bad=dict(files);bad['ci-provenance.zip']=release.make_archive(changed)
            digest=self.write_output(root,bad,report)
            with self.assertRaises(ValueError):release.verify_output(root,digest,rev)

    def test_immutable_publication_resume(self):
        rev='1'*40; tag='test-shared-default-1.2.3'; name='refs/tags/'+tag
        row={'ref':name,'object':{'type':'commit','sha':rev}}
        self.assertFalse(publisher.check_tags([],tag,'1.2.3',rev))
        self.assertTrue(publisher.check_tags([row],tag,'1.2.3',rev))
        for bad in [dict(row,ref='refs/tags/other-1.2.3'),dict(row,object={'type':'commit','sha':'2'*40}),dict(row,object={'type':'tag','sha':rev})]:
            with self.assertRaises(ValueError):publisher.check_tags([bad],tag,'1.2.3',rev)
        r={'tag_name':tag,'prerelease':True,'draft':True,'assets':[{'name':'one','state':'uploaded'}]}
        self.assertEqual(publisher.check_release(r,tag,{'one','two'}),{'two'})
        with self.assertRaises(ValueError):publisher.check_release(dict(r,draft=False),tag,{'one','two'})
        self.assertEqual(publisher.check_release(dict(r,draft=False),tag,{'one'}),set())
        for bad in [dict(r,tag_name='other'),dict(r,prerelease=False),dict(r,assets=r['assets']*2),dict(r,assets=[{'name':'other','state':'uploaded'}]),dict(r,assets=[{'name':'one','state':'new'}])]:
            with self.assertRaises(ValueError):publisher.check_release(bad,tag,{'one','two'})

    def test_full_publication_and_interrupted_upload_resume(self):
        files,report,p,rev=self.output_fixture();p.update(finalized=True,publication_enabled=True);report['publication_enabled']=True
        repo='michaelrolphone-cmyk/'+release.PRODUCTS[p['product']][0];tag=p['release_tag']
        title=release.PRODUCTS[p['product']][1]+' '+p['version']+' shared default, hardware pending'
        for mode in ('new','tag_only','partial_draft','complete_published','corrupt_existing','wrong_text'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d,patch.object(package,'pins',return_value=p):
                root=Path(d);digest=self.write_output(root,files,report);all_files={f.name:f.read_bytes() for f in root.iterdir()}
                state={'tag':mode!='new','release':None,'assets':{},'calls':[]}
                if mode not in ('new','tag_only'):
                    state['release']={'tag_name':tag,'prerelease':True,'draft':mode!='complete_published','name':title,
                        'body':files['RELEASE-NOTES.txt'].decode(),'html_url':'https://github.com/'+repo+'/releases/tag/'+tag}
                    selected=all_files if mode=='complete_published' else dict(list(all_files.items())[:2])
                    state['assets']=dict(selected)
                    if mode=='corrupt_existing':state['assets'][next(iter(selected))]=b'corrupt'
                    if mode=='wrong_text':state['release']['body']='hardware tested'
                def api(*args,**kw):
                    state['calls'].append(args)
                    if args[:3]==('api','--paginate','--slurp'):
                        if args[3].endswith('/git/matching-refs/tags/'):
                            return [[{'ref':'refs/tags/'+tag,'object':{'type':'commit','sha':rev}}]] if state['tag'] else [[]]
                        if args[3].endswith('/releases?per_page=100'):
                            if state['release'] is None:return [[]]
                            r=copy.deepcopy(state['release']);r['assets']=[{'name':n,'state':'uploaded'} for n in state['assets']];return [[r]]
                    if args[:3]==('api','--method','POST'):
                        self.assertFalse(state['tag']);state['tag']=True;return {'ref':'refs/tags/'+tag,'object':{'type':'commit','sha':rev}}
                    if args==('api','repos/'+repo+'/git/ref/tags/'+tag):
                        self.assertTrue(state['tag']);return {'object':{'type':'commit','sha':rev}}
                    self.fail('Unexpected API request: '+str(args))
                def cli(*args,**kw):
                    state['calls'].append(args);self.assertNotIn('--clobber',args)
                    if args[:2]==('release','create'):
                        self.assertIsNone(state['release']);self.assertIn('--draft',args)
                        state['release']={'tag_name':tag,'prerelease':True,'draft':True,'name':args[args.index('--title')+1],
                            'body':Path(args[args.index('--notes-file')+1]).read_text(),'html_url':'https://github.com/'+repo+'/releases/tag/'+tag};return ''
                    if args[:2]==('release','upload'):
                        self.assertTrue(state['release']['draft'])
                        for value in args[3:args.index('--repo')]:
                            f=Path(value);self.assertNotIn(f.name,state['assets']);state['assets'][f.name]=f.read_bytes()
                        return ''
                    if args[:2]==('release','download'):
                        destination=Path(args[args.index('--dir')+1]);destination.mkdir(parents=True,exist_ok=True)
                        for n,b in state['assets'].items():(destination/n).write_bytes(b)
                        return ''
                    if args[:2]==('release','edit'):
                        self.assertEqual(state['assets'],all_files);self.assertIn('--draft=false',args);state['release']['draft']=False;return ''
                    self.fail('Unexpected CLI command: '+str(args))
                with patch.object(publisher,'object_json',side_effect=api),patch.object(publisher,'gh',side_effect=cli):
                    if mode in ('corrupt_existing','wrong_text'):
                        with self.assertRaises(ValueError):publisher.publish(root,digest,rev)
                        self.assertTrue(state['release']['draft'])
                    else:
                        publisher.publish(root,digest,rev)
                        self.assertFalse(state['release']['draft']);self.assertEqual(state['assets'],all_files)
                        self.assertEqual(sum(call[:2]==('release','create') for call in state['calls']),int(mode in ('new','tag_only')))

    def test_workflow_and_shell_contract(self):
        p=package.pins(); workflow=(package.ROOT/'.github/workflows/shared-default-native.yml').read_text()
        script=package.ROOT/'scripts/run_shared_default_native_ci.sh'
        subprocess.run(['bash','-n',str(script)],check=True)
        self.assertIn('espressif/idf:v6.1@sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c',workflow)
        self.assertIn('release/shared-default-'+p['version'],workflow)
        self.assertIn('work/serial-files-native',workflow)
        self.assertIn("needs.native.outputs.publication_enabled == 'true'",workflow)
        self.assertIn('needs.native.outputs.release_branch',workflow)
        self.assertIn('--verify-tag',(package.ROOT/'scripts/publish_shared_default_release.py').read_text())
        self.assertIn("'--prerelease', '--latest=false'",(package.ROOT/'scripts/publish_shared_default_release.py').read_text())
        self.assertNotIn('--clobber',workflow)
        self.assertIn('verify every asset before publication',workflow)
        self.assertIn('for build in a b',script.read_text())
        self.assertIn('build_shared_default_native.py',script.read_text())
        self.assertIn('shared_default_release.py',script.read_text())
        self.assertIn('preservation_model = native.local_qualification().preservation_model',(package.ROOT/'scripts/build_shared_default_native.py').read_text())


if __name__=='__main__':unittest.main(verbosity=2)

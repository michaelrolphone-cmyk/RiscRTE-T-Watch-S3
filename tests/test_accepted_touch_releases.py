"""Current-touch is reused exactly; canonical historical input is never relabeled."""
import copy
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import accepted_touch_release as touch
import publish_drivers as publisher
import publish_complete_watch as complete
import publish_watch_product as pub


class AcceptedTouchReleases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=ROOT/'release/complete-1.0.7'
        cls.plan,payloads=complete.derive(
            gzip.decompress((root/'accepted.bin.gz').read_bytes()),
            (root/'accepted-app-evidence.zip').read_bytes(),
            {n:(complete.CUSTODY/n).read_bytes() for n in complete.CUSTODY_HASHES},
            complete.zip_files((root/'immutable-driver-inputs.zip').read_bytes()),
            complete.parse((root/'predecessor-index.json').read_bytes()),touch.SOURCE_SHA,
            supplement=complete.read_tree(root/'licenses/supplemental'),
            existing_new_raw=(root/'existing-new-driver-records.json').read_bytes())
        cls.files=payloads[touch.TAG]
        cls.release={'tag_name':touch.TAG,'draft':False,'prerelease':False,'target_commitish':touch.SOURCE_SHA,
                     'assets':[{'name':name,'id':i} for i,name in enumerate(sorted(cls.files))]}

    def transport(self, *args):
        self.assertEqual(args[0],'api')
        self.assertNotIn('--method',args)
        if args[1].endswith('/commits/'+touch.TAG):
            return json.dumps({'sha':touch.SOURCE_SHA}).encode()
        i=int(args[1].rsplit('/',1)[1])
        return self.files[sorted(self.files)[i]]

    def test_fixed_assets_match_the_actual_frozen_publisher(self):
        self.assertEqual(touch.ASSETS,{name:{'size':len(raw),'sha256':pub.sha(raw)} for name,raw in self.files.items()})
        touch.verify_published(touch.REPOSITORY,[self.release],self.transport,ROOT)
        self.assertEqual(touch.source_version(ROOT),'0.2.1')
        historical=json.loads((ROOT/'drivers/twatch_touch/manifest.json').read_text())
        self.assertEqual(historical['version'],'0.2.0')

    def test_planner_only_adds_power_packages_and_the_new_board(self):
        prior=[{'tag_name':r['tag'],'draft':False} for r in self.plan['index']['drivers']]
        prior.append({'tag_name':'board-lilygo-t-watch-s3-v1.1.11','draft':False})
        source=publisher.sources()
        self.assertEqual(source['twatch-touch'],'0.2.1')
        self.assertEqual({r['id'] for r in publisher.candidates(source,prior)},
                         {'twatch-imu','twatch-panel','twatch-pmu','lilygo-t-watch-s3'})
        with self.assertRaisesRegex(ValueError,'rollback'):
            publisher.candidates({**source,'twatch-touch':'0.2.0'},prior)
        with self.assertRaisesRegex(ValueError,'rollback'):
            publisher.candidates(source,prior+[{'tag_name':'driver-twatch-touch-v0.2.2','draft':False}])

    def test_missing_draft_prerelease_wrong_source_and_extra_assets_rejected(self):
        with self.assertRaisesRegex(ValueError,'missing or duplicated'):
            touch.verify_published(touch.REPOSITORY,[],self.transport,ROOT)
        for field,value in [('draft',True),('prerelease',True),('target_commitish','0'*40)]:
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'state/source'):
                touch.verify_published(touch.REPOSITORY,[{**self.release,field:value}],self.transport,ROOT)
        extra={**self.release,'assets':self.release['assets']+[{'name':'extra','id':99}]}
        with self.assertRaisesRegex(ValueError,'inventory'):
            touch.verify_published(touch.REPOSITORY,[extra],self.transport,ROOT)

    def test_replaced_remote_bytes_and_retargeted_tag_rejected(self):
        def corrupt(*args):
            raw=self.transport(*args)
            return raw if '/commits/' in args[1] else raw+b'changed'
        with self.assertRaisesRegex(ValueError,'immutable asset changed'):
            touch.verify_published(touch.REPOSITORY,[self.release],corrupt,ROOT)
        def retarget(*args):
            return json.dumps({'sha':'0'*40}).encode() if '/commits/' in args[1] else self.transport(*args)
        with self.assertRaisesRegex(ValueError,'tag source'):
            touch.verify_published(touch.REPOSITORY,[self.release],retarget,ROOT)

    def test_source_changes_require_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in touch.SOURCE_FILES:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())
            self.assertEqual(touch.source_version(root),'0.2.1')
            for name in touch.SOURCE_FILES:
                path=root/name;raw=path.read_bytes()
                try:
                    path.write_bytes(raw+b'change')
                    with self.subTest(name=name),self.assertRaisesRegex(ValueError,'source custody changed'):
                        touch.source_version(root)
                finally:path.write_bytes(raw)


if __name__=='__main__':unittest.main()

import copy,io,json,tempfile,unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import audio_overlay as audio

class AudioOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=ROOT/'dist/audio-common/audio-tools-common.zip'
        if not cls.path.exists(): raise RuntimeError('Build Audio Tools common archive first')
        cls.files=audio.read_zip(cls.path);cls.record=json.loads(cls.files['deployment-record.json'])
    def rewrite(self,files):
        f=dict(files);r=json.loads(f.pop('deployment-record.json'));r['entries']=[{'path':n,'size_bytes':len(b),'sha256':audio.sha(b)} for n,b in sorted(f.items())];f['deployment-record.json']=audio.encoded(r);return f
    def rejects(self,change):
        f=copy.deepcopy(self.files);change(f)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.zip';p.write_bytes(audio.zip_bytes(self.rewrite(f)))
            with self.assertRaises((ValueError,KeyError,AssertionError)): audio.verify(p)
    def test_exact_apps_mic_and_policy(self):
        r=audio.verify(self.path,expected_head=self.record['source_sha'])
        self.assertEqual(r['apps'],['frequency_generator','audio_spectrum'])
        board=json.loads(self.files['store/board.json']);self.assertIn(13,[d['instance_id'] for d in board['devices']])
        boot=json.loads(self.files['store/boot.json'])
        self.assertIn(13,[d.get('instance_id') for d in boot['drivers']])
        policies={p['manifest']:p['grants'] for p in boot['app_capabilities']}
        self.assertIn({'capability':'audio.output','api':1,'instance_id':12},policies['frequency_generator.json'])
        self.assertIn({'capability':'audio.input','api':1,'instance_id':13},policies['audio_spectrum.json'])
        self.assertEqual([g['instance_id'] for g in policies['audio_spectrum.json'] if g['capability']=='storage.key-value'],[7])
        self.assertFalse(any(g['capability']=='storage.key-value' for g in policies['frequency_generator.json']))
    def test_preserves_unrelated_payload(self):
        baseline=audio.read_zip(io.BytesIO(self.files['baseline.zip']))
        for name,data in baseline.items():
            if name.startswith('store/') and name not in audio.CHANGED:
                self.assertEqual(self.files.get(name),data)
    def test_mutations_rejected(self):
        self.rejects(lambda f:f.__setitem__('store/default.elf',f['store/default.elf']+b'x'))
        self.rejects(lambda f:f.__setitem__('store/audio_spectrum.elf',b'not-elf'))
        def broaden(f):
            b=json.loads(f['store/boot.json']);next(p for p in b['app_capabilities'] if p['manifest']=='audio_spectrum.json')['grants'].append({'capability':'storage.key-value','api':1,'instance_id':6});f['store/boot.json']=audio.encoded(b)
        self.rejects(broaden)
        def dropmic(f):
            b=json.loads(f['store/boot.json']);b['drivers']=[d for d in b['drivers'] if d.get('instance_id')!=13];f['store/boot.json']=audio.encoded(b)
        self.rejects(dropmic)
if __name__=='__main__': unittest.main()

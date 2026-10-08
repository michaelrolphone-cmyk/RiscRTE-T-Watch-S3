"""Exercise the installed 1.0.7 update service against all real 1.0.12 records."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import publish_accepted_watch_112 as release

class InstalledAdmission(unittest.TestCase):
    def test_exact_installed_service_refuses_every_new_app_before_transaction(self):
        inputs=release.load_inputs()
        plan,_=release.derive(inputs,release.PUBLISHED_SOURCE)
        old=gzip.decompress((ROOT/'release/complete-1.0.7/accepted.bin.gz').read_bytes())
        store=release.read_image(old[0x2f0000:0x800000],0x510000)
        source=release.zip_files(inputs['installed-app-admission-source.zip'])
        provenance=json.loads(source.pop('SOURCES.json'))
        self.assertEqual(provenance['source_sha'],'f146d82d4c2bc4d4b6ac97f7be83b04035ad7d60')
        self.assertEqual({n:release.pub.sha(v) for n,v in source.items()},provenance['files'])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,raw in source.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            index=root/'index.json';index.write_text(release.serialize_index(plan['index']))
            old_paths=[];positive_paths=[]
            for record in plan['app_records']:
                identity=record['id'];old_path=root/(identity+'-old.json');old_path.write_bytes(store[identity+'.json']);old_paths.append(old_path)
                # A positive control changes only the installed version, retaining
                # the proposed exact authority. It must reach the transaction API.
                manifest={**record['manifest'],'version':'0.0.0'}
                positive=root/(identity+'-positive.json');positive.write_text(json.dumps(manifest));positive_paths.append(positive)
            for sanitized in (False,True):
                executable=root/('admission-san' if sanitized else 'admission')
                flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie'] if sanitized else []
                subprocess.run([os.environ.get('CXX','c++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',*flags,
                    '-I'+str(root),'-I'+str(root/'lib/PortableApps/include'),'-I'+str(root/'lib/NativeApps/include'),
                    str(ROOT/'tests/watch112_release/installed_app_admission.cpp'),'-o',str(executable)],check=True)
                for scenario,paths in [('negative',old_paths),('positive',positive_paths)]:
                    result=subprocess.run([str(executable),scenario,str(index),*map(str,paths)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertIn('22 rows',result.stdout)
                    print(('ASan/UBSan ' if sanitized else 'ordinary ')+result.stdout.strip())

if __name__=='__main__':unittest.main()

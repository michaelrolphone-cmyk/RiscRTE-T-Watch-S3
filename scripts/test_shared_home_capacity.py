#!/usr/bin/env python3
"""Exercise actual profile delta and actual ELF/DWARF capacity rejection."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import shared_home_capacity as capacity
ROOT=Path(__file__).resolve().parents[1]
def main():
    pins=json.loads((ROOT/'docs/shared-app-native/source-pins.json').read_text())
    cmake=shutil.which('cmake')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        capacity.profile_delta(ROOT,root,pins['profile'],cmake)
        shutil.copytree(ROOT/'profiles',root/'profiles')
        path=root/'profiles/shared-home-capacity.cmake'
        path.write_text(path.read_text().replace('CAPACITY=48','CAPACITY=49'))
        try: capacity.profile_delta(root,root,pins['profile'],cmake)
        except ValueError: pass
        else: raise AssertionError('Bad profile accepted')
        source=root/'src/bootstrap/Runtime.cpp';source.parent.mkdir(parents=True)
        for count,valid in [(48,True),(40,False)]:
            source.write_text('struct GraphV2 { char nodes_['+str(count)+']; };\\n'.replace('\\n','\n')+
                'struct Invocation { char appGrants_[16]; };\\n'.replace('\\n','\n')+
                'struct Runtime { char drivers_['+str(count)+'],providerStorage_['+str(count)+'],grants_['+str(count)+'],platforms_[32]; GraphV2 graph; Invocation invocation; }; Runtime runtime; int main(){ return runtime.drivers_[0]; }\n')
            binary=root/('fixture'+str(count))
            subprocess.run(['g++','-g','-O0',str(source),'-o',str(binary)],check=True)
            try: capacity.linked_capacity(binary.read_bytes())
            except ValueError:
                if valid: raise
            else:
                if not valid: raise AssertionError('Bad linked capacity accepted')
    print('Actual profile delta + linked array48 positive/40 negative PASS')
if __name__=='__main__': main()

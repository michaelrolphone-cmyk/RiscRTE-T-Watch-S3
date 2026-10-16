#!/usr/bin/env python3
"""Reject coherent metadata for modified final17 package bytes or overstated scope."""
import argparse,json,shutil,tempfile
from pathlib import Path
from bound_preserving_watch_update import arguments,verify_package
from current_apps_overlay import ROOT,encoded,metadata,require
from build_preserving_watch_update import clean

CASES=('bootloader','nvs','appdata','journal','payload','cohort','notices','outer-url','extra-member','physical-claim','checksum','linked-member',
       'null-packager-source','wrong-packager-source','wrong-initial-size','nested-physical-claim')

def flip(path,offset=0):
    raw=bytearray(path.read_bytes());raw[offset]^=1;path.write_bytes(raw)

def synchronize(directory):
    name='twatch-s3-launcher-1.0.17.bin';image=(directory/name).read_bytes()
    p=directory/'release-record.json';record=json.loads(p.read_bytes());record['sha256']=metadata(image)['sha256'];p.write_bytes(encoded(record))
    (directory/'catalog-fixture.json').write_bytes(encoded({'schema':1,'firmware':record,'apps':[]}))
    p=directory/'package-proof.json';proof=json.loads(p.read_bytes());proof['initial_image']=metadata(image);p.write_bytes(encoded(proof))
    names=[p.name for p in directory.iterdir() if p.is_file() and p.name!='SHA256SUMS']
    (directory/'SHA256SUMS').write_text(''.join(metadata((directory/n).read_bytes())['sha256']+'  '+n+'\n' for n in sorted(names)))

def main():
    p=argparse.ArgumentParser(description=__doc__);arguments(p)
    p.add_argument('--target',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();require(not a.output.exists(),'Proof output must be new');head=clean(ROOT)
    params=(a.binding_repository,a.binding,a.runtime,a.native)
    def verify(directory):return verify_package(directory,*params,expected_packager_source=a.packager_source)
    verified=verify(a.target);before={p.relative_to(a.target).as_posix():metadata(p.read_bytes()) for p in a.target.rglob('*') if p.is_file()}
    outcomes=[]
    with tempfile.TemporaryDirectory(prefix='watch17-package-mutations-') as temp:
        for case in CASES:
            d=Path(temp)/case;shutil.copytree(a.target,d)
            if case in ('bootloader','nvs','appdata','journal'):
                flip(d/'twatch-s3-launcher-1.0.17.bin',{'bootloader':100,'nvs':0x9000,'appdata':0x270000,'journal':0xff2000}[case]);synchronize(d)
            elif case=='payload':flip(d/'twatch-s3-cohort-1.0.17.bin');synchronize(d)
            elif case=='cohort':flip(d/'files/cohort.json');synchronize(d)
            elif case=='notices':flip(d/'LICENSES.zip');synchronize(d)
            elif case=='outer-url':
                p=d/'release-record.json';r=json.loads(p.read_bytes());r['url']='https://invalid.example/test.bin';p.write_bytes(encoded(r));synchronize(d)
            elif case=='extra-member':(d/'unqualified.bin').write_bytes(b'not a product asset');synchronize(d)
            elif case=='physical-claim':
                p=d/'package-proof.json';r=json.loads(p.read_bytes());r['hardware_qualified']=True;p.write_bytes(encoded(r));synchronize(d)
            elif case in ('null-packager-source','wrong-packager-source','wrong-initial-size','nested-physical-claim'):
                p=d/'package-proof.json';r=json.loads(p.read_bytes())
                if case=='null-packager-source':r['watch_packager_source']=None
                elif case=='wrong-packager-source':r['watch_packager_source']='0'*40
                elif case=='wrong-initial-size':r['initial_image']['size_bytes']=1
                else:r['initial_image']['hardware_qualified']=True
                p.write_bytes(encoded(r))
                # Keep the forged metadata intact while updating its checksum.
                names=sorted(x.name for x in d.iterdir() if x.is_file() and x.name!='SHA256SUMS')
                (d/'SHA256SUMS').write_text(''.join(metadata((d/n).read_bytes())['sha256']+'  '+n+'\n' for n in names))
            elif case=='checksum':flip(d/'SHA256SUMS')
            else:
                p=d/'LICENSES.zip';p.unlink();p.symlink_to((a.target/'LICENSES.zip').resolve())
            try:verify(d)
            except ValueError as error:outcomes.append({'case':case,'rejected':True,'reason':str(error)})
            else:raise AssertionError('Modified package passed: '+case)
            shutil.rmtree(d)
    require(verify(a.target)==verified and clean(ROOT)==head and
            {p.relative_to(a.target).as_posix():metadata(p.read_bytes()) for p in a.target.rglob('*') if p.is_file()}==before,
            'Original bound package/source changed')
    result={'schema':1,'qualification_source':head,'package_files':before,'positive_before_after':True,
            'cases':outcomes,'hardware_qualified':False,'device_accessed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(encoded(result));print(json.dumps({'cases':len(outcomes),'output':str(a.output)}))

if __name__=='__main__':main()

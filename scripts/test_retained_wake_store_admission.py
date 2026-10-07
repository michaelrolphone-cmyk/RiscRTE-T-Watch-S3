#!/usr/bin/env python3
"""Metadata-only fixture validation. Never executes a target ELF or changes a product."""
import argparse,json,pathlib,subprocess,tempfile
from check_runtime_store_admission import compile_harness

def encoded(value):return (json.dumps(value,sort_keys=True)+'\n').encode()
def fixture(retained):
    req=[{'capability':'runtime.retained-wake','api':1}] if retained else []
    grant=[{'capability':'runtime.retained-wake','api':1,'instance_id':0}] if retained else []
    return {'board.json':encoded({'schema':'riscrte.board-hardware','schema_version':1,'board_id':'test','revision':'unspecified','buses':[],'devices':[]}),
      'boot.json':encoded({'board':'board.json','default_app':'default.elf','drivers':[],'app_capabilities':[{'manifest':'app.json','grants':grant}]}),
      'app.json':encoded({'type':'application','id':'test','version':'1.0.0','architecture':'xtensa-esp32s3','file_name':'default.elf','entry':'app_main','requires':req}),
      'cohort.json':encoded({'schema':'riscrte.cohort','schema_version':1,'product':'test','version':'1.0.0','runtime_version':'0.1.47','source_repo':'example/test','source_revision':'1'*40,'layout':'riscrte-paired-appdata-v2','store_abi':2,'firmware_size':32,'firmware_sha256':'1'*64})}
def check(exe,files,expected):
    with tempfile.TemporaryDirectory(prefix='retained-admission-store-') as tmp:
        root=pathlib.Path(tmp)
        for name,data in files.items():(root/name).write_bytes(data)
        result=subprocess.run([str(exe),str(root)],capture_output=True,text=True,check=True,timeout=30)
        result=json.loads(result.stdout)
        assert result['prepared'] is expected,result
        assert result['hardware_calls']==result['storage_calls']==0,result
        assert {p.name:p.read_bytes() for p in root.iterdir()}==files
        print(json.dumps(result,sort_keys=True))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=pathlib.Path,required=True);p.add_argument('--legacy-runtime',type=pathlib.Path);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='retained-admission-build-') as tmp:
        exe=compile_harness(a.runtime,pathlib.Path(tmp)/'admit',app_data=True)
        for retained in (False,True):check(exe,fixture(retained),True)
        for cohort in (None,b'{}',b'x'*16385):
            files=fixture(True)
            if cohort is None:del files['cohort.json']
            else:files['cohort.json']=cohort
            check(exe,files,False)
        for key,value in [('api',2),('instance_id',1)]:
            files=fixture(True);boot=json.loads(files['boot.json']);boot['app_capabilities'][0]['grants'][0][key]=value;files['boot.json']=encoded(boot);check(exe,files,False)
        # Merely supplying this backend cannot add a missing app grant.
        files=fixture(True);boot=json.loads(files['boot.json']);boot['app_capabilities'][0]['grants']=[];files['boot.json']=encoded(boot);check(exe,files,False)
        if a.legacy_runtime:
            old=compile_harness(a.legacy_runtime,pathlib.Path(tmp)/'legacy',app_data=True)
            check(old,fixture(False),True);check(old,fixture(True),False)
    print('Retained-wake admission: explicit authority/cohort checks, no native I/O/store mutation, historical Runtime compatibility PASS')
if __name__=='__main__':main()

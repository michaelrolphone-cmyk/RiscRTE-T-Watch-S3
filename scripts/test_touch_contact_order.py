#!/usr/bin/env python3
"""Actual Watch touch report ordering and original driver contract, no device I/O."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
from test_contracts import config,initializer
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--system',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline',action='store_true');a=p.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);inc=out/'include';inc.mkdir()
for name in ['PortableTouch.h','RiscRuntimeV1.h']:shutil.copy2(a.system/'lib/PortableApps/include'/name,inc/name)
source=ROOT/('drivers/current/twatch_touch/driver.c' if a.baseline else 'drivers/candidates/twatch_touch_022/driver.c')
board=json.loads((ROOT/'hardware/sx1262-915-bma423.json').read_text());entry=next(x for x in board['devices'] if x['compatible']=='focaltech,ft6336u');buses={x['instance_id']:x for x in board['buses']}
records=[];commands=[]
for alternate in [False,True]:
 typ,c=config(entry,buses,alternate)
 (inc/'fixture_config.h').write_text(f'static {typ} m_config={initializer(c)};\nstatic risc_hardware_device_v1 m_device={{1,sizeof(m_device),{entry["instance_id"]},"{entry["compatible"]}","unspecified","{entry["config_type"]}",1,sizeof(m_config),&m_config}};\n')
 for san in [False,True]:
  flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-missing-field-initializers','-DTEST_KIND=6',f'-DDRIVER_SOURCE="{source}"',*['-I'+str(x) for x in [inc,ROOT/'sdk/driver',ROOT/'include',ROOT]],'-no-pie']
  if san:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
  for label,test,cases in [('contract',ROOT/'tests/driver_test.c',['original']),('order',ROOT/'tests/touch_contact_order_test.c',['same-report','unchanged-report','all-released','earlier-move','replacement','rapid-same-tick','unchanged-moves','two-subscribers','overflow','read-failure'])]:
   exe=out/f'{label}-{int(alternate)}-{int(san)}';cmd=[os.environ.get('CC','cc'),*flags,str(test),'-o',str(exe)];commands.append(cmd);subprocess.run(cmd,check=True)
   for case in cases:
    cmd=[str(exe),*([case] if label=='order' else [])];commands.append(cmd);r=subprocess.run(cmd,capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0','UBSAN_OPTIONS':'halt_on_error=1'})
    log=f'{label}-{case}-{int(alternate)}-{int(san)}.log';(out/log).write_text(r.stdout+r.stderr);records.append(dict(case=case,alternate=alternate,sanitized=san,exit_code=r.returncode,log=log))
    if not a.baseline:assert r.returncode==0,(case,r.returncode,r.stderr)
proof={'source_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in [source,ROOT/'tests/touch_contact_order_test.c',ROOT/'tests/driver_test.c',ROOT/'tests/mock.h',Path(__file__).resolve(),inc/'PortableTouch.h',inc/'RiscRuntimeV1.h']},'records':records,'commands':commands,'baseline':a.baseline,'hardware_tested':False}
(out/'qualification.json').write_text(json.dumps(proof,indent=2)+'\n');print(len(records),'cases; failures',sum(x['exit_code']!=0 for x in records))

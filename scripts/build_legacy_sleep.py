"""Reproduce GPIO/PMU historical package bytes from their frozen source prefix.

Only current-apps replaces these with wake-set drivers. Never rehash a prior
release to legitimize newly compiled ABI tables.
"""
import hashlib,json,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def legacy_inputs(root=ROOT):
 source=root/'custody/sleep-prefix';record=json.loads((source/'PROVENANCE.json').read_text())
 assert record['commit']=='2a4fbae8fb2425bf830c302863a5e195106e77c9'
 for name,digest in record['files'].items():assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,name
 return source
def build(cc,root=ROOT):
 source=legacy_inputs(root);catalog=[]
 expected={'twatch-gpio':'0f079b1d8957725ef38c037252eb8cf25e42f2dfff10157bd71cedf4aec78549','twatch-pmu':'ea536f0532e001bd4a3d36e50d2f2fcbe1db5bfab218def6ad28b536f578fbfb'}
 for mp in sorted((source/'drivers').glob('*/manifest.json')):
  m=json.loads(mp.read_text());out=root/'dist/legacy-sleep'/m['id'];out.mkdir(parents=True,exist_ok=True);elf=out/'driver.elf'
  subprocess.run([cc,'-std=c11','-shared','-fPIC','-fvisibility=hidden','-nostdlib','-mlongcalls','-Os','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Wno-misleading-indentation','-Wno-unused-function','-Werror',f'-I{source}/sdk/driver',f'-I{source}/include',f'-Wl,--version-script={source}/exports.map','-Wl,-soname,driver.elf',str(mp.parent/'driver.c'),'-lgcc','-o',str(elf)],check=True)
  cap=m['provides'][0];files={'driver.elf':elf.read_bytes(),'provider-abi.v1':f"os-cpu-abi=1\nprovides={cap['capability']}\napi={cap['api']}\n".encode(),'source-manifest.json':(json.dumps(m,indent=2)+'\n').encode()}
  manifest=dict(schema=1,kind='driver',id=m['id'],version=m['version'],architecture=m['architecture'],artifact='driver.elf',driver_abi=2,provides=m['provides'],requires=[dict(capability=x['capability'],min_api=x['api']) for x in m['requires']],entries=[dict(name=k,size_bytes=len(v),sha256=hashlib.sha256(v).hexdigest(),executable=k.endswith('.elf')) for k,v in files.items()])
  if 'hardware_compatibility' in m:manifest['hardware_compatibility']=m['hardware_compatibility']
  package=root/'dist'/f"driver-{m['id']}-{m['version']}-xtensa-esp32s3.rte.zip"
  with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_STORED) as z:
   for k,v in {'.package.json':(json.dumps(manifest,indent=2)+'\n').encode(),**files}.items():
    info=zipfile.ZipInfo(k,(2026,1,1,0,0,0));info.external_attr=0o100644<<16;z.writestr(info,v)
  data=package.read_bytes();digest=hashlib.sha256(data).hexdigest();assert digest==expected[m['id']],(m['id'],digest)
  catalog.append(dict(id=m['id'],version=m['version'],kind='driver',architecture=m['architecture'],archive=package.name,size_bytes=len(data),sha256=digest))
 (root/'dist/legacy-sleep/catalog.json').write_text(json.dumps({'packages':catalog},indent=2)+'\n')
 print('Frozen GPIO0.4.2/PMU0.5.3 target package bytes remain exact')

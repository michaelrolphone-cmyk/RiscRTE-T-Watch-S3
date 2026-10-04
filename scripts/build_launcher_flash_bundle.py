#!/usr/bin/env python3
"""Assemble verified launcher CI + exact paired runtime; never access a device."""
import argparse,hashlib,io,json,re,struct,subprocess,tempfile,zipfile
from pathlib import Path,PurePosixPath
from verify_clock_deployment import verify
from rtc_metadata import normalize as normalize_rtc
ROOT=Path(__file__).resolve().parents[1]
RUNTIME_SHA=json.loads((ROOT/'apps/clock/runtime-requirements.json').read_text())['source_sha']
RUNTIME_ZIP_SHA='760d5403203a71dd5aba8a28101e377b26b94f8d22402eea4d89bc6138845022'
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(o):return (json.dumps(o,indent=2)+'\n').encode()
def members(z):
 names=z.namelist()
 if len(names)!=len(set(names)) or any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts for n in names):raise ValueError('Unsafe or duplicate archive members')
 if len(names)>1000 or sum(e.file_size for e in z.infolist())>160*1024*1024:raise ValueError('Archive exceeds bounded artifact limits')
 return names
def build(runtime,artifact,head,runtime_source,out):
 if not re.fullmatch('[0-9a-f]{40}',head):raise ValueError('Exact PR head required')
 subprocess.run(['git','diff','--exit-code',head,'--'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
 if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=runtime_source,text=True).strip():raise ValueError('Runtime source must be clean')
 if sha(runtime.read_bytes())!=RUNTIME_ZIP_SHA:raise ValueError('Runtime artifact differs from accepted exact pair')
 if subprocess.check_output(['git','rev-parse','HEAD'],cwd=runtime_source,text=True).strip()!=RUNTIME_SHA:raise ValueError('Runtime source must match accepted pair')
 with zipfile.ZipFile(runtime) as z:
  members(z);rc=json.loads(z.read('candidate.json'))
  assert rc['source_sha']==RUNTIME_SHA and rc['flash_bytes']==0x1000000 and rc['bootfs_offset']==0x310000 and rc['bootfs_bytes']==0x4f0000 and rc['usb_cdc_on_boot']
  for n,e in rc['assets'].items():
   data=z.read(n);assert len(data)==e['bytes'] and sha(data)==e['sha256']
  components={n:z.read(n) for n in ('bootloader.bin','partitions.bin','firmware.bin')}
  files={'reproduce/'+n:z.read(n) for n in ('platformio.ini','partitions.csv','requirements-ci.txt')}
  for n in ('bootloader.bin','firmware.bin'):
   b=components[n];assert b[0]==0xe9 and b[3]>>4==4 and struct.unpack_from('<H',b,12)[0]==9
  assert RUNTIME_SHA.encode() in components['firmware.bin']
 with zipfile.ZipFile(artifact) as z:
  names=members(z)
  common=[n for n in names if n.endswith('-launcher-common.zip')]
  image=[n for n in names if n.endswith('-launcher-common-bootfs.bin')]
  assert len(common)==len(image)==1
  proof=json.loads(z.read(next(n for n in names if n.endswith('hybrid-increment-proof.json'))))
  assert proof['label']=='0.5.2-hybrid-polish' and proof['unchanged_file_count']==10
  rtc_raw=z.read(next(n for n in names if n.endswith('compiled-driver.elf')))
  rtc_proof=json.loads(z.read(next(n for n in names if n.endswith('metadata-proof.json'))))
  rtc_canonical,rtc_checked=normalize_rtc(rtc_raw)
  assert all(rtc_proof[k]==v for k,v in rtc_checked.items()) and '8.4.0' in rtc_proof['compiler']
  common_bytes=z.read(common[0]);image_bytes=z.read(image[0]);image_record=json.loads(z.read(image[0][:-4]+'.json'))
  assert image_record['sha256']==sha(image_bytes) and image_record['deployment_sha256']==sha(common_bytes)
  assert image_record['round_trip_verified'] and image_record['files']==28 and image_record['partition_offset']==0x310000 and len(image_bytes)==0x4f0000
 with tempfile.TemporaryDirectory() as tmp:
  p=Path(tmp)/'common.zip';p.write_bytes(common_bytes);record=verify(p)
 assert record['profile']=='launcher-common' and record['pull_request_head_sha']==head and record['source_sha']==head
 assert record['source_sha']==image_record['watch_source_sha'] and len(record['common_launcher']['inputs'])==8
 assert record['runtime_requirements']['source_sha']==RUNTIME_SHA and record['runtime_requirements']['firmware_version']==rc['firmware_version']
 version=record['app_version'];assert re.fullmatch(r'\d+\.\d+\.\d+',version)
 with zipfile.ZipFile(io.BytesIO(common_bytes)) as z:
  members(z)
  store={n:z.read(n) for n in z.namelist() if n.startswith('store/')};assert len(store)==28
  assert proof['variant_store_sha256']=={n.removeprefix('store/'):sha(b) for n,b in sorted(store.items())}
  baseline=json.loads((ROOT/'docs/HYBRID_BASELINE.json').read_text())
  assert proof['baseline_store_sha256']==baseline['baseline_store_sha256']
  changed=sorted(n.removeprefix('store/') for n,b in store.items() if n.removeprefix('store/') in baseline['baseline_store_sha256'] and sha(b)!=baseline['baseline_store_sha256'][n.removeprefix('store/')])
  assert changed==sorted(baseline['changed_store_files'])
  assert store['store/rtc/driver.elf']==rtc_canonical
  board=json.loads(store['store/board.json']);assert {d['instance_id'] for d in board['devices']}=={1,2,3,4,5,6,8}
  assert next(b for b in board['buses'] if b['instance_id']==103)['frequency_hz']==40000000
  assert next(d for d in board['devices'] if d['instance_id']==5)['config']['rotation']==2
  files.update({n:z.read(n) for n in z.namelist() if n.startswith(('licenses/','shared/')) or n in ('INSTALL.md','CROWN_SLEEP.md','PMU_BATTERY.md','time-policy.json','settings-time-policy.json','runtime-requirements.json','DEEP_SLEEP.md')})
 files.update(store)
 files.update({'licenses/'+p.name:p.read_bytes() for p in (ROOT/'licenses').glob('*') if p.is_file()})
 files['licenses/BOOT_WORDMARK_LICENSE.txt']=(ROOT/'apps/clock/effects/reference/BOOT_WORDMARK_LICENSE.txt').read_bytes()
 files['reproduce/RUNTIME-LICENSE']=(runtime_source/'LICENSE').read_bytes()
 files['provenance/hybrid-increment-proof.json']=encoded(proof)
 files['provenance/rtc-metadata-proof.json']=encoded(rtc_proof)
 files['provenance/rtc-compiled.elf']=rtc_raw
 files['DEEP_SLEEP.md']=(ROOT/'docs/DEEP_SLEEP.md').read_bytes()
 files['provenance/runtime-candidate.json']=encoded(rc)
 files['provenance/common-deployment.zip']=common_bytes
 files['provenance/bootfs.json']=encoded(image_record)
 components['bootfs.bin']=image_bytes
 merged=bytearray(b'\xff'*0x800000);parts=[];cursor=0
 for name,offset in [('bootloader.bin',0),('partitions.bin',0x8000),('firmware.bin',0x10000),('bootfs.bin',0x310000)]:
  data=components[name];assert offset>=cursor and offset+len(data)<=len(merged)
  merged[offset:offset+len(data)]=data;files['components/'+name]=data;cursor=offset+len(data)
  parts.append({'file':'components/'+name,'offset':hex(offset),'size_bytes':len(data),'sha256':sha(data)})
 cursor=0
 for part in parts:
  offset=int(part['offset'],16);assert all(v==255 for v in merged[cursor:offset]);assert merged[offset:offset+part['size_bytes']]==files[part['file']];cursor=offset+part['size_bytes']
 assert all(v==255 for v in merged[cursor:])
 manifest={'schema':1,'target':'Original/non-Plus LILYGO T-Watch-S3,16MB flash/8MB OPI PSRAM','app_version':version,'runtime_version':rc['firmware_version'],'runtime_commit':RUNTIME_SHA,'watch_pr_head':head,'runtime_artifact_sha256':sha(runtime.read_bytes()),'watch_artifact_sha256':sha(artifact.read_bytes()),'flash_start':0,'overwrite_bytes':len(merged),'flash_capacity_bytes':0x1000000,'merged_sha256':sha(merged),'components':parts,'clock_policy':record['clock_policy'],'time_policy':record['time_policy'],'settings_time_policy':json.loads(files['settings-time-policy.json']),'store':[{'path':n.removeprefix('store/'),'size_bytes':len(b),'sha256':sha(b)} for n,b in sorted(store.items())],'physical_verification':'Pending; host/model/target CI are not hardware qualification'}
 manifest['configuration_variant']='0.5.2-hybrid-polish'
 manifest['changed_from_0_5_1']=changed
 manifest['added_store_files']=baseline['added_store_files']
 files['manifest.json']=encoded(manifest)
 name=f'twatch-s3-launcher-{version}.bin';files[name]=bytes(merged)
 files['FLASHING.md']=f'''# T-Watch-S3 launcher {version}

Target: original/non-Plus T-Watch-S3, 16MB flash and 8MB OPI PSRAM.
Merged BIN address: 0x0. It replaces the first 8MiB including NVS/settings and
saved Stopwatch state; upper 8MiB stays untouched. Keep delivered 0.5.1/0.5.0
and physically accepted 0.4.5 for recovery. No flashing was performed.

Fresh-install Clock and all app idle sleep use Light for five minutes, then
Deep. Light wakes directly in the same app; Deep boots a fresh Clock. Clock
still sleeps on crown; crown Back in other apps is preserved. Explicit saved
manual Clock-only Light/Deep choices are preserved. Settings never grants its
namespace to other apps; Stopwatch keeps private namespace 2.

Springboard uses the real FontAwesome stopwatch, varied neighboring colors,
and white labels over solid black text blocks with tightly feathered edges.
The accepted physical full-frame panel, touch, rails and RTC transport are
unchanged. Stopwatch maintains monotonic live precision across Light, while
its existing persisted Deep/relaunch recovery remains approximate RTC seconds.

Runtime 0.1.6 supplies the owned bounded timer. No alarm service, ULP program,
double-tap wake, device access, merge or release is included. Software checks
and target builds do not qualify physical wake reliability or power consumption.

To flash after your own backup/decision, close serial monitors and replace PORT:
python -m esptool --chip esp32s3 --port PORT --baud 460800 write_flash 0x0 {name}

Components: bootloader 0x0; partitions 0x8000; runtime 0x10000; bootfs 0x310000.
Watch source: {head}
Runtime source: {RUNTIME_SHA}
Merged SHA256: {sha(merged)}
'''.encode()
 files['SHA256SUMS']=''.join(f'{sha(b)}  {n}\n' for n,b in sorted(files.items())).encode()
 out.mkdir(parents=True,exist_ok=True);(out/name).write_bytes(merged)
 archive=out/f'twatch-s3-launcher-{version}-flashing.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n,b in sorted(files.items()):
   entry=zipfile.ZipInfo(n,(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16;z.writestr(entry,b)
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for n,b in files.items():assert z.read(n)==b
 result={'head':head,'version':version,'bin':str(out/name),'bin_sha256':sha(merged),'zip':str(archive),'zip_sha256':sha(archive.read_bytes()),'members':len(files)}
 (out/'bundle-record.json').write_bytes(encoded(result));print(json.dumps(result,indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('runtime','artifact','runtime-source','output'):p.add_argument('--'+n,required=True,type=Path)
 p.add_argument('--pr-head',required=True);a=p.parse_args()
 build(a.runtime,a.artifact,a.pr_head,a.runtime_source,a.output)

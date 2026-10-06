#!/usr/bin/env python3
"""Prepare exact staged SDR update inputs from released1.0.2, without publication.

Ordinary payloads contain only native firmware or native+bootfs. The separate
initial full image is never an upgrade path for an installed/data-bearing Watch.
"""
import argparse,copy,hashlib,importlib.util,json,subprocess
from pathlib import Path
from current_apps_overlay import ROOT,config,verify,encoded,require,metadata
from current_bootfs import build as build_store
from read_only_spiffs import read_image
from current_cohort import create,encode,package
from current_flash_layout import assemble
from watch_release_index import update_index,REPOSITORY
from build_wifi_common import zip_bytes
OLD_BIN_SHA='849e57783b25bca4bdb25aa7815867ad06714425f605aefe760d211ea1d21c04'
OLD_SOURCE='27876749f08deaa78910cbd16aa54345684b6bf7'
def sha(data):return hashlib.sha256(data).hexdigest()
def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def prepare(released_bin,apps_dir,runtime,native_dir,index_path,output,system_apps):
 output=Path(output);require(not output.exists(),'Output must be new')
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True).strip(),'Dirty Watch source')
 c=config();files,apps=verify(apps_dir,head);runtime=Path(runtime);native_dir=Path(native_dir)
 require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=runtime,text=True).strip()==c['sources']['runtime']['commit'],'Wrong Runtime source')
 require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=runtime,text=True).strip(),'Dirty Runtime source')
 old=Path(released_bin).read_bytes();require(len(old)==0x1000000 and sha(old)==OLD_BIN_SHA,'Released1.0.2 custody differs')
 previous=read_image(old[0x2f0000:0x800000],0x510000);before=json.loads(previous['boot.json']);old_cohort=json.loads(previous['cohort.json'])
 require(old_cohort['version']=='1.0.2' and old_cohort['source_revision']==OLD_SOURCE,'Wrong source cohort')
 following=dict(previous);following.update(files);following['boot.json']=encoded(apps['boot'])
 require(following['board.json']==previous['board.json'],'SDR may not change existing hardware declarations')
 stripped=copy.deepcopy(apps['boot']);migration=stripped.pop('cohort_migration')
 stripped['app_capabilities']=[q for q in stripped['app_capabilities'] if q['manifest']!='waterfall.json']
 stripped['drivers']=[q for q in stripped['drivers'] if q['manifest']!='s3-radio-iq/manifest.json']
 require(stripped==before,'SDR unexpectedly changes existing boot authority')
 require(migration=={'schema':1,'from':{'product':'twatch-s3','version':'1.0.2','source_revision':OLD_SOURCE},'to':{'product':'twatch-s3','version':'1.0.4'},'shared_key_value':[{'application_id':'waterfall','api':1,'namespace':1}]},'Migration authority differs')
 new_files={'waterfall.elf','waterfall.json','s3-radio-iq/driver.elf','s3-radio-iq/manifest.json'}
 require(set(following)==set(previous)|new_files,'SDR store inventory differs')
 for row in before['app_capabilities']:
  require(json.loads(previous[row['manifest']])==json.loads(following[row['manifest']]),'Existing app authority/version differs: '+row['manifest'])
 candidate=json.loads((native_dir/'candidate.json').read_text());fw=(native_dir/'firmware.bin').read_bytes();elf=(native_dir/'firmware.elf').read_bytes()
 require(candidate['source_sha']==c['sources']['runtime']['commit'] and candidate['target']=='esp32s3-16mb-appdata-iq' and candidate['firmware_version']=='0.1.34','Wrong guarded native candidate')
 for name,meta in candidate['assets'].items():
  data=(native_dir/name).read_bytes();require(len(data)==meta['bytes'] and sha(data)==meta['sha256'],'Native candidate member differs: '+name)
 iq=json.loads(json.dumps(load_module('iq_proof',runtime/'scripts/radio_iq_proof.py').prove(elf)))
 require(candidate['native_proof']['radio_iq']==iq,'SRAM/ROM proof differs')
 version=json.loads((ROOT/'apps/current-cohort.json').read_text())['version'];require(version=='1.0.4','SDR cohort version differs')
 identity=create(version,'0.1.34',head,fw);following['cohort.json']=encode(identity)
 store,packing=build_store(following);payload,ota=package(identity,fw,store)
 bank=load_module('iq_bank_metadata',runtime/'scripts/paired_bank_images.py')
 parts={n:(native_dir/n).read_bytes() for n in ('bootloader.bin','partitions.bin','firmware.bin','appdata.bin')}
 parts.update({'bootfs.bin':store,'otadata.bin':bank.initial_otadata(),'bank_state.bin':bank.initial_bank_state(fw,store,app_data=True)})
 requirements=json.loads((ROOT/'apps/current-runtime-requirements.json').read_text())
 full,placement=assemble(parts,requirements['deployment'],True)
 release='firmware-v'+version;full_name='twatch-s3-launcher-'+version+'.bin';native_name='riscrte-runtime-0.1.34.bin'
 record=dict(kind='firmware',version=version,tag=release,asset=full_name,url=f'https://github.com/{REPOSITORY}/releases/download/{release}/{full_name}',size=len(full),sha256=sha(full),source_sha=head,component_versions={**c['app_versions'],'runtime':'0.1.34'},hardware_qualified=False,ota=ota)
 base=json.loads(Path(index_path).read_text());require(base['firmware']['version']=='1.0.2','Expected released1.0.2 index')
 # A native-only transaction clones the old store, including its1.0.2 cohort
 # anchor. Its separate initial image mirrors that same state. The bridge is
 # release1.0.3; the final coherent SDR product is release1.0.4.
 bridge_version='1.0.3';bridge_tag='firmware-v'+bridge_version;bridge_full_name='twatch-s3-launcher-'+bridge_version+'.bin'
 bridge_parts={**parts,'bootfs.bin':old[0x2f0000:0x800000]}
 bridge_parts['bank_state.bin']=bank.initial_bank_state(fw,bridge_parts['bootfs.bin'],app_data=True)
 bridge_full,bridge_placement=assemble(bridge_parts,requirements['deployment'],True)
 first=dict(kind='firmware',version=bridge_version,tag=bridge_tag,asset=bridge_full_name,url=f'https://github.com/{REPOSITORY}/releases/download/{bridge_tag}/{bridge_full_name}',size=len(bridge_full),sha256=sha(bridge_full),source_sha=head,component_versions={**base['firmware']['component_versions'],'runtime':'0.1.34'},hardware_qualified=False,native_bridge={'retained_cohort_version':'1.0.2','retained_store_sha256':sha(bridge_parts['bootfs.bin'])})
 first['ota']=dict(kind='runtime-image',runtime_version='0.1.34',layout=identity['layout'],store_abi=2,asset=native_name,url=f'https://github.com/{REPOSITORY}/releases/download/{bridge_tag}/{native_name}',size=len(fw),sha256=sha(fw))
 stage1=update_index(base,'firmware',first)
 stage2=update_index(stage1,'firmware',record) # Prove monotonic publication; never rewrite a version.
 output.mkdir(parents=True);assets=output/release;assets.mkdir();(output/'store').mkdir()
 for name,data in following.items():p=output/'store'/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(data)
 for name,data in {full_name:full,ota['asset']:payload,'release-record.json':encoded(record),'radio-iq-proof.json':encoded(iq),'LICENSES.zip':zip_bytes({p.relative_to(Path(apps_dir)/'licenses').as_posix():p.read_bytes() for p in (Path(apps_dir)/'licenses').rglob('*') if p.is_file()})}.items():(assets/name).write_bytes(data)
 bridge_assets=output/bridge_tag;bridge_assets.mkdir()
 for name,data in {bridge_full_name:bridge_full,native_name:fw,'release-record.json':encoded(first),'radio-iq-proof.json':encoded(iq),'LICENSES.zip':(assets/'LICENSES.zip').read_bytes()}.items():(bridge_assets/name).write_bytes(data)
 (output/'bootfs.bin').write_bytes(store)
 for n,d in [('release-index.stage1-native.json',stage1),('release-index.stage2-cohort.json',stage2)]:(output/n).write_bytes(encoded(d))
 proof=dict(schema=1,watch_source=head,configuration=c,source_release_sha256=sha(old),source_cohort=old_cohort,target_cohort=identity,migration=migration,packing=packing,native_candidate_sha256=sha((native_dir/'candidate.json').read_bytes()),native_sha256=sha(fw),cohort_sha256=sha(payload),cohort_bytes=len(payload),initial_image_sha256=sha(full),bridge_release=bridge_version,bridge_initial_image_sha256=sha(bridge_full),bridge_initial_component_placement=bridge_placement,monotonic_catalog_stages=True,initial_image_is_destructive=True,ordinary_payloads_exclude_nvs_appdata_bootloader_partitions=True,source_board_sha256=sha(previous['board.json']),target_board_sha256=sha(following['board.json']),new_store_members=sorted(new_files),initial_component_placement=placement,files={n:metadata(b) for n,b in following.items()})
 system_apps=Path(system_apps).resolve()
 require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=system_apps,text=True).strip()==c['sources']['system-apps']['commit'],'Wrong installed provider grammar')
 parser=output/'catalog-test'
 subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',*['-I'+str(system_apps/p) for p in ('Services/update','lib/PortableApps/include','lib/NativeApps/include')],str(ROOT/'tests/sdr_upgrade/catalog.cpp'),'-o',str(parser)],check=True)
 for name,mode in [('release-index.stage1-native.json','native'),('release-index.stage2-cohort.json','cohort')]:subprocess.run([str(parser),str(output/name),mode],check=True)
 proof['both_catalogs_accepted_by_installed_provider']=True
 (output/'sdr-build-proof.json').write_bytes(encoded(proof))
 (output/'INSTALL.txt').write_text('SDR test candidate 1.0.4; native bridge release 1.0.3. Not published or hardware-qualified.\n\nFor an installed Watch1.0.2, use the existing built-in Firmware Update twice. First publish/select only the prepared stage1 native catalog and install Runtime0.1.34. Restart and verify Clock is healthy; the existing19-app store and its cohort1.0.2 identity remain. Only then switch to the prepared stage2 cohort catalog and install Watch 1.0.4. Restart and verify Clock before opening Waterfall. Stage2 carries native+bootfs together and explicitly grants Waterfall the already shared settings namespace. Both stages preserve NVS and app-data, and keep the preceding complete pair as rollback.\n\nBoth full initial images are destructive. The full twatch-s3-launcher-1.0.4.bin is destructive initial provisioning and must NOT be used for this upgrade. Do not flash any payload at offset0 or write the empty appdata image. The OTA payloads are not direct serial-flash images. Current clients cannot install a local ZIP or CI artifact: immutable assets and each reviewed catalog stage must be published before using the Watch updater. No publication or device action is performed by this package.\n\nWaterfall: fixed2440MHz receive bursts. START/PAUSE top-right; BACK top-left. Turn off Bluetooth before capture. Busy/error statuses require explicit START retry. Sleep pauses capture. RF, hardware wake/current and physical OTA/power-loss remain unrun.\n')
 for folder in (assets,bridge_assets):(folder/'SHA256SUMS').write_text(''.join(f'{sha(p.read_bytes())}  {p.name}\n' for p in sorted(folder.iterdir()) if p.is_file()))
 return proof
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for n in ('released-bin','apps-dir','runtime','native-dir','index','output','system-apps'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();result=prepare(a.released_bin,a.apps_dir,a.runtime,a.native_dir,a.index,a.output,a.system_apps);print(json.dumps({k:result[k] for k in ('watch_source','native_sha256','cohort_sha256','cohort_bytes')}))

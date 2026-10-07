from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys
sys.path.insert(0,str(Path('scripts').resolve()))
from current_apps_overlay import verify,metadata,encoded
from current_cohort import create,encode
from current_bootfs import build
from current_flash_layout import assemble
from read_only_spiffs import read_image
root=Path('dist/full-107-recovery');head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
files,record=verify(root/'current',head,profile='low-battery')
base=Path('dist/ci-repair-8c1a/cohort/store')
store={p.relative_to(base).as_posix():p.read_bytes() for p in base.rglob('*') if p.is_file()}
store.update(files);store['boot.json']=encoded(record['boot'])
runtime=Path('../watch-runtime-iq-038');native=runtime/'dist/esp32s3-16mb-appdata-iq';candidate=json.loads((native/'candidate.json').read_text())
assert candidate['source_sha']==record['configuration']['sources']['runtime']['commit']
for name,entry in candidate['assets'].items():
 data=(native/name).read_bytes();assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'],name
firmware=(native/'firmware.bin').read_bytes();store['cohort.json']=encode(create('1.0.7',candidate['firmware_version'],head,firmware))
bootfs,packing=build(store)
metadata_path=runtime/'scripts/paired_bank_images.py';spec=importlib.util.spec_from_file_location('paired_images',metadata_path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
components={name:(native/name).read_bytes() for name in ('bootloader.bin','partitions.bin','firmware.bin','appdata.bin')}
components['bootfs.bin']=bootfs;components['otadata.bin']=module.initial_otadata();components['bank_state.bin']=module.initial_bank_state(firmware,bootfs,app_data=True)
module.parse_record(components['bank_state.bin'][:96],app_data=True)
deployment=json.loads(Path('apps/apex-runtime-requirements.json').read_text())['deployment']
full,parts=assemble(components,deployment,True)
assert len(full)==16777216 and full[0x10000:0x10000+len(firmware)]==firmware
assert read_image(full[0x2f0000:0x800000],0x510000)==store
assert len(record['apps'])==22 and all('-DPORTABLE_LOW_BATTERY' in a['defines'] for a in record['apps'].values())
output=root/'twatch-s3-1.0.7-RECOVERY-TRACE-FULL-INITIAL-ERASES-DATA-bma423.bin';output.write_bytes(full)
(root/'bootfs.bin').write_bytes(bootfs)
for name,data in store.items():
 p=root/'store'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
proof={'product_version':'1.0.7','motion_model':'bma423','watch_source':head,'utilities_source':record['configuration']['sources']['utilities']['commit'],'runtime_source':candidate['source_sha'],'runtime_version':candidate['firmware_version'],'file':output.name,**metadata(full),'flash_offset':'0x0','full_initial_image':True,'erases_nvs_settings_wifi_credentials_alarms_points_and_app_data':True,'app_count':22,'automatic_low_battery_every_app':True,'configuration':record['configuration'],'components':parts,'packing':packing,'fixes':{'touch':'0.2.1 last-emitted event sequence','hid_apps':'0.1.3 packet error ownership, clean saved-bond reconnect and original-cause diagnostics','sdr':'0.1.4 no CPU reads while DMA owns SRAM, stop/settle/copy and stage/register tracing','waterfall':'0.1.6 pre-operation capture stage diagnostics','native_iq':'Runtime0.1.41 balanced modem/power-domain/PHY ownership'},'validation':'Focused production regressions and sanitizers passed; full target compilation and package integrity checked. Native power lifecycle and SRAM ownership corrections follow pinned SDK/upstream contracts. Prior device freeze and intermittent HID failure still require hardware confirmation; no CI wait.'}
(root/'BUILD-AND-FLASH-NOTES.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'file':str(output.resolve()),'sha256':hashlib.sha256(full).hexdigest(),'bytes':len(full),'watch_source':head}))

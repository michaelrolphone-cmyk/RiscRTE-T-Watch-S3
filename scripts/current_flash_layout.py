"""Explicit full-image layouts; never formats or accesses a device."""
import hashlib
from expanded_layout import (LAYOUT as EXPANDED_LAYOUT, DEPLOYMENT_PARTS as EXPANDED_PARTS,
                             FACTORY_WARNING, verify_factory_components)
from build_update_flash_bundle import assemble as assemble_legacy, LAYOUT as LEGACY_LAYOUT
APP_DATA_LAYOUT='riscrte-paired-appdata-v2'
APP_DATA_SHA='5f03c248f2de31c4da9ae8d9bc2033df064cee5e37694a9982f70fbb2f1d2ef0'
LEGACY_PARTS={'app0':{'offset':0x10000,'size':0x300000},'bootfs0':{'offset':0x310000,'size':0x4f0000},'app1':{'offset':0x800000,'size':0x300000},'bootfs1':{'offset':0xb00000,'size':0x4f0000},'otadata':{'offset':0xff0000,'size':0x2000},'bank_state':{'offset':0xff2000,'size':0x2000}}
APP_DATA_PARTS={**LEGACY_PARTS,'app0':{'offset':0x10000,'size':0x260000},'app1':{'offset':0x800000,'size':0x260000},'appdata':{'offset':0x270000,'size':0x80000},'bootfs0':{'offset':0x2f0000,'size':0x510000},'bootfs1':{'offset':0xae0000,'size':0x510000}}
def require(ok,message):
 if not ok:raise ValueError(message)
def validate(deployment,initialize_app_data=False):
 expanded=deployment.get('layout')==EXPANDED_LAYOUT
 app_data=expanded or deployment.get('layout')==APP_DATA_LAYOUT
 layout=EXPANDED_LAYOUT if expanded else APP_DATA_LAYOUT if app_data else LEGACY_LAYOUT
 target=('esp32s3-16mb-appdata-iq' if deployment.get('radio_iq') is True else 'esp32s3-16mb-appdata') if app_data else 'esp32s3-16mb-paired'
 if expanded:target='esp32s3-16mb-appdata-expanded-iq' if deployment.get('radio_iq') is True else 'esp32s3-16mb-appdata-expanded'
 abi=3 if expanded else 2 if app_data else 1
 require(deployment.get('layout')==layout and deployment.get('target')==target and type(deployment.get('store_abi')) is int and deployment['store_abi']==abi,'Unknown or mismatched current layout/ABI')
 require(deployment.get('flash_bytes')==0x1000000 and deployment.get('partitions')==(EXPANDED_PARTS if expanded else APP_DATA_PARTS if app_data else LEGACY_PARTS),'Current partition geometry differs')
 require(bool(initialize_app_data)==app_data,'Initial app-data assembly must be explicitly selected and cannot target the legacy layout')
 return app_data

def assemble(components,deployment,initialize_app_data=False):
 if not validate(deployment,initialize_app_data):return assemble_legacy(components)
 expanded=deployment['layout']==EXPANDED_LAYOUT
 store_end=0x840000 if expanded else 0x800000
 store_bytes=0x550000 if expanded else 0x510000
 if expanded:
  require(deployment.get('factory_warning')==FACTORY_WARNING,'Expanded factory artifact must explicitly warn that full 0x0 BIN erases current settings')
 offsets=[('bootloader.bin',0,0x8000),('partitions.bin',0x8000,0x9000),('firmware.bin',0x10000,0x270000),('appdata.bin',0x270000,0x2f0000),('bootfs.bin',0x2f0000,store_end),('otadata.bin',0xff0000,0xff2000),('bank_state.bin',0xff2000,0xff4000)]
 require(set(components)=={name for name,_,_ in offsets},'Initial app-data component membership')
 if expanded:verify_factory_components(components)
 for name,size in [('appdata.bin',0x80000),('bootfs.bin',store_bytes),('otadata.bin',0x2000),('bank_state.bin',0x2000)]:require(len(components[name])==size,'Wrong component size: '+name)
 require(hashlib.sha256(components['appdata.bin']).hexdigest()==APP_DATA_SHA,'Initial app-data bytes differ from verified empty disk2.1 image')
 image=bytearray(b'\xff'*0x1000000);entries=[];cursor=0
 for name,offset,limit in offsets:
  data=components[name];require(data and cursor<=offset and offset+len(data)<=limit,'Component crosses initial app-data partition boundary')
  require(all(v==255 for v in image[cursor:offset]),'Non-erased gap')
  image[offset:offset+len(data)]=data;cursor=offset+len(data)
  entries.append({'file':'components/'+name,'offset':hex(offset),'size_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
 require(all(v==255 for v in image[store_end:0xff0000]),'Inactive bank must remain erased')
 return bytes(image),entries

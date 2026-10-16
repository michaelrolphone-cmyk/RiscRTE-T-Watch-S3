#!/usr/bin/env python3
"""Opt-in Watch 1.0.12. Earlier accepted profiles are unchanged."""
import copy,json,re
from pathlib import Path
from current_apps_overlay import APPS,ROOT,require,metadata
from power_repair_profile import POWER_DRIVERS,STORAGE,baseline_inputs,driver_custody
PROFILE='runtime-features'
VERSION='1.0.12'
RUNTIME_VERSION='0.1.55'
FEATURE_CAPS={'default':('runtime.realtime-control','runtime.retained-wake','runtime.provider-promotion'),
              'clock':('runtime.realtime-control',)}
def runtime_requirements(root=ROOT):
 value=json.loads((Path(root)/'apps/runtime-features-runtime-requirements.json').read_text())
 require(value['firmware_version']==RUNTIME_VERSION and re.fullmatch('[0-9a-f]{40}',value['source_sha']), 'Unpinned Runtime features source')
 prior=json.loads((Path(root)/'apps/power-repair-runtime-requirements.json').read_text())
 expected={**prior['required_behavior'],'app_grant_capacity':16,'app_requirement_capacity':16,
  'native_realtime':True,'retained_wake_checkpoints':True,'demand_provider_activation':True,
  'default_provider_promotion':True,'retained_invocation_fence':True}
 require(value['rf_storage']==STORAGE and value['required_behavior']==expected,'Runtime feature/RF bounds differ')
 require(value['deployment']==prior['deployment'] and value['abi_changed'] is False and
  value['public_runtime_api_prefix_changed'] is False,'Runtime feature layout/ABI drift')
 return value

def validate_configuration(c,root=ROOT,**_):
 prior=json.loads((Path(root)/'apps/power-repair-sources.json').read_text())
 require(c['product_version']==VERSION and c['features']=={**prior['features'],'runtime_features':True},'Incomplete runtime feature profile')
 require(c['power_drivers']==POWER_DRIVERS and c['rf_storage']==STORAGE and set(c['app_versions'])==set(APPS),'Lost accepted Watch inventory')
 for name in APPS:
  require(tuple(map(int,c['app_versions'][name].split('.')))>tuple(map(int,prior['app_versions'][name].split('.'))),'Unversioned rebuilt app: '+name)
 require(c['sources']['runtime']['commit']==runtime_requirements(root)['source_sha'],'Runtime app/native pin mismatch')
 require(c['telemetry_broadcast']=={'id':'telemetry-broadcast','version':'0.1.0'},'Wrong telemetry service')

def upgrade_boot(boot):
 b=copy.deepcopy(boot);b['provider_activation']='demand'
 b['drivers'].append({'manifest':'broadcast/manifest.json'})
 for row in b['app_capabilities']:
  name=row['manifest'].removesuffix('.json')
  if name not in APPS:continue
  for cap in (*FEATURE_CAPS.get(name,()),'telemetry.broadcast'):
   require(not any(g['capability']==cap for g in row['grants']),'Duplicate feature authority')
   row['grants'].append({'capability':cap,'api':1,'instance_id':0})
  require(len(row['grants'])<=16,'Feature grant bound exceeded')
 require(len(b['drivers'])<=24,'Feature provider bound exceeded')
 require(all(len(row['manifest'])<=31 for row in b['drivers']),'Feature provider exceeds SPIFFS path bound')
 return b

def requirements(name,manifest):
 for cap in (*FEATURE_CAPS.get(name,()),'telemetry.broadcast'):
  require(not any(q['capability']==cap for q in manifest['requires']),'Duplicate feature manifest')
  manifest['requires'].append({'capability':cap,'api':1})
 return manifest

def verify_profile(files,record,root=ROOT):
 from current_apps_overlay import configure_boot
 from build_current_apps import definitions
 c=record['configuration'];validate_configuration(c,root)
 require(record['boot']==configure_boot(record['baseline_boot'],PROFILE),'Runtime feature boot authority differs')
 require(record['runtime_requirements']==runtime_requirements(root),'Runtime feature proof differs')
 for row in record['boot']['app_capabilities']:
  m=json.loads(files[row['manifest']]);required={(q['capability'],q['api']) for q in m['requires']}
  require(required=={(g['capability'],g['api']) for g in row['grants']} and len(required)==len(m['requires']),'Feature manifest/grant parity differs')
 for name in APPS:
  require(sorted(record['apps'][name]['defines'])==sorted(definitions(name,c['app_versions'][name],True,rf_spectrum=True,runtime_features=True)),'Feature target flags differ: '+name)
 power=record['power_drivers'];require(power['versions']==POWER_DRIVERS,'Accepted power drivers lost')
 from current_apps_overlay import sha
 require(power['source_sha256'] and all((Path(root)/name).is_file() and sha((Path(root)/name).read_bytes())==digest
  for name,digest in power['source_sha256'].items()),'Power driver source custody differs')
 for folder,version in POWER_DRIVERS.items():
  require(json.loads(files[folder+'/manifest.json'])==json.loads((Path(root)/'drivers'/('twatch_'+folder)/'manifest.json').read_text()),'Power driver manifest differs')
  require(power['files'][folder+'/driver.elf']==metadata(files[folder+'/driver.elf']),'Power driver ELF custody differs')
 require(json.loads(files['broadcast/manifest.json'])['version']=='0.1.0','Telemetry provider version differs')

#!/usr/bin/env python3
"""Add explicit package grants without changing existing app identities/data."""
import argparse,json,hashlib,shutil
from pathlib import Path
import t023_boot_profiles as core_profiles
import t023_provider_compaction as provider_compaction
p=argparse.ArgumentParser()
for key in ['baseline','home','springboard','catalog','internal','output']:p.add_argument('--'+key,type=Path,required=True)
p.add_argument('--firmware',type=Path,required=True)
p.add_argument('--version',required=True)
p.add_argument('--source-revision',required=True)
p.add_argument('--runtime-version',help='Exact native version, verified against firmware.bin; required for boot profiles')
p.add_argument('--boot-profiles',action='store_true',help='Opt in to the native next-boot request bridge')
p.add_argument('--native-provider-manifests',type=Path,help='JSON list of exact native-selected provider manifests; [] if none')
p.add_argument('--composition-report',type=Path,help='Write source-only preservation evidence outside the store')
p.add_argument('--compact-new-providers',action='store_true',help='Losslessly compact only the two newly added provider ELFs')
p.add_argument('--compiler',type=Path,help='Explicit provider gcc path, required for compaction')
p.add_argument('--debug-sidecar-dir',type=Path,help='Separate output directory retaining the original provider ELFs')
a=p.parse_args()
if (a.native_provider_manifests or a.composition_report or a.runtime_version or a.compact_new_providers) and not a.boot_profiles:p.error('Profile options require --boot-profiles')
if (a.compiler or a.debug_sidecar_dir) and not a.compact_new_providers:p.error('Compaction options require --compact-new-providers')
if a.composition_report and a.composition_report.resolve().is_relative_to(a.output.resolve()):p.error('--composition-report must be outside the store')
if a.boot_profiles and not a.runtime_version:p.error('--boot-profiles requires --runtime-version')
if a.boot_profiles:
 firmware=a.firmware.read_bytes()
 core_profiles.verify_runtime_version(a.runtime_version,firmware)
selected_native=core_profiles.validate_inputs(a.catalog,'twatch',a.native_provider_manifests) if a.boot_profiles else []
compaction_plan=None
if a.compact_new_providers:
 if any((a.baseline/name).exists() for name in provider_compaction.PROVIDERS):p.error('Provider compaction is limited to newly added ELFs')
 compaction_plan=provider_compaction.prepare('twatch',a.compiler,a.debug_sidecar_dir,a.composition_report,a.output,[a.baseline,a.home,a.springboard,a.catalog,a.internal,a.firmware])
boot=json.loads((a.baseline/'boot.json').read_text());before=json.loads(json.dumps(boot))
assert 'installation' not in boot,'Unexpected baseline installation authority'
boot['installation']={'grants':[],'volume_instance':0}
assert len(boot['drivers'])==34
entry=next(x for x in boot['app_capabilities'] if x['manifest']=='default.json')
for cap,instance in [('software.installed-apps',0),('storage.key-value',6)]:
 grant={'capability':cap,'api':1,'instance_id':instance}
 if grant not in entry['grants']:entry['grants'].append(grant)
entry=next(x for x in boot['app_capabilities'] if x['manifest']=='springboard.json')
for cap,instance in [('software.installed-apps',0)]:
 grant={'capability':cap,'api':1,'instance_id':instance}
 if grant not in entry['grants']:entry['grants'].append(grant)
boot['drivers'] += [{'manifest':'installed-apps/manifest.json','app_data':[{'name':'installed.apps','namespace':2000,'access':'read-write'}]}, {'manifest':'pkg-internal/manifest.json'}]
envelope=[{'capability':cap,'api':api,'instance_id':instance} for cap,api,instance in [('display.output',1,5),('input.touch.raw',1,6),('board.battery',1,4),('alarm.service',1,0),('runtime.realtime',1,0),('storage.key-value',1,0),('storage.app-data',1,0)]]
boot['installation'].update(internal_volume_instance=0,namespace_range={'first':3000,'count':128},grants=envelope,provider_grants=[g for g in envelope if g['capability'] not in ['storage.key-value','storage.app-data']])
# Existing app grants, private namespaces and driver selections are preserved.
for old,new in zip(before['app_capabilities'],boot['app_capabilities']):
 assert old==new or (old['manifest'] in ('default.json','springboard.json') and all(g in new['grants'] for g in old['grants']))
assert boot['drivers'][:34]==before['drivers']
shutil.copytree(a.baseline,a.output)
for name in ['default.elf','default.json']:shutil.copyfile(a.home/name,a.output/name)
for name in ['springboard.elf','springboard.json']:shutil.copyfile(a.springboard/name,a.output/name)
home=json.loads((a.output/'default.json').read_text())
baseline_home=json.loads((a.baseline/'default.json').read_text())
for field in ('requires','optional'):
 for declaration in baseline_home.get(field,[]):
  if declaration not in home.get('requires',[])+home.get('optional',[]):home.setdefault(field,[]).append(declaration)
(a.output/'default.json').write_text(json.dumps(home,separators=(',',':'))+'\n')
springboard=json.loads((a.output/'springboard.json').read_text())
baseline_springboard=json.loads((a.baseline/'springboard.json').read_text())
for field in ('requires','optional'):
 for declaration in baseline_springboard.get(field,[]):
  if declaration not in springboard.get('requires',[])+springboard.get('optional',[]):
   springboard.setdefault(field,[]).append(declaration)
(a.output/'springboard.json').write_text(json.dumps(springboard,separators=(',',':'))+'\n')
for source,target in [(a.catalog,'installed-apps'),(a.internal,'pkg-internal')]:
 (a.output/target).mkdir()
 for name in ['driver.elf','manifest.json']:shutil.copyfile(source/name,a.output/target/name)
compaction_proof=provider_compaction.compact_new_providers(a.output,compaction_plan) if compaction_plan else None
if a.boot_profiles:
 profile_report=core_profiles.compose(boot,a.output,'twatch',selected_native)
(a.output/'boot.json').write_text(json.dumps(boot,separators=(',',':'))+'\n')
cohort=json.loads((a.output/'cohort.json').read_text())
firmware=firmware if a.boot_profiles else a.firmware.read_bytes()
assert len(a.source_revision)==40 and all(c in '0123456789abcdef' for c in a.source_revision)
cohort.update(version=a.version,source_revision=a.source_revision,firmware_size=len(firmware),firmware_sha256=hashlib.sha256(firmware).hexdigest())
if a.boot_profiles:
 cohort['runtime_version']=a.runtime_version
 profile_report['runtime_version']=a.runtime_version
 profile_report['firmware_sha256']=cohort['firmware_sha256']
(a.output/'cohort.json').write_text(json.dumps(cohort,separators=(',',':'))+'\n')
print('Preserved34 drivers/all existing app policies; explicit catalog/cache/private namespace and package media grants composed. Complete admission remains required.')

if a.boot_profiles:
 profile_report.update(core_profiles.verify_preservation(a.baseline,a.output))
 if compaction_proof is not None:profile_report['provider_compaction']=compaction_proof
 if a.composition_report:
  a.composition_report.write_text(json.dumps(profile_report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in profile_report.items() if k not in ('files','mirrors','provider_compaction')}))

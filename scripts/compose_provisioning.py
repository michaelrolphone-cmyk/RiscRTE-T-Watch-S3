#!/usr/bin/env python3
"""Add explicit package grants without changing existing app identities/data."""
import argparse,json,hashlib,shutil
from pathlib import Path
p=argparse.ArgumentParser()
for key in ['baseline','home','springboard','catalog','internal','output']:p.add_argument('--'+key,type=Path,required=True)
p.add_argument('--firmware',type=Path,required=True)
p.add_argument('--version',required=True)
p.add_argument('--source-revision',required=True)
a=p.parse_args();boot=json.loads((a.baseline/'boot.json').read_text());before=json.loads(json.dumps(boot))
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
for source,target in [(a.catalog,'installed-apps'),(a.internal,'pkg-internal')]:
 (a.output/target).mkdir()
 for name in ['driver.elf','manifest.json']:shutil.copyfile(source/name,a.output/target/name)
(a.output/'boot.json').write_text(json.dumps(boot,separators=(',',':'))+'\n')
cohort=json.loads((a.output/'cohort.json').read_text())
firmware=a.firmware.read_bytes()
assert len(a.source_revision)==40 and all(c in '0123456789abcdef' for c in a.source_revision)
cohort.update(version=a.version,source_revision=a.source_revision,firmware_size=len(firmware),firmware_sha256=hashlib.sha256(firmware).hexdigest())
(a.output/'cohort.json').write_text(json.dumps(cohort,separators=(',',':'))+'\n')
print('Preserved34 drivers/all existing app policies; explicit catalog/cache/private namespace and package media grants composed. Complete admission remains required.')

#!/usr/bin/env python3
"""Verified current-app overlay; historical custody stores are never rewritten."""
import copy,hashlib,json,re,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PROFILE='watch-current-apps-v1'
SYSTEM_APPS=('springboard','settings','wifi_settings','ota_update','app_store')
UTILITY_APPS=('battery','calculator','stopwatch','alarms','countdown','frequency_generator','audio_spectrum')
PRODUCTIVITY_APPS=('points_in_time',)
CLOCK_APPS=('default','clock')
NON_CLOCK_APPS=SYSTEM_APPS+UTILITY_APPS+PRODUCTIVITY_APPS
APPS=NON_CLOCK_APPS+CLOCK_APPS
PROVIDERS=('alarm-service','update-fw','update-apps')
PAYLOADS={n+suffix for n in APPS for suffix in ('.elf','.json')}|{n+'/'+suffix for n in PROVIDERS for suffix in ('driver.elf','manifest.json')}
ALLOWED=PAYLOADS|{'boot.json'}
ALARM_VOLUME={'key':'alarm_volume','namespace':1,'access':'read'}
ALARM_PREFERENCES={'capability':'storage.key-value','api':1,'instance_id':1}
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return (json.dumps(v,indent=2,sort_keys=True)+'\n').encode()
def require(ok,message):
 if not ok:raise ValueError(message)
def metadata(b):return {'size_bytes':len(b),'sha256':sha(b)}
def config(root=ROOT):
 c=json.loads((Path(root)/'apps/current-apps-sources.json').read_text())
 require(c.get('schema')==1 and c.get('profile')==PROFILE,'Wrong current-app profile')
 require(set(c['sources'])=={'system-apps','utilities','productivity','runtime'},'Current source inventory differs')
 for p in c['sources'].values():require(re.fullmatch('[0-9a-f]{40}',p.get('commit','')) is not None,'Unpinned current source')
 require(set(c['app_versions'])==set(APPS),'Current app versions incomplete')
 for v in list(c['app_versions'].values())+[c['service_version']]:require(re.fullmatch(r'\d+\.\d+\.\d+',v) is not None,'Bad current version')
 require(c['service_version']=='0.4.0','Expected reviewed CUE/volume service0.4.0')
 return c

def configure_boot(original):
 """Add shared settings/RTC grants explicitly; preserve each existing grant."""
 b=copy.deepcopy(original)
 rows=[x for x in b['app_capabilities'] if x['manifest']=='alarms.json'];require(len(rows)==1,'Missing/duplicate Alarms policy')
 grants=rows[0]['grants'];kv=[x for x in grants if x['capability']=='storage.key-value']
 require(kv==[{'capability':'storage.key-value','api':1,'instance_id':3}],'Unexpected prior Alarms storage policy')
 grants.insert(next(i for i,x in enumerate(grants) if x['capability']=='alarm.service'),copy.deepcopy(ALARM_PREFERENCES))
 rows=[x for x in b['drivers'] if x['manifest']=='alarm-service/manifest.json'];require(len(rows)==1,'Missing/duplicate alarm provider')
 keys=rows[0]['key_value'];require(len(keys)==7 and not any(x['key']=='alarm_volume' for x in keys),'Unexpected prior bound service policy')
 expected={'alarm_cfg':(3,'read'),'timer_cfg':(3,'read'),'alarm_occ':(4,'read-write'),'timer_occ':(4,'read-write'),'alert_mode':(1,'read'),'points_cfg':(5,'read'),'points_occ':(4,'read-write')}
 require({x['key']:(x['namespace'],x['access']) for x in keys}==expected,'Legacy service bindings differ')
 keys.append(copy.deepcopy(ALARM_VOLUME))
 for row in b['app_capabilities']:
  if row['manifest'] in {n+'.json' for n in APPS}:
   for grant in (ALARM_PREFERENCES,{'capability':'rtc.clock','api':2,'instance_id':8}):
    if grant not in row['grants']:row['grants'].append(copy.deepcopy(grant))
  require(len(row['grants'])<=9,'Current application exceeds Runtime grant bound')
 return b

def verify(artifact,head,root=ROOT):
 artifact=Path(artifact);c=config(root);r=json.loads((artifact/'current-apps-build.json').read_text())
 require(r.get('schema')==1 and r.get('profile')==PROFILE and r.get('watch_source')==head,'Current overlay identity/head mismatch')
 require(r.get('configuration')==c,'Current overlay source/version configuration differs')
 require(set(r['files'])==PAYLOADS and set(r['apps'])==set(APPS),'Current payload inventory differs')
 require(r.get('target_validation') is True,'Current target validation missing')
 files={}
 for name,meta in r['files'].items():
  b=(artifact/'files'/name).read_bytes();require(metadata(b)==meta,'Current payload hash/size differs: '+name);files[name]=b
 for name in APPS:
  m=json.loads(files[name+'.json']);a=r['apps'][name]
  require(m['version']==c['app_versions'][name] and a['version']==m['version'],'Current app version mismatch: '+name)
  require(m['file_name']==name+'.elf' and m['entry']=='app_main' and m['architecture']=='xtensa-esp32s3','Current app ABI mismatch')
  require(a['sha256']==sha(files[name+'.elf']) and a['size_bytes']==len(files[name+'.elf']),'Current app build record differs')
  require(('-DWATCH_CLOCK_ALARMS' if name in CLOCK_APPS else '-DPORTABLE_ALARM_CLIENT') in a['defines'],'Current CUE client missing: '+name)
  if name not in ('frequency_generator',*CLOCK_APPS):require('-DPORTABLE_NOVA_UI' in a['defines'],'Current Nova profile missing: '+name)
 clock=r['clock'];require(clock['watch_source']==head and clock['sources']==c['sources'] and clock['paired_boot_confirmation'] is True,'Current Clock source/profile mismatch')
 require(set(clock['files'])=={n+e for n in CLOCK_APPS for e in ('.elf','.json')},'Current Clock inventory differs')
 for name,meta in clock['files'].items():require(metadata(files[name])==meta,'Current Clock artifact differs: '+name)
 require(clock['headers']==r['service']['points_headers'],'Current Clock/service schema mismatch')
 require(isinstance(clock.get('source_sha256'),dict) and bool(clock['source_sha256']),'Current Clock source hashes missing')
 for name,digest in clock['source_sha256'].items():
  require(not Path(name).is_absolute() and '..' not in Path(name).parts and re.fullmatch('[0-9a-f]{64}',digest) is not None,'Unsafe Clock source hash entry')
  require((Path(root)/name).is_file() and sha((Path(root)/name).read_bytes())==digest,'Current Clock source bytes differ: '+name)
 require(json.loads(files['alarm-service/manifest.json'])['version']==c['service_version'],'Current alarm version mismatch')
 require(r['service']['defines']==['-DPOINTS_IN_TIME_SERVICE','-DPORTABLE_RTC_UTC8_DENVER','-DALARM_VOLUME_CONTROL'],'Wrong current service profile')
 archive=artifact/'current-apps.zip';require(archive.is_file(),'Current archive missing')
 with zipfile.ZipFile(archive) as z:
  names=z.namelist();require(len(names)==len(set(names)),'Duplicate current archive members')
  expected={'current-apps-build.json','source-profile.json'}|{'files/'+n for n in PAYLOADS}|{p.relative_to(artifact).as_posix() for p in (artifact/'licenses').rglob('*') if p.is_file()}
  require(set(names)==expected,'Current archive inventory differs')
  for name in names:require(z.read(name)==(artifact/name).read_bytes(),'Current archive/member differs: '+name)
 require(json.loads((artifact/'source-profile.json').read_text())==c,'Current source profile differs')
 return files,r

def apply(store,artifact,head,root=ROOT):
 """Input has already passed historical archive and paired Clock verification."""
 files,r=verify(artifact,head,root);before=dict(store)
 require(set(PAYLOADS)<=set(before),'Current overlay may replace only installed files')
 require(json.loads(before['boot.json'])==r['baseline_boot'],'Unexpected policy change before current overlay')
 after=dict(before);after.update(files);after['boot.json']=encoded(configure_boot(r['baseline_boot']))
 require(set(before)==set(after),'Current overlay added/removed store members')
 for name,b in before.items():
  if name not in ALLOWED:require(after[name]==b,'Current overlay changed unrelated payload: '+name)
 require(json.loads(after['boot.json'])==r['boot'],'Current overlay boot proof mismatch')
 # Manifest requirements must match configured grants, with KV namespaces
 # declared once in the manifest and independently scoped in the boot policy.
 for row in r['boot']['app_capabilities']:
  if row['manifest'] not in after:continue
  m=json.loads(after[row['manifest']]);expected={(g['capability'],g['api']) for g in row['grants']}
  require({(q['capability'],q['api']) for q in m['requires']}==expected,'Current manifest/grant mismatch: '+row['manifest'])
 provenance={'schema':1,'profile':PROFILE,'watch_source':head,'sources':r['configuration']['sources'],'configuration':r['configuration'],'build_record':r,'build_record_sha256':sha((Path(artifact)/'current-apps-build.json').read_bytes()),'archive_sha256':sha((Path(artifact)/'current-apps.zip').read_bytes()),'files':{n:metadata(after[n]) for n in sorted(ALLOWED)},'preserved_files':{n:metadata(b) for n,b in sorted(before.items()) if n not in ALLOWED},'catalog':r['catalog'],'all_current_clients_cue_aware':True}
 return after,provenance

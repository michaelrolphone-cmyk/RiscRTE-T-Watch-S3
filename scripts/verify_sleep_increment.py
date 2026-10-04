#!/usr/bin/env python3
"""Verify bounded sleep changes against the physically accepted 0.4.5 store."""
import hashlib,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()
def function(source,name):
    match=re.search(r'static\s+[^\n;]+\b'+name+r'\([^;]*?\)\s*\{',source)
    assert match,name
    start=match.start();at=match.end();depth=1
    while depth:
        if source[at]=='{':depth+=1
        elif source[at]=='}':depth-=1
        at+=1
    return source[start:at].encode()
def verify(path):
    baseline=json.loads((ROOT/'docs/SLEEP_BASELINE.json').read_text())
    for name,digest in baseline['unchanged_source_sha256'].items():assert sha((ROOT/name).read_bytes())==digest,name
    panel=(ROOT/'drivers/twatch_panel/driver.c').read_text()
    for name,digest in baseline['unchanged_panel_function_sha256'].items():assert sha(function(panel,name))==digest,name
    with zipfile.ZipFile(path) as z:
        names=z.namelist();assert len(names)==len(set(names))
        files={n.removeprefix('store/'):z.read(n) for n in names if n.startswith('store/')}
        source=json.loads(z.read('shared-app-build.json'))
        assert source['touch_rotation']==0 and source['full_frames'] is True and source['retained_handoff'] is True
        assert source['handoff_ms']==60 and source['return_targets']=={'springboard':'clock.elf','battery':'springboard.elf','settings':'springboard.elf'}
        assert source['crown_navigation']=='app-local-original-pmu'
        assert source['sleep_policy']=={'default':'light','choice':'storage.key-value@1','instance_id':1,'key':'sleep_mode','deep_wake':'fresh-default','ulp_program':False}
        assert source['shared_sources']==json.loads((ROOT/'apps/shared-sources.json').read_text())
    expected=baseline['baseline_store_sha256'];assert set(files)==set(expected) and len(files)==24
    actual={n:sha(b) for n,b in sorted(files.items())}
    changed=sorted(n for n in files if actual[n]!=expected[n]);assert changed==baseline['changed_store_files'],changed
    fixed=sorted(set(expected)-set(changed));assert len(fixed)==11
    boot=json.loads(files['boot.json']);assert boot['drivers']==baseline['baseline_driver_instances'] and len(boot['drivers'])==7
    for app in boot['app_capabilities']:
        kv=[g for g in app['grants'] if g['capability']=='storage.key-value']
        assert kv==([{'capability':'storage.key-value','api':1,'instance_id':1}] if app['manifest'] in ('default.json','clock.json','settings.json') else [])
        assert all(g['capability']!='input.navigation' for g in app['grants'])
    record={**baseline,'variant_store_sha256':actual,'verified_changed_files':changed,'unchanged_file_count':len(fixed),'unchanged_store_files':fixed}
    (Path(path).parent/'sleep-increment-proof.json').write_text(json.dumps(record,indent=2)+'\n')
    print('Verified sleep inventory: 11 unchanged files, 13 bounded mode/app/driver/grant files; accepted panel rendering and board retained')
    return record
if __name__=='__main__':
    assert len(sys.argv)==2
    verify(sys.argv[1])

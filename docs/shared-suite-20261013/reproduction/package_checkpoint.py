from pathlib import Path
import hashlib,json,tarfile,zipfile,subprocess
R=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=json.loads((R/'final-verification.json').read_text());sources=json.loads((R/'recovery/source-checkpoints.json').read_text())
checks={}
for key in ('watch-final-normal','watch-final-sanitized','wave-final-normal','wave-final-sanitized','watch-preserving-transition'):
 p=R/'tests'/(key+'.json');doc=json.loads(p.read_text());v=doc.get('result',doc)
 assert v['prepared'] and v['cohort_validated'] and v['hardware_calls']==v['storage_calls']==0
 assert v['elf_count']==(60 if key.startswith('wave-') else 59)
 checks[key]={'file':str(p.relative_to(R)),'sha256':sha(p),'result':v}
card=json.loads((R/'tests/card-admission.json').read_text());assert all(x['production_native_admission'] and x['each_missing_import_rejected'] for x in card.values())
trace=(R/'tests/wave-transition-diagnostic.log').read_text();assert 'DIAGNOSTIC cohort refusal line 234' in trace
qualification={'schema':1,'sources':sources,'final_images_and_parity':r,'admission':checks,'external_card_native_admission':card,'wave_transition_refusal':{'source':'src/bootstrap/CohortRuntime.inc:234','reason':'New LoRa consumer requests existing persistent namespaces without a selected explicit migration. Production transition rejects before ELF admission; a disposable diagnostic copy identified the guard.','diagnostic_only_source_modified':True,'production_guard_unchanged':True},'test_scopes':{'home':'All 262358 atlas bytes recovered; all 362 existing 240px golden frames exact; 410px rendering; normal and ASan/UBSan sleep/wake, missing-media first-frame label and cleanup.','files':'Actual three-root controller: missing capability, absent/reinserted media, copy/cancel/retained release; normal and UBSan.','viewer':'Actual app entrypoint: absent storage.volume, AppData/source handoff, present SD and legacy SD; ASan/UBSan.','optional_hardware':'Prior exact LoRa source missing-radio/idle/send-history normal+ASan/UBSan and exact Hardware Test present/absent across 240/410/502x410 retained. See prior checkpoint.','runtime':'New removable launch feedback normal+ASan/UBSan. Update health, paired-bank/AppData and native provider custody/admission normal+ASan/UBSan. No target instructions or hardware.'},'hold_until':'2026-10-13T23:30:00Z','build_delivery':'held locally; no new Library build artifact IDs or GitHub/Drive publication','prior_recovery':{'path':'cumulative-rf-0121/recovery-through-0.1.21.tar.gz','sha256':sha(R.parent/'cumulative-rf-0121/recovery-through-0.1.21.tar.gz')},'evidence':{}}
for p in sorted(R.rglob('*.log')):
 if p.is_file():qualification['evidence'][str(p.relative_to(R))]={'bytes':p.stat().st_size,'sha256':sha(p)}
for p in (R/'home-packed-build/build.json',R/'home-packed-build/compaction-v4.json',R/'watch-assembly-final/factory.json',R/'waveshare-assembly-final/assembly.json'):
 qualification['evidence'][str(p.relative_to(R))]={'bytes':p.stat().st_size,'sha256':sha(p)}
(R/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n')
held=R/'held-delivery';held.mkdir(exist_ok=True)
with zipfile.ZipFile(held/'Waveshare-0.1.22-SD-card.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted((R/'staged-final/card').rglob('*')):
  if p.is_file():z.write(p,p.relative_to(R/'staged-final/card'))
readme='Shared 26-app suite, software-qualified factory images\nDelivery hold: 2026-10-13 23:30 UTC.\nBoth full BINs target 0x0 and ERASE saved settings/NVS/AppData if flashed. No device was accessed or flashed.\nT-Watch 1.1.23 keeps all 26 apps internal. Waveshare 0.1.22 keeps Home and core internal; extract the SD-card ZIP at card root for LoRa. Its catalog/permissions remain internal policy. Missing media returns to Home with APP MEDIA UNAVAILABLE. Missing radio shows unavailable UI.\nThe 26 application ELFs are identical across products. Product provider sets differ.\nABI3 and initialized 512 KiB AppData are unchanged; 32 declarations/grant rows, 16 live handles.\nNormal + ASan/UBSan admission: T-Watch 59 ELFs, Waveshare 60 internal ELFs; LoRa external ELF independently checked against both native public export tables. Zero hardware/storage calls in admission.\nT-Watch baseline-to-candidate cohort admission passes. Waveshare preserving transition rejects new LoRa namespace sharing without an explicit migration. These deliverables are factory images, not an OTA package.\nSee qualification.json and final-verification.json for exact sources, hashes, evidence and limitations. Hardware/RF/SD electrical behavior remains unqualified.\n'
(held/'README.txt').write_text(readme)
with zipfile.ZipFile(held/'Shared-watch-26-app-factory-suite.zip','w',zipfile.ZIP_DEFLATED) as z:
 for k,v in r['images'].items():z.write(R/v['file'],Path(v['file']).name)
 for p in (held/'README.txt',held/'Waveshare-0.1.22-SD-card.zip',R/'qualification.json',R/'final-verification.json'):z.write(p,p.name)
 for name in ('watch-assembly-final/factory.json','waveshare-assembly-final/assembly.json','watch-sealed-final/sealed-store.json'):
  z.write(R/name,'evidence/'+name)
with tarfile.open(held/'Shared-watch-26-app-recovery.tar.gz','w:gz') as t:
 for p in sorted((R/'recovery').iterdir()):
  if p.is_file():t.add(p,'current-source/'+p.name)
 for folder in ('home-packed-build','watch-assembly-final','waveshare-assembly-final'):
  for p in sorted((R/folder).iterdir()):
   if p.is_file():t.add(p,'current-build/'+folder+'/'+p.name)
 for name in ('firmware.elf','firmware.bin','partitions.bin','bootloader.bin'):
  t.add(Path('/tmp/twatch-capacity-runtime-0121/.pio/build/watch-expanded')/name,'current-build/watch-native/'+name)
 t.add(R/'baseline/T-Watch-S3-1.1.22-full-0x0.bin','source-inputs/T-Watch-S3-1.1.22-full-0x0.bin')
 t.add(R.parent/'cumulative-rf-0121/final-assembly/Waveshare-0.1.21-expanded-updates-full-initial-erases-data-0x0.bin','source-inputs/Waveshare-0.1.21-full-0x0.bin')
 t.add(R/'staged-final/card','current-card')
 for p in sorted((R/'tests').rglob('*')):
  if p.is_file() and p.suffix in ('.json','.log','.h','.cpp'):t.add(p,'current-tests/'+str(p.relative_to(R/'tests')))
 for p in (R/'qualification.json',R/'final-verification.json',R/'verify_final.py',R/'package_checkpoint.py',R/'card-admission.py',R/'watch-transition.py',R/'checkpoint_sources.py',held/'README.txt'):t.add(p,'current-evidence/'+p.name)
 t.add(R.parent/'cumulative-rf-0121/recovery-through-0.1.21.tar.gz','previous/recovery-through-0.1.21.tar.gz')
 t.add(R.parent/'shared-watch-0121-audit/recovery','previous/shared-watch-0121-source')
 for name in ('resolution.json','constraints.json','target-memory.json','lora-host-recipe.json','lora-prior-recipe.json','measure_lora_target.py','lora-target','lora-results','bringup-pinned.log','custody-sleep-storage-final.log','capacity-tests-complete.log'):
  t.add(R.parent/'shared-watch-0121-audit'/name,'previous/shared-watch-0121-evidence/'+name)
manifest={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in held.iterdir() if p.is_file() and p.name!='SHA256SUMS'}
(held/'SHA256SUMS').write_text(''.join(v['sha256']+'  '+k+'\n' for k,v in sorted(manifest.items())))
(R/'held-artifacts.json').write_text(json.dumps({'delivery_hold_until':'2026-10-13T23:30:00Z','directory':str(held),'artifacts':manifest,'library_artifact_ids':None,'reason':'Build delivery intentionally held; no upload before release time.'},indent=2)+'\n')
print(json.dumps(manifest,indent=2))

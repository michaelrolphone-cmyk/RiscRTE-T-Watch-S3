#!/usr/bin/env python3
"""Prepare only the Files delta against an explicitly hashed X4 cumulative store.

This does not claim full-cohort qualification; the X4 composer must admit the
result against its final settings/native/SD selection.
"""
import argparse
import json
from pathlib import Path
from build_files_policy import PINNED,VERSION,sha,require
from assemble_watch_files_policy import strict_json,same_json

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('build','baseline','baseline-receipt','output'):
  p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--baseline-receipt-sha256',required=True)
 p.add_argument('--provisional',action='store_true')
 a=p.parse_args()
 require(sha(a.baseline_receipt)==a.baseline_receipt_sha256,'X4 baseline receipt changed')
 prior_elf=a.baseline/'store/file_browser.elf'
 prior_manifest=a.baseline/'store/file_browser.json'
 require(sha(prior_elf)==PINNED['x4']['elf'],'Wrong X4 Files predecessor')
 require(strict_json((a.baseline/'store/waterfall.json').read_bytes())['version']=='0.3.4','Unselected RF version in X4 baseline')
 prior=strict_json(prior_manifest.read_bytes())
 require(prior['version']=='1.5.34','Wrong X4 Files version')
 build=strict_json((a.build/'file_browser-build-record.json').read_bytes())
 require(build['device']=='x4' and build['version']==VERSION and build['modal_policy'],'Wrong Files component')
 require(a.provisional or build['source_publication']=='public-exact-commit','Provisional Files cannot be qualified')
 require(sha(a.build/'file_browser.elf')==build['sha256'] and sha(a.build/'file_browser.json')==build['manifest_sha256'],'Files component custody changed')
 manifest=strict_json((a.build/'file_browser.json').read_bytes())
 require(same_json(manifest,dict(prior,version=VERSION)),'Files manifest authority changed')
 snapshot={str(path.relative_to(a.baseline)):sha(path) for path in (a.baseline/'store').rglob('*') if path.is_file()}
 require(not a.output.exists(),'Use fresh overlay output')
 a.output.mkdir(parents=True)
 for name in ('file_browser.elf','file_browser.json'):
  (a.output/name).write_bytes((a.build/name).read_bytes())
 require(snapshot=={str(path.relative_to(a.baseline)):sha(path) for path in (a.baseline/'store').rglob('*') if path.is_file()},'X4 baseline changed during overlay preparation')
 report=dict(schema='files.modal-policy.x4-overlay.v1',status='component-overlay-awaits-complete-x4-admission',
  baseline=str(a.baseline),baseline_receipt_sha256=a.baseline_receipt_sha256,baseline_store_snapshot=snapshot,
  exact_changed_store_paths=['file_browser.elf','file_browser.json'],manifest_authority_unchanged=True,
  unchanged_files_preserved=len(snapshot)-2,baseline_unchanged=True,files_build=build,
  native_unchanged=True,sd_unchanged=True,hardware_verified=False,flashed=False,delivered=False)
 (a.output/'overlay-receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('baseline_store_snapshot','files_build')},indent=2))
if __name__=='__main__':main()

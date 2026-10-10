#!/usr/bin/env python3
"""Restore and verify the original Watch19 policy/qualification source refs."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'docs/lifecycle/watch-1.0.19'
record=json.loads((folder/'source-custody.json').read_bytes())
assert record['schema']==1 and not record['dependency_repositories_included'] and not record['provisioning_payloads_included']
bundle=folder/record['bundle']['file'];raw=bundle.read_bytes()
assert len(raw)==record['bundle']['size_bytes'] and hashlib.sha256(raw).hexdigest()==record['bundle']['sha256']
subprocess.run(['git','-C',str(ROOT),'bundle','verify',str(bundle)],check=True)
subprocess.run(['git','-C',str(ROOT),'fetch',str(bundle),'refs/watch-custody/1.0.19/*:refs/watch-custody/1.0.19/*'],check=True)
for value in record['heads'].values():
    actual=subprocess.check_output(['git','-C',str(ROOT),'rev-parse',value['bundle_ref']],text=True).strip()
    assert actual==value['commit']
    assert subprocess.check_output(['git','-C',str(ROOT),'rev-parse',actual+'^{tree}'],text=True).strip()==value['tree']
for name,key in record['selected_source_files'].items():
    expected=subprocess.check_output(['git','-C',str(ROOT),'show',record['heads'][key]['commit']+':'+name])
    path=ROOT/name;assert path.is_file() and not path.is_symlink() and path.read_bytes()==expected,name
print('Original Watch19 policy and qualification source identities verified')

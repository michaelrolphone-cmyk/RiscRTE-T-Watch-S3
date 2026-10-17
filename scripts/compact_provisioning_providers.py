#!/usr/bin/env python3
"""Compact only new provider metadata; preserve every loader semantic and input."""
import argparse
import importlib.util
import json
from pathlib import Path
from package_provisioning import require,sha,encoded

def compact(watch,compiler,catalog,internal,originals):
    require(not originals.exists(),'Original sidecar directory must be new')
    path=watch/'scripts/compact_current_elf.py'
    spec=importlib.util.spec_from_file_location('pinned_provider_compaction',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result={}
    for directory,name in ((catalog,'installed-apps'),(internal,'pkg-internal')):
        receipt=json.loads((directory/'build.json').read_bytes());raw=(directory/'driver.elf').read_bytes()
        key='elf_sha256' if name=='installed-apps' else 'sha256'
        require(sha(raw)==receipt[key],'Original provider build digest differs')
        require('compaction' not in receipt,'Provider already compacted')
        proof=module.compact(directory/'driver.elf',compiler,debug_path=originals/name/'driver.elf')
        require(proof['retained_loader_sections_symbols_relocations_unchanged'] and proof['original_elf_retained'],'Loader semantics changed')
        receipt['original_elf_sha256']=receipt[key];receipt[key]=sha((directory/'driver.elf').read_bytes())
        receipt['compaction']=dict(proof,checker_sha256=sha(path.read_bytes()))
        (directory/'build.json').write_bytes(encoded(receipt));result[name]=receipt['compaction']
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('watch','compiler','catalog','internal','originals'):p.add_argument('--'+name,type=Path,required=True)
    print(json.dumps(compact(**vars(p.parse_args())),sort_keys=True))

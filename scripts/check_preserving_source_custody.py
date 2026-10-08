#!/usr/bin/env python3
"""Verify this publication retains the exact software-qualified proof closure."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
receipt=json.loads((ROOT/'docs/evidence/watch117-preserving/source-custody.json').read_bytes())
assert receipt['schema']==1 and receipt['byte_identical'] is True
for name,digest in receipt['loaded_python_and_native_fixture_files'].items():
    path=ROOT/name
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise SystemExit('Software-qualified preserving source changed: '+name)
print('Exact preserving proof modules, native fixtures and profiles match the tested source')

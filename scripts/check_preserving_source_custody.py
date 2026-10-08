#!/usr/bin/env python3
"""Verify historical proof-source custody plus explicitly declared hardening."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
receipt=json.loads((ROOT/'docs/evidence/watch117-preserving/source-custody.json').read_bytes())
if receipt['schema']!=2 or receipt['byte_identical'] is not False:
    raise SystemExit('Expected historical proof custody with explicit verifier follow-up')
followup=receipt['verifier_followup']
if followup['historical_matrix_rerun'] is not False or followup['scope']!='Verifier admission hardening only; historical execution receipts are unchanged':
    raise SystemExit('Verifier follow-up must not relabel historical matrix results')
files={**receipt['loaded_python_and_native_fixture_files'],**followup['source_files']}
for name,digest in files.items():
    path=ROOT/name
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise SystemExit('Software-qualified preserving source changed: '+name)
print('Historical preserving source closure and explicit verifier follow-up match; historical matrix was not rerun')
